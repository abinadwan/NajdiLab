const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ChatController}=require('../static/chat.js');

test('collection is separate, send uses only a UUID/revision/text, rollover never replays draft',async()=>{
  const calls=[];
  const old={id:'old',status:'OPEN',revision:2,collect:false,turns:[],model:'m',provider:'lmstudio'};
  const fresh={...old,id:'fresh',revision:0};
  const api=async(path,options)=>{calls.push([path,options]);return {status:'CONTEXT_LIMIT',session:{...old,status:'CONTEXT_LIMIT'},new_session:fresh};};
  const c=new ChatController(api,()=>{},()=> 'uuid');
  c.session=old;c.selectionRevision=4;
  const result=await c.send('  raw text  ');
  assert.equal(c.session.id,'fresh');
  assert.equal(result.status,'CONTEXT_LIMIT');
  const body=JSON.parse(calls[0][1].body);
  assert.deepEqual(body,{request_id:'uuid',revision:2,selection_revision:4,text:'  raw text  '});
  assert.equal(calls.length,1);
  assert.equal(c.session.collect,false);
});

test('failed send refreshes history, retains draft and never retries inference',async()=>{
  const calls=[];const c=new ChatController(async(path,options)=>{calls.push(path);if(options)throw Error('lost response');return {id:'s',revision:3,turns:[],collect:false};},()=>{},()=> 'uuid');
  c.session={id:'s',status:'OPEN',revision:0};c.selectionRevision=1;
  await assert.rejects(()=>c.send('draft'));
  assert.deepEqual(calls,['/api/v1/chat/sessions/s/send','/api/v1/chat/sessions/s']);
  assert.equal(c.pending,false);
});

test('stop remains available during send and only calls own chat endpoint',async()=>{
  const calls=[];const c=new ChatController(async(path,opts)=>{calls.push(path);return {};},()=>{},()=> 'uuid');
  c.session={id:'s'};c.pending=true;
  await c.stop();
  assert.deepEqual(calls,['/api/v1/chat/sessions/s/stop']);
});

test('newer typing is never cleared by an older completed Send; rollover and failed requests keep drafts',()=>{
  const {shouldClearDraft}=require('../static/chat.js');
  assert.equal(shouldClearDraft('old question','new unfinished question','COMPLETED'),false);
  assert.equal(shouldClearDraft('old question','old question','COMPLETED'),true);
  assert.equal(shouldClearDraft('old question','old question','CONTEXT_LIMIT'),false);
  assert.equal(shouldClearDraft('old question','old question','FAILED'),false);
});

test('Phase B manual turn and Add Data tabs operate on element collections',()=>{
  const source=require('node:fs').readFileSync('static/app.js','utf8');
  assert.match(source,/document\.querySelectorAll\('#data-entry-content \.subtabs \[data-add-tab\]'\)\.forEach/);
  assert.match(source,/const rows=Array\.from\(document\.querySelectorAll\('#sft-turns \.turn-row'\)\)/);
  assert.match(source,/payload\.messages=Array\.from\(document\.querySelectorAll\('#manual-edit-turns \.turn-row'\)\)\.map/);
});

test('incomplete collected context shows safe review warning and disables export flags, then resets for complete sources',()=>{
  const source=require('node:fs').readFileSync('static/app.js','utf8');
  const start=source.indexOf('function renderCollectionWarning(');assert.ok(start>=0,'review needs a collection warning renderer');
  const elements=new Map(),get=key=>{if(!elements.has(key))elements.set(key,{textContent:'',checked:true,disabled:false,classList:{toggle(name,value){this[name]=value;}}});return elements.get(key);};
  const context={$:get};require('node:vm').createContext(context);
  require('node:vm').runInContext(source.slice(start,source.indexOf('\nfunction renderReview(',start)),context);
  context.renderCollectionWarning({context_complete:false,context_warning:'<img src=x onerror=alert(1)>'});
  assert.equal(get('#review-context-warning').textContent,'<img src=x onerror=alert(1)>');assert.equal(get('#review-context-warning').classList.hidden,false);
  for(const key of ['#training-eligible','#evaluation-only']){assert.equal(get(key).checked,false);assert.equal(get(key).disabled,true);}
  context.renderCollectionWarning({context_complete:true});
  assert.equal(get('#review-context-warning').classList.hidden,true);for(const key of ['#training-eligible','#evaluation-only'])assert.equal(get(key).disabled,false);
});
