const {test}=require('node:test');
const assert=require('node:assert/strict');
const {ChatController,hardwareReport,budgetPresets,validBudgets,canSend,shouldSendOnEnter,markdownBlocks,inlineMarkdown}=require('../static/chat.js');

test('presets require the actual engine ceiling and an explicit unverified memory estimate',()=>{
  const snapshot={recommendation:{budget_ceiling:8192,model_max_context:131072,runtime_context:8192,candidates:[
    {context:4096,assessment:'ESTIMATE_FITS_FREE_VRAM',estimated_required_bytes:5},
    {context:8192,assessment:'ESTIMATE_EXCEEDS_FREE_VRAM',estimated_required_bytes:10},
    {context:16384,assessment:'ESTIMATE_FITS_FREE_VRAM',estimated_required_bytes:15}]}};
  const presets=budgetPresets(snapshot);
  assert.deepEqual(presets.map(p=>[p.id,p.context,p.reply,p.enabled]),[['light',4096,1024,true],['balanced',8192,2048,false],['long',16384,3072,false]]);
  assert.equal(budgetPresets({recommendation:{model_max_context:131072}}).every(p=>!p.enabled),true);
  assert.equal(budgetPresets().every(p=>!p.enabled),true);
  assert.equal(budgetPresets({recommendation:{budget_ceiling:4096,candidates:[{context:8192,assessment:'ESTIMATE_FITS_FREE_VRAM'}]}})[0].enabled,false,'never borrow a larger estimate');
  assert.equal(budgetPresets({recommendation:{budget_ceiling:4096,candidates:[{context:4096,assessment:'ESTIMATE_FITS_FREE_VRAM'}]}})[0].enabled,false,'missing estimate bytes remain unknown');
});

test('manual budgets preserve backend integer bounds without rounding',()=>{
  for(const [context,reply] of [[128,1],[4096,1024],[1048576,8192]])assert.equal(validBudgets(context,reply),true);
  for(const [context,reply] of [[127,1],[4096.5,1024],[4096,0],[128,128],[4096,4096],[16384,8193],[1048577,1],[NaN,1]])assert.equal(validBudgets(context,reply),false);
});

test('send availability and Enter share guards; IME, repeat, empty, busy, closed and wrong model never send',()=>{
  const session={status:'OPEN',busy:false};
  assert.equal(canSend(' draft ',session,false,true),true);
  for(const [text,s,pending,ready] of [[' ',session,false,true],['x',null,false,true],['x',session,true,true],['x',{...session,busy:true},false,true],['x',{status:'ARCHIVED'},false,true],['x',session,false,false]])assert.equal(canSend(text,s,pending,ready),false);
  const enter={key:'Enter',shiftKey:false,isComposing:false,keyCode:13,repeat:false};
  assert.equal(shouldSendOnEnter(enter),true);
  for(const change of [{key:'a'},{shiftKey:true},{isComposing:true},{keyCode:229},{repeat:true},{composing:true}])assert.equal(shouldSendOnEnter({...enter,...change}),false);
});

test('controller rejects guarded sends before any API call',async()=>{
  const calls=[];const c=new ChatController(async(...args)=>calls.push(args),()=>{});
  for(const [session,pending,modelReady,text] of [[null,false,true,'x'],[{status:'ARCHIVED'},false,true,'x'],[{status:'OPEN',busy:true},false,true,'x'],[{status:'OPEN'},true,true,'x'],[{status:'OPEN'},false,false,'x'],[{status:'OPEN'},false,true,' ']]){
    c.session=session;c.pending=pending;c.modelReady=modelReady;await assert.rejects(()=>c.send(text));
  }
  assert.deepEqual(calls,[]);
});

test('restricted Markdown parses formatting while preserving literal escapes and unsafe source as text',()=>{
  const raw='# Heading\n\n**bold** and `code`\n\n- one\n- two\n\n```html\n<img src=x onerror=alert(1)>\\n\n```';
  const blocks=markdownBlocks(raw);
  assert.equal(blocks[0].tag,'h1');assert.equal(blocks[1].text,'**bold** and `code`');
  assert.deepEqual(blocks[2],{tag:'ul',items:['one','two']});
  assert.equal(blocks[3].tag,'pre');assert.equal(blocks[3].text,'<img src=x onerror=alert(1)>\\n');
  assert.deepEqual(inlineMarkdown('**bold** and `code` <script>x</script>\\n'),[
    {tag:'strong',text:'bold'},{tag:null,text:' and '},{tag:'code',text:'code'},{tag:null,text:' <script>x</script>\\n'}]);
  assert.deepEqual(markdownBlocks('literal\\nnext &lt;b&gt; [x](javascript:alert(1))'),[{tag:'p',text:'literal\\nnext &lt;b&gt; [x](javascript:alert(1))'}]);
});

test('backslash-escaped Markdown delimiters remain exact literal source',()=>{
  for(const raw of [String.raw`\*\*literal\*\*`,String.raw`\**literal**`,String.raw`\*literal\*`,String.raw`*literal\*`,String.raw`\`literal\``])assert.deepEqual(inlineMarkdown(raw),[{tag:null,text:raw}]);
  assert.deepEqual(inlineMarkdown(String.raw`\**literal** then **bold**`),[{tag:null,text:String.raw`\**literal** then `},{tag:'strong',text:'bold'}]);
});

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

test('newer typing is never cleared by an older completed Send; rollover and failed requests keep drafts',()=>{
  const {shouldClearDraft}=require('../static/chat.js');
  assert.equal(shouldClearDraft('old question','new unfinished question','COMPLETED'),false);
  assert.equal(shouldClearDraft('old question','old question','COMPLETED'),true);
  assert.equal(shouldClearDraft('old question','old question','CONTEXT_LIMIT'),false);
  assert.equal(shouldClearDraft('old question','old question','FAILED'),false);
});

test('Phase B manual turn and Add Data tabs operate on element collections',()=>{
  const source=require('node:fs').readFileSync('static/app.js','utf8');
  assert.match(source,/document\.querySelectorAll\('#view-add-data \.subtabs \[data-add-tab\]'\)\.forEach/);
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
