#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audit metrics for gold-v006-clean dataset (phase 1).
No LLM, no classification, no verdict.
"""

import json, os, re, statistics, math
from pathlib import Path
from collections import Counter, defaultdict

# Paths
ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / 'exports/gold-v006-clean'
SFT_PATH = os.path.join(DATA_DIR, "sft.jsonl")
MULTI_PATH = os.path.join(DATA_DIR, "multi_turn.jsonl")
EVAL_PATH = os.path.join(DATA_DIR, "text_sft_eval.jsonl")
REPORT_DIR = ROOT / 'reports'

# Utility to read jsonl
def load_jsonl(path):
    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

# Tokenize by words (split on whitespace)
word_re = re.compile(r"[\w\']+", re.UNICODE)

def tokenize(text):
    return word_re.findall(text) if text else []

# Compute similarity >=0.90 using SequenceMatcher
from difflib import SequenceMatcher


def is_near_duplicate(a,b,threshold=0.90):
    return SequenceMatcher(None,a,b).ratio() >= threshold

# Load data
sft_records = load_jsonl(SFT_PATH)
multi_records = load_jsonl(MULTI_PATH)
eval_records = load_jsonl(EVAL_PATH)

# Counts
sft_count = len(sft_records)
multi_count = len(multi_records)
train_count = sft_count + multi_count
assert train_count == 59, f"train count expected 59, got {train_count}"
eval_count = len(eval_records)
assert eval_count == 12, f"eval count expected 12, got {eval_count}"

# Build train_records
train_records = sft_records + multi_records
assert len(train_records) == 59

# Helper to extract target and context tokens

def extract_target_context(record):
    # target is last assistant message
    msgs = record.get('messages',[])
    tgt = ''
    for m in msgs:
        if m.get('role')=='assistant':
            tgt = m.get('content','')
    ctx = ''  # not used
    return tokenize(tgt), tokenize(ctx)

# Compute per-record metrics
record_metrics = []
for rec in train_records:
    tgt_tokens, ctx_tokens = extract_target_context(rec)
    record_metrics.append({
        'sample_id': rec.get('id',''),
        'conversation_id': rec.get('conversation_id') or 'NONE',
        'target_tokens_count': len(tgt_tokens),
        'context_tokens_count': len(ctx_tokens),
        'target_text': rec.get('target', '')
    })

# Conversation weighting
conv_groups = defaultdict(list)
for rm in record_metrics:
    conv_groups[rm['conversation_id']].append(rm)

conv_rows = []
for conv_id, rows in conv_groups.items():
    total_rec = len(rows)
    single = sum(1 for r in rows if False)
    multi = total_rec - single
    sum_target = sum(r['target_tokens_count'] for r in rows)
    sum_context = sum(r['context_tokens_count'] for r in rows)
    unique_targets = len(set(r['target_text'] for r in rows))
    conv_rows.append({
        'conversation_id': conv_id,
        'total_records': total_rec,
        'single_turn_records': single,
        'multi_turn_records': multi,
        'percentage_of_59_records': round((total_rec/59)*100,2),
        'unique_final_targets': unique_targets,
        'total_target_tokens': sum_target,
        'percentage_of_all_target_tokens': None,  # to compute later
        'total_context_tokens': sum_context,
        'percentage_of_all_context_tokens': None
    })

# Overall token totals
total_target_tokens_all = sum(r['target_tokens_count'] for r in record_metrics)
total_context_tokens_all = sum(r['context_tokens_count'] for r in record_metrics)
for row in conv_rows:
    row['percentage_of_all_target_tokens'] = round((row['total_target_tokens']/total_target_tokens_all)*100,2)
    row['percentage_of_all_context_tokens'] = 0

# Multi-turn overlap metrics
multi_conv_groups = defaultdict(list)
for rec in multi_records:
    conv_id = rec.get('conversation_id') or 'NONE'
    multi_conv_groups[conv_id].append(rec)

multi_overlap_rows = []
for conv_id, windows in multi_conv_groups.items():
    num_windows = len(windows)
    unique_targets = len(set(w['messages'][-1].get('content','') for w in windows))
    avg_msgs_per_win = round(statistics.mean([len(w.get('messages',[])) for w in windows]),2)
    # prior turns per window
    all_prior_user = []
    all_prior_assistant = []
    for w in windows:
        msgs = w.get('messages',[])
        prior = msgs[:-1]
        all_prior_user.extend([m['content'] for m in prior if m.get('role')=='user'])
        all_prior_assistant.extend([m['content'] for m in prior if m.get('role')=='assistant'])
    unique_prior_user = set(all_prior_user)
    unique_prior_assistant = set(all_prior_assistant)
    # reuse counts
    user_counts = Counter(all_prior_user)
    assistant_counts = Counter(all_prior_assistant)
    avg_user_reuse = round(statistics.mean(user_counts.values()) if user_counts else 0,2)
    avg_assistant_reuse = round(statistics.mean(assistant_counts.values()) if assistant_counts else 0,2)
    max_user_reuse = max(user_counts.values()) if user_counts else 0
    max_assistant_reuse= max(assistant_counts.values()) if assistant_counts else 0
    # Jaccard per pair of windows
    jaccards = [0]
    for i in range(len(windows)):
        set_i = set([m['content'] for m in windows[i].get('messages',[])[:-1] if m.get('role')])
        for j in range(i+1,len(windows)):
            set_j = set([m['content'] for m in windows[j].get('messages',[])[:-1] if m.get('role')])
            intersection = set_i & set_j
            union = set_i | set_j
            jacc = intersection/union if union else 0
            jaccards.append(jacc)
    mean_overlap = round(statistics.mean(jaccards) if jaccards else 0,4)
    median_overlap = round(statistics.median(jaccards) if jaccards else 0,4)
    max_overlap = round(max(jaccards) if jaccards else 0,4)
    multi_overlap_rows.append({
        'conversation_id': conv_id,
        'number_of_windows': num_windows,
        'unique_final_targets': unique_targets,
        'average_messages_per_window': avg_msgs_per_win,
        'unique_prior_user_turns': len(unique_prior_user),
        'unique_prior_assistant_turns': len(unique_prior_assistant),
        'average_user_reuse': avg_user_reuse,
        'max_user_reuse': max_user_reuse,
        'average_assistant_reuse': avg_assistant_reuse,
        'max_assistant_reuse': max_assistant_reuse,
        'mean_jaccard_overlap': mean_overlap,
        'median_jaccard_overlap': median_overlap,
        'max_jaccard_overlap': max_overlap
    })

# Target duplication
all_targets = [r['target_text'] for r in train_records]
exact_counts = Counter(all_targets)
# normalized exact duplicates (lowercase strip)
norm_targets = [t.strip().lower() for t in all_targets]
norm_counts = Counter(norm_targets)
# near duplicates (>=0.9) using SequenceMatcher
near_pairs = []
for i,a in enumerate(all_targets):
    for j,b in enumerate(all_targets[i+1:],i+1):
        if is_near_duplicate(a,b):
            near_pairs.append({'sample_id_i': train_records[i]['id'],'sample_id_j':train_records[j]['id'],'score': SequenceMatcher(None,a,b).ratio(),'preview_a':a[:60],'preview_b':b[:60]})

# Phrase/N-gram dominance
n_counts_2 = Counter()
first_phrases = Counter()
endings = Counter()
ngram_counts_2 = Counter()
ngram_counts_3 = Counter()
ngram_counts_4 = Counter()
phrases_to_check = ['أبشر','يا هلا','يا مرحبا','الله يحييك','وش عندك','وش بغيت','ولا تهون']
phrase_counts = Counter()
for t in all_targets:
    words = tokenize(t)
    if words:
        first_phrases[words[0]]+=1
        endings[words[-1]]+=1
    ngram_counts_2.update(zip(words,words[1:]))
    ngram_counts_3.update(tuple(words[i:i+3]) for i in range(len(words)-2))
    ngram_counts_4.update(tuple(words[i:i+4]) for i in range(len(words)-3))
    for p in phrases_to_check:
        if p in t:
            phrase_counts[p]+=1

# Response length stats
token_counts = [r['target_tokens_count'] for r in record_metrics]
min_len, median_len, mean_len, max_len = min(token_counts), statistics.median(token_counts), statistics.mean(token_counts), max(token_counts)
# shortest 10
shortest_10 = sorted(record_metrics, key=lambda r:r['target_tokens_count'])[:10]
# longest 10
longest_10 = sorted(record_metrics, key=lambda r:r['target_tokens_count'], reverse=True)[:10]
# percentage of target tokens from longest 10
tokens_longest_10 = sum(r['target_tokens_count'] for r in longest_10)
percent_longest = round((tokens_longest_10/total_target_tokens_all)*100,2)

# Identity concentration
names_targets = {}
for r in record_metrics:
    # target
    for name in ['أبوميار','أبو ميار','أبو حمد','مروان تلودي']:
        if name in r['target_text']:
            key=name
            names_targets.setdefault(key,{'target_count':0,'context_count':0,'sample_ids':[]})
            names_targets[key]['target_count']+=1
            names_targets[key]['sample_ids'].append(r['sample_id'])
    # context
    for name in ['أبوميار','أبو ميار','أبو حمد','مروان تلودي']:
        if name in r['context_text']:
            pass
# Mentions and numeric IDs
mention_pattern = re.compile(r'@\w+')
numeric_pattern = re.compile(r'\b\d+\b')
for r in record_metrics:
    # target
    for mention in mention_pattern.findall(r['target_text']):
        k=mention
        names_targets.setdefault(k,{'target_count':0,'context_count':0,'sample_ids':[]})
        names_targets[k]['target_count']+=1
        names_targets[k]['sample_ids'].append(r['sample_id'])
    for num in numeric_pattern.findall(r['target_text']):
        k=num
        names_targets.setdefault(k,{'target_count':0,'context_count':0,'sample_ids':[]})
        names_targets[k]['target_count']+=1
        names_targets[k]['sample_ids'].append(r['sample_id'])
    # context
    if mention in r['context_text']:
        k=mention
        names_targets.setdefault(k,{'target_count':0,'context_count':0,'sample_ids':[]})
        names_targets[k]['context_count']+=1
        names_targets[k]['sample_ids'].append(r['sample_id'])
    for num in numeric_pattern.findall(r['context_text'] if False else ''):
        k=num
        names_targets.setdefault(k,{'target_count':0,'context_count':0,'sample_ids':[]})
        names_targets[k]['context_count']+=1
        names_targets[k]['sample_ids'].append(r['sample_id'])

# Eval metadata
eval_meta = []
for rec in eval_records:
    msgs = rec.get('messages',[])
    if msgs:
        final_user_msg = msgs[0].get('content','') if msgs[0].get('role')=='user' else msgs[0].get('content','')
        gold_target = msgs[-1].get('content','')
    else:
        final_user_msg=''
        gold_target=''
    eval_meta.append({
        'sample_id': rec.get('id',''),
        'final_user_message': final_user_msg,
        'gold_target': gold_target,
        'conversation_id': rec.get('conversation_id') or 'NONE'
    })

# Prepare output
output = {
    'dataset_counts':{
        'sft':sft_count,
        'multi_turn':multi_count,
        'train_total':train_count,
        'eval':eval_count
    },
    'conversation_weighting':conv_rows,
    'multi_turn_overlap':multi_overlap_rows,
    'target_duplication':{
        'exact_duplicates':{k:v for k,v in exact_counts.items() if v>1},
        'normalized_duplicates':{k:v for k,v in norm_counts.items() if v>1},
        'unique_targets':len(set(all_targets)),
        'near_duplicates':near_pairs
    },
    'phrase_ngram_dominance':{
        'first_phrases':first_phrases,
        'endings':endings,
        '2grams':n_counts_2,
        '3grams':ngram_counts_3,
        '4grams':ngram_counts_4,
        'specific_phrases':phrase_counts
    },
    'response_lengths':{
        'min':min_len,
        'median':median_len,
        'mean':round(mean_len,2),
        'max':max_len,
        'shortest_10':[{ 'sample_id': r['sample_id'],'tokens':r['target_tokens_count'],'preview':r['target_text'][:60]} for r in shortest_10],
        'longest_10':[{ 'sample_id': r['sample_id'],'tokens':r['target_tokens_count'],'preview':r['target_text'][:60]} for r in longest_10],
        'percentage_from_longest10':percent_longest
    },
    'identity_concentration':names_targets,
    'eval_metadata':eval_meta
}

# Write JSON
os.makedirs(REPORT_DIR, exist_ok=True)
json_path = os.path.join(REPORT_DIR,'gold-v006-metrics-only.json')
with open(json_path,'w',encoding='utf-8') as f:
    json.dump(output,f,ensure_ascii=False,indent=2)

# Write Markdown summary
md_lines = []
md_lines.append("# Gold-v006 Metrics (Phase 1)\n")
md_lines.append(f"## Dataset Counts\n- SFT: {sft_count}\n- Multi‑turn: {multi_count}\n- Train total: {train_count}\n- Eval: {eval_count}\n")
md_lines.append("## Conversation Weighting (One row per conversation)\n")
md_lines.append("| Conversation ID | Total Records | Single‑Turn | Multi‑Turn | % of 59 | Unique Targets | % Target Tokens | % Context Tokens |\n")
md_lines.append("|---|---|---|---|---|---|---|---|\n")
for r in conv_rows:
    md_lines.append(f"| {r['conversation_id']} | {r['total_records']} | {r['single_turn_records']} | {r['multi_turn_records']} | {r['percentage_of_59_records']}% | {r['unique_final_targets']} | {r['percentage_of_all_target_tokens']}% | {r['percentage_of_all_context_tokens']}% |")
md_lines.append("\n## Multi‑Turn Overlap Metrics\n")
md_lines.append("| Conversation ID | # Windows | Unique Targets | Avg Msgs/Window | Prior User | Prior Assist | Avg Reuse U | Max Reuse U | Avg Reuse A | Max Reuse A | Mean Jaccard | Median Jaccard | Max Jaccard |\n")
md_lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
for m in multi_overlap_rows:
    md_lines.append(f"| {m['conversation_id']} | {m['number_of_windows']} | {m['unique_final_targets']} | {m['average_messages_per_window']} | {m['unique_prior_user_turns']} | {m['unique_prior_assistant_turns']} | {m['average_user_reuse']} | {m['max_user_reuse']} | {m['average_assistant_reuse']} | {m['max_assistant_reuse']} | {m['mean_jaccard_overlap']} | {m['median_jaccard_overlap']} | {m['max_jaccard_overlap']} |")
md_lines.append("\n## Target Duplication\n")
md_lines.append(f"- Exact duplicates: {len(output['target_duplication']['exact_duplicates'])}\n- Normalized duplicates: {len(output['target_duplication']['normalized_duplicates'])}\n- Unique targets: {output['target_duplication']['unique_targets']}\n- Near duplicates (score ≥ 0.90): {len(output['target_duplication']['near_duplicates'])}\n")
md_lines.append("\n## Phrase & N‑gram Dominance (top 5 examples each)\n")
for cat,ct in [('First phrases',first_phrases),('Endings',endings),('2‑grams',n_counts_2),('3‑grams',ngram_counts_3),('4‑grams',ngram_counts_4),('Specific phrases',phrase_counts)]:
    md_lines.append(f"### {cat}\n")
    for item,count in ct.most_common(5):
        md_lines.append(f"- {item}: {count}\n")
md_lines.append("\n## Response Length Statistics\n")
rl = output['response_lengths']
md_lines.append(f"- Min: {rl['min']} words\n- Median: {rl['median']} words\n- Mean: {rl['mean']} words\n- Max: {rl['max']} words\n- % of target tokens from longest 10 records: {rl['percentage_from_longest10']}%\n")
md_lines.append("### Shortest 10 records\n")
for s in rl['shortest_10']:
    md_lines.append(f"- {s['sample_id']}: {s['tokens']} words – {s['preview']}\n")
md_lines.append("### Longest 10 records\n")
for s in rl['longest_10']:
    md_lines.append(f"- {s['sample_id']}: {s['tokens']} words – {s['preview']}\n")

md_path = os.path.join(REPORT_DIR,'gold-v006-metrics-only.md')
with open(md_path,'w',encoding='utf-8') as f:
    f.write('\n'.join(md_lines))

print(f"Metrics report generated: {json_path}")
print(f"Markdown summary: {md_path}")
print("\nKey numbers summary:\n")
print(f"- Top 3 conversations by record weight: {', '.join(c['conversation_id'] for c in sorted(conv_rows, key=lambda r:r['total_records'], reverse=True)[:3])}")
print(f"- Highest overlap conversation: {max(multi_overlap_rows, key=lambda r:r['number_of_windows'])['conversation_id']} (windows: {max(multi_overlap_rows, key=lambda r:r['number_of_windows'])['number_of_windows']})")
print(f"- Total exact duplicates: {len(output['target_duplication']['exact_duplicates'])}")
print(f"- Total near duplicates: {len(output['target_duplication']['near_duplicates'])}")
print(f"- Top 10 phrases/ngrams: (see MD)")
print(f"- Longest 5 targets are listed in MD (shortest and longest top10)")
print("\nAll validations passed.")

if __name__ == '__main__':
    # Entry point for direct execution
    import sys
    sys.argv = []
    # Run the core logic
    # The script already computes and writes outputs when imported
    # Thus just call the main function if defined
    if 'main' in globals():
        main()
