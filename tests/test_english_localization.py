from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_english_ltr_document_shell_and_localization_api():
    for name in ("index.html", "phase38-review.html"):
        html = (ROOT / "static" / name).read_text(encoding="utf-8")
        assert '<html lang="en" dir="ltr">' in html
    source = (ROOT / "static/localization.js").read_text(encoding="utf-8")
    assert "global.NajdiI18n" in source
    assert "locale:'en-US'" in source
    assert "direction:'ltr'" in source
    assert "READY: 'Ready'" in source


def test_english_chrome_retains_bidirectional_content_isolation():
    html = (ROOT / "static/index.html").read_text(encoding="utf-8")
    source = (ROOT / "static/app.js").read_text(encoding="utf-8")
    css = (ROOT / "static/rtl-overhaul.css").read_text(encoding="utf-8")
    assert 'dir="auto"' in html
    assert '<p dir="auto">${esc(m.content' in source
    assert 'html{direction:ltr}' in css
    assert 'inset-inline-start:0' in css
    assert 'transform:translateX(-105%)' in css
    assert 'unicode-bidi:isolate' in css


def test_mutations_obtain_session_token_and_merge_security_headers():
    source = (ROOT / "static/app.js").read_text(encoding="utf-8")
    assert "'/api/v1/session'" in source
    assert "X-NajdiLab-CSRF" in source
    assert "csrf_token" in source
    assert "method === 'GET'" in source


def test_chrome_has_no_arabic_literals_outside_api_decision_values():
    source = (ROOT / "static/app.js").read_text(encoding="utf-8")
    for decision in ("\u0627\u0639\u062a\u0645\u0627\u062f \u0627\u0644\u062a\u0639\u062f\u064a\u0644", "\u064a\u062d\u062a\u0627\u062c \u062a\u0639\u062f\u064a\u0644 \u0625\u0636\u0627\u0641\u064a", "\u0631\u0641\u0636"):
        source = source.replace('data-phase39-decision="' + decision + '"', '')
    assert not re.search(r"[\u0600-\u06ff]", source)
    for name in ("index.html", "localization.js", "theme.js", "phase38-review.html"):
        assert not re.search(r"[\u0600-\u06ff]", (ROOT / "static" / name).read_text(encoding="utf-8"))


def run_browser_script(script):
    import shutil
    import subprocess
    import pytest
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for browser JavaScript behavior tests")
    bootstrap = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const elements = new Map();
const element = selector => {
    if (!elements.has(selector)) elements.set(selector, {checked: false, innerHTML: '', textContent: '', className: '',style:{},classList:{toggle(){},add(){},remove(){}}});
    return elements.get(selector);
};
const context = {console, Intl, Date, URLSearchParams, setTimeout: () => 0, clearTimeout: () => {},
    document: {querySelector: element, querySelectorAll: () => [], addEventListener: () => {}},
    window: {}, location: {search: '', pathname: '/'}, assert, element};
vm.createContext(context);
vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), context);
"""
    result = subprocess.run([node, "-e", bootstrap + script], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_pending_review_does_not_display_training_eligibility_before_human_choice():
    run_browser_script(r"""
vm.runInContext(`state.queue=[{conversation_title:'Synthetic pending',training_eligible:0,context:[],original_response:'raw'}];renderReview();`,context);
assert.equal(element('#training-eligible').checked,false);
""")


def test_export_readiness_findings_render_as_text():
    run_browser_script(r"""
vm.runInContext(`api = async path => path.includes('dedup-report')
    ? {record_count: 1, exact_duplicate_groups: [], near_duplicates: []}
    : {ok: false, blocking_findings: [{sample_id: '<img src=x onerror=alert(1)>', reason: '<svg onload=alert(2)>'}]};`, context);
vm.runInContext('previewDedup()', context).then(() => {
    const html = element('#dedup-result').innerHTML;
    assert.ok(!html.includes('<img'));
    assert.ok(!html.includes('<svg'));
    assert.ok(html.includes('&lt;img'));
    assert.ok(html.includes('&lt;svg'));
}).catch(error => { console.error(error); process.exitCode = 1; });
""")


def test_content_renderers_preserve_arabic_and_escape_markup():
    run_browser_script(r"""
const text = '\u0645\u0631\u062d\u0628\u0627 <img src=x onerror=alert(1)> model/123';
context.exampleText = text;
const html = vm.runInContext('phase38Messages([{role:"assistant",content:exampleText}])', context);
assert.ok(html.includes('dir="auto"'));
assert.ok(html.includes(text.split(' ')[0]));
assert.ok(html.includes('&lt;img'));
assert.ok(!html.includes('<img'));
""")


def test_browser_api_caches_session_and_preserves_headers_and_json_body():
    run_browser_script(r"""
const calls = [];
context.fetch = async (path, options) => {
    calls.push({path, options});
    return {ok: true, status: 200, json: async () => path === '/api/v1/session' ? {csrf_token: 'session-1'} : {ok: true}};
};
vm.runInContext(`(async () => {
    await api('/read');
    await api('/write', {method:'POST', headers:{'X-Custom':'kept'}, body:'{"text":"original"}'});
    await api('/write', {method:'DELETE', body:'{}'});
})()`, context).then(() => {
    assert.equal(calls.filter(x => x.path === '/api/v1/session').length, 1);
    const post = calls.find(x => x.options.method === 'POST');
    assert.equal(post.options.headers['X-NajdiLab-CSRF'], 'session-1');
    assert.equal(post.options.headers['X-Custom'], 'kept');
    assert.equal(post.options.headers['Content-Type'], 'application/json');
    assert.equal(post.options.body, '{"text":"original"}');
    assert.ok(!calls[0].options.headers['X-NajdiLab-CSRF']);
}).catch(error => {console.error(error); process.exitCode = 1;});
""")


def test_browser_api_refreshes_only_csrf_rejections_once():
    run_browser_script(r"""
let sessions = 0;
let writes = 0;
context.fetch = async path => {
    if (path === '/api/v1/session') return {ok:true,status:200,json:async () => ({csrf_token:`session-${++sessions}`})};
    writes++;
    return writes === 1 ? {ok:false,status:403,json:async () => ({code:'CSRF_TOKEN_INVALID',error:'Reload'})}
        : {ok:true,status:200,json:async () => ({ok:true})};
};
vm.runInContext("api('/write',{method:'POST',body:'{}'})", context).then(() => {
    assert.equal(sessions, 2);
    assert.equal(writes, 2);
    context.fetch = async () => {writes++; return {ok:false,status:403,json:async () => ({error:'Business rule rejected'})};};
    return vm.runInContext("api('/write',{method:'POST',body:'{}'})", context).then(
        () => assert.fail('business rejection should throw'),
        error => {assert.equal(error.message, 'Business rule rejected'); assert.equal(writes, 3);}
    );
}).catch(error => {console.error(error); process.exitCode = 1;});
""")
