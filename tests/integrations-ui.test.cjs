// Framework-free controller behavior; the served UI also requires visual QA.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture() {
  const ids = ['integrations-controls','integration-cards','integration-status','integration-scan','integration-model-lmstudio','native-path-lmstudio'];
  const elements = Object.fromEntries(ids.map(id => [id, {innerHTML:'', textContent:'', disabled:false, value:'synthetic-model', setAttribute(){}}]));
  const calls = [], confirmations = [];
  const state = {items:[{id:'lmstudio', name:'LM Studio', kind:'model_runtime', endpoint:'http://127.0.0.1:1234', installation:'NOT_DETECTED', availability:'AVAILABLE', connection:'CONNECTED', selection_revision:2, models:['synthetic-model'], selected_model:'synthetic-model', disconnect:{local_verified:false,external_status:'NOT_MANAGED'}}, {id:'hermes',name:'Hermes Agent',kind:'conversation_source',availability:'BLOCKED',connection:'BLOCKED',models:[],disconnect:{local_verified:true,external_status:'UNVERIFIED'}}]};
  for (const service of state.items) service.native_capture = {capability:service.id==='lmstudio'?'UNSUPPORTED':'BLOCKED',reason:'No verified native completed-turn capture.',source_status:'MISSING',source_location:'DEFAULT',version:'NOT_VERIFIED',format_verification:'NOT_TESTED',connection:'DISCONNECTED',enabled:false,last_capture_at:null,local_disconnect_verified:true};
  elements['native-path-lmstudio'].value='C:\\synthetic\\conversations';
  let consent = true, failure = false;
  const context = vm.createContext({window:{}, document:{querySelector:sel=>elements[sel.slice(1)]},
    esc:value=>String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    fmtDate:value=>value||'—', confirm:message=>{confirmations.push(message);return consent;},
    api:async (path, options={})=>{calls.push([path,options]);if(failure)throw new Error('offline');return structuredClone(state);}});
  vm.runInContext(fs.readFileSync('static/integrations.js','utf8'), context);
  const click = (action,id='lmstudio') => elements['integration-cards'].onclick({target:{closest:()=>({dataset:{integrationAction:action,connector:id}})}});
  return {ui:context.window.NajdiIntegrations,elements,calls,confirmations,state,click,setConsent:v=>consent=v,setFailure:v=>failure=v};
}

test('opening Settings discovers once and never connects or generates automatically', async()=>{
  const f=fixture(); await f.ui.load(); await f.ui.load();
  assert.deepEqual(f.calls.map(x=>x[0]),['/api/v1/integrations','/api/v1/integrations/discover','/api/v1/integrations']);
  assert.equal(f.confirmations.length,0);
});

test('canceling each human action sends no request', async()=>{
  const f=fixture();await f.ui.load();f.calls.length=0;f.setConsent(false);
  for(const action of ['connect','select','test','disconnect'])await f.click(action);
  assert.equal(f.confirmations.length,4); assert.equal(f.calls.length,0);
});

test('synthetic test approval is explicit and sends no prompt or credentials', async()=>{
  const f=fixture(); await f.ui.load();f.calls.length=0;await f.click('test');
  assert.match(f.confirmations[0],/Reply with OK/);
  assert.equal(f.calls[0][0],'/api/v1/integrations/lmstudio/test');
  assert.deepEqual(JSON.parse(f.calls[0][1].body),{approved:true,selection_revision:2});
  await f.click('select'); assert.deepEqual(JSON.parse(f.calls[1][1].body),{approved:true,model:'synthetic-model'});
});

test('untrusted model text is escaped and Hermes never claims sender disconnect', async()=>{
  const f=fixture(); f.state.items[0].models=['<img src=x onerror=alert(1)>'];await f.ui.load();
  const html=f.elements['integration-cards'].innerHTML;
  assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));
  assert.match(html,/External sender: UNVERIFIED/);
  await f.click('disconnect','hermes');assert.match(f.confirmations[0],/does not stop Hermes/);
});

test('failed loads remain visible and controls recover', async()=>{
  const f=fixture();f.setFailure(true);await f.ui.load();
  assert.match(f.elements['integration-status'].textContent,/offline/);
  assert.equal(f.elements['integrations-controls'].disabled,false);
  assert.equal(f.elements['integration-cards'].innerHTML,'');
});

test('runtime consent never disguises native collection as enabled', async()=>{
  const f=fixture();await f.ui.load();f.calls.length=0;
  const html=f.elements['integration-cards'].innerHTML;
  assert.match(html,/Native application capture/);
  assert.match(html,/Automatic Conversation Collection/);
  assert.match(html,/NOT_VERIFIED/);
  assert.match(html,/UNSUPPORTED/);
  assert.match(html,/<input[^>]+type="checkbox"[^>]+disabled/);
  for (const action of ['native-connect','native-enable'])await f.click(action);
  assert.equal(f.calls.length,0);
  assert.match(f.elements['integration-status'].textContent,/No verified native/);
});

test('manual path metadata and OFF verification require separate consent', async()=>{
  const f=fixture();await f.ui.load();f.calls.length=0;
  f.setConsent(false);await f.click('native-path');assert.equal(f.calls.length,0);
  f.setConsent(true);await f.click('native-path');
  assert.equal(f.calls[0][0],'/api/v1/integrations/lmstudio/native/path');
  assert.deepEqual(JSON.parse(f.calls[0][1].body),{approved:true,path:'C:\\synthetic\\conversations'});
  assert.match(f.confirmations[0],/metadata only/);
  await f.click('native-disconnect');
  assert.equal(f.calls[1][0],'/api/v1/integrations/lmstudio/native/disconnect');
  assert.deepEqual(JSON.parse(f.calls[1][1].body),{approved:true});
  assert.match(f.elements['integration-status'].textContent,/OFF/);
});

test('native path fallback is hidden after source auto detection succeeds', async()=>{
  const f=fixture();f.state.items[0].native_capture.source_status='DETECTED';await f.ui.load();
  const html=f.elements['integration-cards'].innerHTML;
  assert.ok(!html.includes('id="native-path-lmstudio"'));
  assert.ok(html.includes('id="native-path-hermes"'));
});
