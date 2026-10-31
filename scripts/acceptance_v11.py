"""Retired live Hermes utility; use disposable integration tests instead.

Hermes v0.22.5 does not enforce the assumed fields allowlist or enabled:false
switch. Database-only redaction cannot prove wire privacy. No external imports,
collector requests or database writes are made by this utility.
"""


def main():
    raise SystemExit(
        "BLOCKED: live Hermes acceptance is disabled until sender-side privacy "
        "and external disconnect are verified. See docs/hermes-integration.md. "
        "Run python -m pytest -q tests/test_integrations.py tests/test_integrations_http.py instead."
    )


if __name__ == "__main__":
    main()
