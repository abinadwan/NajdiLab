import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read_all_jsonl(path):
    records = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if line:
                records.append(json.loads(line))
    return records

if __name__ == "__main__":
    path = ROOT / 'exports/gold-v006-clean/multi_turn.jsonl'
    records = read_all_jsonl(path)
    total = len(records)
    print(f"Total records: {total}")
    # Counters
    conv_id_none = 0
    conv_id_exists = 0
    msgs_with_msg_id = 0
    msgs_without_msg_id = 0
    source_type_counts = {}
    source_counts = {}
    conv_windows = {}
    target_msg_errors = []
    for r in records:
        cid = r.get('conversation_id')
        if cid is None:
            conv_id_none += 1
        else:
            conv_id_exists += 1
        msgs = r.get('messages', [])
        # message_id in any msg?
        if any('message_id' in m for m in msgs):
            msgs_with_msg_id += 1
        else:
            msgs_without_msg_id += 1
        # source_type & source
        st = r.get('source_type')
        src = r.get('source')
        source_type_counts[st] = source_type_counts.get(st, 0) + 1
        source_counts[src] = source_counts.get(src, 0) + 1
        # conv windows count
        if cid is not None:
            conv_windows[cid] = conv_windows.get(cid, 0) + 1
        # target message index checks
        tmi = r.get('target_message_index')
        if tmi is None:
            target_msg_errors.append((r.get('id'), 'missing target_message_index'))
        else:
            if not (0 <= tmi < len(msgs)):
                target_msg_errors.append((r.get('id'), 'target_message_index out of bounds'))
            else:
                if msgs[tmi].get('role') != 'assistant':
                    target_msg_errors.append((r.get('id'), 'target_message_index not an assistant'))
            if r.get('message_loss_mask', [])[tmi: tmi+1] != [1]:
                target_msg_errors.append((r.get('id'), 'message_loss_mask at target not 1'))
            if r.get('message_loss_mask', []).count(1) > 1:
                target_msg_errors.append((r.get('id'), 'more than one 1 in message_loss_mask'))
    # Output
    print("1. counts:")
    print(f"   conversation_id = None: {conv_id_none}")
    print(f"   conversation_id present: {conv_id_exists}")
    print(f"   messages contain message_id: {msgs_with_msg_id}")
    print(f"   Messages without message_id: {msgs_without_msg_id}")
    print("2. source_type counts:")
    for k,v in source_type_counts.items():
        print(f"   {k}: {v}")
    print("3. source counts:")
    for k,v in source_counts.items():
        print(f"   {k}: {v}")
    print("4. records with conversation_id=None:")
    for r in records:
        if r.get('conversation_id') is None:
            print(f"   id: {r.get('id')}, source: {r.get('source')}, source_type: {r.get('source_type')}, messages: {len(r.get('messages',[]))}, target_message_index: {r.get('target_message_index')}")
    print("5. window counts per conversation_id: (not None)")
    for cid, count in conv_windows.items():
        print(f"   {cid}: {count}")
    print("6. target_message_index validation:")
    if target_msg_errors:
        for err in target_msg_errors:
            print(f"   record {err[0]}: {err[1]}")
    else:
        print("   all records passed validations")
    # 7. sample non-manual with real cid
    sample = None
    for r in records:
        if r.get('source') != 'manual_sft_items' and r.get('conversation_id') is not None:
            sample = r
            break
    if sample:
        print("7. sample record:")
        print(f"   id: {sample.get('id')}")
        print(f"   conversation_id: {sample.get('conversation_id')}")
        print(f"   keys: {list(sample.keys())}")
        msgs = sample.get('messages', [])
        print(f"   number of messages: {len(msgs)}")
        print(f"   roles: {[m.get('role') for m in msgs]}")
        print(f"   target_message_index: {sample.get('target_message_index')}")
        print(f"   message_id in messages? {any('message_id' in m for m in msgs)}")
        print(f"   source: {sample.get('source')}")
        print(f"   source_type: {sample.get('source_type')}")
    else:
        print("No suitable sample found")
