"""Token-level check of a NajdiLab Unsloth handoff with Unsloth Studio's own formatting and masking.

Run it with the Python that ships with your Unsloth Studio install (it has transformers, unsloth and
Studio's backend), not with NajdiLab's Python:

    <Unsloth Studio>/unsloth_studio/Scripts/python.exe -I scripts/verify_unsloth_studio.py \
        <NajdiLab data>/exports/unsloth-handoffs/<id> --model unsloth/Qwen2.5-0.5B-Instruct

For every record it runs Studio's token-preview path (the dataset formatting, chat template and
"train on completions" masking that Studio training uses) with the training model's real tokenizer, then
checks that the trained tokens are one contiguous span that decodes to exactly the record's approved
answer. Nothing is trained, uploaded or written into the handoff; the report goes to stdout or --output.

This script imports Unsloth Studio from the user's own installation and copies none of its code.
It uses Studio's internal preview module, so a future Studio release may need an update here; it then
stops with an error instead of reporting a pass. Set HF_HUB_OFFLINE=1 to use only a cached tokenizer.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
import tempfile
from pathlib import Path


def studio_backend(explicit: str | None) -> Path:
    candidates = [Path(explicit)] if explicit else []
    candidates.append(Path(sys.executable).resolve().parent.parent / 'Lib' / 'site-packages' / 'studio' / 'backend')
    candidates.append(Path(sys.executable).resolve().parent.parent / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}'
                      / 'site-packages' / 'studio' / 'backend')
    for path in candidates:
        if (path / 'core' / 'training' / 'token_preview_worker.py').is_file():
            return path
    raise SystemExit('Unsloth Studio backend not found. Run this with Unsloth Studio\'s Python or pass --studio-backend.')


def target_of(row: dict, profile: str) -> str:
    if profile == 'studio_chat':
        return row['messages'][-1]['content']
    if profile == 'studio_alpaca':
        return row['output']
    return row['completion'][0]['content']


def load_handoff(directory: Path):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    raw = (directory / 'dataset.jsonl').read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['sha256']['dataset.jsonl']:
        raise SystemExit('dataset.jsonl does not match its manifest hash; refusing to verify a changed file.')
    rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    provenance = [json.loads(line) for line in (directory / 'provenance.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    return manifest, rows, provenance


def check(tokenizer, sample: dict, target: str) -> dict:
    tokens = sample.get('tokens') or []
    trained = [i for i, entry in enumerate(tokens) if entry[2]]
    trained_ids = [tokens[i][0] for i in trained]
    decoded = tokenizer.decode(trained_ids, skip_special_tokens=True)
    contiguous = bool(trained) and trained == list(range(trained[0], trained[-1] + 1))
    problems = []
    if sample.get('truncated_from'):
        problems.append(f"truncated from {sample['truncated_from']} tokens")
    if not trained:
        problems.append('no token is trained')
    elif not contiguous:
        problems.append('trained tokens are not one contiguous span (more than one target is supervised)')
    if decoded.strip() != target.strip():
        problems.append('trained text is not exactly the approved answer')
    return {'num_tokens': sample.get('num_tokens'), 'num_trained': sample.get('num_trained'),
            'num_masked': (sample.get('num_tokens') or 0) - (sample.get('num_trained') or 0),
            'truncated_from': sample.get('truncated_from'), 'ok': not problems, 'problems': problems,
            'trained_text_sha256': hashlib.sha256(decoded.encode('utf-8')).hexdigest()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('handoff', type=Path, help='a NajdiLab handoff directory (holds manifest.json and dataset.jsonl)')
    parser.add_argument('--model', required=True, help='training model id or local folder, e.g. unsloth/Qwen2.5-0.5B-Instruct')
    parser.add_argument('--max-seq-length', type=int, default=2048)
    parser.add_argument('--studio-backend', help='path to Studio\'s studio/backend folder, if not found automatically')
    parser.add_argument('--output', type=Path, help='write the JSON report here instead of stdout')
    args = parser.parse_args(argv)

    manifest, rows, provenance = load_handoff(args.handoff)
    backend = studio_backend(args.studio_backend)
    # Unsloth writes a compiled-code cache into the current folder unless told otherwise; keep the
    # user's folders (and a NajdiLab checkout) untouched.
    os.environ.setdefault('UNSLOTH_COMPILE_LOCATION', str(Path(tempfile.gettempdir()) / 'najdilab-unsloth-compiled-cache'))
    sys.path[:0] = [str(backend), str(backend / 'core' / 'training')]
    try:
        from transformers import AutoTokenizer
        import token_preview_worker as studio_preview
        preview = studio_preview._preview
    except (ImportError, AttributeError) as error:
        raise SystemExit(f'This Unsloth Studio version has no compatible token preview ({error}).')

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=False)
    result = preview(tokenizer, {'model_name': args.model},
                     {'rows': rows, 'train_on_completions': True, 'num_samples': len(rows), 'max_seq_length': args.max_seq_length})
    samples = result['samples']
    if len(samples) != len(rows):
        raise SystemExit(f'Studio formatted {len(samples)} of {len(rows)} rows; some rows were dropped, so the export is not compatible.')
    records = []
    for index, (row, sample) in enumerate(zip(rows, samples)):
        record = {'line': index + 1, 'source_record_id': provenance[index].get('source_record_id') if index < len(provenance) else None,
                  **check(tokenizer, sample, target_of(row, manifest.get('profile', 'trl_prompt_completion')))}
        records.append(record)
    versions = {}
    for name in ('unsloth', 'trl', 'transformers', 'tokenizers'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    template = getattr(tokenizer, 'chat_template', None) or ''
    failed = [r for r in records if not r['ok']]
    report = {
        'tool': 'scripts/verify_unsloth_studio.py', 'method': 'Unsloth Studio token preview (formatting, chat template and '
        'train-on-completions masking used for Studio training) with the training model tokenizer, every record',
        'handoff_id': manifest.get('id'), 'profile': manifest.get('profile', 'trl_prompt_completion'), 'export_format': manifest.get('format'),
        'dataset_sha256': manifest['sha256']['dataset.jsonl'], 'model': args.model, 'max_seq_length': args.max_seq_length,
        'studio_format': result.get('final_format'), 'masking': {k: result['masking'].get(k) for k in ('applied', 'instruction_part', 'response_part')},
        'tokenizer_chat_template_sha256': hashlib.sha256(template.encode('utf-8')).hexdigest() if template else None,
        'eos_token': result.get('eos_token'), 'versions': versions,
        'records_inspected': len(records), 'records_passed': len(records) - len(failed), 'records_failed': len(failed),
        'trained_tokens': sum(r['num_trained'] or 0 for r in records), 'masked_tokens': sum(r['num_masked'] for r in records),
        'verdict': 'PASS' if not failed else 'FAIL', 'records': records,
        'limitations': ['Checks the supervision mask and truncation only; it does not train and says nothing about model quality.',
                        'Valid for this tokenizer, Studio version and max_seq_length; re-run after changing any of them.'],
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(text, encoding='utf-8')
    else:
        sys.stdout.write(text)
    return 0 if not failed else 1


if __name__ == '__main__':
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
    raise SystemExit(main())
