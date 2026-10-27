import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_first_jsonl(path: str):
    """Return the first JSON record as a dict.
    Do not use yield.
    """
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                return json.loads(line)
    return None


def read_all_jsonl(path: str):
    """Return a list of all JSON records in the file.
    Do not use yield.
    """
    res = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                res.append(json.loads(line))
    return res

if __name__ == "__main__":
    base = ROOT / 'exports/gold-v006-clean'
    sft_path = base / "sft.jsonl"
    multi_path = base / "multi_turn.jsonl"
    eval_path = base / "text_sft_eval.jsonl"

    sft_records = read_all_jsonl(sft_path)
    multi_records = read_all_jsonl(multi_path)
    eval_records = read_all_jsonl(eval_path)

    print(f"1. SFT record count: {len(sft_records)}")
    print(f"2. Multi-turn record count: {len(multi_records)}")
    print(f"3. Evaluation record count: {len(eval_records)}")

    first_sft = sft_records[0] if sft_records else {}
    first_multi = multi_records[0] if multi_records else {}
    first_eval = eval_records[0] if eval_records else {}

    print(f"4. Keys in the first SFT record: {list(first_sft.keys())}")
    print(f"5. Keys in the first multi-turn record: {list(first_multi.keys())}")
    print(f"6. Keys in the first evaluation record: {list(first_eval.keys())}")

    def print_summary(name, rec):
        conv_id = rec.get('conversation_id')
        rec_id = rec.get('id')
        msgs = rec.get('messages', [])
        roles = [m.get('role') for m in msgs]
        last_assistant = None
        for m in msgs:
            if m.get('role') == 'assistant':
                last_assistant = m.get('content')
        print(f"7. First record from {name}:")
        print(f"   conversation_id: {conv_id}")
        print(f"   id: {rec_id}")
        print(f"   Message count: {len(msgs)}")
        print(f"   Roles in order: {roles}")
        print(f"   Final assistant content: {last_assistant}")

    print_summary('sft', first_sft)

    # For multi_turn, extra checks
    msgs_m = first_multi.get('messages', [])
    has_msg_id = any('message_id' in m for m in msgs_m)
    last_assistant = None
    for m in msgs_m:
        if m.get('role') == 'assistant':
            last_assistant = m.get('content')
    print(f"8. First multi-turn record:")
    print(f"   conversation_id: {first_multi.get('conversation_id')}")
    print(f"   id: {first_multi.get('id')}")
    print(f"   Message count: {len(msgs_m)}")
    print(f"   Roles in order: {[m.get('role') for m in msgs_m]}")
    print(f"   Do messages contain message_id? {has_msg_id}")
    print(f"   Final assistant content: {last_assistant}")
