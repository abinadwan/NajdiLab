# NajdiLab Chat collection and training context audit

Date: 2026-11-02. Scope: source review and synthetic temporary databases only.
No installed runtime, private conversation, production database, training run,
historical release rewrite, or migration was used for this audit.

## Traced invariant

`ChatWorkspace.send` sends every completed raw user/assistant pair plus the new
user message to the selected model. Collection never changes this inference
history. It stores only a completed pair whose collection consent epoch is still
the same when the response commits. Turning collection OFF then ON, restarting,
or revoking consent during an in-flight reply cannot retrospectively copy older
roles into the review database. The response, raw pair, review pair and request
receipt commit atomically.

`ingest_turn` appends the pair to the conversation for this collection epoch,
links the assistant to its user message and creates a PENDING review with
training eligibility OFF. `_message_context` returns this consented conversation
prefix through the target assistant. Human approval or correction and training
eligibility remain distinct explicit review choices.

For a complete consented conversation, `_review_training_records` retains its
actual prefix and substitutes reviewed Gold text only at the target assistant.
`_annotate_sft_record` emits `target_message_index`,
`train_on_last_assistant_only=true` and `[0, ..., 0, 1]` as
`message_loss_mask`. The first pair goes into `sft.jsonl`; later targets with
earlier context go into `multi_turn.jsonl`. Previous assistant mistakes remain
masked prompt context, including when the new user refers to them.

`create_handoff` reads both files from an immutable validated version, verifies
hashes, roles, eligibility, masks and leakage, and emits conversational
`prompt=messages[:-1]`, `completion=[messages[-1]]`. Its manifest requires
completion-only loss and rejects truncation/packing by default. It does not run
Unsloth, select a model, or train anything.

## Gaps reproduced and changes

Nine initial failing synthetic tests showed that incomplete collected context
had only a title warning, could be promoted/exported, and could be rewritten or
trimmed by the legacy clean exporter. Chat clean reconstruction also accepted a
privacy-flagged or excluded earlier pair.

New capture metadata records `context_complete` alongside the existing
`context_scope=continuous_consented_segment_only`. A segment is complete only
when every prior raw turn was captured in this exact consent epoch. A title
warning now reflects that invariant, including all later turns in an incomplete
segment. The raw transcript remains unchanged.

Pending review and individual review responses expose `context_complete`,
`context_scope` and `context_warning`. An incomplete segment remains available
for human review, but training or evaluation eligibility is rejected. Export
readiness and its locked publication recheck block legacy inconsistent eligible
rows with `EXPORT_INCOMPLETE_CONTEXT`. Export records and handoff provenance
carry the context fields; handoff validation rejects missing/false/invalid
completeness for an explicitly collected segment, including historical exports
identified by their `najdilab-chat:` conversation namespace even when the old
export omitted context fields.

The clean exporter now treats collected Chat as an exact transcript: it keeps
the original consented prefix and changes only the reviewed target. It blocks
the whole Chat record when the prefix is incomplete, privacy-flagged, excluded,
ignored, deleted, or marked evaluation-only for a training view. Classification
cannot route a blocked segment around that check. Validation compares the Chat
prefix to its source archive and verifies its final-only mask. Other sources
retain their existing cleaning behavior.

The `no_known_bad_corrected_assistant_in_context` diagnostic reports the actual
value when an earlier Chat mistake is preserved; the separate
`collected_chat_prefix_preserved_and_masked` check describes the required Chat
behavior. Preserving a mistaken prompt response does not approve it as a target.

## Schema and historical-data decision

The existing conversation/message metadata, review decisions and message masks
already represent this workflow. No schema change or migration is necessary.
Chat records without explicit completeness evidence remain reviewable but are
conservatively ineligible. The audit does not infer permission from older raw
history, fetch pre-consent messages, or update historical records. To collect a
complete training context, start a new chat and enable collection before the
first turn. A truncated segment is never silently treated as standalone.

No single-turn/multi-turn ratio was introduced. Existing conversation caps,
deduplication and conversation-isolated evaluation splitting remain in place;
there is no forced 60/40 quota.

## Verification and limits

Initial regression proof: 9 failures before the fixes in
`tests/test_chat_dataset_context.py`.

Final synthetic regression command:

```text
python -m pytest tests/test_chat_dataset_context.py tests/test_chat_workspace.py tests/test_unsloth_export.py tests/test_clean_export.py tests/test_najdilab.py tests/test_review_integrity.py tests/test_review_restriction_integrity.py -q -k "not http"
156 passed, 6 deselected in 5.93s
```

Coverage includes raw Chat with collection enabled before the first turn;
PENDING export rejection; explicit human decisions; simultaneous single-turn
and multi-turn export; unchanged whitespace and earlier mistaken replies;
exact loss masks; completion-only handoff; pre-consent history absence;
incomplete/unknown context promotion rejection; legacy export backstop; private
prefix rejection; malformed context provenance at handoff; and historical Chat
handoff without completeness provenance (also reproduced as a failing test).

An earlier broader run reported 149 passes and six existing HTTP-test failures
because Windows denied loopback sockets with WinError 10013. Those tests were
not retried with elevated/network permissions; they are the six deselections
above. No external model/provider was contacted. Real tokenizer compatibility,
hardware inference and a live external trainer remain untested by this audit.
