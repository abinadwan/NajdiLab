import json
from pathlib import Path


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
    base = Path(r"C:\\Users\\Admin\\AppData\\Local\\hermes\\NajdiLab\\exports\\gold-v006-clean")
    sft_path = base / "sft.jsonl"
    multi_path = base / "multi_turn.jsonl"
    eval_path = base / "text_sft_eval.jsonl"

    sft_records = read_all_jsonl(sft_path)
    multi_records = read_all_jsonl(multi_path)
    eval_records = read_all_jsonl(eval_path)

    print(f"1. عدد سجلات sft: {len(sft_records)}")
    print(f"2. عدد سجلات multi_turn: {len(multi_records)}")
    print(f"3. عدد سجلات eval: {len(eval_records)}")

    first_sft = sft_records[0] if sft_records else {}
    first_multi = multi_records[0] if multi_records else {}
    first_eval = eval_records[0] if eval_records else {}

    print(f"4. keys لأول سجل من sft: {list(first_sft.keys())}")
    print(f"5. keys لأول سجل من multi_turn: {list(first_multi.keys())}")
    print(f"6. keys لأول سجل من eval: {list(first_eval.keys())}")

    def print_summary(name, rec):
        conv_id = rec.get('conversation_id')
        rec_id = rec.get('id')
        msgs = rec.get('messages', [])
        roles = [m.get('role') for m in msgs]
        last_assistant = None
        for m in msgs:
            if m.get('role') == 'assistant':
                last_assistant = m.get('content')
        print(f"7. لأول سجل من {name}:")
        print(f"   conversation_id: {conv_id}")
        print(f"   id: {rec_id}")
        print(f"   عدد messages: {len(msgs)}")
        print(f"   roles بالترتيب: {roles}")
        print(f"   آخر assistant content: {last_assistant}")

    print_summary('sft', first_sft)

    # For multi_turn, extra checks
    msgs_m = first_multi.get('messages', [])
    has_msg_id = any('message_id' in m for m in msgs_m)
    last_assistant = None
    for m in msgs_m:
        if m.get('role') == 'assistant':
            last_assistant = m.get('content')
    print(f"8. لأول سجل من multi_turn:")
    print(f"   conversation_id: {first_multi.get('conversation_id')}")
    print(f"   id: {first_multi.get('id')}")
    print(f"   عدد messages: {len(msgs_m)}")
    print(f"   roles بالترتيب: {[m.get('role') for m in msgs_m]}")
    print(f"   هل يوجد message_id داخل الرسائل؟ {has_msg_id}")
    print(f"   آخر assistant content: {last_assistant}")
