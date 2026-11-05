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


def test_dashboard_describes_dataset_scope_without_training_status_probes():
    app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert "/api/v1/platform/status" not in app
    assert "Privacy, eligibility and split checks run in Prepare data" in app
    assert "build readiness has not been checked here" in app
    assert "Training runs externally in Unsloth" not in app


def test_manual_modal_color_pairs_meet_text_contrast_in_both_themes():
    """Resolve component colors against real theme tokens, including inherited ink."""
    import re

    theme = (ROOT / "static/theme.css").read_text(encoding="utf-8")
    styles = (ROOT / "static/styles.css").read_text(encoding="utf-8")
    manual = (ROOT / "static/manual-data.css").read_text(encoding="utf-8")

    def declarations(source, selector):
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
        result = {}
        for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", source):
            if selector in [item.strip() for item in selectors.split(",")]:
                result.update(item.strip().split(":", 1) for item in body.split(";") if ":" in item)
        return result

    def luminance(color):
        value = color.lstrip("#")
        if len(value) == 3:
            value = "".join(ch * 2 for ch in value)
        channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in channels]
        return sum(x * weight for x, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    selectors = (
        ".detail-grid>div", ".manual-chat", ".full-text", ".dpo-detail section",
        ".icon-close", ".danger-button", ".status-pill.ok", ".status-pill.neutral",
        ".status-pill.archived", ".status-pill.danger", ".status-pill.exported",
        ".export-history", ".readonly-banner", ".row-actions button",
        ".manual-dialog", ".dialog-tabs", ".dialog-tabs button", ".dialog-tabs button.active",
    )
    for mode in ("light", "dark"):
        tokens = declarations(styles, ":root") | declarations(theme, ":root")
        if mode == "dark":
            tokens.update(declarations(theme, ':root[data-theme="dark"]'))

        def resolve(value):
            while value.startswith("var("):
                value = tokens[value[4:-1]]
            return value

        for selector in selectors:
            props = declarations(manual, selector)
            foreground = resolve(props.get("color", "var(--ink)"))
            background = resolve(props["background"])
            light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
            contrast = (light + 0.05) / (dark + 0.05)
            assert contrast >= 4.5, f"{mode} {selector}: {foreground} on {background} has contrast {contrast:.2f}"

        # Metadata labels sit on the card surface; they must also remain readable.
        foreground = luminance(resolve(declarations(manual, ".detail-grid dt")["color"]))
        background = luminance(resolve(declarations(manual, ".detail-grid>div")["background"]))
        light, dark = sorted((foreground, background), reverse=True)
        assert (light + 0.05) / (dark + 0.05) >= 4.5
