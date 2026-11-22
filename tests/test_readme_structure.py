"""RESTORE-README guard: the owner-approved README design must survive refactors.

The approved design (from `feat/native-conversation-capture:README.md`) was lost
once when a cleanup shortened the README. These checks fail if a future change
removes its core elements. They check structure, not wording, so content can
still be updated. Changing this list needs the owner's approval.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")

# Sections of the approved design, in order. New sections may be added between them.
APPROVED_SECTIONS = [
    "The idea and the problem",
    "Key capabilities and intended users",
    "Visual introduction",
    "Contents",
    "Current status",
    "Interface preview",
    "Technology stack and versions",
    "System requirements",
    "Downloads and prerequisites",
    "Installation and quick start",
    "System architecture",
    "Dataset and model workflow",
    "Database and integrity",
    "Optional training infrastructure",
    "Project structure",
    "Configuration",
    "Security and limitations",
    "Testing and quality",
    "Development progress and roadmap",
    "Developer guide and documentation",
    "Licensing and attribution",
    "Maintainer handover",
]
REQUIRED_BADGES = ["Python", "SQLite", "JavaScript", "HTML5", "CSS3", "Architecture", "Development", "License"]


def headings(level: int) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(rf"^{'#' * level} (.+)$", README, re.M)]


def section(title: str) -> str:
    marker = f"\n## {title}\n"
    assert marker in README, f"README section missing: {title}"
    return README.split(marker, 1)[1].split("\n## ", 1)[0]


def anchor(text: str) -> str:
    return re.sub(r"[^\w\- ]", "", text.lower()).strip().replace(" ", "-")


def test_title_and_tagline():
    # The owner's workflow banner (an image from assets/ with alt text) may sit above the title; nothing else may.
    banner = re.match(r'<p align="center">\s*<img src="assets/[\w.-]+" alt="[^"]+"[^>]*>\s*</p>\s*', README)
    assert README[banner.end() if banner else 0:].startswith("# NajdiLab\n")
    assert "local-first platform" in README and "Arabic" in README


def test_approved_sections_exist_in_order():
    found = headings(2)
    missing = [s for s in APPROVED_SECTIONS if s not in found]
    assert not missing, f"approved README sections removed: {missing}"
    positions = [found.index(s) for s in APPROVED_SECTIONS]
    assert positions == sorted(positions), "approved sections must keep their order"


def test_colored_technology_badges_are_kept():
    badges = re.findall(r'<img alt="[^"]+" src="https://img\.shields\.io/badge/([^"]+)"', README)
    assert len(badges) >= 10, f"expected the badge rows, found {len(badges)}"
    labels = [unquote(b.split("-")[0]) for b in badges]
    for name in REQUIRED_BADGES:
        assert any(label.startswith(name) for label in labels) or (name == "License" and '<img alt="NajdiLab License: Apache-2.0" src="https://img.shields.io/github/license/abinadwan/NajdiLab?style=for-the-badge">' in README), f"badge missing: {name}"
    assert all("style=for-the-badge" in b for b in badges), "badges keep the approved style"


def test_contents_links_resolve_to_headings():
    toc = section("Contents")
    targets = re.findall(r"\]\(#([^)]+)\)", toc)
    assert len(targets) >= len(APPROVED_SECTIONS) - 4
    available = {anchor(h) for h in headings(2) + headings(3)}
    assert not [t for t in targets if t not in available], "table of contents points at missing headings"


def test_screenshots_and_architecture_images_exist_and_are_synthetic():
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", README) + re.findall(r'<img alt="[^"]*" src="(docs/[^"]+)"', README)
    local = [i for i in images if not i.startswith("http")]
    assert any("architecture" in i and i.endswith(".svg") for i in local), "architecture diagram missing"
    assert sum("screenshots/" in i for i in local) >= 3, "interface screenshots missing"
    for path in local:
        assert (ROOT / unquote(path)).is_file(), f"README image missing: {path}"
    assert "synthetic" in section("Visual introduction").lower()


def test_diagrams_install_commands_and_structure_are_present():
    assert README.count("```mermaid") >= 2, "architecture and workflow diagrams"
    assert "```powershell" in README and "```bash" in README, "Windows and Linux quick start"
    assert "```text\nNajdiLab/" in README, "project structure tree"
    install = section("Installation and quick start")
    assert "run.ps1" in install and "run.sh" in install


def test_status_separates_done_in_development_and_planned():
    status = section("Feature status")
    for label in ("Available in `V2.3.0`", "In development", "Planned"):
        assert label in status


def test_licensing_and_attribution_links():
    licensing = section("Licensing and attribution")
    assert "docs/THIRD_PARTY_ATTRIBUTION.md" in licensing
    assert "[Apache License, Version 2.0](LICENSE)" in licensing
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").find("Apache License") >= 0
    assert "docs/public-release-decision.md" in licensing


def test_badge_urls_are_well_formed_shields_badges():
    """shields.io renders `badge/<label>-<message>-<hex color>`; a malformed URL shows
    a broken image on GitHub. Checked offline (the renderer is not contacted)."""
    rows = re.findall(r'<p align="center">\s*((?:<a [^>]+><img [^>]+></a>\s*)+)</p>', README)
    assert len(rows) == 4, f"four badge rows in the approved design, found {len(rows)}"
    for url in re.findall(r'src="(https://img\.shields\.io/badge/[^"]+)"', README):
        path, _, query = url.partition('?')
        body = unquote(path.rsplit('/badge/', 1)[1])
        parts = re.split(r'(?<!-)-(?!-)', body)
        assert len(parts) == 3 and re.fullmatch(r'[0-9A-Fa-f]{6}', parts[2]), f"malformed badge: {url}"
        assert 'style=for-the-badge' in query.replace('&amp;', '&'), url


def test_badge_links_and_all_relative_links_resolve():
    targets = re.findall(r'<a href="([^"#]+)', README) + re.findall(r'\]\((?!https?:|#)([^)#\s]+)', README)
    missing = [t for t in targets if not t.startswith('http') and not (ROOT / unquote(t)).exists()]
    assert not missing, f"README links to missing files: {missing}"
