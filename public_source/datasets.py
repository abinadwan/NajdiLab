"""Candidate-local readiness, managed-version integrity and read-only diagnostics."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from . import service, dataset_quality
from .core_snapshot import SnapshotDirectory
from collections import Counter
from statistics import median
from .db import ROOT, DB_PATH
from .core_reviews import ReviewError
from .review_integrity import ExportReadinessError, export_readiness

DATA_FILES = {'sft.jsonl', 'multi_turn.jsonl', 'direct_language.jsonl', 'preference_pairs.jsonl', 'evaluation_holdout.jsonl'}
INTERNAL_FILES = DATA_FILES | {'full_archive.json', 'dedup_report.json'}
MAX_FILE_BYTES = 16 * 1024 * 1024


def _connect():
    try:
        conn = sqlite3.connect(DB_PATH.resolve().as_uri() + '?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        raise ReviewError('STORAGE_UNAVAILABLE', 'Candidate-local storage is unavailable.', 503) from None


def _entries(conn, include_demo, evaluation=False):
    reviews = service._review_training_records(conn, include_demo, evaluation=evaluation)
    manual = service._manual_records(conn, 'manual_sft_items', include_demo, evaluation=evaluation)
    direct = service._manual_records(conn, 'direct_language_texts', include_demo, evaluation=evaluation)
    preference = service._manual_records(conn, 'preference_pairs', include_demo, evaluation=evaluation)
    return [('sft', service._annotate_sft_record(x)) for x in reviews + manual] + [('direct_language', x) for x in direct] + [('preference_pairs', x) for x in preference]


def _conflicts(entries):
    prompts = {}
    for _, row in entries:
        messages = row.get('messages')
        if messages:
            key = service._normalized(messages[:-1])
            prompts.setdefault(key, set()).add(service._normalized(service._training_target(row)))
    return sum(len(targets) > 1 for targets in prompts.values())


def _preview(conn, include_demo):
    entries, evaluation_entries = _entries(conn, include_demo), _entries(conn, include_demo, evaluation=True)
    if len(entries) + len(evaluation_entries) < service.EXPORT_MIN_AUTO_SPLIT_RECORDS:
        raise service.ValidationError('Candidate preparation requires at least 20 eligible records so the existing automatic holdout split can be verified.')
    if any(kind != 'sft' for kind,_ in entries + evaluation_entries):
        raise ReviewError('UNSUPPORTED_RECORD_KIND', 'This core profile prepares conversational SFT records only. Manual direct/preference workflows are deferred; no version was written.', 409)
    if _conflicts(entries + evaluation_entries):
        raise ReviewError('CONTRADICTORY_TARGETS', 'Identical conversational context has conflicting targets; review it before preparation.', 409)
    training, evaluation, split = service._split_export_entries(entries, evaluation_entries)
    sft = [x for kind, x in training if kind == 'sft']
    multi, balance = service._balance_multi_turn_records([x for x in sft if len(x.get('messages', [])) > 2])
    files, dedup = service._duplicate_analysis({'sft.jsonl': [x for x in sft if len(x.get('messages', [])) <= 2],
        'multi_turn.jsonl': multi, 'direct_language.jsonl': [x for kind, x in training if kind == 'direct_language'],
        'preference_pairs.jsonl': [x for kind, x in training if kind == 'preference_pairs']}, remove_exact=True)
    validation = service._validate_export_records(files, evaluation, include_demo, split, balance)
    leakage = _leakage([x for rows in files.values() for x in rows], evaluation)
    if not leakage['leakage_free']:
        raise ReviewError('TRAIN_EVAL_LEAKAGE', 'Training and evaluation share conversation, record or target identities.', 409)
    if not all(_split_checks([x for records in files.values() for x in records], evaluation, leakage).values()):
        raise ReviewError('DATASET_SPLIT_GATE', 'After deduplication, preparation needs at least 20 records, three holdout conversations and a 10–15% holdout. Resolve findings without bypassing these gates.', 409)
    return {'split': split, 'validation': validation, 'dedup': dedup, 'leakage': leakage,
            'file_counts': {name: len(rows) for name, rows in files.items()}, 'evaluation_records': len(evaluation)}


def _block(result, code, message):
    finding = {'code': code, 'reason': message, 'severity': 'ERROR', 'blocking': True, 'confirmed': True}
    result['findings'].append(finding); result['blocking_findings'].append(finding)
    result['counts']['blocking'] += 1; result['counts']['errors'] += 1; result['counts']['total'] += 1
    result['ok'], result['status'] = False, 'BLOCKED'


def readiness(include_demo=False):
    result = export_readiness(DB_PATH, include_demo=include_demo)
    result['candidate_minimum_records'] = service.EXPORT_MIN_AUTO_SPLIT_RECORDS
    conn = _connect()
    try:
        unsafe = conn.execute("SELECT COUNT(*) FROM reviews r JOIN messages m ON m.id=r.message_id JOIN conversations c ON c.id=m.conversation_id WHERE r.exclude_from_training=0 AND (r.training_eligible=1 OR r.evaluation_only=1) AND (r.contains_sensitive_data=1 OR r.contains_personal_data=1 OR r.needs_fact_check=1) AND (?=1 OR c.demo=0)", (int(include_demo),)).fetchone()[0]
        for table in ('manual_sft_items', 'direct_language_texts', 'preference_pairs'):
            unsafe += conn.execute(f"SELECT COUNT(*) FROM {table} WHERE archived=0 AND exclude_from_training=0 AND ignored_at IS NULL AND deleted_at IS NULL AND (training_eligible=1 OR evaluation_only=1) AND (contains_sensitive_data=1 OR contains_personal_data=1) AND (?=1 OR demo=0)", (int(include_demo),)).fetchone()[0]
        context_unsafe = conn.execute("SELECT COUNT(DISTINCT selected.id) FROM reviews selected JOIN messages target ON target.id=selected.message_id JOIN conversations c ON c.id=target.conversation_id JOIN messages prior ON prior.conversation_id=target.conversation_id AND prior.turn_index<=target.turn_index AND prior.role='assistant' LEFT JOIN reviews context_review ON context_review.message_id=prior.id WHERE selected.exclude_from_training=0 AND (selected.training_eligible=1 OR selected.evaluation_only=1) AND (?=1 OR c.demo=0) AND (context_review.id IS NULL OR context_review.review_status IN ('PENDING','IGNORED','DELETED') OR context_review.exclude_from_training=1 OR context_review.contains_sensitive_data=1 OR context_review.contains_personal_data=1 OR context_review.needs_fact_check=1)", (int(include_demo),)).fetchone()[0]
        if context_unsafe:
            _block(result, 'CONTEXT_REVIEW_REQUIRED', 'A selected conversation contains an earlier unresolved, excluded or privacy-restricted response. Exclude affected targets or explicitly resolve the context; it is never silently stripped.')
        try:
            raw_entries = _entries(conn, include_demo)
            _, result['dedup'] = service._duplicate_analysis({'eligible': [row for _,row in raw_entries]}, remove_exact=False)
        except service.ValidationError:
            result['dedup'] = {'status': 'UNAVAILABLE', 'message': 'Resolve record structure before duplicate analysis.'}
        if unsafe:
            _block(result, 'PRIVACY_REVIEW_REQUIRED', 'A selected record has unresolved personal, sensitive or fact-check flags; exclude it or explicitly resolve those flags.')
        if result['ok']:
            try:
                result['preparation'] = _preview(conn, include_demo)
            except ReviewError as exc:
                _block(result, exc.code, str(exc))
            except service.ValidationError as exc:
                _block(result, 'DATASET_SPLIT_GATE', str(exc))
        return result
    finally:
        conn.close()


def prepare(include_demo=False):
    root = ROOT / 'exports'
    if root.resolve() != root or root.is_symlink() or getattr(root, 'is_junction', lambda: False)():
        raise ReviewError('DATASET_PATH_DENIED', 'Linked export roots are not supported.', 403)
    result = readiness(include_demo)
    if not result['ok']:
        raise ExportReadinessError(result)
    return service.create_export(include_demo=include_demo)


def _regular(path):
    if path.is_symlink() or getattr(path, 'is_junction', lambda: False)() or path.resolve() != path or not path.is_file():
        raise ReviewError('DATASET_PATH_DENIED', 'A dataset path is not a regular candidate-local file.', 403)
    if path.stat().st_size > MAX_FILE_BYTES or path.stat().st_nlink > 1:
        raise ReviewError('DATASET_FILE_DENIED', 'Dataset file exceeds the size or file-link policy.', 403)
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ReviewError('DATASET_FILE_DENIED', 'Dataset file exceeds the size policy.', 403)
    return raw


def checked_version(version):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}', version):
        raise ReviewError('INVALID_VERSION', 'Invalid local version identifier.')
    root = ROOT / 'exports'; directory = root / version
    if root.resolve() != root or directory.resolve() != directory or root.is_symlink() or directory.is_symlink() or getattr(directory, 'is_junction', lambda: False)():
        raise ReviewError('DATASET_PATH_DENIED', 'Linked dataset directories are not supported.', 403)
    conn = _connect()
    try:
        row = conn.execute('SELECT manifest_json FROM dataset_versions WHERE version=?', (version,)).fetchone()
    finally:
        conn.close()
    if row is None or not directory.is_dir():
        raise ReviewError('DATASET_NOT_FOUND', 'Managed local dataset version not found.', 404)
    try:
        manifest = json.loads(_regular(directory / 'manifest.json'))
        if manifest != json.loads(row['manifest_json']) or manifest.get('version') != version:
            raise ValueError('registry manifest mismatch')
        checksums, counts = manifest['sha256'], manifest['files']
        if not isinstance(checksums, dict) or not isinstance(counts, dict) or set(checksums) - INTERNAL_FILES or set(counts) != DATA_FILES:
            raise ValueError('manifest file policy')
        if set(p.name for p in directory.iterdir()) != set(checksums) | {'manifest.json'} or not DATA_FILES <= set(checksums):
            raise ValueError('unexpected/missing file')
        blobs = {}
        for name, digest in checksums.items():
            if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):raise ValueError('invalid digest')
            raw = _regular(directory / name)
            if hashlib.sha256(raw).hexdigest() != digest:raise ValueError('changed bytes')
            blobs[name] = raw
        if sum(map(len, blobs.values())) > 64 * 1024 * 1024:raise ValueError('aggregate size')
        for name in DATA_FILES:
            records = [json.loads(line) for line in blobs[name].decode('utf-8').splitlines() if line.strip()]
            if type(counts[name]) is not int or counts[name] != len(records) or any(not isinstance(x, dict) for x in records):raise ValueError('count/record mismatch')
        return directory, manifest, blobs
    except (ValueError, TypeError, KeyError, UnicodeError, OSError):
        raise ReviewError('DATASET_INTEGRITY_FAILED', 'Version files or manifest do not match registered preparation evidence. Do not use or share this version.', 409) from None


def _leakage(training, evaluation):
    def identities(rows):
        return ({service._conversation_id(x) for x in rows if service._conversation_id(x)},
                {str(x['id']) for x in rows if x.get('id') is not None},
                {service._normalized(service._training_target(x)) for x in rows if service._training_target(x)})
    tc, ti, tt = identities(training); ec, ei, et = identities(evaluation)
    return {'leakage_free': not (tc & ec or ti & ei or tt & et), 'training_conversations': len(tc),
            'evaluation_conversations': len(ec), 'conversation_overlap_count': len(tc & ec),
            'record_overlap_count': len(ti & ei), 'target_overlap_count': len(tt & et),
            'evaluation_records': len(evaluation), 'holdout_file': 'evaluation_holdout.jsonl'}


def _split_checks(training, evaluation, leakage):
    total = len(training) + len(evaluation)
    return {'minimum_records': total >= service.EXPORT_MIN_AUTO_SPLIT_RECORDS,
            'holdout_present': bool(evaluation),
            'holdout_conversation_diversity': leakage['evaluation_conversations'] >= 3,
            'holdout_fraction': 10 * total <= 100 * len(evaluation) <= 15 * total}


def version_detail(version, kind='detail'):
    directory, manifest, blobs = checked_version(version)
    rows = {name: [json.loads(line) for line in blobs[name].decode('utf-8').splitlines() if line.strip()] for name in DATA_FILES}
    training = [r for name, records in rows.items() if name != 'evaluation_holdout.jsonl' for r in records]
    leakage = _leakage(training, rows['evaluation_holdout.jsonl'])
    # Adapt the known legacy holdout filename only in memory. All helpers consume
    # the already checked bytes, never re-resolve an arbitrary path.
    snapshot = SnapshotDirectory(version, {**blobs, 'text_sft_eval.jsonl': blobs['evaluation_holdout.jsonl']})
    quality = dataset_quality.analyze_directory(snapshot, version=version)
    quality['dataset_fingerprint'] = hashlib.sha256(json.dumps(manifest['sha256'],sort_keys=True).encode()).hexdigest()
    masks_valid = dataset_quality._loss_masks_valid(snapshot)
    for name in ('sft.jsonl', 'multi_turn.jsonl', 'evaluation_holdout.jsonl'):
        for row in rows[name]:
            try:service._validate_sft_record(row, name)
            except (service.ValidationError,TypeError,IndexError):masks_valid = False
    if not masks_valid:
        quality['findings'].append({'code':'LOSS_MASK_INVALID','severity':'confirmed_blocker','sample_ids':[], 'evidence':'Training or holdout masks are invalid.'})
        quality['counts']['confirmed_blocker'] += 1
        quality['status'] = 'BLOCKED'
    checks = {**_split_checks(training, rows['evaluation_holdout.jsonl'], leakage),
              'manifest_counts': manifest.get('record_count') == len(training) + len(rows['evaluation_holdout.jsonl']) and manifest.get('training_record_count') == len(training) and manifest.get('evaluation_record_count') == len(rows['evaluation_holdout.jsonl']),
              'supported_record_kinds': not rows['direct_language.jsonl'] and not rows['preference_pairs.jsonl'],
              'manifest_and_hashes': True, 'quality_no_blockers': quality['counts']['confirmed_blocker'] == 0,
              'response_only_loss_masks': masks_valid, 'holdout_separation': leakage['leakage_free']}
    healthy = all(checks.values())
    if kind == 'eval-sets':return leakage
    if kind == 'quality-findings':return {**quality, 'candidate_holdout': leakage}
    if kind == 'balance':
        conversations = Counter(service._conversation_id(row) for row in training if service._conversation_id(row))
        lengths = [len(service._training_target(row).split()) for row in training]
        counts = {'sft': len(rows['sft.jsonl']), 'multi_turn': len(rows['multi_turn.jsonl']), 'direct_language': len(rows['direct_language.jsonl']), 'preference': len(rows['preference_pairs.jsonl']), 'evaluation': len(rows['evaluation_holdout.jsonl']), 'unknown': 0}
        return {'version':version,'status':'DIAGNOSTIC_ONLY','record_counts':counts,'training_conversations':len(conversations),'largest_conversation_records':max(conversations.values(),default=0),'target_word_lengths':{'minimum':min(lengths,default=0),'median':median(lengths) if lengths else 0,'maximum':max(lengths,default=0)},'review_status_counts':dict(Counter(row.get('review_status','unspecified') for row in training)),'holdout_separate':leakage['leakage_free'],'policy':'Read-only counts; no automatic balancing or deletion.'}
    if kind == 'release-validation':return {'status': 'VALID' if healthy else 'BLOCKED', 'checks': checks, 'publication_approved': False}
    if kind == 'health':return {'version': version, 'status': 'READY' if healthy else 'BLOCKED', 'checks': checks, 'counts': manifest['files'], 'leakage': leakage, 'training_actions': False}
    return {'version': version, 'state': 'Prepared locally', 'manifest': manifest,
            'files': [{'name': name, 'sha256': manifest['sha256'][name], 'bytes': len(blobs[name]), 'count': len(rows[name])} for name in sorted(DATA_FILES)],
            'private_archive_present': 'full_archive.json' in blobs, 'health': {'status': 'READY' if healthy else 'BLOCKED', 'checks': checks}, 'leakage': leakage}


def list_versions():
    conn = _connect()
    try:versions = [row['version'] for row in conn.execute('SELECT version FROM dataset_versions ORDER BY id DESC')]
    finally:conn.close()
    items = []
    for version in versions:
        try:
            detail = version_detail(version)
            items.append({'version': version, 'state': detail['state'], 'readable': True, 'health_status': detail['health']['status']})
        except ReviewError as exc:items.append({'version': version, 'state': 'Unavailable', 'readable': False, 'error': exc.code})
    return {'items': items}
