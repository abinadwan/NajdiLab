// Phase B UX-18: synthetic-only acceptance for Phase 3.9 UI; no private v009 artifacts.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const source=fs.readFileSync('static/app.js','utf8');
const start=source.indexOf('async function loadPhase39Verification(){');
const end=source.indexOf('async function ensureDatasetVersions(){',start);
assert.ok(start>=0&&end>start,'expected Phase39 view/controller implementation');

function fixture(records){
  const els=new Map(),buttons=[
    {dataset:{phase39Decision:'اعتماد التعديل'},classList:{toggle(){}},setAttribute(){}},
    {dataset:{phase39Decision:'يحتاج تعديل إضافي'},classList:{toggle(){}},setAttribute(){}},
    {dataset:{phase39Decision:'رفض'},classList:{toggle(){}},setAttribute(){}}
  ];
  function element(id){
    if(!els.has(id))els.set(id,{
      id,textContent:'',innerHTML:'',className:'',value:'',disabled:false,
      replaceChildren(){this.innerHTML='';},classList:{toggle(){},add(){},remove(){}}
    });
    return els.get(id);
  }
  let response={records,summary:{verified:records.filter(r=>r.decision).length,total:records.length}};
  const context={
    state:{phase39Index:0,phase39:null,phase39Dirty:false,phase39Decision:null},
    $:element,$$:(selector)=>selector==='[data-phase39-decision]'?buttons:[],
    esc:(x)=>String(x??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),
    api:async(path,opts)=>{
      if(!opts)return response;
      if(context.failSave)throw Error('synthetic write failure');
      response={...response,records:response.records.map((r,i)=>i===context.state.phase39Index?{...r,decision:JSON.parse(opts.body).decision}:r)};
      response.summary.verified=response.records.filter(r=>r.decision).length;
      return {verification:response};
    },
    toast:()=>{},confirm:()=>false, encodeURIComponent, JSON
  };
  vm.createContext(context);vm.runInContext(source.slice(start,end),context);
  return {context,element,setResponse:r=>response=r};
}
const row=(i,decision=null)=>({
  record_id:'synthetic-'+i,record_type:'sft',validation_status:'EDIT_APPLIED_VALID',
  original_assistant_messages:'before',requested_correction:'after',final_assistant_messages:'after',
  reviewer_note:'none',decision
});

test('Phase39 renders arbitrary server queue sizes without inventing PASS on missing gate evidence',async()=>{
  const f=fixture([row(1),row(2,'اعتماد التعديل'),row(3)]);
  await f.context.loadPhase39Verification();
  assert.match(f.element('#phase39-status').textContent,/1\/3.*1 of 3/);
  assert.match(f.element('#phase39-records').innerHTML,/contamination: UNVERIFIED/);
  f.context.phase39Navigate(1);
  assert.equal(f.context.state.phase39Index,1);
  assert.equal(f.context.state.phase39Decision,'اعتماد التعديل');
  assert.match(f.element('#phase39-status').textContent,/2 of 3/);
  f.context.phase39Navigate(1);
  assert.match(f.element('#phase39-status').textContent,/3 of 3/);
  f.context.phase39Navigate(1);
  assert.equal(f.context.state.phase39Index,2);
});

test('Phase39 empty queue has a useful empty state and no navigation exceptions',async()=>{
  const f=fixture([]);await f.context.loadPhase39Verification();
  assert.match(f.element('#phase39-status').textContent,/No post-edit verification records/);
  assert.equal(f.element('#phase39-records').innerHTML,'');
});

test('Phase39 failed save retains decision and displays a persistent retry state',async()=>{
  const f=fixture([row(1)]);await f.context.loadPhase39Verification();
  f.context.state.phase39Decision='اعتماد التعديل';f.context.failSave=true;
  f.element('#phase39-reviewer-note').value='synthetic note';
  const save=f.element('#phase39-save'),root=f.element('#view-phase39-review');
  await root.onclick({target:{closest:q=>q==='#phase39-save'?save:null}});
  assert.equal(save.disabled,false);
  assert.equal(save.textContent,'Retry save');
  assert.match(f.element('#phase39-save-state').textContent,/synthetic write failure/);
  assert.equal(f.context.state.phase39Decision,'اعتماد التعديل');
});
