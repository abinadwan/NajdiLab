"""UX consistency contracts without changing dataset or route semantics."""
import re
from pathlib import Path

from tests.test_english_localization import run_browser_script

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_uses_prepare_journey_and_independent_review():
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    dashboard = html.split('id="view-dashboard"', 1)[1].split('id="view-review-queue"', 1)[0]
    assert 'data-go="prepare"' in dashboard
    assert 'data-go="my-versions"' in dashboard
    assert 'data-go="review-queue"' in dashboard
    assert all(label in dashboard for label in ('Choose data', 'Check and prepare', 'Create Gold and export'))
    assert not re.search(r'data-go="(?:dataset-health|balancer|exports)"', dashboard)


def test_specialist_tools_live_in_settings_only():
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    versions = html.split('id="view-my-versions"', 1)[1].split('id="view-dataset"', 1)[0]
    settings = html.split('id="view-settings"', 1)[1]
    assert 'data-advanced-view' not in versions
    assert 'id="advanced-mode"' in settings and 'data-advanced-only' in settings
    for view in ('dataset', 'dataset-health', 'balancer', 'dataset-versions', 'eval-sets', 'exports'):
        assert f'data-advanced-view="{view}"' in settings


def test_advanced_mode_defaults_off_and_survives_storage_failure():
    run_browser_script(r"""
context.document.documentElement = {classList:{toggle(name, enabled){context.enabled=enabled;}}};
context.localStorage = {getItem(){return null;}, setItem(){throw Error('blocked');}};
vm.runInContext('initAdvancedMode()', context);
assert.equal(element('#advanced-mode').checked, false);
assert.equal(context.enabled, false);
element('#advanced-mode').checked = true;
element('#advanced-mode').onchange();
assert.equal(context.enabled, true);
context.localStorage.getItem = () => '1';
vm.runInContext('initAdvancedMode()', context);
assert.equal(element('#advanced-mode').checked, true);
context.localStorage.getItem = () => 'false';
vm.runInContext('initAdvancedMode()', context);
assert.equal(context.enabled, false);
""")


def test_health_interface_descriptions_are_localizable():
    run_browser_script(r"""
const html = vm.runInContext("healthCard('Structural validity','VALID',0,'Structure, targets, loss masks and diagnostics are valid.','training')", context);
assert.ok(!html.includes('dir="auto"'), 'interface explanations must reach the localizer');
""")


def test_dashboard_stats_open_normal_journey_without_readiness_claims():
    run_browser_script(r"""
vm.runInContext(`api = async path => path.endsWith('analytics')
    ? {summary:{total_conversations:2,pending_reviews:1}}
    : path.endsWith('dataset-versions') ? {items:[]} : {manual_sft:[{}]};`, context);
vm.runInContext('loadDashboard()', context).then(() => {
    const html = element('#dashboard-stats').innerHTML;
    assert.ok(html.includes('data-go="prepare"'));
    assert.ok(html.includes('data-go="my-versions"'));
    assert.ok(!html.includes('Eligible for build'));
    assert.ok(element('#dashboard-readiness').innerHTML.includes('build readiness has not been checked here'));
}).catch(error => {console.error(error);process.exitCode=1;});
""")


def test_dashboard_counts_all_frozen_versions_from_the_shared_catalog():
    run_browser_script(r"""
vm.runInContext(`api = async path => path.endsWith('analytics')
    ? {summary:{total_conversations:0,pending_reviews:0}}
    : path.endsWith('dataset-versions') ? {items:[
        {version:'gold-v009',state:'Frozen',counts:{'sft.jsonl':3,'multi_turn.jsonl':2}},
        {version:'gold-v010-draft',state:'Draft',counts:{'sft.jsonl':8}}
      ]} : path.endsWith('exports') ? {items:[]} : {};`, context);
vm.runInContext('loadDashboard()', context).then(() => {
    assert.ok(element('#dashboard-stats').innerHTML.includes('Gold versions</span><strong>1</strong>'));
    const recent=element('#dashboard-exports').innerHTML;
    assert.ok(recent.includes('gold-v009'));
    assert.ok(recent.includes('5 records'));
    assert.ok(!recent.includes('gold-v010-draft'));
}).catch(error => {console.error(error);process.exitCode=1;});
""")
