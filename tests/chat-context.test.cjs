const {test}=require('node:test');
const assert=require('node:assert/strict');
const chat=require('../static/chat.js');

const session=(turns=[],budget=4096,reserve=1024)=>({id:'s',status:'OPEN',context_budget:budget,reply_reserve:reserve,turns});

test('usage before the first message counts only the reply reserve and calls the rest an estimate',()=>{
  const u=chat.contextUsage(session());
  assert.deepEqual({used:u.used,available:u.available,percent:u.percent,kind:u.kind,availableKind:u.availableKind},
    {used:0,available:3072,percent:25,kind:'empty',availableKind:'estimate'});
});

test('after a saved turn the history is the last measured prompt plus its reply',()=>{
  const u=chat.contextUsage(session([{input_tokens:900,output_tokens:300},{input_tokens:1500,output_tokens:200}]));
  assert.equal(u.used,1700);assert.equal(u.available,4096-1024-1700);assert.equal(u.percent,Math.round((1700+1024)/4096*100));
  assert.equal(u.kind,'measured_history');assert.equal(u.availableKind,'estimate');
});

test('during a turn the admitted prompt is measured exactly',()=>{
  const u=chat.contextUsage(session([{input_tokens:900,output_tokens:300}]),{input_tokens:2000});
  assert.equal(u.used,2000);assert.equal(u.kind,'measured_prompt');assert.equal(u.availableKind,'measured');
  assert.equal(u.available,4096-1024-2000);
});

test('the full boundary reads 100 percent and never goes negative',()=>{
  const full=chat.contextUsage(session([{input_tokens:3000,output_tokens:72}]));
  assert.equal(full.available,0);assert.equal(full.percent,100);
  const over=chat.contextUsage(session([{input_tokens:3500,output_tokens:400}]));
  assert.equal(over.available,0);assert.equal(over.percent,100);
});

test('warning levels follow the thresholds and invalid thresholds fall back to 70/85/95',()=>{
  assert.equal(chat.contextLevel(69),null);assert.equal(chat.contextLevel(70),'info');
  assert.equal(chat.contextLevel(85),'warn');assert.equal(chat.contextLevel(95),'critical');assert.equal(chat.contextLevel(100),'critical');
  assert.equal(chat.contextLevel(60,{info:50,warn:60,critical:90}),'warn');
  for(const bad of [{info:90,warn:80,critical:95},{info:0,warn:50,critical:60},{info:50,warn:60,critical:100},{info:1.5,warn:2,critical:3},null]){
    assert.equal(chat.validThresholds(bad),false);
    assert.equal(chat.contextLevel(86,bad),'warn');
  }
});

test('missing or invalid numbers give no indicator rather than a guess',()=>{
  assert.equal(chat.contextUsage(null),null);
  assert.equal(chat.contextUsage({context_budget:0,turns:[]}),null);
  assert.equal(chat.contextUsage(session([{input_tokens:null,output_tokens:5}])).kind,'empty');
});

test('failure categories explain why a reply ended without changing the engine message',()=>{
  assert.equal(chat.failureCategory({code:'STOPPED'}),'Cancelled.');
  assert.equal(chat.failureCategory({code:'INCOMPLETE_RESPONSE',check:'STOP_REASON_LENGTH'}),'Reply reserve reached.');
  assert.equal(chat.failureCategory({code:'INCOMPLETE_RESPONSE',check:'EMPTY_CONTENT'}),'The runtime did not finish the reply.');
  assert.equal(chat.failureCategory({code:'CONTEXT_SHRANK'}),'Context capacity.');
  assert.equal(chat.failureCategory({code:'ENGINE_TIMEOUT'}),'Runtime error.');
  assert.equal(chat.failureCategory({code:'INVALID_TEXT'}),null);
});

test('the context-limit rollover still keeps the draft and opens the server-created session',async()=>{
  assert.equal(chat.shouldClearDraft('long question','long question','CONTEXT_LIMIT'),false);
  const fresh={id:'fresh',status:'OPEN',revision:0,collect:false,turns:[]};
  const c=new chat.ChatController(async()=>({status:'CONTEXT_LIMIT',session:{id:'old',status:'CONTEXT_LIMIT'},new_session:fresh}),()=>{},()=> 'u');
  c.session={id:'old',status:'OPEN',revision:1,turns:[]};c.modelReady=true;
  await c.send('x');
  assert.equal(c.session.id,'fresh');assert.equal(c.session.collect,false);
});
