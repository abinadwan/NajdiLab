from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_theme_bootstrap_precedes_styles_and_main_app():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert html.index('/theme-init.js') < html.index('/styles.css')
    assert html.index('/theme.js') < html.index('/app.js')


def test_theme_modes_persistence_and_system_listener_are_present():
    init = (ROOT / "static" / "theme-init.js").read_text(encoding="utf-8")
    runtime = (ROOT / "static" / "theme.js").read_text(encoding="utf-8")
    for mode in ("light", "dark", "system"):
        assert mode in init and mode in runtime
    assert "localStorage" in init and "localStorage" in runtime
    assert "prefers-color-scheme: dark" in init and "prefers-color-scheme: dark" in runtime
    assert "addEventListener?.('change'" in runtime


def test_theme_uses_tokens_and_distinguishes_status_classes():
    css = (ROOT / "static" / "theme.css").read_text(encoding="utf-8")
    assert ':root[data-theme="dark"]' in css
    assert "--status-ready-bg" in css
    assert "--status-warning-bg" in css
    assert "--status-blocked-bg" in css
    assert ".gate-badge.blocked" in css


def test_dashboard_uses_derived_platform_status():
    app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/v1/platform/status" in app
    assert "platform.phase4" in app
