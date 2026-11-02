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
  const e=new chat.ChatError('Engine did not return…','INCOMPLETE_RESPONSE','STOP_REASON_LENGTH');
  assert.deepEqual(chat.errorParts(e),['Engine did not return…',' ',{id:'INCOMPLETE_RESPONSE · STOP_REASON_LENGTH'}]);
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
