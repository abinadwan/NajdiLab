const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ChatController}=require('../static/chat.js');

test('collection is separate, send uses only a UUID/revision/text, rollover never replays draft',async()=>{
  const calls=[];
  const old={id:'old',revision:2,collect:false,turns:[],model:'m',provider:'lmstudio'};
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
  c.session={id:'s',revision:0};c.selectionRevision=1;
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
