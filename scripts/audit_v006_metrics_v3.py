import json, re, math, statistics
from pathlib import Path

DATA_DIR = Path(r"C:\Users\Admin\AppData\Local\hermes\NajdiLab\exports\gold-v006-clean")
SFT_PATH = DATA_DIR / "sft.jsonl"
MULTI_PATH = DATA_DIR / "multi_turn.jsonl"
EVAL_PATH = DATA_DIR / "text_sft_eval.jsonl"

REPORT_DIR = Path(r"C:\Users\Admin\AppData\Local\hermes\NajdiLab\reports")
REPORT_JSON = REPORT_DIR / "gold-v006-metrics-v3.json"
REPORT_MD = REPORT_DIR / "gold-v006-metrics-v3.md"

# helper

def read_jsonl(path):
    recs=[]
    with open(path,'r',encoding='utf-8') as f:
        for l in f:
            if l.strip():
                recs.append(json.loads(l))
    return recs

def normalize(txt):
    txt=txt.strip()
    txt=re.sub(r"\s+", " ", txt)
    return txt

sft = read_jsonl(SFT_PATH)
multi = read_jsonl(MULTI_PATH)
eval_rec = read_jsonl(EVAL_PATH)

# ----- Conversation weighting ------------------------------------------------

convs={}
for rec in sft+multi:
    cid=rec.get('conversation_id')
    if cid is None:
        cid='manual:manual_sft_items:3'
    convs.setdefault(cid,{'total':0,'single':0,'multi':0,'targets':set(),'target_words':0,'context_words':0,'ids':[]})
    convs[cid]['total']+=1
    msgs=rec.get('messages',[])
    is_single=len(msgs)==2
    if is_single:
        convs[cid]['single']+=1
    else:
        convs[cid]['multi']+=1
    tgt=msgs[rec['target_message_index']]['content']
    convs[cid]['targets'].add(tgt)
    convs[cid]['target_words']+=len(re.findall(r"[\w']+",tgt))
    ctx_text=' '.join(m.get('content','') for m in msgs[:rec['target_message_index']])
    convs[cid]['context_words']+=len(re.findall(r"[\w']+",ctx_text))
    convs[cid]['ids'].append(rec['id'])

# totals for percent calculations
all_target_words=sum(c['target_words'] for c in convs.values())
all_context_words=sum(c['context_words'] for c in convs.values())
report_convs={}
for cid,c in convs.items():
    pct=round(c['total']/59*100,2)
    pct_tgt=round(c['target_words']/all_target_words*100,2)
    pct_ctx=round(c['context_words']/all_context_words*100,2)
    report_convs[cid]={'total_records':c['total'],'single_turn_records':c['single'],'multi_turn_records':c['multi'],'percentage_of_59':pct,'unique_final_targets':len(c['targets']),'total_target_words':c['target_words'],'percentage_of_all_target_words':pct_tgt,'total_context_words':c['context_words'],'percentage_of_all_context_words':pct_ctx}

# filter >15%
conv_over15=[cid for cid,p in report_convs.items() if p['percentage_of_59']>15 or p['percentage_of_all_target_words']>15]

# ----- Multi-turn overlap real --------------------------------------------
# we only process multi-turn
windows_by_conv={}
prior_identities_by_conv={}
for rec in multi:
    cid=rec.get('conversation_id')
    if cid is None: continue
    win_id=rec['id']
    msgs=rec.get('messages',[])
    tgt_idx=rec['target_message_index']
    prior=msgs[:tgt_idx]
    prior_ids=[normalize(m['role']+'\n'+m.get('content','')) for m in prior]
    windows_by_conv.setdefault(cid,[]).append(prior_ids)
    prior_identities_by_conv.setdefault(cid,[]).append(prior_ids)

# compute per conv metrics
conv_overlap={}
for cid,windows in windows_by_conv.items():
    num_win=len(windows)
    unique_targets=len(set(' '.join(x[-1] for x in windows)))
    # average prior msgs per window
    avg_prior=sum(len(w) for w in windows)/num_win if num_win else 0
    uniq_prior_set=set()
    for w in windows:
        uniq_prior_set.update(w)
    uniq_prior=len(uniq_prior_set)
    # reuse count per prior message across windows
    reuse_counts={}
    for w in windows:
        for msg in w:
            reuse_counts[msg]=reuse_counts.get(msg,0)+1
    counts=list(reuse_counts.values())
    avg_reuse=statistics.mean(counts) if counts else 0
    max_reuse=max(counts) if counts else 0
    used_in_2plus=sum(1 for c in counts if c>=2)
    used_in_5plus=sum(1 for c in counts if c>=5)
    used_in_all=sum(1 for c in counts if c==num_win)
    # pairwise Jaccard
    jaccard_vals=[]
    for i in range(num_win):
        for j in range(i+1,num_win):
            set_i=set(windows[i])
            set_j=set(windows[j])
            inter=len(set_i & set_j)
            uni=len(set_i | set_j)
            jaccard_vals.append(inter/uni if uni else 0)
    if jaccard_vals:
        mean_j=statistics.mean(jaccard_vals)
        med_j=statistics.median(jaccard_vals)
        max_j=max(jaccard_vals)
        min_j=min(jaccard_vals)
    else:
        mean_j=med_j=max_j=min_j=0
    conv_overlap[cid]={'number_of_windows':num_win,'unique_final_targets':unique_targets,'average_prior_messages_per_window':avg_prior,'unique_prior_messages_across_conversation':uniq_prior,'average_reuse_count':avg_reuse,'max_reuse_count':max_reuse,'number_of_prior_messages_reused_in_2plus_windows':used_in_2plus,'number_of_prior_messages_reused_in_5plus_windows':used_in_5plus,'number_of_prior_messages_reused_in_all_windows':used_in_all,'mean_jaccard':mean_j,'median_jaccard':med_j,'max_jaccard':max_j,'min_jaccard':min_j}

# ----- Window nesting -------------------------------------------------
# Count subset pairs per conv
n_nested={}
for cid,windows in windows_by_conv.items():
    pairs=0
    nested=0
    for i in range(len(windows)):
        for j in range(len(windows)):
            if i==j: continue
            set_i=set(windows[i])
            set_j=set(windows[j])
            if set_i.issubset(set_j):
                nested+=1
                pairs+=1
    total_pairs=len(windows)*(len(windows)-1)
    ratio=round(nested/total_pairs*100,2) if total_pairs else 0
    n_nested[cid]={'nested_pairs':nested,'total_pairs':total_pairs,'nested_pair_ratio_percent':ratio}

# ----- Target analysis -------------------------------------------------
all_targets=[msgs[rec['target_message_index']]['content'] for rec in sft+multi]
unique_targets=set(all_targets)
exact_dups=[t for t,cnt in ((t,all_targets.count(t)) for t in unique_targets) if cnt>1]
# normalized exact
norm={normalize(t):t for t in all_targets}
norm_dups=[t for t,cnt in ((t,all_targets.count(t)) for t in unique_targets) if cnt>1]
# near duplicates
near=[]
for i,a in enumerate(all_targets):
    for j,b in enumerate(all_targets[i+1:],i+1):
        if len(a)*len(b)==0: continue
        ratio=__import__('difflib').SequenceMatcher(None,a,b).ratio()
        if ratio>=0.9:
            near.append((a,b,ratio))

# ----- Phrase counts -------------------------------------------------
phrases=["أبشر","يا هلا","يا مرحبا","الله يحييك","وش عندك","وش بغيت","ولا تهون"]
phrase_counts=Counter()
phrase_begs=Counter()
phrase_end=Counter()
phrase_bigrams=Counter()
phrase_trigrams=Counter()
from collections import Counter
for t in all_targets:
    words=re.findall(r"[\w']+",t)
    for p in phrases:
        if p in t:
            phrase_counts[p]+=1
    if words:
        first=' '.join(words[:2])
        phrase_begs[first]+=1
        end=' '.join(words[-2:])
        phrase_end[end]+=1
    for i in range(len(words)-1):
        bigr=' '.join(words[i:i+2])
        phrase_bigrams[bigr]+=1
    for i in range(len(words)-2):
        trig=' '.join(words[i:i+3])
        phrase_trigrams[trig]+=1

# ----- Length concentration --------------------------------------------
word_counts=[len(re.findall(r"[\w']+",t)) for t in all_targets]
min_w=min(word_counts)
median_w=statistics.median(word_counts)
mean_w=sum(word_counts)/len(word_counts)
max_w=max(word_counts)
# longest 10 IDs
ids_with_len=sorted(zip(all_targets,word_counts),key=lambda x:x[1],reverse=True)[:10]
longest_ids=[t[0] for t in ids_with_len]
# proportion of target words in longest10
prop_longest=sum(word_counts[:10])/sum(word_counts)

# ----- Identity concentration ------------------------------------------
ids=[t for t in all_targets]
identifiers=['أبوميار','أبو ميار','أبو حمد','مروان تلودي']
id_counts=Counter()
for t in ids:
    for idf in identifiers:
        if idf in t:
            id_counts[idf]+=1
# @mentions and numeric IDs
mentions=re.findall(r"@\w+",' '.join(ids))
mentions_counts=Counter(mentions)
numeric_ids=re.findall(r"\d+",' '.join(ids))
numeric_counts=Counter(numeric_ids)

# ----- Validation --------------------------------------------------------
assert len(sft)==16
assert len(multi)==43
assert len(eval_rec)==12
assert sum(c['total'] for c in convs.values())==59

# ----- Output ------------------------------------------------------------
output={'conversation_weighting':report_convs,'conversations_over15%':conv_over15,'multi_turn_overlap':conv_overlap,'window_nesting':n_nested,'target_analysis':{'unique':len(unique_targets),'exact_duplicates':len(exact_dups),'normalized_exact':len(norm_dups),'near_duplicates':len(near),'near_pair_info':near,'ids':longest_ids,'prop_longest10':prop_longest,'ids_with_target_words':ids},'phrase_counts':phrase_counts,'phrase_begs':phrase_begs,'phrase_end':phrase_end,'phrase_bigrams':phrase_bigrams,'phrase_trigrams':phrase_trigrams,'length_concentration':{'min':min_w,'median':median_w,'mean':mean_w,'max':max_w,'longest_ids':longest_ids,'prop_longest10':prop_longest},'identity_concentration':{'ids':id_counts,'mentions':mentions_counts,'numeric':numeric_counts}}
# write json
REPORT_DIR.mkdir(parents=True,exist_ok=True)
with open(REPORT_JSON,'w',encoding='utf-8') as f:
    json.dump(output,f,ensure_ascii=False,indent=2)
# write md simple summary
with open(REPORT_MD,'w',encoding='utf-8') as f:
    f.write('# Metrics v3 Summary\n\n')
    f.write(f'- عدد conversations: {len(report_convs)}\n')
    sorted_weights=sorted(report_convs.items(),key=lambda x:x[1]['total_records'],reverse=True)[:5]
    f.write('- أعلى 5 conversation weights:\n')
    for cid,info in sorted_weights:
        f.write(f'  - {cid}: {info}\n')
    f.write('- conversations >15%:\n')
    for cid in conv_over15:
        f.write(f'  - {cid}\n')
    f.write('- overlap metrics للمحادثات الأربع ذات 10 windows: (placeholder)\n')
    f.write('- nested-pair ratio لكل واحدة: (placeholder)\n')
    f.write('- أعلى prior-message reuse: (placeholder)\n')
    f.write('- exact/near duplicate counts: (placeholder)\n')
    f.write('- phrase counts: (placeholder)\n')
    f.write('- target length concentration: (placeholder)\n')
print('Done')
