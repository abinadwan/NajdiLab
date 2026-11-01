const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ChatController,hardwareReport}=require('../static/chat.js');

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

test('hardware report keeps maximum, runtime, measured and estimated evidence on separate lines',()=>{
  const text=hardwareReport({ram_total_bytes:32*1024**3,ram_available_bytes:20*1024**3,gpus:[{name:'GPU',free_bytes:10*1024**3,total_bytes:12*1024**3}],
    model:{architecture:'gemma4',quantization:'Q4',weights_bytes:5*1024**3,other_loaded_models:[]},
    recommendation:{model_max_context:131072,runtime_context:16384,measured:{context:16384,size_bytes:7*1024**3,size_vram_bytes:7*1024**3},
      candidates:[{context:8192,estimated_required_bytes:7*1024**3,assessment:'ESTIMATE_FITS_FREE_VRAM'},{context:65536,estimated_required_bytes:20*1024**3,assessment:'ESTIMATE_EXCEEDS_FREE_VRAM'}],
      recommended_context:8192,label:'Unverified estimate, not a guaranteed safe limit.',reason:'Free VRAM changes.'}});
  assert.match(text,/Model maximum context: 131072/);
  assert.match(text,/Runtime context now: 16384/);
  assert.match(text,/Measured now at 16384: 7\.0 GiB loaded, 7\.0 GiB on GPU/);
  assert.match(text,/Estimate 65536: likely exceeds free VRAM/);
  assert.match(text,/Suggested starting context: 8192\. Unverified estimate/);
});

test('hardware report states when no reliable recommendation exists',()=>{
  const text=hardwareReport({gpus:[],recommendation:{recommended_context:null,reason:'GPU free memory is unavailable.'}});
  assert.match(text,/No reliable recommendation\. GPU free memory is unavailable\./);
  assert.match(text,/Model maximum context: Unknown/);
  assert.match(text,/Runtime context now: Not loaded/);
});
