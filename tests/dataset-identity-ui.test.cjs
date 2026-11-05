// Synthetic-only controller acceptance for UX-13 and UX-27.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const src=fs.readFileSync('static/app.js','utf8');
const catalog=src.slice(src.indexOf('async function ensureDatasetVersions('),src.indexOf('function pct(',src.indexOf('async function ensureDatasetVersions(')));
const library=src.slice(src.indexOf('async function loadDatasetVersions('),src.indexOf('async function showVersionDetail(',src.indexOf('async function loadDatasetVersions(')));
const evaluation=src.slice(src.indexOf('async function loadEvalSets('),src.indexOf('async function loadDashboard(',src.indexOf('async function loadEvalSets(')));
const health=src.slice(src.indexOf('function pct('),src.indexOf('function showHealthDetail('));
assert.ok(catalog.startsWith('async function')&&library.startsWith('async function')&&evaluation.startsWith('async function'));

test('conversation concentration is unavailable without a measurable share',async()=>{
  const elements=new Map();
  const element=key=>{
    if(!elements.has(key))elements.set(key,{value:'gold-v001',innerHTML:'',textContent:'',className:'',disabled:false,classList:{add(){},remove(){}}});
    return elements.get(key);
  };
  const data={version:'gold-v001',checked_at:'2026-11-06',training_count:0,exact_duplicate_extra:0,training_readiness:{},
    readiness:{structural:{status:'VALID',errors:0},training_compatibility:{status:'STRUCTURE_CHECKED'},evaluation:{status:'NO_EVALUATION_DATA',samples:0}},
    evaluation_integrity:{status:'CLEAN',conversation_overlap_count:0},counts:{},warnings:[],highest_record_share:null,
    statistics:{independent_source_conversations:0,training_records:0,largest_source_share:0,stage:'technical_smoke_test',stage_reason:'no independent evaluation samples',split:{evaluation:0}}};
  const catalogRequests=[];
  const context={state:{datasetVersions:[{version:'gold-v001'}]},$:element,api:async()=>data,ensureDatasetVersions:async force=>{catalogRequests.push(force);},updateLocation(){},esc:String};
  vm.createContext(context);vm.runInContext(health,context);
  await context.loadHealth();
  assert.match(element('#health-checks').innerHTML,/Unavailable<\/span><h3>Conversation Balance<\/h3><strong>—<\/strong>/);
  data.highest_record_share=['c1',{record_share:.5}];
  await context.loadHealth();
  assert.match(element('#health-checks').innerHTML,/WARNING<\/span><h3>Conversation Balance<\/h3><strong>50.00%<\/strong>/);
  assert.deepEqual(catalogRequests,[true,true],'each visit refreshes the catalog after another version is created');
});

test('UX-13 dataset library refreshes from API and never selects a deleted/stale version',async()=>{
  const elements=new Map(),byName=key=>{
    if(!elements.has(key))elements.set(key,{value:'',innerHTML:''});
    return elements.get(key);
  };
  const apiCalls=[];let result=[{version:'current-1',readable:true,created_at:'2026-01-01'}];
  const context={
    state:{datasetVersions:[{version:'deleted',readable:true}],selectedDataset:'deleted'},
    $:byName,api:async path=>{apiCalls.push(path);return {items:result};},
    selectedVersion:()=>'',esc:String,fmtDate:()=>'',showVersionDetail:async version=>{context.selected=version;}
  };
  vm.createContext(context);
  vm.runInContext(catalog+'\n'+library,context);
  await context.loadDatasetVersions();
  assert.equal(context.selected,'current-1');
  assert.ok(!byName('#version-list').innerHTML.includes('deleted'));
  result=[{version:'current-2',readable:true}];
  await context.loadDatasetVersions();
  assert.equal(context.selected,'current-2');
  assert.equal(apiCalls.length,2);
});

function evaluationHarness(){
  const els=new Map(),element=key=>{
    if(!els.has(key))els.set(key,{value:'',textContent:'',innerHTML:''});
    return els.get(key);
  };
  const pending=new Map();
  const context={
    state:{},$:element,ensureDatasetVersions:async()=>{},
    api:path=>new Promise(resolve=>pending.set(path,resolve)),
    esc:String,JSON
  };
  vm.createContext(context);vm.runInContext(evaluation,context);
  // Wait until the controller has actually issued the request, instead of guessing tick counts.
  const requested=async path=>{
    for(let i=0;i<100&&!pending.has(path);i++)await new Promise(resolve=>setImmediate(resolve));
    assert.ok(pending.has(path),'expected request '+path);
  };
  const data={leakage_free:true,train_count:1,eval_count:0,eval_files:[],conversation_overlap_count:0,exact_target_overlap_count:0};
  return {context,element,pending,requested,data};
}
const OLD='/api/v1/dataset-versions/gold-v1/eval-sets',NEW='/api/v1/dataset-versions/gold-v2/eval-sets';

test('UX-27 a delayed response for old eval version cannot overwrite the newest results',async()=>{
  const {context,element,pending,requested,data}=evaluationHarness();
  element('#eval-version').value='gold-v1';
  const older=context.loadEvalSets();await requested(OLD);
  element('#eval-version').value='gold-v2';
  const newest=context.loadEvalSets();await requested(NEW);
  pending.get(NEW)(data);
  await newest;
  assert.match(element('#eval-version-identity').textContent,/gold-v2/);
  pending.get(OLD)({...data,leakage_free:false});
  await older;
  assert.match(element('#eval-version-identity').textContent,/gold-v2/);
  assert.doesNotMatch(element('#eval-version-identity').textContent,/gold-v1/);
});

test('UX-27 an old response that arrives first is discarded while the new request is pending',async()=>{
  const {context,element,pending,requested,data}=evaluationHarness();
  element('#eval-version').value='gold-v1';
  const older=context.loadEvalSets();await requested(OLD);
  element('#eval-version').value='gold-v2';
  const newest=context.loadEvalSets();await requested(NEW);
  pending.get(OLD)({...data,leakage_free:false});
  await older;
  assert.equal(element('#eval-version-identity').textContent,'Checking evaluation integrity for gold-v2…');
  assert.equal(element('#eval-status-card').innerHTML,'');
  pending.get(NEW)(data);
  await newest;
  assert.equal(element('#eval-version-identity').textContent,'Evaluation results for gold-v2 · No leakage detected');
});
