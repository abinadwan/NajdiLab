#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dataset Influence Audit - Verification Pass
Verify all computed results without modifying the source data.
"""

import json
import os
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]

# Paths
SFT_PATH = ROOT / 'exports/gold-v006-clean/sft.jsonl'
MULTI_TURN_PATH = ROOT / 'exports/gold-v006-clean/multi_turn.jsonl'
EVAL_PATH = ROOT / 'exports/gold-v006-clean/text_sft_eval.jsonl'
REPORTS_DIR = ROOT / 'reports'

def load_jsonl(path):
    """Load JSONL file and return list of records"""
    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def load_qwen_model():
    """Load Qwen model from Ollama"""
    try:
        import subprocess
        # Try to call Ollama API
        result = subprocess.run(
            ['ollama', 'run', 'qwen2.5', '-p', 'exit', '--no-stream'],
            capture_output=True, text=True, timeout=10
        )
        return True
    except:
        return False

def classify_target_simple(target):
    """Simple keyword-based classification as fallback"""
    target_lower = target.lower()
    
    # Greeting/social
    greetings = ['يا هلا', 'يا مرحبا', 'الله يحييك', 'أبشر', 'ارحب', 'حياك الله', 
                  'وش عندك', 'بخير', 'والله', 'تقبل', 'يعطيك العافية']
    for g in greetings:
        if g in target_lower:
            return 'greeting/social'
    
    # Tool-aware
    tools = ['أداة', 'tool', 'browser', 'terminal', 'file', 'folder', 'path', 
             'command', 'script', 'python', 'bash', 'api', 'endpoint']
    for t in tools:
        if t in target_lower:
            return 'tool-aware'
    
    # Instruction following
    instructions = ['تسليم', 'موعد', 'أرتب', 'ترتيب', 'تنظيم', 'جدول', 'قائمة', 
                    'خطوة', 'طريقة', 'كيف', 'كيفاش', 'وش تبي']
    for i in instructions:
        if i in target_lower:
            return 'instruction_following'
    
    # Technical
    tech = ['ويندوز', 'windows', 'linux', 'macos', 'python', 'code', 'program', 
            'software', 'hardware', 'ram', 'cpu', 'gpu', 'disk']
    for t in tech:
        if t in target_lower:
            return 'technical'
    
    # Factual
    factual = ['تعريف', 'مفهوم', 'ما هو', 'يعني', 'هو نظام', 'هي منصة', 
               'تدعى', 'يسمى', 'المعروف']
    for f in factual:
        if f in target_lower:
            return 'factual'
    
    # Grammar/language
    grammar = ['خطأ', 'نحوي', 'قواعد', 'إملائي', 'تصحيح', 'صحح', 'اكتب', 
               'كيف تكتب', 'الصيغة']
    for g in grammar:
        if g in target_lower:
            return 'grammar/language'
    
    # Other (default)
    return 'other'

def main():
    print("=" * 80)
    print("DATASET INFLUENCE AUDIT - VERIFICATION PASS")
    print("=" * 80)
    
    # Load datasets
    print("\n1. Loading datasets...")
    sft_records = load_jsonl(SFT_PATH)
    multi_records = load_jsonl(MULTI_TURN_PATH)
    eval_records = load_jsonl(EVAL_PATH)
    
    print(f"   SFT records: {len(sft_records)}")
    print(f"   Multi-turn records: {len(multi_records)}")
    print(f"   Eval records: {len(eval_records)}")
    print(f"   Total: {len(sft_records) + len(multi_records) + len(eval_records)}")
    
    # Verify counts match expected
    assert len(sft_records) == 16, f"SFT count mismatch: expected 16, got {len(sft_records)}"
    assert len(multi_records) == 43, f"Multi-turn count mismatch: expected 43, got {len(multi_records)}"
    assert len(eval_records) == 12, f"Eval count mismatch: expected 12, got {len(eval_records)}"
    
    print("\n✅ Count verification passed!")
    
    # 2. Category classification for ALL targets
    print("\n2. Classifying all targets...")
    all_targets = sft_records + multi_records + eval_records
    
    category_counts = Counter()
    classifications = []
    
    for i, record in enumerate(all_targets):
        target = record.get('target', '')
        conv_id = record.get('conversation_id', 'unknown')
        
        # Use simple classification as fallback (Qwen not available)
        category = classify_target_simple(target)
        category_counts[category] += 1
        
        classifications.append({
            'sample_id': f"{record.get('id', 'unknown')}:{i}",
            'conversation_id': conv_id,
            'target_preview': target[:100],
            'category': category
        })
    
    # Print category distribution
    print("\n   Category Distribution:")
    print(f"   {'Category':<25} | {'Count':>6} | {'Percentage':>10}")
    print(f"   {'-'*25} | {'-'*6} | {'-'*10}")
    
    total = len(all_targets)
    for cat in sorted(category_counts.keys(), key=lambda x: category_counts[x], reverse=True):
        count = category_counts[cat]
        pct = (count / total) * 100
        print(f"   {cat:<25} | {count:>6} | {pct:>9.1f}%")
    
    # Verify sum
    total_count = sum(category_counts.values())
    print(f"\n   Total classified: {total_count}")
    print(f"   Expected: {total}")
    assert total_count == total, f"Classification count mismatch: {total_count} != {total}"
    
    # 3. Conversation weighting
    print("\n3. Conversation Weighting Analysis:")
    print(f"\n   Total records: {total}")
    
    conv_weighting = []
    for record in all_targets:
        conv_id = record.get('conversation_id', 'unknown')
        
        # Count records per conversation
        conv_record_count = sum(1 for r in all_targets if r.get('conversation_id') == conv_id)
        
        # Calculate percentages
        record_pct = (conv_record_count / total) * 100
        
        # Get target tokens
        target_tokens = len(record.get('target', '').split())
        
        conv_weighting.append({
            'conversation_id': conv_id,
            'record_count': conv_record_count,
            'single_turn': conv_record_count,  # All are single-turn in this dataset
            'multi_turn': 0,
            'target_tokens': target_tokens,
            'record_pct': record_pct,
            'exceeds_15pct': record_pct > 15
        })
    
    # Sort by record count
    conv_weighting.sort(key=lambda x: x['record_count'], reverse=True)
    
    print(f"\n   {'Conversation ID':<60} | {'Records':>8} | {'% of 59':>10} | {'Tokens':>8} | {'% Tokens':>10}")
    print(f"   {'-'*60} | {'-'*8} | {'-'*10} | {'-'*8} | {'-'*10}")
    
    for c in conv_weighting:
        conv_id = c.get('conversation_id') or 'unknown'
        print(f"   {conv_id[:55]}... | {c['record_count']:>8} | {c['record_pct']:>9.1f}% | {c['target_tokens']:>8} | {c['record_pct']:>9.1f}%")
    
    # Check for any conversation > 15%
    high_pct_convs = [c for c in conv_weighting if c['exceeds_15pct']]
    print(f"\n   Conversations exceeding 15%: {len(high_pct_convs)}")
    assert len(high_pct_convs) == 0, "Found conversations exceeding 15%"
    
    # 4. Multi-turn overlap analysis
    print("\n4. Multi-Turn Overlap Analysis:")
    
    # Group by conversation_id
    conv_groups = {}
    for record in multi_records:
        conv_id = record.get('conversation_id', 'unknown')
        if conv_id not in conv_groups:
            conv_groups[conv_id] = []
        conv_groups[conv_id].append(record)
    
    print(f"\n   Total conversations with multi-turn data: {len(conv_groups)}")
    
    for conv_id, records in conv_groups.items():
        total_windows = len(records)
        unique_targets = len(set(r.get('target', '') for r in records))
        
        # Count prior turns (simplified)
        prior_turns = sum(1 for r in records if 'prior' in str(r).lower())
        
        print(f"\n   Conversation: {conv_id[:50]}...")
        print(f"   Total windows: {total_windows}")
        print(f"   Unique targets: {unique_targets}")
        print(f"   Prior turns count: {prior_turns}")
    
    # 5. Phrase dominance analysis
    print("\n5. Phrase Dominance Analysis:")
    
    phrase_keywords = {
        'أبشر': [],
        'يا هلا': [],
        'يا مرحبا': [],
        'الله يحييك': [],
        'وش عندك': [],
        'وش بغيت': [],
        'ولا تهون': [],
        'خير': [],
        'بخير': []
    }
    
    for record in all_targets:
        target = record.get('target', '')
        for phrase, samples in phrase_keywords.items():
            if phrase in target:
                samples.append(record.get('id', 'unknown'))
    
    print(f"\n   {'Phrase':<15} | {'Count':>6} | {'Sample IDs'}")
    print(f"   {'-'*15} | {'-'*6} | {'-'*30}")
    
    for phrase, samples in phrase_keywords.items():
        if samples:
            count = len(samples)
            ids_str = ', '.join(samples[:5]) + ('...' if len(samples) > 5 else '')
            print(f"   {phrase:<15} | {count:>6} | {ids_str}")
    
    # 6. Eval coverage analysis
    print("\n6. Evaluation Coverage Analysis:")
    
    eval_categories = Counter()
    for record in eval_records:
        target = record.get('target', '')
        category = classify_target_simple(target)
        eval_categories[category] += 1
    
    train_categories = Counter()
    for record in sft_records:
        target = record.get('target', '')
        category = classify_target_simple(target)
        train_categories[category] += 1
    
    print(f"\n   Eval Categories:")
    for cat, count in eval_categories.items():
        print(f"   {cat}: {count}")
    
    print(f"\n   Train Categories:")
    for cat, count in train_categories.items():
        print(f"   {cat}: {count}")
    
    # Check coverage
    missing_categories = set(eval_categories.keys()) - set(train_categories.keys())
    if missing_categories:
        print(f"\n   ⚠️  Missing categories in train: {missing_categories}")
    else:
        print(f"\n   ✅ All eval categories covered in train")
    
    # 7. Generate verdict
    print("\n7. Verdict Generation:")
    
    # Check indicators
    indicators = []
    
    # Category imbalance
    if total > 0:
        min_cat = min(category_counts.items(), key=lambda x: x[1])
        if min_cat[1] / total < 0.2:  # Less than 20%
            indicators.append(f"Category imbalance: '{min_cat[0]}' has only {min_cat[1]} samples ({min_cat[1]/total*100:.1f}%)")
    
    # Phrase dominance
    if phrase_keywords['أبشر']:
        count = len(phrase_keywords['أبشر'])
        if count > total * 0.1:  # More than 10%
            indicators.append(f"Phrase dominance: 'أبشر' appears {count} times ({count/total*100:.1f}%)")
    
    # Eval coverage
    if missing_categories:
        indicators.append(f"Eval coverage issue: categories {missing_categories} not in train")
    
    # Multi-turn overlap
    high_overlap_convs = [c for c in conv_groups.values() if len(c) > 1]
    if len(high_overlap_convs) > 0:
        indicators.append(f"Multi-turn overlap: {len(high_overlap_convs)} conversations have multiple turns")
    
    # Determine verdict
    if len(indicators) >= 3:
        verdict = 'DATA_IMBALANCE_CONFIRMED'
    elif len(indicators) >= 1:
        verdict = 'DATA_IMBALANCE_LIKELY'
    elif len(indicators) == 0:
        verdict = 'TRAINING_CONFIG_MORE_LIKELY'
    else:
        verdict = 'INCONCLUSIVE'
    
    print(f"\n   Verdict: {verdict}")
    print(f"\n   Reasons ({len(indicators)}):")
    for i, reason in enumerate(indicators, 1):
        print(f"   {i}. {reason}")
    
    # 8. Write reports
    print("\n8. Writing verification reports...")
    
    # JSON report
    json_report = {
        'verification_status': 'PASSED',
        'total_records': total,
        'sft_count': len(sft_records),
        'multi_turn_count': len(multi_records),
        'eval_count': len(eval_records),
        'category_distribution': dict(category_counts),
        'conversation_weighting': conv_weighting,
        'phrase_counts': {k: len(v) for k, v in phrase_keywords.items() if v},
        'eval_categories': dict(eval_categories),
        'train_categories': dict(train_categories),
        'missing_categories': list(missing_categories),
        'verdict': verdict,
        'indicators': indicators
    }
    
    json_path = os.path.join(REPORTS_DIR, 'gold-v006-dataset-influence-audit-v2.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)
    
    print(f"   JSON report: {json_path}")
    
    # Markdown report
    md_content = f"""# Dataset Influence Audit - Verification Pass

## Verdict: `{verdict}`

## Summary
- Total records: {total}
- SFT records: {len(sft_records)}
- Multi-turn records: {len(multi_records)}
- Eval records: {len(eval_records)}

## Category Distribution
"""
    
    for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total) * 100
        md_content += f"- **{cat}**: {count} ({pct:.1f}%)\n"
    
    md_content += """
## Conversation Weighting
"""
    
    for c in conv_weighting:
        md_content += f"- {c['conversation_id'][:50]}... : {c['record_count']} records ({c['record_pct']:.1f}%)\n"
    
    md_content += """
## Phrase Dominance
"""
    
    for phrase, count in phrase_keywords.items():
        if count:
            md_content += f"- **{phrase}**: {len(count)} times\n"
    
    md_content += """
## Eval Coverage
- Eval categories: """ + ", ".join(eval_categories.keys()) + """
- Train categories: """ + ", ".join(train_categories.keys()) + """
"""
    
    if missing_categories:
        md_content += f"\n⚠️  Missing categories in train: {missing_categories}\n"
    else:
        md_content += "\n✅ All eval categories covered in train\n"
    
    md_path = os.path.join(REPORTS_DIR, 'gold-v006-dataset-influence-audit-v2.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    
    print(f"   Markdown report: {md_path}")
    
    print("\n✅ Verification complete!")
    print(f"\nFinal Verdict: {verdict}")

if __name__ == '__main__':
    main()
