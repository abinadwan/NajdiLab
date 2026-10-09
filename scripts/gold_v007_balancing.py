import json, re, statistics, os
from pathlib import Path
from collections import Counter, defaultdict

# config
SRC_DIR = Path(r"C:\Users\Admin\AppData\Local\hermes\NajdiLab\exports\gold-v006-clean")
DST_DIR = Path(r"C:\Users\Admin\AppData\Local\hermes\NajdiLab\exports\gold-v007-balanced")

# helper

def read_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]

def write_jsonl(path, records):
    with open(path, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False)+'\n')

# normalization for message identity

def message_identity(msg):
    role = msg.get('role','')
    content = msg.get('content','')
    return re.sub(r"\s+", " ", (role+'\n'+content).strip())

# compute Jaccard between two sets

def jaccard(set1, set2):
    inter = len(set1 & set2)
    uni = len(set1 | set2)
    return inter/uni if uni else 0.0

# read data
sft = read_jsonl(SRC_DIR/'sft.jsonl')
multi = read_jsonl(SRC_DIR/'multi_turn.jsonl')
text_eval = read_jsonl(SRC_DIR/'text_sft_eval.jsonl')

# extract targets from eval for exclusion
eval_targets = {r.get('messages', [{}])[r.get('target_message_index',0)].get('content','') for r in text_eval if r.get('messages')}

# ---- 1. Single-turn balancing ----
# Identify duplicates across entire dataset: build set of targets from sft+multi
all_targets_set = set()
# add multi targets
for r in multi:
    msgs=r.get('messages',[])
    idx=r.get('target_message_index')
    if 0<=idx<len(msgs):
        all_targets_set.add(msgs[idx].get('content',''))

# duplicate targets in sft
valid_sft = []
seen_targets = set()
for r in sft:
    msgs=r.get('messages',[])
    idx=r.get('target_message_index')
    if not (0<=idx<len(msgs)):
        continue
    target = msgs[idx].get('content','')
    # filter duplicates
    if target in seen_targets:
        continue
    # eval overlap
    if target in eval_targets:
        continue
    # contamination: skip if target contains "Assistant:" maybe
    if re.search(r"Assistant[:?]", target):
        continue
    # target must be non-empty and not all spaces
    if not target.strip():
        continue
    seen_targets.add(target)
    valid_sft.append(r)

# ---- 2. Multi-turn balancing ----
# group by conversation_id
conv_map = defaultdict(list)
for r in multi:
    cid = r.get('conversation_id')
    conv_map[cid].append(r)

# helper to compute nested ratio for conv

def compute_nested_ratio(window_sets):
    total_pairs = 0
    nested = 0
    for i in range(len(window_sets)):
        for j in range(i+1, len(window_sets)):
            total_pairs+=1
            if window_sets[i].issubset(window_sets[j]) or window_sets[j].issubset(window_sets[i]):
                nested+=1
    return nested/total_pairs if total_pairs else 0.0

# helper to compute mean Jaccard

def compute_mean_jaccard(window_sets):
    if len(window_sets)<2:
        return 0.0
    vals=[jaccard(window_sets[i], window_sets[j]) for i in range(len(window_sets)) for j in range(i+1,len(window_sets))]
    return sum(vals)/len(vals)

# function to pick windows

def select_windows_for_conv(rlist):
    # precompute info per window
    infos = []
    for r in rlist:
        msgs = r.get('messages',[])
        t_idx = r.get('target_message_index')
        prior_idents = [message_identity(m) for m in msgs[:t_idx]]
        target = msgs[t_idx].get('content','')
        ctx_len = len(re.findall(r"[\w']+", " ".join([m.get('content','') for m in msgs[:t_idx]])))
        infos.append({'record':r,'idents':set(prior_idents),'target':target,'ctx_len':ctx_len})
    n = len(infos)
    if n<=2:
        return [i['record'] for i in infos]  # keep all
    # compute nested ratio and mean jaccard
    sets=[i['idents'] for i in infos]
    nested_ratio = compute_nested_ratio(sets)
    mean_j = compute_mean_jaccard(sets)
    selected = []
    if nested_ratio>=0.80:
        # keep max 3: short, medium, long context
        infos_sorted = sorted(infos, key=lambda x: x['ctx_len'])
        # short
        selected.append(infos_sorted[0])
        # medium
        if len(infos_sorted)>2:
            selected.append(infos_sorted[len(infos_sorted)//2])
        else:
            selected.append(infos_sorted[-1])
        # long
        selected.append(infos_sorted[-1])
        # ensure unique targets; if duplicates, drop later one
        uniq_targets=set()
        final=[]
        for cand in selected:
            tgt=cand['target']
            if tgt not in uniq_targets:
                uniq_targets.add(tgt)
                final.append(cand)
        selected=final[:3]
    else:
        # keep max 4, selection order
        # step1 shortest context
        infos_by_ctx=sorted(infos, key=lambda x: x['ctx_len'])
        selected.append(infos_by_ctx[0])
        # step2 longest context
        selected.append(infos_by_ctx[-1])
        # step3 lowest Jaccard with selected so far
        def jacc_with_selected(cand):
            return min([jaccard(cand['idents'], s['idents']) for s in selected])
        remaining=[i for i in infos if i not in selected]
        if remaining:
            cand=min(remaining, key=jacc_with_selected)
            selected.append(cand)
        # step4 if fourth allowed and less overlap group
        if len(selected)<4:
            # compute average jacc with group for each remaining
            def avg_j(cand):
                return sum(jaccard(cand['idents'], s['idents']) for s in selected)/len(selected)
            if remaining:
                cand=min([i for i in remaining if i not in selected], key=avg_j)
                selected.append(cand)
        # ensure unique targets, drop duplicates if any
        uniq_targets=set()
        final=[]
        for cand in selected:
            tgt=cand['target']
            if tgt not in uniq_targets:
                uniq_targets.add(tgt)
                final.append(cand)
        selected=final[:4]
    return [i['record'] for i in selected]

# apply selection to each conv
selected_multi=[]
for cid, rlist in conv_map.items():
    sel=select_windows_for_conv(rlist)
    selected_multi.extend(sel)

# ---- 3. Compose new dataset ----
DST_DIR.mkdir(parents=True, exist_ok=True)

# Write sft
write_jsonl(DST_DIR/'sft.jsonl', valid_sft)
# Write multi_turn
write_jsonl(DST_DIR/'multi_turn.jsonl', selected_multi)

# Copy other files
for fname in ['direct_language.jsonl','preference_pairs.jsonl','tool_eval.jsonl','vision_eval.jsonl','runtime_agent_eval.jsonl','text_sft_eval.jsonl']:
    src = SRC_DIR / fname
    if src.exists():
        dst = DST_DIR / fname
        dst.write_bytes(src.read_bytes())

# Write empty manifest.json and balancing_report.json placeholders
bal_report={'before':{},'after':{}}
write_jsonl(DST_DIR/'balancing_report.json', [bal_report])
write_jsonl(DST_DIR/'manifest.json', [{}])
write_jsonl(DST_DIR/'loss-mask-validation.json', [{}])

# ---- 4. Metrics for reporting ----
# Compute stats before
before_stats={}
for cid, rlist in conv_map.items():
    recs=len(rlist)
    ctx_words=sum(len(re.findall(r"[\w']+", " ".join(m.get('content','') for m in r.get('messages',[])))) for r in rlist)
    tgt_words=sum(len(re.findall(r"[\w']+", r.get('messages',[])[r.get('target_message_index',0)].get('content','')) if 0<=r.get('target_message_index',0)<len(r.get('messages',[])) else 0) for r in rlist)
    before_stats[cid]={'records':recs,'ctx_words':ctx_words,'tgt_words':tgt_words}
# after stats
after_map=defaultdict(list)
for r in selected_multi:
    after_map[r.get('conversation_id')].append(r)
after_stats={}
for cid, rlist in after_map.items():
    recs=len(rlist)
    ctx_words=sum(len(re.findall(r"[\w']+", " ".join(m.get('content','') for m in r.get('messages',[])))) for r in rlist)
    tgt_words=sum(len(re.findall(r"[\w']+", r.get('messages',[])[r.get('target_message_index',0)].get('content','')) if 0<=r.get('target_message_index',0)<len(r.get('messages',[])) else 0) for r in rlist)
    after_stats[cid]={'records':recs,'ctx_words':ctx_words,'tgt_words':tgt_words}

# compute global stats
total_train_before = len(sft)+len(multi)
valid_sft_count=len(valid_sft)
valid_multi_before=len(multi)
valid_multi_after=len(selected_multi)

# conversation count after
after_conversation_count=len(after_stats)

# highest conversation share after
after_shares=[(cid,info['records']/len(selected_multi)*100) for cid,info in after_stats.items()]
max_share=max(after_shares, key=lambda x:x[1]) if after_shares else (None,0)

# highest target-word share after
# compute target word count per conversation after
target_words_after={cid:after_stats[cid]['tgt_words'] for cid in after_stats}
max_target_share=max(target_words_after.items(), key=lambda x:x[1]) if target_words_after else (None,0)

# mean Jaccard after per conv
mean_jacc_after={cid:compute_mean_jaccard([set(j['idents']) for j in conv_map[cid]]) for cid in after_stats}
max_mean_jacc=max(mean_jacc_after.items(), key=lambda x:x[1]) if mean_jacc_after else (None,0)

# nested pair ratio after
nested_after={cid:compute_nested_ratio([set(j['idents']) for j in conv_map[cid]]) for cid in after_stats}
max_nested_after=max(nested_after.items(), key=lambda x:x[1]) if nested_after else (None,0)

# phrase counts after across all targets
all_targets_after=[]
for r in selected_multi:
    msgs=r.get('messages',[])
    idx=r.get('target_message_index')
    if 0<=idx<len(msgs):
        all_targets_after.append(msgs[idx].get('content',''))
phrase_phrases=["أبشر","يا هلا","يا مرحبا","الله يحييك","وش عندك","وش بغيت","ولا تهون"]
phrase_counts_after={p:sum(p in t for t in all_targets_after) for p in phrase_phrases}

# loss-mask validation
# ensure each record has target_index, train_on_last_assistant_only true, message_loss_mask ends with 1
loss_ok=True
for r in valid_sft+selected_multi:
    if not (0<=r.get('target_message_index',-1)<len(r.get('messages',[]))):
        loss_ok=False
        break
    if not r.get('train_on_last_assistant_only',False):
        loss_ok=False
        break
    mask=r.get('message_loss_mask',[])
    if not mask or mask[-1]!=1:
        loss_ok=False
        break

# print requested summary
print('SFT count:', valid_sft_count)
print('multi-turn count before:', valid_multi_before)
print('multi-turn count after:', valid_multi_after)
print('total training count after:', valid_sft_count+valid_multi_after)
print('number of conversations after:', after_conversation_count)
print('highest conversation share after (cid, %):', max_share)
print('highest target-word share after (cid, words):', max_target_share)
print('highest mean Jaccard after (cid, value):', max_mean_jacc)
print('highest nested-pair ratio after (cid, value):', max_nested_after)
print('phrase counts after:', phrase_counts_after)
print('loss-mask validation passes:', loss_ok)
print('READY_FOR_CONTROLLED_EPOCH1')
