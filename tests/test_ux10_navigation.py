"""UX-10: the 16 destinations are grouped by workflow without removing any of them (Model library added with Hugging Face Direct)."""
from __future__ import annotations

import html.parser
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = [
    ("Overview", ["dashboard"]),
    ("Chat", ["chat", "models"]),
    ("Review", ["review-queue", "conversations", "reviewed"]),
    # Data management is three destinations (V2.2.0 UX): the specialist pages below stay routable.
    ("Data", ["add-data", "prepare", "my-versions"]),
    ("Administration", ["analytics", "settings"]),
]
ADVANCED = ["manual-data", "dataset", "dataset-health", "balancer", "dataset-versions", "eval-sets", "exports"]

class Nav(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.groups: list[dict] = []
        self.ids: dict[str, str] = {}
        self.capture: str | None = None
        self.item: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "nav" and a.get("id") == "main-nav":
            self.depth = 1
            self.nav_label = a.get("aria-label")
            return
        if not self.depth:
            return
        if tag == "div" and "nav-section" in a.get("class", ""):
            self.groups.append({"role": a.get("role"), "labelledby": a.get("aria-labelledby"), "items": []})
        elif tag == "span" and a.get("class") == "nav-group":
            self.capture = a.get("id")
            self.ids[self.capture] = ""
        elif tag == "button" and "nav-item" in a.get("class", ""):
            self.item = {"view": a.get("data-view"), "title": a.get("title"), "icon_hidden": None, "label": ""}
            self.groups[-1]["items"].append(self.item)
        elif tag == "span" and a.get("class") == "nav-icon" and self.item is not None:
            self.item["icon_hidden"] = a.get("aria-hidden")
        elif tag == "span" and a.get("class") == "nav-label" and self.item is not None:
            self.capture = "label"

    def handle_endtag(self, tag):
        if tag == "nav" and self.depth:
            self.depth = 0
        if tag == "span":
            self.capture = None
        if tag == "button":
            self.item = None

    def handle_data(self, data):
        if self.capture == "label" and self.item is not None:
            self.item["label"] += data
        elif self.capture in self.ids:
            self.ids[self.capture] += data


def _nav() -> Nav:
    parser = Nav()
    parser.feed((ROOT / "static" / "index.html").read_text(encoding="utf-8"))
    return parser


def test_every_destination_appears_once_in_workflow_order():
    nav = _nav()
    groups = [(nav.ids[g["labelledby"]].strip(), [i["view"] for i in g["items"]]) for g in nav.groups]
    assert groups == EXPECTED
    views = [v for _, vs in groups for v in vs]
    assert len(views) == 11 == len(set(views))


def test_every_destination_is_still_routable():
    source = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    titles = source[source.index("const titles = {"):source.index("};", source.index("const titles = {"))]
    for _, views in [*EXPECTED, ("Advanced", ADVANCED)]:
        for view in views:
            assert re.search(rf"(^|\s|')({re.escape(view)})'?:\s*\[", titles, re.M), view


def test_groups_and_items_are_accessible():
    nav = _nav()
    assert nav.nav_label == "Main navigation"
    for group in nav.groups:
        assert group["role"] == "group" and nav.ids.get(group["labelledby"], "").strip()
        for item in group["items"]:
            assert item["icon_hidden"] == "true", item["view"]
            assert item["label"].strip(), item["view"]
            assert item["title"] == item["label"].strip(), "collapsed sidebar keeps a tooltip and a name"


def test_sidebar_and_navigation_landmarks_have_distinct_names():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert '<aside class="sidebar" aria-label="Application sidebar">' in html
    assert html.count('aria-label="Main navigation"') == 1


def test_collapsed_labels_are_visually_hidden_not_removed():
    css = (ROOT / "static" / "theme.css").read_text(encoding="utf-8")
    rule = re.search(r"\.sidebar-collapsed \.nav-item>\.nav-label\{([^}]*)\}", css)
    assert rule and "display:block" in rule.group(1) and "clip" in rule.group(1)
