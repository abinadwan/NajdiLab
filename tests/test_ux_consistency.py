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


def test_specialist_tools_have_an_independent_workspace_and_a_visible_mode_toggle():
    html = (ROOT / 'static/index.html').read_text(encoding='utf-8')
    versions = html.split('id="view-my-versions"', 1)[1].split('id="view-dataset"', 1)[0]
    settings = html.split('id="view-settings"', 1)[1]
    workspace = html.split('id="advanced-workspace"', 1)[1].split('id="guided-wizard"', 1)[0]
    wizard = html.split('id="guided-wizard"', 1)[1].split('id="view-my-versions"', 1)[0]
    topbar = html.split('class="top-actions"', 1)[1].split('</header>', 1)[0]
    assert 'data-advanced-view' not in versions
    assert 'data-advanced-view' not in wizard
    assert 'id="workspace-mode"' in topbar
    assert 'id="advanced-mode"' in settings and 'data-advanced-only' in settings
    assert 'data-go="prepare"' in settings
    for view in ('manual-data', 'dataset-health', 'balancer', 'dataset-versions', 'eval-sets', 'exports'):
        assert f'data-advanced-view="{view}"' in workspace
    assert re.findall(r'id="prepare-panel-(\d)"', wizard) == ['1', '2', '3', '4']
    css = (ROOT / 'static/workspace.css').read_text(encoding='utf-8')
    assert '#advanced-workspace{display:none}' in css
    assert 'html.advanced-mode #advanced-workspace{display:block}' in css
    assert 'html.advanced-mode #guided-wizard{display:none}' in css


def test_advanced_mode_defaults_off_and_survives_storage_failure():
    run_browser_script(r"""
context.document.documentElement = {classList:{toggle(name, enabled){context.enabled=enabled;}}};
context.document.getElementById = id => element('#'+id);
context.navigations = [];
vm.runInContext('switchView = view => navigations.push(view)', context);
let savedDrafts = 0;
context.window.NajdiPrepare = {save(){savedDrafts++;}};
const writes = [];
context.localStorage = {getItem(){return null;}, setItem(key,value){writes.push([key,value]);throw Error('blocked');}};
vm.runInContext('initAdvancedMode()', context);
assert.equal(element('#advanced-mode').checked, false);
assert.equal(element('#workspace-mode').checked, false);
assert.equal(context.enabled, false);
assert.deepEqual(context.navigations, []);
element('#workspace-mode').checked = true;
element('#workspace-mode').onchange();
assert.equal(context.enabled, true);
assert.equal(element('#advanced-mode').checked, true);
assert.deepEqual(writes, [['najdilab.advancedMode','1']]);
assert.deepEqual(context.navigations, ['prepare']);
assert.equal(savedDrafts, 1);
element('#advanced-mode').checked = false;
element('#advanced-mode').onchange();
assert.equal(context.enabled, false);
assert.equal(element('#workspace-mode').checked, false);
assert.deepEqual(writes[1], ['najdilab.advancedMode','0']);
assert.deepEqual(context.navigations, ['prepare','prepare']);
assert.equal(savedDrafts, 2);

const storage = new Map([['najdilab.advancedMode','1']]);
context.localStorage = {getItem:key=>storage.get(key), setItem:(key,value)=>storage.set(key,value)};
vm.runInContext('initAdvancedMode()', context);
assert.equal(element('#advanced-mode').checked, true);
assert.equal(element('#workspace-mode').checked, true);
element('#advanced-mode').checked = false;
element('#advanced-mode').onchange();
assert.equal(storage.get('najdilab.advancedMode'), '0');
vm.runInContext('initAdvancedMode()', context);
assert.equal(context.enabled, false);
assert.equal(element('#workspace-mode').checked, false);
context.localStorage.getItem = () => 'false';
vm.runInContext('initAdvancedMode()', context);
assert.equal(context.enabled, false);
context.localStorage.getItem = () => {throw Error('blocked');};
vm.runInContext('initAdvancedMode()', context);
assert.equal(context.enabled, false);
assert.equal(element('#advanced-mode').checked, false);
assert.equal(element('#workspace-mode').checked, false);
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
