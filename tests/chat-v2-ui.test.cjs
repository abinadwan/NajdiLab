// Chat V2 pure UI logic: keyboard sending, duplicate protection, streaming parse,
// grouping, presets and the safe Markdown renderer. No DOM or network needed.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const chat=require('../static/chat.js');
const md=require('../static/chat-markdown.js');

const key=(k,extra={})=>({key:k,isComposing:false,keyCode:k==='Enter'?13:0,shiftKey:false,altKey:false,ctrlKey:false,metaKey:false,...extra});

test('Enter sends, Shift+Enter is a new line, IME composition never sends (Arabic and English)',()=>{
  assert.equal(chat.keyAction(key('Enter')),'send');
  assert.equal(chat.keyAction(key('Enter',{shiftKey:true})),'newline');
  assert.equal(chat.keyAction(key('Enter',{ctrlKey:true})),'newline');
  assert.equal(chat.keyAction(key('Enter',{isComposing:true})),'compose');
  assert.equal(chat.keyAction(key('Enter',{keyCode:229})),'compose','Chromium IME commit keydown');
  assert.equal(chat.keyAction(key('a')),'none');
  assert.equal(chat.keyAction(key('ع')),'none');
});

test('blank, duplicate and in-flight sends are refused before any request',async()=>{
  const calls=[];let release;
  const c=new chat.ChatController(async()=>{},()=>{},()=> 'uuid',async(path,body)=>{calls.push(body);await new Promise(r=>{release=r;});return {status:'COMPLETED',session:{id:'s',revision:2,status:'OPEN',turns:[]}};});
  c.session={id:'s',revision:1,status:'OPEN',turns:[]};c.selectionRevision=3;
  for(const text of ['','   ','\n\t'])assert.equal(c.canSend(text),false);
  await assert.rejects(()=>c.send('   '),/Write a message first/);
  assert.equal(calls.length,0);
  const first=c.send('مرحبا');
  assert.equal(c.pending,true,'pending is set synchronously');
  assert.equal(c.canSend('hello again'),false);
  await assert.rejects(()=>c.send('hello again'),e=>e.code==='CHAT_BUSY');
  release();await first;
  assert.equal(calls.length,1);
  assert.deepEqual(calls[0],{request_id:'uuid',revision:1,selection_revision:3,text:'مرحبا'});
  assert.equal(c.pending,false);
});

test('a closed or archived conversation cannot send',()=>{
  const c=new chat.ChatController(async()=>{},()=>{});
  for(const status of ['CONTEXT_LIMIT','ARCHIVED']){c.session={id:'s',status};assert.equal(c.canSend('x'),false);}
});

test('NDJSON splitter only emits complete lines, across arbitrary chunk boundaries',()=>{
  const events=[];const s=chat.ndjsonSplitter(e=>events.push(e));
  const text='{"type":"content","text":"هلا"}\n{"type":"thinking","text":"x"}\n{"type":"done","result":{}}\n';
  for(const piece of text.match(/[\s\S]{1,5}/g))s.push(piece);
  s.end();
  assert.deepEqual(events.map(e=>e.type),['content','thinking','done']);
  assert.equal(events[0].text,'هلا');
  assert.throws(()=>chat.ndjsonSplitter(()=>{}).push('{broken\n'));
});

test('sessions group by local day of last activity, pinned first',()=>{
  const now=new Date(2026,10,2,15,0,0);
  const at=(d,h=12)=>new Date(2026,10,d,h).toISOString();
  const groups=chat.groupSessions([
    {id:'p',pinned_at:'x',last_activity_at:at(1)},{id:'t',last_activity_at:at(2,1)},{id:'y',last_activity_at:at(1,23)},
    {id:'w',last_activity_at:new Date(2026,9,20,12).toISOString()},{id:'o',last_activity_at:new Date(2026,5,1).toISOString()},{id:'bad',last_activity_at:'nope'}],now);
  assert.deepEqual(groups.map(g=>[g.key,g.items.map(i=>i.id)]),[['pinned',['p']],['today',['t']],['yesterday',['y']],['month',['w']],['older',['o','bad']]]);
});

test('presets match the approved table and the budget breakdown validates limits',()=>{
  assert.deepEqual(chat.PRESETS,{light:{context_budget:4096,reply_reserve:1024},balanced:{context_budget:8192,reply_reserve:2048},long:{context_budget:16384,reply_reserve:3072}});
  assert.equal(chat.presetFor(8192,2048),'balanced');assert.equal(chat.presetFor(8192,999),'custom');
  assert.deepEqual(chat.budgetBreakdown(8192,2048),{context:8192,reserve:2048,input:6144,valid:true,warnings:[]});
  assert.equal(chat.budgetBreakdown(4096,4096).valid,false);
  assert.equal(chat.budgetBreakdown(4096,9000).valid,false);
  assert.match(chat.budgetBreakdown(8192,256).warnings[0],/Thinking models/);
  assert.match(chat.budgetBreakdown(65536,2048,32768).warnings[0],/maximum context/);
});

test('errors keep the readable message and the technical code',()=>{
  const e=new chat.ChatError('The engine did not finish the reply normally; no pair was saved.','INCOMPLETE_RESPONSE','STOP_REASON_LENGTH','Thinking tokens count toward this limit.');
  assert.deepEqual(chat.errorParts(e),['The engine did not finish the reply normally; no pair was saved.',' ',{id:'INCOMPLETE_RESPONSE · STOP_REASON_LENGTH'},' ','Thinking tokens count toward this limit.']);
  assert.deepEqual(chat.errorParts(new Error('x')),['x']);
});

// ------------------------------------------------------------------ Markdown
const types=nodes=>nodes.map(n=>n.type);
test('Markdown parses headings, lists, emphasis, code and tables without changing text',()=>{
  const ast=md.parse('# عنوان\n\n**غامق** *مائل* `x`\n\n- أ\n- ب\n  - ج\n\n1. one\n2. two\n\n```py\nprint(1)\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |');
  assert.deepEqual(types(ast),['heading','paragraph','list','list','code','table']);
  assert.equal(ast[2].items[1].blocks[0].type,'list','nested list');
  assert.equal(ast[4].text,'print(1)');assert.equal(ast[4].lang,'py');
  assert.deepEqual(types(ast[1].children),['strong','text','em','text','code']);
});

test('an unfinished code fence while streaming still renders as code',()=>{
  const ast=md.parse('قبل\n```js\nlet a = 1;');
  assert.deepEqual([ast[1].type,ast[1].closed,ast[1].text],['code',false,'let a = 1;']);
});

test('only http, https and mailto links survive; everything else stays text',()=>{
  for(const bad of ['javascript:alert(1)','JAVASCRIPT:alert(1)','data:text/html;base64,PHNjcmlwdD4=','vbscript:x','//evil.example','file:///etc/passwd','/relative']){
    assert.equal(md.safeHref(bad),null,bad);
    const flat=JSON.stringify(md.parse(`[x](${bad})`));
    assert.ok(!flat.includes('"type":"link"'),bad);
  }
  assert.equal(md.safeHref('https://example.org/a?b=1'),'https://example.org/a?b=1');
  assert.equal(md.parse('<https://example.org>')[0].children[0].href,'https://example.org/');
  assert.equal(md.parse('see https://example.org/x.')[0].children[1].href,'https://example.org/x');
});

test('raw HTML is never interpreted: it is plain text in the tree',()=>{
  const flat=md.parse('<img src=x onerror=alert(1)><script>alert(1)</script>');
  assert.deepEqual(types(flat[0].children),['text']);
  assert.equal(flat[0].children[0].text,'<img src=x onerror=alert(1)><script>alert(1)</script>');
});

test('the DOM builder only uses createElement/createTextNode, never innerHTML',()=>{
  const src=require('node:fs').readFileSync('static/chat-markdown.js','utf8');
  assert.ok(!/innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function/.test(src));
  const chatSrc=require('node:fs').readFileSync('static/chat.js','utf8');
  assert.ok(!/innerHTML|insertAdjacentHTML/.test(chatSrc),'chat.js builds nodes, never HTML strings');
});

test('pathological input is bounded',()=>{
  const long='*'.repeat(50000)+'x';
  const started=Date.now();md.parse(long);md.parse('['.repeat(20000));md.parse('`'.repeat(20000));
  assert.ok(Date.now()-started<2000,'parsing stays fast');
  const huge='a'.repeat(300000);
  assert.deepEqual(types(md.parse(huge)),['paragraph'],'over the limit renders as one text paragraph');
});

// ---------------------------------------------------------------------------
// Ported from PR #21 (95e7604, tests/chat-ui.test.cjs) onto the Chat V2 API.
test('(PR #21) presets require the actual engine ceiling and an explicit unverified memory estimate',()=>{
  const snapshot={recommendation:{budget_ceiling:8192,model_max_context:131072,runtime_context:8192,candidates:[
    {context:4096,assessment:'ESTIMATE_FITS_FREE_VRAM',estimated_required_bytes:5},
    {context:8192,assessment:'ESTIMATE_EXCEEDS_FREE_VRAM',estimated_required_bytes:10},
    {context:16384,assessment:'ESTIMATE_FITS_FREE_VRAM',estimated_required_bytes:15}]}};
  assert.deepEqual(chat.budgetPresets(snapshot).map(p=>[p.id,p.context,p.reply,p.enabled]),[['light',4096,1024,true],['balanced',8192,2048,false],['long',16384,3072,false]]);
  assert.equal(chat.budgetPresets({recommendation:{model_max_context:131072}}).every(p=>!p.enabled),true);
  assert.equal(chat.budgetPresets().every(p=>!p.enabled),true);
  assert.equal(chat.budgetPresets({recommendation:{budget_ceiling:4096,candidates:[{context:8192,assessment:'ESTIMATE_FITS_FREE_VRAM'}]}})[0].enabled,false,'never borrow a larger estimate');
  assert.equal(chat.budgetPresets({recommendation:{budget_ceiling:4096,candidates:[{context:4096,assessment:'ESTIMATE_FITS_FREE_VRAM'}]}})[0].enabled,false,'missing estimate bytes remain unknown');
  assert.deepEqual(chat.budgetPresets().map(p=>p.reason),['Engine ceiling unknown','Engine ceiling unknown','Engine ceiling unknown']);
});

test('(PR #21) manual budgets preserve backend integer bounds without rounding',()=>{
  for(const [context,reply] of [[128,1],[4096,1024],[1048576,8192]])assert.equal(chat.validBudgets(context,reply),true);
  for(const [context,reply] of [[127,1],[4096.5,1024],[4096,0],[128,128],[4096,4096],[16384,8193],[1048577,1],[NaN,1]])assert.equal(chat.validBudgets(context,reply),false);
});

test('(PR #21) send availability and Enter share guards; IME, repeat, empty, busy, closed and wrong model never send',()=>{
  const session={status:'OPEN',busy:false};
  assert.equal(chat.canSend(' draft ',session,false,true),true);
  for(const [text,s,pending,ready] of [[' ',session,false,true],['x',null,false,true],['x',session,true,true],['x',{...session,busy:true},false,true],['x',{status:'ARCHIVED'},false,true],['x',session,false,false]])assert.equal(chat.canSend(text,s,pending,ready),false);
  const enter={key:'Enter',shiftKey:false,isComposing:false,keyCode:13,repeat:false};
  assert.equal(chat.shouldSendOnEnter(enter),true);
  for(const change of [{key:'a'},{shiftKey:true},{isComposing:true},{keyCode:229},{repeat:true},{composing:true}])assert.equal(chat.shouldSendOnEnter({...enter,...change}),false);
});

test('(PR #21) controller rejects guarded sends before any API call',async()=>{
  const calls=[];const c=new chat.ChatController(async(...args)=>calls.push(args),()=>{});
  for(const [session,pending,modelReady,text] of [[null,false,true,'x'],[{status:'ARCHIVED'},false,true,'x'],[{status:'OPEN',busy:true},false,true,'x'],[{status:'OPEN'},true,true,'x'],[{status:'OPEN'},false,false,'x'],[{status:'OPEN'},false,true,' ']]){
    c.session=session;c.pending=pending;c.modelReady=modelReady;await assert.rejects(()=>c.send(text));
  }
  assert.deepEqual(calls,[]);
});

test('(PR #21) backslash-escaped Markdown delimiters remain exact literal source',()=>{
  for(const raw of [String.raw`\*\*literal\*\*`,String.raw`\**literal**`,String.raw`\*literal\*`,String.raw`*literal\*`,String.raw`\`literal\``])assert.deepEqual(md.inline(raw),[{type:'text',text:raw}]);
  assert.deepEqual(md.inline(String.raw`\**literal** then **bold**`),[{type:'text',text:String.raw`\**literal** then `},{type:'strong',children:[{type:'text',text:'bold'}]}]);
  const blocks=md.parse('literal\\nnext &lt;b&gt; [x](javascript:alert(1))');
  assert.equal(blocks.length,1);assert.ok(!JSON.stringify(blocks).includes('"type":"link"'),'unsafe link stays text');
  assert.ok(JSON.stringify(blocks).includes('&lt;b&gt;'),'entities are not decoded');
});
