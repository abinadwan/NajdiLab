# NajdiLab Tool Runtime Contract v1

The active capability list is the intersection of the versioned registry and tools reported available by the current runtime/session. A registered but unavailable tool is never model-visible. The canonical registry fingerprint is SHA-256 over sorted, compact UTF-8 JSON excluding the derived `fingerprint` field.

## Native Ministral serialization

- Tool definitions: `[AVAILABLE_TOOLS]` + canonical tool-schema JSON + `[/AVAILABLE_TOOLS]`.
- Assistant call: `[TOOL_CALLS]` + tool name + `[ARGS]` + canonical arguments JSON.
- Tool result: `[TOOL_RESULTS]` + canonical result JSON + `[/TOOL_RESULTS]`.
- Assistant messages end with the tokenizer EOS. Multiple calls are serialized in declared order and correlated by unique call IDs in the structured record/controller trace.

Natural-language placeholders or execution claims are not calls or results. Malformed calls never execute.

## Controller authority

The event lifecycle is `TOOL_CALL_REQUESTED`, `TOOL_CALL_VALIDATED`, `TOOL_EXECUTION_STARTED`, then exactly one terminal `TOOL_RESULT`, `TOOL_ERROR`, or `TOOL_EXECUTION_DENIED`. Only an authoritative controller-generated `TOOL_RESULT` proves execution. Every trace binds normalized arguments, execution ID, timestamp, runtime target, and capability-registry fingerprint.

Read-only, mutating, approval-required, unavailable, denied, and error behavior remain distinct. The controller enforces approval and availability; model prose cannot override either.

## Native Tool-Use training records

`native_tool_use.jsonl` records use `schema_version: 1`, `record_type: native_tool_use`, a registry version/fingerprint binding, the available tool names, and ordered structured messages. Tool messages carry `outcome: result|error|denied` (with `result` as the compatibility default) and validate against the corresponding result/error schema. Validation rejects unknown tools, schema-invalid arguments/results/errors, invalid ordering, duplicate/unmatched calls, orphan or non-authoritative results, and missing final responses.

Loss is applied to assistant tool-call generation and the final assistant response. System definitions, user text, and authoritative external tool-result contents use `IGNORE_INDEX`. This teaches requesting an action and consuming its result without teaching the model to fabricate external output.

## Benchmark and generation

Tool evaluation must inspect controller event traces. A textual claim without an authoritative result is a failure. Future paired model comparisons must use identical generation settings. The proposed development candidate is deterministic decoding, 256 maximum new tokens, repetition penalty 1.05, no forced repeated-ngram ban, tokenizer EOS, validated tool-call stopping, and a 60-second controller timeout. It remains a candidate until development evaluation confirms language and behavior quality.
