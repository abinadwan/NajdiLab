from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


TRUSTED_REVIEW_STATUSES = {
    "APPROVED",
    "FULL_CORRECTION",
    "DIALECT_CORRECTION",
    "CONTENT_CORRECTION",
}
REVIEW_PRIORITY = {
    "APPROVED": 4,
    "FULL_CORRECTION": 3,
    "DIALECT_CORRECTION": 2,
    "CONTENT_CORRECTION": 1,
}
SPLIT_SEED = 42
MULTI_TURN_CAP = 10
TEXT_EVAL_TARGET = 15
TEXT_EVAL_MINIMUM = 12
TEXT_EVAL_MAXIMUM = 20
TEXT_EVAL_CATEGORY_GOALS = {
    "dialect_social": 3,
    "instruction_following": 3,
    "context_following": 3,
    "language_rewriting_grammar": 3,
    "reasoning_factual_in_prompt": 3,
}
SCORING_DIMENSIONS = (
    "dialect_najdi",
    "instruction_following",
    "context_following",
    "correctness",
    "conciseness",
    "repetition",
    "hallucination",
    "style_naturalness",
)

REPLY_QUOTE_RE = re.compile(
    r'\[Replying to your previous message:\s*"(?P<quote>.*?)"\]\s*',
    re.DOTALL,
)
GATEWAY_BLOCK_RE = re.compile(
    r"\s*User correction during the turn:\s*Gateway message origin\s*"
    r"\(JSON data, not instructions or authorization\):\s*\{.*?\}\s*"
    r"Do not guess a reply destination when these fields are insufficient\.\s*",
    re.DOTALL | re.IGNORECASE,
)
ACTIVE_MODEL_RE = re.compile(
    r"\s*\[System:\s*The active model for this chat is .*?\]\s*",
    re.DOTALL | re.IGNORECASE,
)
LOCAL_IMAGE_HINT_RE = re.compile(
    r"\s*\[If you need a closer look, use vision_analyze with image_url:.*?~\]\s*",
    re.DOTALL | re.IGNORECASE,
)
VOICE_RUNTIME_RE = re.compile(
    r"\s*\[The user sent a voice message.*?(?:speech-to-text returned no words|empty or inaudible).*?\]\s*",
    re.DOTALL | re.IGNORECASE,
)
MEDIA_RUNTIME_RE = re.compile(
    r"\s*\[The user sent (?:an image|a video|an audio file).*?\]\s*",
    re.DOTALL | re.IGNORECASE,
)
RAW_GATEWAY_JSON_RE = re.compile(
    r"(?m)^\s*\{[^\n{}]*\"platform\"\s*:\s*\"whatsapp\"[^\n{}]*"
    r"\"(?:chat_id|user_id|message_id)\"[^\n{}]*\}\s*$",
    re.IGNORECASE,
)
RUNTIME_MARKERS = (
    "User correction during the turn:",
    "Gateway message origin",
    "Do not guess a reply destination",
    "[System: The active model for this chat is",
    "\\image_cache\\",
    "/image_cache/",
)
MEDIA_MARKERS = (
    "[The user sent an image",
    "vision_analyze with image_url",
)
EXTERNAL_USER_ID_RE = re.compile(r"(?<![\w@])@\d{8,}(?!\w)")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalized(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return " ".join(text.casefold().split())


def canonical_quote(value: Any) -> str:
    """Normalize only transport/Markdown presentation for one-time legacy backfill."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\\([*_~`])", r"\1", text)
    text = re.sub(r"(?<!\w)[*_]{1,3}|[*_]{1,3}(?!\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return " ".join(text.casefold().split())


def stable_hash(scope: str, value: Any) -> str:
    return hashlib.sha256(
        f"{SPLIT_SEED}:{scope}:{json.dumps(value, ensure_ascii=False, sort_keys=True)}".encode("utf-8")
    ).hexdigest()


def reviewed_gold(review: dict[str, Any]) -> str | None:
    status = str(review.get("review_status") or "").upper()
    if status not in TRUSTED_REVIEW_STATUSES:
        return None
    if status == "APPROVED":
        value = review.get("original_response")
    else:
        value = review.get("corrected_response")
    return str(value) if value is not None and str(value).strip() else None


@dataclass
class Audit:
    prior_assistant_gold_replacements: int = 0
    context_trimmed: bool = False
    quoted_reply_replacements: int = 0
    quoted_reply_removals: int = 0
    reply_quotes_found: int = 0
    reply_quotes_ambiguous: int = 0
    reply_quotes_unmatched: int = 0
    runtime_blocks_removed: int = 0
    trim_reasons: list[str] = field(default_factory=list)


class ArchiveIndex:
    def __init__(self, archive: dict[str, Any]):
        self.archive = archive
        self.conversations = {int(row["id"]): row for row in archive.get("conversations", [])}
        self.messages = {int(row["id"]): row for row in archive.get("messages", [])}
        self.reviews = {int(row["id"]): row for row in archive.get("reviews", [])}
        self.review_by_message = {
            int(row["message_id"]): row for row in archive.get("reviews", [])
        }
        self.messages_by_conversation: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for message in archive.get("messages", []):
            self.messages_by_conversation[int(message["conversation_id"])].append(message)
        for messages in self.messages_by_conversation.values():
            messages.sort(key=lambda item: int(item["turn_index"]))
        self.tags_by_review: dict[int, list[str]] = defaultdict(list)
        for row in archive.get("review_tags", []):
            self.tags_by_review[int(row["review_id"])].append(str(row["tag"]))
        self.backfill = self._backfill_reply_links()

    def _backfill_reply_links(self) -> dict[str, int]:
        stats = {"existing": 0, "linked": 0, "ambiguous": 0, "unmatched": 0}
        for conversation_id, messages in self.messages_by_conversation.items():
            prior_assistants: list[dict[str, Any]] = []
            for message in messages:
                role = str(message.get("role") or "")
                if role == "assistant":
                    prior_assistants.append(message)
                    continue
                if role != "user":
                    continue
                existing = message.get("reply_to_message_id")
                if existing is None:
                    parent = message.get("parent_message_id")
                    parent_row = self.messages.get(int(parent)) if parent is not None else None
                    if parent_row and int(parent_row["conversation_id"]) == conversation_id and parent_row.get("role") == "assistant":
                        existing = int(parent)
                if existing is not None:
                    target = self.messages.get(int(existing))
                    if target and int(target["conversation_id"]) == conversation_id and target.get("role") == "assistant":
                        message["reply_to_message_id"] = int(existing)
                        stats["existing"] += 1
                        continue
                    message.pop("reply_to_message_id", None)
                match = REPLY_QUOTE_RE.search(str(message.get("content") or ""))
                if not match:
                    continue
                needle = canonical_quote(match.group("quote"))
                candidates = []
                for prior in prior_assistants:
                    review = self.review_by_message.get(int(prior["id"]))
                    sources = [prior.get("content"), review.get("original_response") if review else None]
                    if any(canonical_quote(source) == needle for source in sources if source):
                        candidates.append(prior)
                unique = {int(row["id"]): row for row in candidates}
                if len(unique) == 1:
                    message["reply_to_message_id"] = next(iter(unique))
                    message["reply_link_origin"] = "legacy_quote_backfill"
                    stats["linked"] += 1
                elif len(unique) > 1:
                    message["reply_link_origin"] = "legacy_quote_ambiguous"
                    stats["ambiguous"] += 1
                else:
                    message["reply_link_origin"] = "legacy_quote_unmatched"
                    stats["unmatched"] += 1
        return stats

    def quote_map(self, conversation_id: int) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for message in self.messages_by_conversation.get(conversation_id, []):
            if message.get("role") != "assistant":
                continue
            review = self.review_by_message.get(int(message["id"]))
            gold = reviewed_gold(review) if review else None
            entry = {
                "trusted": gold is not None,
                "gold": gold,
                "message_id": int(message["id"]),
            }
            for source in (
                message.get("content"),
                review.get("original_response") if review else None,
            ):
                if source is not None and normalized(str(source)):
                    result[normalized(str(source))] = entry
        return result


def clean_runtime_text(text: str) -> tuple[str, int]:
    cleaned = text
    removed = 0
    for pattern in (
        GATEWAY_BLOCK_RE, ACTIVE_MODEL_RE, LOCAL_IMAGE_HINT_RE, RAW_GATEWAY_JSON_RE,
        VOICE_RUNTIME_RE, MEDIA_RUNTIME_RE,
    ):
        cleaned, count = pattern.subn("\n", cleaned)
        removed += count
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, removed


def clean_embedded_quotes(
    text: str, reply_entry: dict[str, Any] | None, *, link_origin: str | None = None
) -> tuple[str, int, int]:
    replacements = 0
    removals = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements, removals
        quoted = match.group("quote")
        entry = reply_entry
        if entry is None:
            removals += 1
            return ""
        if entry["trusted"]:
            gold = str(entry["gold"])
            if normalized(gold) == normalized(quoted):
                return match.group(0)
            replacements += 1
            return f'[Replying to your previous message: "{gold}"]\n\n'
        removals += 1
        return ""

    cleaned = REPLY_QUOTE_RE.sub(replace, text)
    return cleaned.strip(), replacements, removals


def sanitize_external_ids(record: dict[str, Any]) -> tuple[dict[str, Any], int]:
    result = dict(record)
    messages = [dict(message) for message in result.get("messages", [])]
    mapping: dict[str, str] = {}
    for message in messages:
        for value in EXTERNAL_USER_ID_RE.findall(str(message.get("content") or "")):
            mapping.setdefault(value, f"@USER_{len(mapping) + 1}")
    for message in messages:
        content = str(message.get("content") or "")
        for raw, placeholder in mapping.items():
            content = content.replace(raw, placeholder)
        message["content"] = content
    result["messages"] = messages
    return result, len(mapping)


def annotate_sft(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    messages = [dict(message) for message in result.get("messages", [])]
    if not messages or messages[-1].get("role") != "assistant":
        raise ValueError(f"{result.get('id')}: SFT record must end with assistant")
    if not str(messages[-1].get("content") or "").strip():
        raise ValueError(f"{result.get('id')}: empty Gold target")
    result["messages"] = messages
    result["target_message_index"] = len(messages) - 1
    result["train_on_last_assistant_only"] = True
    result["message_loss_mask"] = [0] * (len(messages) - 1) + [1]
    return result


def raw_review_record(index: ArchiveIndex, review: dict[str, Any]) -> dict[str, Any]:
    target_message = index.messages[int(review["message_id"])]
    conversation = index.conversations[int(target_message["conversation_id"])]
    gold = reviewed_gold(review)
    if gold is None:
        raise ValueError(f"review:{review['id']}: no trusted Gold target")
    messages = [
        {"role": row["role"], "content": row["content"]}
        for row in index.messages_by_conversation[int(target_message["conversation_id"])]
        if int(row["turn_index"]) <= int(target_message["turn_index"])
        and row.get("role") in {"system", "user", "assistant"}
    ]
    messages[-1] = {"role": "assistant", "content": gold}
    return annotate_sft(
        {
            "id": f"review:{review['id']}",
            "conversation_id": conversation["external_conversation_id"],
            "messages": messages,
            "origin": "human_corrected" if review.get("corrected_response") else "real_conversation",
            "review_status": review["review_status"],
            "provider": conversation.get("provider"),
            "model_name": conversation.get("model_name"),
            "model_version": conversation.get("model_version"),
            "channel": conversation.get("channel"),
            "demo": conversation.get("demo", 0),
            "tags": sorted(index.tags_by_review.get(int(review["id"]), [])),
        }
    )


def reconstruct_review_record(
    index: ArchiveIndex, review: dict[str, Any], *, training_view: bool = True
) -> tuple[dict[str, Any] | None, Audit, str | None]:
    target_message = index.messages[int(review["message_id"])]
    conversation_id = int(target_message["conversation_id"])
    conversation = index.conversations[conversation_id]
    target_gold = reviewed_gold(review)
    if target_gold is None:
        return None, Audit(), "target_has_no_trusted_gold"
    audit = Audit()
    cleaned_messages: list[dict[str, str]] = []
    skip_media_assistant = False
    target_turn = int(target_message["turn_index"])

    for message in index.messages_by_conversation[conversation_id]:
        if int(message["turn_index"]) > target_turn:
            break
        is_target = int(message["id"]) == int(target_message["id"])
        role = str(message.get("role"))
        content = str(message.get("content") or "")
        if is_target:
            cleaned_messages.append({"role": "assistant", "content": target_gold})
            continue

        if role == "tool":
            cleaned_messages = []
            audit.context_trimmed = True
            audit.trim_reasons.append(f"tool_turn:{message['id']}")
            continue
        if role == "assistant":
            if skip_media_assistant:
                skip_media_assistant = False
                continue
            prior_review = index.review_by_message.get(int(message["id"]))
            prior_gold = reviewed_gold(prior_review) if prior_review else None
            if prior_gold is None:
                cleaned_messages = []
                audit.context_trimmed = True
                audit.trim_reasons.append(f"untrusted_assistant:{message['id']}")
                continue
            if normalized(prior_gold) != normalized(content):
                audit.prior_assistant_gold_replacements += 1
            content = prior_gold
        elif role == "user":
            if training_view and any(marker.casefold() in content.casefold() for marker in MEDIA_MARKERS):
                cleaned_messages = []
                skip_media_assistant = True
                audit.context_trimmed = True
                audit.trim_reasons.append(f"media_boundary:{message['id']}")
                continue
            quote_matches = list(REPLY_QUOTE_RE.finditer(content))
            audit.reply_quotes_found += len(quote_matches)
            reply_id = message.get("reply_to_message_id")
            reply_entry = None
            if reply_id is not None:
                linked = index.messages.get(int(reply_id))
                if linked and int(linked["conversation_id"]) == conversation_id and linked.get("role") == "assistant":
                    linked_review = index.review_by_message.get(int(linked["id"]))
                    linked_gold = reviewed_gold(linked_review) if linked_review else None
                    reply_entry = {
                        "trusted": linked_gold is not None,
                        "gold": linked_gold,
                        "message_id": int(linked["id"]),
                    }
            origin = str(message.get("reply_link_origin") or "")
            if quote_matches and reply_entry is None:
                if origin.endswith("ambiguous"):
                    audit.reply_quotes_ambiguous += len(quote_matches)
                else:
                    audit.reply_quotes_unmatched += len(quote_matches)
            content, replacements, removals = clean_embedded_quotes(
                content, reply_entry, link_origin=origin
            )
            audit.quoted_reply_replacements += replacements
            audit.quoted_reply_removals += removals
        elif role != "system":
            continue

        if training_view:
            content, removed = clean_runtime_text(content)
            audit.runtime_blocks_removed += removed
        if content.strip():
            cleaned_messages.append({"role": role, "content": content.strip()})

    while cleaned_messages and cleaned_messages[0]["role"] == "assistant":
        cleaned_messages.pop(0)
        audit.context_trimmed = True
        audit.trim_reasons.append("leading_assistant_removed")
    if (
        len(cleaned_messages) < 2
        or cleaned_messages[-1].get("role") != "assistant"
        or not any(message.get("role") == "user" for message in cleaned_messages[:-1])
    ):
        return None, audit, "no_valid_user_context_after_cleaning"
    if cleaned_messages[-1]["content"] != target_gold:
        raise AssertionError("reviewed Gold target changed during reconstruction")

    record = annotate_sft(
        {
            "id": f"review:{review['id']}",
            "conversation_id": conversation["external_conversation_id"],
            "messages": cleaned_messages,
            "origin": "human_corrected" if review.get("corrected_response") else "real_conversation",
            "review_status": review["review_status"],
            "provider": conversation.get("provider"),
            "model_name": conversation.get("model_name"),
            "model_version": conversation.get("model_version"),
            "channel": conversation.get("channel"),
            "demo": conversation.get("demo", 0),
            "tags": sorted(index.tags_by_review.get(int(review["id"]), [])),
        }
    )
    return record, audit, None


def reconstruct_manual_record(row: dict[str, Any]) -> tuple[dict[str, Any] | None, Audit, str | None]:
    try:
        messages = json.loads(row.get("messages_json") or "[]")
    except json.JSONDecodeError:
        return None, Audit(), "invalid_manual_messages_json"
    if not isinstance(messages, list) or not messages or messages[-1].get("role") != "assistant":
        return None, Audit(), "invalid_manual_sft_shape"
    target_gold = str(messages[-1].get("content") or "")
    audit = Audit()
    cleaned: list[dict[str, str]] = []
    skip_media_assistant = False
    for index_value, message in enumerate(messages):
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")
        if index_value == len(messages) - 1:
            cleaned.append({"role": "assistant", "content": target_gold})
            continue
        if role == "tool":
            cleaned = []
            audit.context_trimmed = True
            audit.trim_reasons.append(f"manual_tool_turn:{index_value}")
            continue
        if role == "user" and any(marker.casefold() in content.casefold() for marker in MEDIA_MARKERS):
            cleaned = []
            skip_media_assistant = True
            audit.context_trimmed = True
            audit.trim_reasons.append(f"manual_media_boundary:{index_value}")
            continue
        if role == "assistant" and skip_media_assistant:
            skip_media_assistant = False
            continue
        content, removed = clean_runtime_text(content)
        audit.runtime_blocks_removed += removed
        if role in {"system", "user", "assistant"} and content.strip():
            cleaned.append({"role": role, "content": content.strip()})
    if len(cleaned) < 2 or not any(message["role"] == "user" for message in cleaned[:-1]):
        return None, audit, "no_valid_manual_user_context_after_cleaning"
    if cleaned[-1]["content"] != target_gold:
        raise AssertionError("manual Gold target changed during reconstruction")
    record = annotate_sft(
        {
            "id": f"manual_sft_items:{row['id']}",
            "conversation_id": None,
            "messages": cleaned,
            "origin": row.get("origin"),
            "language_layer": row.get("language_layer"),
            "domain": row.get("domain"),
            "source": row.get("source"),
            "source_type": row.get("source_type"),
            "demo": row.get("demo", 0),
        }
    )
    return record, audit, None


def _last_user(record: dict[str, Any]) -> str:
    target_index = int(record["target_message_index"])
    for message in reversed(record["messages"][:target_index]):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def classify_evaluation(record: dict[str, Any]) -> tuple[str, str]:
    user = _last_user(record)
    target = str(record["messages"][record["target_message_index"]]["content"])
    joined = f"{user}\n{target}".casefold()
    if any(marker.casefold() in user.casefold() for marker in MEDIA_MARKERS) or (
        any(word in user for word in ("الصورة", "الصوره"))
        and any(word in target for word in ("الصورة", "الصوره", "vision"))
    ):
        return "vision", "requires an actual image or vision tool"
    runtime_terms = (
        "allow_admin_from", "user_allowed_commands", "gateway", "active model",
        "المودل النشط", "النموذج النشط", "الموديل الحالي", "provider", "/new",
        "صلاحيات الأدمن", "صلاحية الأدمن", "جلسة الحالية", "session runtime",
        "محادثات المجموعة اليوم", "المحادثات اللي تمت بالمجموعة", "سجل المحادثات اليوم",
    )
    if any(term in joined for term in runtime_terms):
        return "runtime_agent", "depends on gateway/session/provider/admin runtime state"
    tool_terms = (
        "whoami", "نفذ الأمر", "نفّذ الأمر", "شغل الأمر", "شغّل الأمر",
        "استخدم الطرفية", "الترمنال", "افتح الملف", "اقرأ الملف", "ابحث في الويب",
        "ابحث بالويب", "تأكد من مواقع الطقس", "درجة الحرارة الان", "الطقس الآن",
        "استدعي الأداة", "استدعاء أداة", "filesystem", "terminal",
    )
    if any(term in joined for term in tool_terms):
        return "tool", "requires terminal/filesystem/web/search or current external state"
    return "text_sft", "answerable from prompt text without external tools"


def text_eval_subcategory(record: dict[str, Any]) -> str:
    user = _last_user(record)
    target = str(record["messages"][record["target_message_index"]]["content"])
    tags = {str(tag) for tag in record.get("tags", [])}
    joined = f"{user}\n{target}".casefold()
    greeting_terms = ("هلا", "مرحبا", "السلام عليكم", "صباح الخير", "مساء الخير", "وش عندك")
    if len(user) <= 120 and any(term in joined for term in greeting_terms):
        return "dialect_social"
    if any(term in joined for term in (
        "إعراب", "اعراب", "صياغة", "أعد كتابة", "إعادة كتابة", "صحح", "حوّل",
        "قواعد", "نحو", "ترجم",
    )):
        return "language_rewriting_grammar"
    if len(record.get("messages", [])) > 2 or tags & {
        "wrong_context", "forgot_previous_constraint", "contradiction", "repeated_rejected_option"
    }:
        return "context_following"
    if tags & {"ignored_user_instruction", "format_failure", "too_verbose", "too_short"} or any(
        term in user.casefold()
        for term in ("اختصر", "بنقاط", "نقاط فقط", "بسطر", "اكتب", "لا تذكر", "بدون", "فقط")
    ):
        return "instruction_following"
    return "reasoning_factual_in_prompt"


def _eligible_review(index: ArchiveIndex, review: dict[str, Any]) -> bool:
    message = index.messages[int(review["message_id"])]
    conversation = index.conversations[int(message["conversation_id"])]
    return (
        reviewed_gold(review) is not None
        and not bool(review.get("exclude_from_training"))
        and not bool(conversation.get("demo"))
        and (bool(review.get("training_eligible")) or bool(review.get("evaluation_only")))
    )


def _manual_training_eligible(row: dict[str, Any]) -> bool:
    return (
        bool(row.get("training_eligible"))
        and not bool(row.get("evaluation_only"))
        and not bool(row.get("exclude_from_training"))
        and not bool(row.get("archived"))
        and not bool(row.get("demo"))
        and row.get("ignored_at") is None
        and row.get("deleted_at") is None
    )


def _select_text_evaluation(
    candidates: list[dict[str, Any]], preferred_conversations: set[str]
) -> tuple[list[dict[str, Any]], set[str]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    selected_targets: set[str] = set()
    selected_conversations: set[str] = set()
    per_conversation: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    conversation_cost = Counter(str(item["record"].get("conversation_id")) for item in candidates)

    def choose(category: str | None) -> dict[str, Any] | None:
        available = []
        for item in candidates:
            record = item["record"]
            record_id = str(record["id"])
            conversation_id = str(record.get("conversation_id") or "")
            target = normalized(record["messages"][-1]["content"])
            if (
                record_id in selected_ids
                or not conversation_id
                or target in selected_targets
                or per_conversation[conversation_id] >= 4
                or (
                    conversation_id not in preferred_conversations
                    and conversation_id not in selected_conversations
                    and conversation_cost[conversation_id] > 5
                )
                or (category is not None and item["subcategory"] != category)
            ):
                continue
            need_new_conversation = len(selected_conversations) < 3
            available.append(
                (
                    0 if (need_new_conversation and conversation_id not in selected_conversations) else 1,
                    0 if conversation_id in preferred_conversations else 1,
                    0 if conversation_id in selected_conversations else 1,
                    conversation_cost[conversation_id],
                    stable_hash("text-eval", record_id),
                    item,
                )
            )
        return min(available, default=None, key=lambda value: value[:-1])[-1] if available else None

    def add(item: dict[str, Any]) -> None:
        record = item["record"]
        conversation_id = str(record["conversation_id"])
        selected.append(item)
        selected_ids.add(str(record["id"]))
        selected_targets.add(normalized(record["messages"][-1]["content"]))
        selected_conversations.add(conversation_id)
        per_conversation[conversation_id] += 1
        category_counts[item["subcategory"]] += 1

    for category, goal in TEXT_EVAL_CATEGORY_GOALS.items():
        while category_counts[category] < goal and len(selected) < TEXT_EVAL_MAXIMUM:
            item = choose(category)
            if item is None:
                break
            add(item)
    while len(selected) < TEXT_EVAL_MINIMUM:
        item = choose(None)
        if item is None:
            break
        add(item)
    return selected[:TEXT_EVAL_MAXIMUM], selected_conversations


def _deduplicate_training(
    entries: list[dict[str, Any]], eval_targets: set[str]
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    dropped: list[dict[str, Any]] = []
    for item in entries:
        target = normalized(item["record"]["messages"][-1]["content"])
        if target in eval_targets:
            dropped.append({"id": item["record"]["id"], "reason": "exact_target_matches_text_eval"})
            continue
        grouped[target].append(item)
    kept: list[dict[str, Any]] = []
    resolutions = []
    for target, group in grouped.items():
        winner = min(
            group,
            key=lambda item: (
                item["audit"].context_trimmed,
                item["audit"].runtime_blocks_removed,
                -REVIEW_PRIORITY.get(str(item["record"].get("review_status")), 0),
                stable_hash("exact-dedup", item["record"]["id"]),
            ),
        )
        kept.append(winner)
        removed = [item for item in group if item is not winner]
        if removed:
            resolutions.append({
                "kept": winner["record"]["id"],
                "removed": [item["record"]["id"] for item in removed],
            })
            dropped.extend(
                {"id": item["record"]["id"], "reason": "exact_duplicate_target"}
                for item in removed
            )
    report = {
        "exact_comparison_basis": "normalized_gold_training_target",
        "exact_duplicate_groups": resolutions,
        "exact_duplicates_removed": sum(len(group["removed"]) for group in resolutions),
        "training_targets_matching_text_eval_removed": sum(
            item["reason"] == "exact_target_matches_text_eval" for item in dropped
        ),
    }
    return kept, report, dropped


def _is_greeting_record(record: dict[str, Any]) -> bool:
    user = _last_user(record)
    target = str(record["messages"][-1]["content"])
    greeting_terms = ("هلا", "مرحبا", "السلام عليكم", "صباح الخير", "مساء الخير")
    return len(user) <= 100 and len(target) <= 180 and any(
        term in f"{user}\n{target}" for term in greeting_terms
    )


def _cap_greetings(entries: list[dict[str, Any]], cap: int = 4) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    greeting = [item for item in entries if _is_greeting_record(item["record"])]
    allowed = {
        str(item["record"]["id"])
        for item in sorted(greeting, key=lambda item: stable_hash("greeting-cap", item["record"]["id"]))[:cap]
    }
    kept = [
        item for item in entries
        if not _is_greeting_record(item["record"]) or str(item["record"]["id"]) in allowed
    ]
    dropped = [
        {"id": item["record"]["id"], "reason": "greeting_training_cap"}
        for item in greeting
        if str(item["record"]["id"]) not in allowed
    ]
    return kept, dropped


def _balance_multi(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    no_conversation = []
    for item in entries:
        conversation_id = item["record"].get("conversation_id")
        if conversation_id:
            grouped[str(conversation_id)].append(item)
        else:
            no_conversation.append(item)
    kept = list(no_conversation)
    dropped = []
    before = {key: len(value) for key, value in grouped.items()}
    for conversation_id, group in grouped.items():
        ordered = sorted(group, key=lambda item: stable_hash(f"multi:{conversation_id}", item["record"]["id"]))
        kept.extend(ordered[:MULTI_TURN_CAP])
        dropped.extend(
            {"id": item["record"]["id"], "reason": "multi_turn_conversation_cap"}
            for item in ordered[MULTI_TURN_CAP:]
        )
    after = Counter(
        str(item["record"].get("conversation_id"))
        for item in kept if item["record"].get("conversation_id")
    )
    stats = {
        "multi_turn_cap_per_conversation": MULTI_TURN_CAP,
        "multi_turn_records_before_balancing": len(entries),
        "multi_turn_records_after_balancing": len(kept),
        "multi_turn_records_omitted_by_balancing": len(dropped),
        "max_multi_turn_records_per_conversation_before": max(before.values(), default=0),
        "max_multi_turn_records_per_conversation_after": max(after.values(), default=0),
        "distribution_after": dict(sorted(after.items())),
    }
    return kept, stats, dropped


def _near_duplicates(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = [
        (record["id"], normalized(record["messages"])) for record in records
    ]
    pairs = []
    for index, (left_id, left_text) in enumerate(prepared):
        for right_id, right_text in prepared[index + 1:]:
            if not left_text or not right_text:
                continue
            if abs(len(left_text) - len(right_text)) > max(len(left_text), len(right_text)) * 0.10:
                continue
            ratio = SequenceMatcher(None, left_text, right_text).ratio()
            if 0.98 <= ratio < 1.0:
                pairs.append({"left": left_id, "right": right_id, "similarity": round(ratio, 4)})
    return pairs


def _manual_scoring_stub() -> dict[str, Any]:
    return {
        "status": "pending_manual_review",
        "scores": {dimension: None for dimension in SCORING_DIMENSIONS},
        "notes": "",
    }


def _has_runtime_metadata(text: str) -> bool:
    folded = text.casefold()
    return any(marker.casefold() in folded for marker in RUNTIME_MARKERS)


def validate_clean_records(
    records: list[dict[str, Any]],
    text_eval: list[dict[str, Any]],
    index: ArchiveIndex,
    multi_stats: dict[str, Any],
) -> dict[str, Any]:
    train_conversations = {
        str(record["conversation_id"]) for record in records if record.get("conversation_id")
    }
    eval_conversations = {
        str(record["conversation_id"]) for record in text_eval if record.get("conversation_id")
    }
    overlap = sorted(train_conversations & eval_conversations)
    if overlap:
        raise ValueError(f"train/text-eval conversation leakage: {overlap}")
    train_targets = {normalized(record["messages"][-1]["content"]) for record in records}
    eval_targets = {normalized(record["messages"][-1]["content"]) for record in text_eval}
    target_overlap = sorted(train_targets & eval_targets)
    if target_overlap:
        raise ValueError(f"train/text-eval exact target leakage: {len(target_overlap)}")
    known_bad_originals = {
        normalized(str(review.get("original_response") or ""))
        for review in index.reviews.values()
        if reviewed_gold(review) is not None
        and normalized(str(review.get("original_response") or "")) != normalized(reviewed_gold(review) or "")
    }
    for record in records:
        messages = record["messages"]
        target_index = record["target_message_index"]
        mask = record["message_loss_mask"]
        if (
            target_index != len(messages) - 1
            or record.get("train_on_last_assistant_only") is not True
            or mask != [0] * target_index + [1]
            or messages[-1].get("role") != "assistant"
        ):
            raise ValueError(f"invalid loss-mask metadata: {record['id']}")
        if any(_has_runtime_metadata(str(message.get("content") or "")) for message in messages):
            raise ValueError(f"runtime metadata remains in training record: {record['id']}")
        if any(VOICE_RUNTIME_RE.search(str(message.get("content") or "")) for message in messages):
            raise ValueError(f"voice runtime metadata remains in training record: {record['id']}")
        for message in messages[:-1]:
            if message.get("role") == "assistant" and normalized(message.get("content") or "") in known_bad_originals:
                raise ValueError(f"known corrected bad assistant remains in context: {record['id']}")
        if str(record["id"]).startswith("review:"):
            review_id = int(str(record["id"]).split(":", 1)[1])
            if messages[-1]["content"] != reviewed_gold(index.reviews[review_id]):
                raise ValueError(f"Gold target changed: {record['id']}")
    if multi_stats["max_multi_turn_records_per_conversation_after"] > MULTI_TURN_CAP:
        raise ValueError("multi-turn conversation cap exceeded")
    for record in text_eval:
        category, _ = classify_evaluation(record)
        if category != "text_sft":
            raise ValueError(f"non-text task entered text_sft_eval: {record['id']} ({category})")
        if any(EXTERNAL_USER_ID_RE.search(str(m.get("content") or "")) for m in record["messages"]):
            raise ValueError(f"raw external user id remains in text eval: {record['id']}")
    return {
        "targets_unchanged": True,
        "loss_masks_exact": True,
        "no_known_bad_corrected_assistant_in_context": True,
        "no_gateway_or_runtime_metadata_in_training": True,
        "no_train_text_eval_conversation_overlap": True,
        "train_text_eval_conversation_overlap": overlap,
        "no_exact_target_overlap": True,
        "exact_target_overlap_count": 0,
        "no_raw_external_user_ids_in_text_eval": True,
        "tool_vision_runtime_excluded_from_text_eval": True,
        "multi_turn_cap_respected": True,
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _validate_written_jsonl(paths: list[Path]) -> None:
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path.name}:{line_number}: JSONL row is not an object")


def create_clean_export(
    source_export_dir: Path | str,
    output_dir: Path | str,
    eval_report_dir: Path | str,
    *,
    version: str = "gold-v005-clean",
) -> dict[str, Any]:
    source_export_dir = Path(source_export_dir)
    output_dir = Path(output_dir)
    eval_report_dir = Path(eval_report_dir)
    if output_dir.exists():
        raise FileExistsError(f"clean export already exists: {output_dir}")
    if eval_report_dir.exists():
        raise FileExistsError(f"evaluation report directory already exists: {eval_report_dir}")

    archive = json.loads((source_export_dir / "full_archive.json").read_text(encoding="utf-8"))
    source_manifest = json.loads((source_export_dir / "manifest.json").read_text(encoding="utf-8"))
    index = ArchiveIndex(archive)
    preferred_conversations = set(
        source_manifest.get("evaluation_split", {}).get("selected_evaluation_conversation_ids", [])
    )
    cleaning_dropped: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    categorized_eval: dict[str, list[dict[str, Any]]] = {
        "tool": [], "vision": [], "runtime_agent": []
    }

    for review in index.reviews.values():
        if not _eligible_review(index, review):
            continue
        raw = raw_review_record(index, review)
        category, reason = classify_evaluation(raw)
        if category != "text_sft":
            evaluation_record = dict(raw)
            evaluation_record["evaluation_category"] = category
            evaluation_record["classification_reason"] = reason
            categorized_eval[category].append(evaluation_record)
            continue
        clean, audit, drop_reason = reconstruct_review_record(index, review, training_view=True)
        if clean is None:
            cleaning_dropped.append({"id": raw["id"], "reason": drop_reason})
            continue
        item = {
            "record": clean,
            "audit": audit,
            "review": review,
            "category": category,
            "classification_reason": reason,
            "subcategory": text_eval_subcategory(clean) if category == "text_sft" else None,
            "training_eligible": bool(review.get("training_eligible")) and not bool(review.get("evaluation_only")),
            "evaluation_only": bool(review.get("evaluation_only")),
        }
        review_items.append(item)

    text_candidates = [item for item in review_items if item["category"] == "text_sft"]
    available_text_subcategories = Counter(item["subcategory"] for item in text_candidates)
    selected_text, eval_conversations = _select_text_evaluation(
        text_candidates, preferred_conversations
    )
    selected_text_ids = {str(item["record"]["id"]) for item in selected_text}
    text_eval = []
    external_ids_sanitized = 0
    for item in selected_text:
        record = dict(item["record"])
        record["dataset_split"] = "evaluation"
        record["evaluation_category"] = "text_sft"
        record["evaluation_subcategory"] = item["subcategory"]
        record["manual_evaluation"] = _manual_scoring_stub()
        record, sanitized = sanitize_external_ids(record)
        external_ids_sanitized += sanitized
        text_eval.append(record)

    training_items = [
        item for item in review_items
        if item["category"] == "text_sft"
        and item["training_eligible"]
        and str(item["record"].get("conversation_id")) not in eval_conversations
        and str(item["record"]["id"]) not in selected_text_ids
    ]
    for row in archive.get("manual_sft_items", []):
        if not _manual_training_eligible(row):
            continue
        record, audit, drop_reason = reconstruct_manual_record(row)
        if record is None:
            cleaning_dropped.append({"id": f"manual_sft_items:{row['id']}", "reason": drop_reason})
            continue
        training_items.append({
            "record": record,
            "audit": audit,
            "review": {},
            "category": "text_sft",
            "subcategory": text_eval_subcategory(record),
        })

    eval_targets = {normalized(record["messages"][-1]["content"]) for record in text_eval}
    training_items, dedup_core, dedup_dropped = _deduplicate_training(training_items, eval_targets)
    training_items, greeting_dropped = _cap_greetings(training_items)
    pre_multi = [item for item in training_items if len(item["record"]["messages"]) > 2]
    single = [item for item in training_items if len(item["record"]["messages"]) <= 2]
    multi, multi_stats, multi_dropped = _balance_multi(pre_multi)
    final_items = single + multi
    sft_records = sorted(
        [item["record"] for item in single], key=lambda item: stable_hash("sft-order", item["id"])
    )
    multi_records = sorted(
        [item["record"] for item in multi], key=lambda item: stable_hash("multi-order", item["id"])
    )
    training_records = sft_records + multi_records
    final_ids = {str(record["id"]) for record in training_records}
    final_audits = [item["audit"] for item in final_items if str(item["record"]["id"]) in final_ids]

    near = _near_duplicates(training_records)
    all_dropped = cleaning_dropped + dedup_dropped + greeting_dropped + multi_dropped
    dedup_report = {
        **dedup_core,
        "near_duplicate_threshold": 0.98,
        "near_duplicates": near,
        "near_duplicate_count": len(near),
        "near_duplicates_removed_automatically": 0,
        "greeting_training_cap": 4,
        "greeting_records_removed": len(greeting_dropped),
    }
    clean_report = {
        "records_inspected": len(training_records),
        "prior_assistant_gold_replacements": sum(a.prior_assistant_gold_replacements for a in final_audits),
        "contexts_trimmed": sum(a.context_trimmed for a in final_audits),
        "quoted_reply_replacements": sum(a.quoted_reply_replacements for a in final_audits),
        "quoted_reply_removals": sum(a.quoted_reply_removals for a in final_audits),
        "embedded_reply_quotes_cleaned": sum(
            a.quoted_reply_replacements + a.quoted_reply_removals for a in final_audits
        ),
        "gateway_runtime_blocks_removed": sum(a.runtime_blocks_removed for a in final_audits),
        "reply_quotes_found": sum(a.reply_quotes_found for a in final_audits),
        "reply_quotes_gold_replaced": sum(a.quoted_reply_replacements for a in final_audits),
        "reply_quotes_removed_unmatched": sum(a.reply_quotes_unmatched for a in final_audits),
        "reply_quotes_ambiguous": sum(a.reply_quotes_ambiguous for a in final_audits),
        "remaining_contaminated_quotes": 0,
        "external_ids_sanitized": external_ids_sanitized,
        "reply_link_backfill": index.backfill,
        "records_dropped": all_dropped,
        "records_dropped_count": len(all_dropped),
        "trimmed_records": [
            {
                "id": item["record"]["id"],
                "reasons": item["audit"].trim_reasons,
            }
            for item in final_items if item["audit"].context_trimmed
        ],
    }
    validation = validate_clean_records(training_records, text_eval, index, multi_stats)
    validation["jsonl_parse_valid"] = False
    validation["text_eval_count_within_requested_range"] = (
        TEXT_EVAL_MINIMUM <= len(text_eval) <= TEXT_EVAL_MAXIMUM
    )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    eval_report_dir.parent.mkdir(parents=True, exist_ok=True)
    temp_export = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=output_dir.parent))
    temp_eval = Path(tempfile.mkdtemp(prefix=".eval-v2-", dir=eval_report_dir.parent))
    try:
        _write_jsonl(temp_export / "sft.jsonl", sft_records)
        _write_jsonl(temp_export / "multi_turn.jsonl", multi_records)
        shutil.copyfile(source_export_dir / "direct_language.jsonl", temp_export / "direct_language.jsonl")
        shutil.copyfile(source_export_dir / "preference_pairs.jsonl", temp_export / "preference_pairs.jsonl")
        _write_jsonl(temp_export / "text_sft_eval.jsonl", text_eval)
        (temp_export / "full_archive.json").write_text(
            json.dumps(index.archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (temp_export / "clean_context_report.json").write_text(
            json.dumps(clean_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (temp_export / "dedup_report.json").write_text(
            json.dumps(dedup_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        eval_files = {
            "text_sft_eval.jsonl": text_eval,
            "tool_eval.jsonl": categorized_eval["tool"],
            "vision_eval.jsonl": categorized_eval["vision"],
            "runtime_agent_eval.jsonl": categorized_eval["runtime_agent"],
        }
        for filename, rows in eval_files.items():
            _write_jsonl(temp_eval / filename, rows)
        scoring_schema = {
            "type": "manual_evaluation",
            "scale": {
                "0": "Poor",
                "1": "Partial",
                "2": "Good",
            },
            "dimensions": list(SCORING_DIMENSIONS),
            "automatic_llm_judge": False,
            "instructions": "Score each dimension manually from 0 to 2 and add a short note where needed.",
        }
        (temp_eval / "scoring_schema.json").write_text(
            json.dumps(scoring_schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        jsonl_paths = [
            temp_export / "sft.jsonl",
            temp_export / "multi_turn.jsonl",
            temp_export / "direct_language.jsonl",
            temp_export / "preference_pairs.jsonl",
            temp_export / "text_sft_eval.jsonl",
            *(temp_eval / filename for filename in eval_files),
        ]
        _validate_written_jsonl(jsonl_paths)
        validation["jsonl_parse_valid"] = True

        direct_count = len(_read_jsonl(temp_export / "direct_language.jsonl"))
        preference_count = len(_read_jsonl(temp_export / "preference_pairs.jsonl"))
        text_subcategories = Counter(record["evaluation_subcategory"] for record in text_eval)
        text_subcategory_shortfalls = {
            category: max(0, goal - text_subcategories.get(category, 0))
            for category, goal in TEXT_EVAL_CATEGORY_GOALS.items()
        }
        train_conversations = {
            str(record["conversation_id"]) for record in training_records if record.get("conversation_id")
        }
        text_eval_conversations = {
            str(record["conversation_id"]) for record in text_eval if record.get("conversation_id")
        }
        sha256 = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(temp_export.iterdir()) if path.name != "manifest.json"
        }
        manifest = {
            "version": version,
            "created_at": utc_now(),
            "source_export": str(source_export_dir),
            "source_version": source_manifest.get("version"),
            "database_modified": False,
            "reviewed_gold_responses_modified": False,
            "sft_training_record_count": len(training_records),
            "training_record_count": len(training_records) + direct_count + preference_count,
            "files": {
                "sft.jsonl": len(sft_records),
                "multi_turn.jsonl": len(multi_records),
                "direct_language.jsonl": direct_count,
                "preference_pairs.jsonl": preference_count,
                "text_sft_eval.jsonl": len(text_eval),
            },
            "preference_pairs_used_for_sft": False,
            "full_archive": {
                "mode": "read_only_snapshot_with_reply_link_overlay",
                "source": str(source_export_dir / "full_archive.json"),
                "source_database_modified": False,
                "reply_link_backfill": index.backfill,
            },
            "clean_context": {
                "enabled": True,
                "prior_assistant_gold_replacements": clean_report["prior_assistant_gold_replacements"],
                "contexts_trimmed": clean_report["contexts_trimmed"],
                "quoted_reply_replacements": clean_report["quoted_reply_replacements"],
                "quoted_reply_removals": clean_report["quoted_reply_removals"],
                "runtime_blocks_removed": clean_report["gateway_runtime_blocks_removed"],
                "reply_quotes_found": clean_report["reply_quotes_found"],
                "reply_quotes_gold_replaced": clean_report["reply_quotes_gold_replaced"],
                "reply_quotes_removed_unmatched": clean_report["reply_quotes_removed_unmatched"],
                "reply_quotes_ambiguous": clean_report["reply_quotes_ambiguous"],
                "remaining_contaminated_quotes": clean_report["remaining_contaminated_quotes"],
            },
            "external_ids_sanitized": external_ids_sanitized,
            "multi_turn_balancing": multi_stats,
            "multi_turn_cap_per_conversation": MULTI_TURN_CAP,
            "exact_duplicates_removed": dedup_report["exact_duplicates_removed"],
            "near_duplicate_threshold": 0.98,
            "near_duplicate_count": dedup_report["near_duplicate_count"],
            "evaluation_v2": {
                "text_sft_count": len(text_eval),
                "tool_eval_count": len(categorized_eval["tool"]),
                "vision_eval_count": len(categorized_eval["vision"]),
                "runtime_agent_eval_count": len(categorized_eval["runtime_agent"]),
                "text_sft_subcategory_counts": dict(text_subcategories),
                "available_text_subcategory_counts": dict(available_text_subcategories),
                "text_sft_subcategory_shortfalls": text_subcategory_shortfalls,
                "training_conversation_count": len(train_conversations),
                "text_eval_conversation_count": len(text_eval_conversations),
                "train_eval_conversation_overlap": len(train_conversations & text_eval_conversations),
                "scoring": "manual_0_1_2",
            },
            "validation": validation,
            "sha256": sha256,
        }
        (temp_export / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temp_eval, eval_report_dir)
        os.replace(temp_export, output_dir)
    except Exception:
        shutil.rmtree(temp_export, ignore_errors=True)
        shutil.rmtree(temp_eval, ignore_errors=True)
        raise
    return {
        "path": str(output_dir),
        "eval_report_path": str(eval_report_dir),
        "manifest": manifest,
        "clean_context_report": clean_report,
        "dedup_report": dedup_report,
    }
