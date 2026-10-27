import json, re, statistics, itertools
from collections import Counter, defaultdict
from pathlib import Path
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = ROOT / 'exports/gold-v006-clean'
SFT_PATH = DATA_DIR / "sft.jsonl"
MULTI_PATH = DATA_DIR / "multi_turn.jsonl"
EVAL_PATH = DATA_DIR / "text_sft_eval.jsonl"

REPORT_DIR = ROOT / 'reports'
OUTPUT_JSON = REPORT_DIR / "gold-v006-overlap-metrics.json"

# Helper to read jsonl

def read_jsonl(path):
    recs = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                recs.append(json.loads(line))
    return recs

# Normalization : strip + collapse whitespace only

def normalize(text):
    return re.sub(r"\s+", " ", text.strip())

# Load data
sft = read_jsonl(SFT_PATH)
multi = read_jsonl(MULTI_PATH)
eval_rec = read_jsonl(EVAL_PATH)

# 1. Conversation weighting on 59 train records
all_train = sft + multi
conv_stats = defaultdict(lambda: {'records':0,'target_words':0,'context_words':0})
for rec in all_train:
    cid = rec.get('conversation_id')
    if cid is None:
        cid = 'manual:manual_sft_items:3'
    conv_stats[cid]['records'] += 1
    msgs = rec.get('messages', [])
    t_idx = rec.get('target_message_index')
    target = msgs[t_idx]['content'] if 0 <= t_idx < len(msgs) else ""
    context = " ".join(m.get('content','') for m in msgs[:t_idx])
    conv_stats[cid]['target_words'] += len(re.findall(r"[\w']+", target))
    conv_stats[cid]['context_words'] += len(re.findall(r"[\w']+", context))

# Totals
all_tgt_words = sum(v['target_words'] for v in conv_stats.values())
all_ctx_words = sum(v['context_words'] for v in conv_stats.values())
conv_summary = {}
for cid, v in conv_stats.items():
    pct = round(v['records']/59*100,2)
    pct_tgt = round(v['target_words']/all_tgt_words*100,2) if all_tgt_words else 0
    pct_ctx = round(v['context_words']/all_ctx_words*100,2) if all_ctx_words else 0
    conv_summary[cid] = {
        'records': v['records'],
        '%59': pct,
        'total_target_words': v['target_words'],
        '%target_words': pct_tgt,
        'total_context_words': v['context_words'],
        '%context_words': pct_ctx
    }

# 2. Multi-turn overlap metrics
# Group by conversation_id
convs = defaultdict(list)
for rec in multi:
    # only multi-turn (conversation_id may be None for manual, skip that as per constraints? but manual is only sft)
    cid = rec.get('conversation_id')
    if cid is None:
        continue
    convs[cid].append(rec)

# Compute per conversation overlap
overlap_stats = {}
for cid, windows in convs.items():
    # Identify windows, each with prior message identities set
    prior_sets = []
    targets = []
    for rec in windows:
        t_idx = rec.get('target_message_index')
        msgs = rec.get('messages', [])
        prior = msgs[:t_idx]
        ident = [normalize(m.get('role','') + " " + normalize(m.get('content','')) ) for m in prior]
        prior_sets.append(set(ident))
        targets.append(msgs[t_idx]['content'])
    # unique targets
    unique_targets = set(targets)
    # Jaccard between each pair
    jaccards = []
    for i in range(len(prior_sets)):
        for j in range(i+1,len(prior_sets)):
            s1 = prior_sets[i]
            s2 = prior_sets[j]
            inter = len(s1 & s2)
            uni = len(s1 | s2)
            jacc = inter/uni if uni else 0
            jaccards.append(jacc)
    mean_j = round(statistics.mean(jaccards),3) if jaccards else 0
    med_j = round(statistics.median(jaccards),3) if jaccards else 0
    max_j = round(max(jaccards),3) if jaccards else 0
    # nested pair percentage
    nested = 0
    total_pairs = 0
    for i in range(len(prior_sets)):
        for j in range(i+1,len(prior_sets)):
            total_pairs+=1
            if prior_sets[i].issubset(prior_sets[j]) or prior_sets[j].issubset(prior_sets[i]):
                nested+=1
    nested_pct = round(nested/total_pairs*100,2) if total_pairs else 0
    # reuse stats
    all_priors = list(itertools.chain.from_iterable(prior_sets))
    counts = Counter(all_priors)
    avg_reuse = round(statistics.mean(counts.values()),3) if counts else 0
    max_reuse = max(counts.values()) if counts else 0
    overlap_stats[cid] = {
        'windows': len(windows),
        'unique_targets': len(unique_targets),
        'mean_jaccard': mean_j,
        'median_jaccard': med_j,
        'max_jaccard': max_j,
        'nested_pair_percentage': nested_pct,
        'average_prior_message_reuse': avg_reuse,
        'max_prior_message_reuse': max_reuse
    }

# 3. Target analysis on 59 targets (sft + multi)
all_targets = []
for rec in all_train:
    msgs = rec.get('messages', [])
    t_idx = rec.get('target_message_index')
    if 0 <= t_idx < len(msgs):
        all_targets.append(msgs[t_idx]['content'])

# exact duplicates
exact_counts = Counter(all_targets)
exact_dups = [t for t,c in exact_counts.items() if c>1]

# normalized duplicates
norm_targets = [normalize(t) for t in all_targets]
norm_counts = Counter(norm_targets)
norm_dups = [t for t,c in norm_counts.items() if c>1]

# near duplicates >=0.9
near_dups = []
for i,a in enumerate(all_targets):
    for j,b in enumerate(all_targets[i+1:],i+1):
        if len(a)*len(b)==0:
            continue
        ratio=SequenceMatcher(None,a,b).ratio()
        if ratio>=0.90:
            near_dups.append((a,b,ratio))

# 4. Phrase counts
phrases = ["أبشر","يا هلا","يا مرحبا","الله يحييك","وش عندك","وش بغيت","ولا تهون"]
phrase_counts = Counter()
for t in all_targets:
    for p in phrases:
        if p in t:
            phrase_counts[p]+=1

# 5. Length stats
word_counts = [len(re.findall(r"[\w']+", t)) for t in all_targets]
min_wc = min(word_counts)
median_wc = statistics.median(word_counts)
mean_wc = round(sum(word_counts)/len(word_counts),2)
max_wc = max(word_counts)
# longest 10 targets
ids_longest = sorted(zip(all_targets,word_counts), key=lambda x:x[1], reverse=True)[:10]
prop_longest = round(sum(w for _,w in ids_longest)/sum(word_counts)*100,2)

# Compile results
results = {
    'conversation_weighting': conv_summary,
    'multi_turn_overlap': overlap_stats,
    'target_analysis': {
        'exact_duplicates': exact_dups,
        'normalized_duplicates': norm_dups,
        'near_duplicates_count': len(near_dups),
        'unique_targets_count': len(set(all_targets))
    },
    'phrase_counts': dict(phrase_counts),
    'length_stats': {
        'min': min_wc,
        'median': median_wc,
        'mean': mean_wc,
        'max': max_wc,
        'prop_longest_10_targets_pct': prop_longest
    }
}

# Write JSON
REPORT_DIR.mkdir(parents=True,exist_ok=True)
with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

# Print minimal numeric output as per request
print('Conversation weighting per cid:')
for cid,info in conv_summary.items():
    print(f'{cid}: records={info["records"]}, %59={info["%59"]}%, words_target={info["total_target_words"]}, pct_target={info["%target_words"]}%, words_context={info["total_context_words"]}, pct_context={info["%context_words"]}%')

print('\nMulti-turn overlap metrics:')
for cid,info in overlap_stats.items():
    print(f'{cid}: windows={info["windows"]}, meanJ={info["mean_jaccard"]}, medJ={info["median_jaccard"]}, maxJ={info["max_jaccard"]}, nested_pct={info["nested_pair_percentage"]}%, avgReuse={info["average_prior_message_reuse"]}, maxReuse={info["max_prior_message_reuse"]}')

print('\nTarget analysis:')
print('exact duplicates count:', len(exact_dups))
print('normalized duplicates count:', len(norm_dups))
print('near duplicates count >=0.90:', len(near_dups))
print('unique targets count:', len(set(all_targets)))

print('\nPhrase counts:')
for p,c in phrase_counts.items():
    print(f'{p}: {c}')

print('\nLength stats:')
print('min_words:', min_wc)
print('median_words:', median_wc)
print('mean_words:', mean_wc)
print('max_words:', max_wc)
print('prop_longest10_pct:', prop_longest)

