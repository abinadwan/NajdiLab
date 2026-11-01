#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dataset Influence Audit for NajdiLab gold-v006-clean
Local analysis only - no training, no modifications
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Paths
BASE = ROOT / 'exports/gold-v006-clean'
SFT_FILE = BASE / "sft.jsonl"
MULTI_TURN_FILE = BASE / "multi_turn.jsonl"
EVAL_FILE = BASE / "text_sft_eval.jsonl"
REPORT_JSON = ROOT / 'reports/gold-v006-dataset-influence-audit.json'
REPORT_MD = ROOT / 'reports/gold-v006-dataset-influence-audit.md'

# Ensure reports dir exists
REPORTS_DIR = BASE.parent / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

def load_jsonl(path):
    """Load JSONL file and return list of records"""
    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def count_tokens(text):
    """Simple token approximation - count Arabic words + English words"""
    # Remove markdown formatting
    text = re.sub(r'[*_`~#\-]', '', text)
    # Count Arabic and English tokens roughly
    arabic_pattern = r'[\u0600-\u06FF]'
    english_pattern = r'[a-zA-Z]+'
    arabic_count = len(re.findall(arabic_pattern, text))
    english_count = len(re.findall(english_pattern, text))
    # Arabic words are longer on average
    return arabic_count + int(english_count * 0.7)

def analyze_conversation_weighting(sft_records):
    """1) Conversation weighting"""
    conv_stats = defaultdict(lambda: {
        'records': [],
        'single_turn': 0,
        'multi_turn': 0,
        'target_tokens': 0,
        'context_tokens': 0
    })
    
    for rec in sft_records:
        conv_id = rec.get('conversation_id') or 'manual'
        messages = rec.get('messages', [])
        
        # Count turns
        user_turns = sum(1 for m in messages if m.get('role') == 'user')
        assistant_turns = sum(1 for m in messages if m.get('role') == 'assistant')
        
        is_single_turn = (user_turns == 1 and assistant_turns == 1)
        
        # Token counts
        target_msg = messages[-1] if messages else {}
        target_content = target_msg.get('content', '')
        target_tokens = count_tokens(target_content)
        
        context_tokens = sum(count_tokens(m.get('content', '')) for m in messages[:-1])
        
        conv_stats[conv_id]['records'].append(rec)
        conv_stats[conv_id]['single_turn'] += 1 if is_single_turn else 0
        conv_stats[conv_id]['multi_turn'] += 1 if not is_single_turn else 0
        conv_stats[conv_id]['target_tokens'] += target_tokens
        conv_stats[conv_id]['context_tokens'] += context_tokens
    
    # Calculate percentages
    total_records = sum(len(r['records']) for r in conv_stats.values())
    
    results = []
    for conv_id, stats in sorted(conv_stats.items(), key=lambda x: x[1]['target_tokens'], reverse=True):
        record_count = len(stats['records'])
        single_pct = (stats['single_turn'] / record_count * 100) if record_count > 0 else 0
        multi_pct = (stats['multi_turn'] / record_count * 100) if record_count > 0 else 0
        
        results.append({
            'conversation_id': conv_id,
            'record_count': record_count,
            'single_turn': stats['single_turn'],
            'multi_turn': stats['multi_turn'],
            'target_tokens': stats['target_tokens'],
            'context_tokens': stats['context_tokens'],
            'single_turn_pct': round(single_pct, 2),
            'multi_turn_pct': round(multi_pct, 2),
            'exceeds_15pct': multi_pct > 15
        })
    
    # Sort by multi_turn_pct descending
    results.sort(key=lambda x: x['multi_turn_pct'], reverse=True)
    return results

def analyze_multi_turn_overlap(multi_records):
    """2) Multi-turn overlap analysis"""
    conv_stats = defaultdict(lambda: {
        'windows': [],
        'prior_turns': [],
        'final_targets': set(),
        'overlap_count': 0
    })
    
    for rec in multi_records:
        conv_id = rec.get('conversation_id') or 'manual'
        messages = rec.get('messages', [])
        
        # Get all assistant responses (windows)
        windows = [m.get('content', '') for m in messages if m.get('role') == 'assistant']
        
        # Prior turns (all user + assistant before last)
        prior_turns = [m.get('content', '') for m in messages[:-1]]
        
        # Final target
        final_target = messages[-1].get('content', '') if messages else ''
        
        conv_stats[conv_id]['windows'].append(windows)
        conv_stats[conv_id]['prior_turns'].extend(prior_turns)
        conv_stats[conv_id]['final_targets'].add(final_target)
    
    # Calculate overlap between windows for each conversation
    results = []
    for conv_id, stats in conv_stats.items():
        all_windows = []
        for window_list in stats['windows']:
            all_windows.extend(window_list)
        
        # Count unique windows vs total
        unique_windows = len(set(all_windows))
        total_windows = len(all_windows)
        overlap_ratio = 1 - (unique_windows / total_windows) if total_windows > 0 else 0
        
        results.append({
            'conversation_id': conv_id,
            'total_windows': total_windows,
            'unique_windows': unique_windows,
            'overlap_ratio': round(overlap_ratio, 4),
            'prior_turns_count': len(stats['prior_turns']),
            'unique_final_targets': len(stats['final_targets'])
        })
    
    return results

def analyze_target_dominance(sft_records):
    """3) Target dominance analysis"""
    # Extract all targets
    all_targets = []
    greeting_patterns = ['يا هلا', 'يا مرحبا', 'الله يحييك', 'أبشر', 'ولا تهون', 
                        'وش عندك', 'وش بغيت']
    
    for rec in sft_records:
        messages = rec.get('messages', [])
        target_idx = rec.get('target_message_index', -1)
        
        if target_idx >= 0 and len(messages) > target_idx:
            target = messages[target_idx].get('content', '')
            all_targets.append({
                'id': rec.get('id'),
                'conversation_id': rec.get('conversation_id') or 'manual',
                'target': target,
                'is_greeting': any(g in target for g in greeting_patterns)
            })
    
    # Exact duplicates
    exact_dupes = Counter()
    for t in all_targets:
        exact_dupes[t['target']] += 1
    
    exact_duplicate_groups = {k: v for k, v in exact_dupes.items() if v > 1}
    
    # Near duplicates (>= 0.90 similarity)
    def similarity(s1, s2):
        """Simple Jaccard-like similarity"""
        if not s1 or not s2:
            return 0
        set1 = set(s1.split())
        set2 = set(s2.split())
        if not set1 or not set2:
            return 0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0
    
    near_dupes = []
    for i, t1 in enumerate(all_targets):
        for j, t2 in enumerate(all_targets):
            if i < j and similarity(t1['target'], t2['target']) >= 0.90:
                pair = (t1['id'], t2['id'])
                near_dupes.append(pair)
    
    # Most common starting phrases
    start_phrases = Counter()
    for t in all_targets:
        target_lower = t['target'].lower()
        for phrase in greeting_patterns:
            if phrase.lower() in target_lower:
                start_phrases[phrase] += 1
    
    # Most common ending phrases
    end_phrases = Counter()
    for t in all_targets:
        target_lower = t['target'].lower()
        if target_lower.endswith('؟') or target_lower.endswith('?'):
            # Find last phrase before question mark
            parts = target_lower.rsplit('؟', 1)[0].rsplit(' ', 1)
            if len(parts) == 2:
                end_phrases[parts[1]] += 1
    
    # Most common n-grams (2-grams)
    ngram_counter = Counter()
    for t in all_targets:
        words = t['target'].split()
        for i in range(len(words) - 1):
            ngram = ' '.join(words[i:i+2])
            ngram_counter[ngram] += 1
    
    top_ngrams = ngram_counter.most_common(20)
    
    return {
        'exact_duplicates': exact_duplicate_groups,
        'near_duplicate_pairs': near_dupes[:50],  # Top 50
        'most_common_starts': dict(start_phrases.most_common(10)),
        'most_common_ends': dict(end_phrases.most_common(10)),
        'top_ngrams': top_ngrams
    }

def classify_targets_by_rules(sft_records):
    """4) Category balance using deterministic keyword rules"""
    
    # Categories
    categories = [
        'greeting/social',
        'dialect/style', 
        'instruction_following',
        'context_following',
        'technical',
        'factual',
        'tool-aware',
        'refusal/safety',
        'memory/name',
        'grammar/language',
        'other'
    ]
    
    # Keywords for each category
    category_keywords = {
        'greeting/social': ['مرحبا', 'يا هلا', 'يا مرحبا', 'الله يحييك', 'أبشر', 'وش عندك', 'وش بغيت'],
        'dialect/style': ['نجدية', 'لهجة', 'أسلوب', 'صيغة'],
        'instruction_following': ['تذكر', 'تأكد', 'تأكد من', 'يجب أن'],
        'context_following': ['تذكر', 'في السياق', 'من قبل', 'السابق'],
        'technical': ['كود', 'برمجة', 'API', 'Python', 'SQL', 'database'],
        'factual': ['حقائق', 'معلومات', 'أرقام', 'إحصائيات'],
        'tool-aware': ['أداة', 'أدوات', 'API', 'function', 'library'],
        'refusal/safety': ['لا يمكن', 'لا أستطيع', 'غير آمن', 'سياسة'],
        'memory/name': ['تذكر', 'تذكر أن', 'اسمك', 'اسمي'],
        'grammar/language': ['خطأ', 'قواعد', 'نحو', 'إملاء']
    }
    
    classifications = []
    category_counts = Counter()
    
    for rec in sft_records:
        messages = rec.get('messages', [])
        target_idx = rec.get('target_message_index', -1)
        
        if target_idx >= 0 and len(messages) > target_idx:
            target = messages[target_idx].get('content', '')
            
            # Try to match categories
            best_category = 'other'
            best_score = 0
            
            for cat, keywords in category_keywords.items():
                score = sum(1 for kw in keywords if kw in target)
                if score > best_score:
                    best_score = score
                    best_category = cat
            
            # If no keyword match, use fallback heuristics
            if best_score == 0:
                greeting_words = ['مرحبا', 'يا هلا', 'أبشر']
                if any(g in target for g in greeting_words):
                    best_category = 'greeting/social'
                elif 'خطأ' in target or 'قواعد' in target:
                    best_category = 'grammar/language'
                elif 'تذكر' in target:
                    best_category = 'memory/name'
                else:
                    best_category = 'other'
            
            classifications.append({
                'sample_id': rec.get('id'),
                'conversation_id': rec.get('conversation_id') or 'manual',
                'target_preview': target[:100],
                'category': best_category,
                'reason': f"matched {best_score} keywords for {best_category}" if best_score > 0 else "no keyword match"
            })
            
            category_counts[best_category] += 1
    
    return {
        'classifications': classifications[:100],  # First 100 samples
        'category_distribution': dict(category_counts)
    }

def analyze_response_lengths(sft_records):
    """5) Response lengths analysis"""
    lengths = []
    
    for rec in sft_records:
        messages = rec.get('messages', [])
        target_idx = rec.get('target_message_index', -1)
        
        if target_idx >= 0 and len(messages) > target_idx:
            target = messages[target_idx].get('content', '')
            token_count = count_tokens(target)
            lengths.append({
                'id': rec.get('id'),
                'tokens': token_count,
                'conversation_id': rec.get('conversation_id') or 'manual'
            })
    
    if not lengths:
        return {'error': 'No records found'}
    
    tokens = [l['tokens'] for l in lengths]
    
    return {
        'min': min(tokens),
        'max': max(tokens),
        'mean': round(sum(tokens) / len(tokens), 2),
        'median': sorted(tokens)[len(tokens) // 2],
        'shortest_10': sorted(lengths, key=lambda x: x['tokens'])[:10],
        'longest_10': sorted(lengths, key=lambda x: -x['tokens'])[:10]
    }

def analyze_identity_concentration(sft_records):
    """6) Identity concentration"""
    names = ['أبوميار', 'أبو حمد', 'مروان تلودي']
    
    identity_counts = {name: 0 for name in names}
    other_names = set()
    
    for rec in sft_records:
        messages = rec.get('messages', [])
        
        for msg in messages:
            content = msg.get('content', '')
            for name in names:
                if name in content:
                    identity_counts[name] += 1
            
            # Find other names
            found_names = set(re.findall(r'([أ-ي]+)', content))
            for n in found_names:
                if n not in names and len(n) > 2:
                    other_names.add(n)
    
    return {
        'named_entities': identity_counts,
        'other_names_sample': list(other_names)[:20]
    }

def analyze_eval_representativeness(eval_records, sft_records):
    """7) Eval representativeness"""
    
    # Build index of training samples
    training_index = {}
    for rec in sft_records:
        messages = rec.get('messages', [])
        target_idx = rec.get('target_message_index', -1)
        
        if target_idx >= 0 and len(messages) > target_idx:
            target = messages[target_idx].get('content', '')[:200]  # First 200 chars
            training_index[rec.get('id')] = {
                'full_target': messages[target_idx].get('content', ''),
                'conversation_id': rec.get('conversation_id') or 'manual'
            }
    
    # For each eval sample, find closest training match
    eval_matches = []
    for rec in eval_records:
        messages = rec.get('messages', [])
        target_idx = rec.get('target_message_index', -1)
        
        if target_idx >= 0 and len(messages) > target_idx:
            eval_target = messages[target_idx].get('content', '')
            
            # Find closest match (simple string containment check)
            best_match = None
            best_score = 0
            
            for train_id, train_data in training_index.items():
                if any([train_data['full_target'] in eval_target or 
                       eval_target[:50] in train_data['full_target']]):
                    score = min(len(eval_target), len(train_data['full_target'])) / max(len(eval_target), len(train_data['full_target']))
                    if score > best_score:
                        best_score = score
                        best_match = train_id
            
            eval_matches.append({
                'eval_id': rec.get('id'),
                'eval_target': eval_target[:100],
                'best_training_match': best_match,
                'match_score': round(best_score, 4) if best_match else None,
                'no_close_match': best_match is None
            })
    
    return eval_matches

def analyze_failure_tracing(sft_records):
    """8) Failure tracing for specific review IDs"""
    
    failure_ids = ['review:109', 'review:110', 'review:112', 'review:108', 
                   'review:208', 'review:62', 'review:157', 'review:156', 'review:207']
    
    failure_analysis = {}
    
    for rec in sft_records:
        rec_id = rec.get('id')
        
        if rec_id in failure_ids:
            messages = rec.get('messages', [])
            tags = rec.get('tags', [])
            
            # Analyze the conversation for evidence
            user_messages = [m.get('content', '') for m in messages if m.get('role') == 'user']
            assistant_messages = [m.get('content', '') for m in messages if m.get('role') == 'assistant']
            
            failure_analysis[rec_id] = {
                'tags': tags,
                'user_messages_count': len(user_messages),
                'assistant_messages_count': len(assistant_messages),
                'last_user_message': user_messages[-1][:100] if user_messages else '',
                'last_assistant_response': assistant_messages[-1][:100] if assistant_messages else '',
                'potential_causes': []
            }
            
            # Detect potential causes
            if 'too_verbose' in tags:
                failure_analysis[rec_id]['potential_causes'].append('Response exceeds expected length')
            
            if 'dialect_issue' in tags:
                failure_analysis[rec_id]['potential_causes'].append('Dialect mismatch detected')
            
            if 'factual_error' in tags:
                failure_analysis[rec_id]['potential_causes'].append('Factual accuracy issue')
            
            if 'ignored_user_instruction' in tags:
                failure_analysis[rec_id]['potential_causes'].append('Failed to follow user instruction')
            
            if 'unnatural_arabic' in tags:
                failure_analysis[rec_id]['potential_causes'].append('Arabic sounds unnatural/robotic')
    
    return failure_analysis

def generate_verdict(all_data, category_balance, conv_weighting, eval_representativeness, failure_tracing):
    """Generate final verdict"""
    
    # Check for data imbalance indicators
    imbalance_indicators = 0
    
    # 1) High multi-turn overlap
    multi_overlap_convs = all_data.get('multi_turn_overlap', {}).get('conversations', [])
    high_overlap_count = sum(1 for c in multi_overlap_convs if c.get('overlap_ratio', 0) > 0.5)
    if high_overlap_count > 5:
        imbalance_indicators += 2
    
    # 2) Target dominance issues
    target_dominance = all_data.get('target_dominance', {})
    if target_dominance.get('exact_duplicates'):
        imbalance_indicators += 1
    if len(target_dominance.get('near_duplicate_pairs', [])) > 10:
        imbalance_indicators += 1
    
    # 3) Category imbalance
    category_dist = all_data.get('category_balance', {}).get('category_distribution', {})
    total_samples = sum(category_dist.values())
    if total_samples > 0:
        for cat, count in category_dist.items():
            pct = count / total_samples * 100
            if pct < 5 and cat != 'other':  # Very small categories (excluding 'other')
                imbalance_indicators += 0.5
    
    # 4) Identity concentration
    identity_data = all_data.get('identity_concentration', {})
    for name, count in identity_data.get('named_entities', {}).items():
        if count > total_samples * 0.3:  # More than 30% mentions
            imbalance_indicators += 1
    
    # 5) Eval representativeness
    eval_data = all_data.get('eval_representativeness', [])
    no_match_count = sum(1 for e in eval_data if e.get('no_close_match'))
    if len(eval_data) > 0 and no_match_count > len(eval_data) * 0.3:  # More than 30% have no close match
        imbalance_indicators += 1
    
    # Determine verdict
    if imbalance_indicators >= 4:
        verdict = 'DATA_IMBALANCE_CONFIRMED'
    elif imbalance_indicators >= 2:
        verdict = 'DATA_IMBALANCE_LIKELY'
    elif imbalance_indicators <= 1:
        verdict = 'NO_DETERMINISTIC_IMBALANCE_FOUND'
    else:
        verdict = 'INCONCLUSIVE'
    
    # Collect reasons for verdict explanation
    reasons = []
    
    if target_dominance.get('exact_duplicates'):
        reasons.append(f"Exact duplicate targets found: {len(target_dominance['exact_duplicates'])} groups")
    
    if len(target_dominance.get('near_duplicate_pairs', [])) > 0:
        reasons.append(f"Near-duplicate pairs (>=90% similarity): {len(target_dominance['near_duplicate_pairs'])}")
    
    category_dist = all_data.get('category_balance', {}).get('category_distribution', {})
    total_cat = sum(category_dist.values())
    if total_cat > 0:
        min_cat = min(category_dist.items(), key=lambda x: x[1])
        if min_cat[1] / total_cat < 0.1:
            reasons.append(f"Category imbalance: '{min_cat[0]}' has only {min_cat[1]} samples ({min_cat[1]/total_cat*100:.1f}%)")
    
    high_overlap = sum(1 for c in conv_weighting if c.get('exceeds_15pct'))
    if high_overlap > 0:
        reasons.append(f"High multi-turn overlap: {high_overlap} conversations exceed 15% multi-turn records")
    
    no_match_count = sum(1 for e in eval_representativeness if e.get('no_close_match'))
    if no_match_count > 0:
        reasons.append(f"Eval representativeness issue: {no_match_count}/{len(eval_representativeness)} eval samples have no close training match")
    
    # Add failure causes
    for rec_id, analysis in failure_tracing.items():
        for cause in analysis.get('potential_causes', []):
            if cause not in reasons:
                reasons.append(f"Failure {rec_id}: {cause}")
    
    # Limit to top 5
    reasons = reasons[:5]
    
    return verdict

def main():
    print("Loading datasets...")
    
    # Load data
    sft_records = load_jsonl(SFT_FILE)
    multi_records = load_jsonl(MULTI_TURN_FILE)
    eval_records = load_jsonl(EVAL_FILE)
    
    print(f"Loaded {len(sft_records)} SFT records")
    print(f"Loaded {len(multi_records)} multi-turn records")
    print(f"Loaded {len(eval_records)} eval records")
    
    # Run analyses
    print("\n1. Analyzing conversation weighting...")
    conv_weighting = analyze_conversation_weighting(sft_records)
    
    print("2. Analyzing multi-turn overlap...")
    multi_overlap = analyze_multi_turn_overlap(multi_records)
    
    print("3. Analyzing target dominance...")
    target_dominance = analyze_target_dominance(sft_records)
    
    print("4. Classifying targets (category balance)...")
    category_balance = classify_targets_by_rules(sft_records)
    
    print("5. Analyzing response lengths...")
    response_lengths = analyze_response_lengths(sft_records)
    
    print("6. Analyzing identity concentration...")
    identity_concentration = analyze_identity_concentration(sft_records)
    
    print("7. Analyzing eval representativeness...")
    eval_representativeness = analyze_eval_representativeness(eval_records, sft_records)
    
    print("8. Analyzing failure tracing...")
    failure_tracing = analyze_failure_tracing(sft_records)
    
    # Compile all data
    all_data = {
        'conversation_weighting': conv_weighting,
        'multi_turn_overlap': {'conversations': multi_overlap},
        'target_dominance': target_dominance,
        'category_balance': category_balance,
        'response_lengths': response_lengths,
        'identity_concentration': identity_concentration,
        'eval_representativeness': eval_representativeness,
        'failure_tracing': failure_tracing,
        'total_sft_records': len(sft_records),
        'total_multi_turn_records': len(multi_records),
        'total_eval_records': len(eval_records)
    }
    
    # Generate verdict
    print("\nGenerating verdict...")
    verdict = generate_verdict(all_data, category_balance, conv_weighting, eval_representativeness, failure_tracing)
    all_data['verdict'] = verdict
    
    # Top 5 reasons
    reasons = []
    
    if target_dominance.get('exact_duplicates'):
        reasons.append(f"Exact duplicate targets found: {len(target_dominance['exact_duplicates'])} groups")
    
    if len(target_dominance.get('near_duplicate_pairs', [])) > 0:
        reasons.append(f"Near-duplicate pairs (>=90% similarity): {len(target_dominance['near_duplicate_pairs'])}")
    
    category_dist = all_data.get('category_balance', {}).get('category_distribution', {})
    total_cat = sum(category_dist.values())
    if total_cat > 0:
        min_cat = min(category_dist.items(), key=lambda x: x[1])
        if min_cat[1] / total_cat < 0.1:
            reasons.append(f"Category imbalance: '{min_cat[0]}' has only {min_cat[1]} samples ({min_cat[1]/total_cat*100:.1f}%)")
    
    high_overlap = sum(1 for c in conv_weighting if c.get('exceeds_15pct'))
    if high_overlap > 0:
        reasons.append(f"High multi-turn overlap: {high_overlap} conversations exceed 15% multi-turn records")
    
    no_match_count = sum(1 for e in eval_representativeness if e.get('no_close_match'))
    if no_match_count > 0:
        reasons.append(f"Eval representativeness issue: {no_match_count}/{len(eval_representativeness)} eval samples have no close training match")
    
    # Add failure causes
    for rec_id, analysis in failure_tracing.items():
        for cause in analysis.get('potential_causes', []):
            if cause not in reasons:
                reasons.append(f"Failure {rec_id}: {cause}")
    
    # Limit to top 5
    reasons = reasons[:5]
    
    # Add verdict explanation
    all_data['verdict_explanation'] = f"{verdict} - Based on {len(reasons)} key indicators:\n" + "\n".join(reasons)
    
    # Write JSON report
    print(f"\nWriting JSON report to {REPORT_JSON}...")
    with open(REPORT_JSON, 'w', encoding='utf-8') as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    # Write Markdown report
    print(f"Writing Markdown report to {REPORT_MD}...")
    md_content = f"""# Dataset Influence Audit Report - gold-v006-clean

## Verdict: `{verdict}`

### Summary
- Total SFT records: {len(sft_records)}
- Multi-turn records: {len(multi_records)}
- Eval records: {len(eval_records)}

### Key Findings

{all_data['verdict_explanation']}

---

## 1. Conversation Weighting

"""
    
    # Add conversation weighting summary
    high_pct_convs = [c for c in conv_weighting if c.get('exceeds_15pct')]
    md_content += f"Conversations exceeding 15% multi-turn: {len(high_pct_convs)}\n\n"
    
    md_content += "| Conversation ID | Records | Single-Turn | Multi-Turn | Target Tokens | Context Tokens | Multi-% |\n"
    md_content += "|------------------|---------|--------------|------------|---------------|----------------|----------|\n"
    
    for c in conv_weighting[:10]:  # Top 10
        md_content += f"| {c['conversation_id'][:50]}... | {c['record_count']} | {c['single_turn']} | {c['multi_turn']} | {c['target_tokens']} | {c['context_tokens']} | {c['multi_turn_pct']}% |\n"
    
    md_content += f"""
---

## 2. Multi-Turn Overlap

Total conversations analyzed: {len(multi_overlap)}

"""
    
    high_overlap_convs = [c for c in multi_overlap if c.get('overlap_ratio', 0) > 0.5]
    md_content += f"Conversations with >50% window overlap: {len(high_overlap_convs)}\n\n"
    
    md_content += "| Conversation ID | Total Windows | Unique Windows | Overlap Ratio | Prior Turns | Unique Final Targets |\n"
    md_content += "|------------------|---------------|-----------------|---------------|-------------|----------------------|\n"
    
    for c in multi_overlap[:10]:
        md_content += f"| {c['conversation_id'][:50]}... | {c['total_windows']} | {c['unique_windows']} | {c['overlap_ratio']} | {c['prior_turns_count']} | {c['unique_final_targets']} |\n"
    
    md_content += f"""
---

## 3. Target Dominance

### Exact Duplicate Groups: {len(target_dominance.get('exact_duplicates', {}))}

"""
    
    for target, count in list(target_dominance.get('exact_duplicates', {}).items())[:5]:
        md_content += f"- **\"{target[:80]}...\"**: appears {count} times\n"
    
    md_content += f"""
### Near-Duplicate Pairs (>=90% similarity): {len(target_dominance.get('near_duplicate_pairs', []))}

### Most Common Starting Phrases:
"""
    
    for phrase, count in target_dominance.get('most_common_starts', {}).items():
        md_content += f"- **\"{phrase}\"**: {count} times\n"
    
    md_content += f"""
### Most Common Ending Phrases:
"""
    
    for phrase, count in target_dominance.get('most_common_ends', {}).items():
        md_content += f"- **\"{phrase}\"**: {count} times\n"
    
    md_content += f"""
---

## 4. Category Balance

"""
    
    cat_dist = category_balance.get('category_distribution', {})
    total_cat_samples = sum(cat_dist.values())
    
    md_content += "| Category | Count | Percentage |\n"
    md_content += "|----------|-------|------------|\n"
    
    for cat, count in sorted(cat_dist.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_cat_samples * 100) if total_cat_samples > 0 else 0
        md_content += f"| {cat} | {count} | {pct:.1f}% |\n"
    
    md_content += f"""
---

## 5. Response Lengths

- Minimum tokens: {response_lengths.get('min', 'N/A')}
- Maximum tokens: {response_lengths.get('max', 'N/A')}
- Mean tokens: {response_lengths.get('mean', 'N/A')}
- Median tokens: {response_lengths.get('median', 'N/A')}

---

## 6. Identity Concentration

"""
    
    identity_data = all_data.get('identity_concentration', {})
    for name, count in identity_data.get('named_entities', {}).items():
        md_content += f"- **{name}**: {count} mentions\n"
    
    md_content += f"""
---

## 7. Eval Representativeness

Eval samples with no close training match: {sum(1 for e in eval_representativeness if e.get('no_close_match'))}/{len(eval_representativeness)}

---

## 8. Failure Tracing

"""
    
    for rec_id, analysis in failure_tracing.items():
        md_content += f"### {rec_id}\n"
        md_content += f"- Tags: {', '.join(analysis.get('tags', []))}\n"
        md_content += f"- Potential causes: {', '.join(analysis.get('potential_causes', []))}\n\n"
    
    md_content += f"""
---

## Verdict Explanation

{all_data['verdict_explanation']}

---

*Report generated locally using Qwen and Python - no external APIs used*
"""
    
    with open(REPORT_MD, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"\n✅ Reports written successfully!")
    print(f"   JSON: {REPORT_JSON}")
    print(f"   Markdown: {REPORT_MD}")
    print(f"\n🎯 Verdict: `{verdict}`")
    
    return all_data

if __name__ == "__main__":
    main()
