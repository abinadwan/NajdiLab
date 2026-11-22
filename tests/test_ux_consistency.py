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
    steps = dashboard.split('<ol class="workflow-steps">', 1)[1].split('</ol>', 1)[0]
    assert re.findall(r'<strong>(.*?)</strong>', steps) == ['Choose data', 'Check and prepare', 'Approve Gold', 'Export']
    assert not re.search(r'data-go="(?:dataset-health|balancer|exports)"', dashboard)


def test_official_workspace_is_guided_and_legacy_interface_is_not_loaded():
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    source = (ROOT / 'static/app.js').read_text(encoding='utf-8')
    assert 'id="guided-wizard"' in html
    assert 'id="workspace-mode"' not in html
    assert 'id="advanced-mode"' not in html
    assert 'id="advanced-workspace"' not in html
    assert 'data-advanced-view=' not in html
    assert 'src="/advanced-workspace.js"' not in html
    assert 'href="/advanced-workspace.css"' not in html
    for view in ('dataset', 'dataset-health', 'balancer', 'dataset-versions', 'eval-sets', 'exports', 'manual-data'):
        assert f'id="view-{view}"' not in html
    assert 'function bindLegacyEvents()' in source
    assert "import('/advanced-workspace.js')" in source


def test_historical_mode_preference_is_ignored_without_writing_workflow_storage():
    run_browser_script(r"""
context.document.documentElement = {classList:{remove(name){context.removed=name;}}};
const values = new Map([['najdilab.advancedMode','1'],['najdilab.workflow.v1','synthetic-existing-draft']]);
context.localStorage = {getItem:key=>values.get(key), setItem(){throw Error('unexpected storage mutation');}, removeItem(){throw Error('unexpected storage deletion');}};
vm.runInContext('initGuidedWorkspace()', context);
assert.equal(context.removed, 'advanced-mode');
assert.equal(values.get('najdilab.workflow.v1'), 'synthetic-existing-draft');
assert.equal(values.get('najdilab.advancedMode'), '1');
context.localStorage.getItem = () => {throw Error('storage blocked');};
vm.runInContext('initGuidedWorkspace()', context);
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
