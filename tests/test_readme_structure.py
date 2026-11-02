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
    assert README.startswith("# NajdiLab\n")
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
        assert any(label.startswith(name) for label in labels), f"badge missing: {name}"
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
    for label in ("Available on `main`", "In development", "Planned"):
        assert label in status


def test_licensing_and_attribution_links():
    licensing = section("Licensing and attribution")
    assert "docs/THIRD_PARTY_ATTRIBUTION.md" in licensing
    assert "no active source license" in licensing.lower()
