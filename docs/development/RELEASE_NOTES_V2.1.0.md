# Najdi Lab V2.1.0 — development candidate

**Status:** development candidate on `update-project`, Draft PR #23. V2.1.0 is the owner-approved product version identifier; it is **not** a public release, a production approval or a merge to `main`.

**Why V2.1.0 (SemVer minor):** a new user-facing capability — the unified chat composer with one runtime-preparation path — with no incompatible API or data change. Existing conversations, reviews, datasets, migrations, downloaded models and the managed runtime keep working unchanged. Everything in [V2.0.0](RELEASE_NOTES_V2.0.0.md) is included.

| Area | Change | Record |
|---|---|---|
| Chat composer | Model and context selectors inside the message box; icon Send that becomes Stop; Collect state visible; quiet context meter | [Chat composer](CHAT_COMPOSER.md) |
| New chat | Opens an empty chat at once; the conversation is created by the first send; no configuration dialog | [Chat composer §2](CHAT_COMPOSER.md#2-state-and-invariants) |
| Runtime preparation | One server path (`/api/v1/chat/prepare`): reuse, start, restart at another context, LM Studio select, Ollama load — each explained first and approved once | [Chat composer §3](CHAT_COMPOSER.md#3-one-preparation-path) |
| Chat information | Former Chat settings, now read only | [Chat composer §1](CHAT_COMPOSER.md#1-what-the-user-sees) |
| Model library | *Use in Chat* replaces the library's own load flow; Advisor settings marked as simulation | [Chat composer §1](CHAT_COMPOSER.md#1-what-the-user-sees) |
| Layout | Copyright moved from every page footer to the sidebar | [Chat composer §1](CHAT_COMPOSER.md#1-what-the-user-sees) |

## Open acceptance gates

- GitHub Actions on the final commit (not triggered, as instructed).
- Owner review and approval of PR #23.

## Rollback

`git revert` the V2.1.0 commit; no migration was added. See [Chat composer §7](CHAT_COMPOSER.md#7-rollback).
