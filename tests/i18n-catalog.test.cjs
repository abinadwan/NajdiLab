// UX-21: static coverage of the Arabic catalog using the real translation function.
// Hidden markup (dialogs, edit panels) and state-dependent messages (toasts, confirms, titles)
// are not all visible during a browser walk, so they are checked here from source.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function loadI18n(){
  const listeners={};
  const documentElement={attributes:{},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this.attributes[k];}};
  const window={localStorage:{getItem:()=>null,setItem(){}},document:{documentElement,readyState:'complete',title:'',
    querySelectorAll:()=>[],body:null,createTreeWalker(){return {nextNode:()=>false};}},
    NodeFilter:{SHOW_ELEMENT:1,SHOW_TEXT:4},MutationObserver:class{observe(){}},addEventListener(t,f){listeners[t]=f;},
    dispatchEvent(){},CustomEvent:class{},Intl};
  window.window=window;
  vm.createContext(window);
  vm.runInContext(fs.readFileSync('static/i18n-ar.js','utf8'),window);
  vm.runInContext(fs.readFileSync('static/localization.js','utf8'),window);
  return window.NajdiI18n;
}
const I18N=loadI18n();
// Strings that are product/format names in every language.
const LITERAL=new Set(['NajdiLab','SFT','DPO','JSONL','SFT JSONL']);
const arabic=/[؀-ۿ]/;
function untranslated(strings){
  return [...new Set(strings)].filter(text=>{
    if(LITERAL.has(text)||!/[A-Za-z]{2,}/.test(text))return false;
    const shown=I18N.translate(text,'ar');
    return shown===text||!arabic.test(shown);
  });
}

// Minimal tokenizer for the generated index.html: text nodes and UI attributes, skipping the
// same containers the runtime localizer skips.
function htmlStrings(html){
  const out=[],stack=[];
  const SKIP_TAGS=new Set(['script','style','code','pre','textarea','bdi','kbd','samp']);
  const VOID=new Set(['br','img','input','meta','link','hr','source']);
  const skipping=()=>stack.some(e=>SKIP_TAGS.has(e.tag)||e.attrs.dir==='auto'||e.attrs.translate==='no');
  const re=/<!--[\s\S]*?-->|<![^>]*>|<\/?([a-zA-Z0-9-]+)((?:\s+[^\s=>\/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*\/?>|([^<]+)/g;
  let m;
  while((m=re.exec(html))){
    if(m[3]!==undefined){const text=m[3].replace(/\s+/g,' ').trim();if(text&&!skipping())out.push(text.replace(/&amp;/g,'&').replace(/&gt;/g,'>').replace(/&lt;/g,'<'));continue;}
    if(!m[1])continue;
    const tag=m[1].toLowerCase(),closing=m[0].startsWith('</');
    if(closing){const i=stack.map(e=>e.tag).lastIndexOf(tag);if(i>=0)stack.length=i;continue;}
    const attrs={};for(const a of (m[2]||'').matchAll(/([^\s=]+)(?:\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+)))?/g))attrs[a[1].toLowerCase()]=a[3]??a[4]??a[5]??'';
    const inheritedNo=stack.some(e=>e.attrs.translate==='no')||attrs.translate==='no';
    for(const name of ['placeholder','aria-label','title','alt'])if(attrs[name]&&!inheritedNo)out.push(attrs[name]);
    if(!VOID.has(tag)&&!m[0].endsWith('/>'))stack.push({tag,attrs});
  }
  return out;
}

// String arguments of UI message sinks in the scripts; ${...} becomes a sample value.
function sinkStrings(source){
  const out=[];
  const literal=String.raw`'((?:[^'\\\n]|\\.)*)'|\x60((?:[^\x60\\]|\\.|\$\{(?:[^{}]|\{[^{}]*\})*\})*)\x60`;
  const sinks=[String.raw`toast\(`,String.raw`\btr\(`,String.raw`NajdiI18n\.t\(`,String.raw`textContent\s*=\s*`,String.raw`\bstatus\(`,String.raw`notice\s*=\s*`];
  for(const sink of sinks){
    for(const m of source.matchAll(new RegExp(sink+'(?:'+literal+')','g'))){
      let text=m[1]??m[2];if(text==null)continue;
      text=text.replace(/\$\{(?:[^{}]|\{[^{}]*\})*\}/g,'7').replace(/\\'/g,"'").replace(/\s+/g,' ').trim();
      if(text&&!/[<>]/.test(text))out.push(text);
    }
  }
  return out;
}

test('every text in index.html has an Arabic translation',()=>{
  const missing=untranslated(htmlStrings(fs.readFileSync('static/index.html','utf8')));
  assert.deepEqual(missing,[],'missing Arabic:\n'+missing.join('\n'));
});

test('every toast, confirm, status and fixed message in the scripts has an Arabic translation',()=>{
  const strings=['static/app.js','static/chat.js','static/chat-markdown.js','static/integrations.js','static/theme.js','static/prepare-data.js','static/my-versions.js'].flatMap(f=>sinkStrings(fs.readFileSync(f,'utf8')));
  assert.ok(strings.length>60,'expected to find the UI message sinks');
  const missing=untranslated(strings);
  assert.deepEqual(missing,[],'missing Arabic:\n'+missing.join('\n'));
});

test('guided workspace and version dialogs translate labels created through DOM helpers',()=>{
  const strings=['static/prepare-data.js','static/my-versions.js'].flatMap(file=>{
    const source=fs.readFileSync(file,'utf8');
    return [...source.matchAll(/'((?:[^'\\\n]|\\.)*)'/g)]
      .map(match=>match[1].replace(/\\'/g,"'"))
      .filter(text=>/^[A-Z][A-Za-z0-9]* /.test(text)&&!/[{}<>]/.test(text));
  });
  assert.ok(strings.length>40,'expected fixed DOM labels and compatibility explanations');
  const missing=untranslated(strings);
  assert.deepEqual(missing,[],'missing Arabic:\n'+missing.join('\n'));
});

test('Gold ownership, deletion and export compatibility explanations have Arabic translations',()=>{
  const source=fs.readFileSync('app/gold_management.py','utf8');
  const errors=[...source.matchAll(/(?:_error\('[A-Z_]+',\s*|OSError\()'((?:[^'\\]|\\.)*)'/g)]
    .map(match=>match[1].replace(/\\'/g,"'"));
  const reasons=[...source.matchAll(/\breturn '((?:[^'\\]|\\.)*)'/g)]
    .map(match=>match[1].replace(/\\'/g,"'"));
  assert.ok(errors.length>30&&reasons.length>8,'expected deletion refusals and profile compatibility reasons');
  const missing=untranslated([...errors,...reasons]);
  assert.deepEqual(missing,[],'missing Arabic:\n'+missing.join('\n'));
  for(const message of [
    'multi_turn.jsonl: incomplete collected context: manual_sft_items:17',
    'multi_turn.jsonl: record has no messages: manual_sft_items:17',
    'multi_turn.jsonl: record has no user message: manual_sft_items:17',
    'multi_turn.jsonl: invalid message in manual_sft_items:17 at 3',
    'multi_turn.jsonl: the training target is not uniquely identified: manual_sft_items:17'
  ]){
    const translated=I18N.translate(message,'ar');
    assert.ok(arabic.test(translated));
    assert.ok(translated.includes('multi_turn.jsonl')&&translated.includes('manual_sft_items:17'),'technical identities stay literal');
  }
});

test('view titles, review statuses and error tags are translated',()=>{
  const src=fs.readFileSync('static/app.js','utf8');
  const block=name=>src.slice(src.indexOf(name),src.indexOf('};',src.indexOf(name)));
  const values=[...block('const titles = {').matchAll(/'([^']+)'/g)].map(m=>m[1]).filter(v=>v.includes(' ')||/^[A-Z]/.test(v));
  const maps=['const statusArabic = {','const tagArabic = {'].flatMap(name=>[...block(name).matchAll(/:'([^']+)'/g)].map(m=>m[1]));
  const missing=untranslated([...values,...maps]);
  assert.deepEqual(missing,[],'missing Arabic:\n'+missing.join('\n'));
});

test('patterns translate embedded values and keep free text as is',()=>{
  assert.equal(I18N.translate('Showing 1–100 of 250','ar'),'عرض 1–100 من 250');
  assert.equal(I18N.translate('Current theme: Dark','ar'),'السمة الحالية: داكن');
  assert.equal(I18N.translate('Unable to save: Disk full','ar'),'تعذّر الحفظ: Disk full');
  assert.equal(I18N.translate('  Approve  ','ar'),'  اعتماد  ','surrounding whitespace is preserved');
  assert.equal(I18N.translate('Approve','en'),'Approve');
  assert.equal(I18N.translate('A sentence nobody translated','ar'),'A sentence nobody translated');
});

test('every Arabic value contains Arabic script or is a declared literal',()=>{
  const catalog=vm.runInNewContext(fs.readFileSync('static/i18n-ar.js','utf8')+';window.NajdiI18nCatalogs.ar',{window:{}});
  const bad=Object.entries(catalog.exact).filter(([en,ar])=>!arabic.test(ar)&&!LITERAL.has(en)).map(([en])=>en);
  assert.deepEqual(bad,[]);
  for(const [en,ar] of catalog.patterns){
    const names=s=>[...s.matchAll(/\{(\w+)\}/g)].map(m=>m[1]).sort().join();
    assert.equal(names(en),names(ar),'placeholders must match: '+en);
  }
});

// Phase C / AI-02: Chat engine refusals reach the page as error.message. Every fixed message in
// app/chat_engine.py, including the four content-free RESULT_MISMATCH diagnostics, must read in Arabic.
function chatEngineMessages(){
  const src=fs.readFileSync('app/chat_engine.py','utf8');
  const dict=name=>{const start=src.indexOf(name+' = {');assert.ok(start>=0,name);
    return Object.fromEntries([...src.slice(start,src.indexOf('\n}',start)).matchAll(/'([A-Z_]+)':\s*'((?:[^'\\]|\\.)*)'/g)].map(m=>[m[1],m[2].replace(/\\'/g,"'")]));};
  const errors=dict('WORKER_ERRORS'),details=dict('WORKER_MISMATCH_DETAILS');
  assert.deepEqual(Object.keys(details).sort(),['INSTANCE_REFERENCE','PROMPT_TOKEN_COUNT','STREAM_CONTENT','STRUCTURED_OUTPUT']);
  const raised=[...src.matchAll(/IntegrationError\('[A-Z_]+',\s*f?'((?:[^'\\]|\\.)*)'/g)].map(m=>m[1].replace(/\\'/g,"'").replace(/\{[A-Z_]+\}/g,'600'));
  const composite=Object.values(details).map(detail=>errors.RESULT_MISMATCH+' Integrity check: '+detail);
  return {all:[...Object.values(errors),...raised,...composite],composite};
}

test('every Chat engine refusal, including the AI-02 integrity diagnostics, has an Arabic translation',()=>{
  const {all,composite}=chatEngineMessages();
  assert.ok(all.length>25,'expected to find the Chat engine messages');
  const missing=untranslated(all);
  assert.deepEqual(missing,[],'missing Arabic:\n'+missing.join('\n'));
  for(const text of composite)assert.notEqual(I18N.translate(text,'ar'),I18N.translate(composite[0].split(' Integrity check: ')[0],'ar'),'the diagnostic stays visible: '+text);
});

// Chat V2: every fixed server message a chat page can show (workspace, permanent
// deletion, NajdiLab Native, completion checks) has an Arabic translation, and the
// INCOMPLETE_RESPONSE detail stays distinguishable from the generic message.
function pythonMessages(file){
  const src=fs.readFileSync(file,'utf8');
  return [...src.matchAll(/IntegrationError\(\s*["'][A-Z_]+["'],\s*f?(["'])((?:(?!\1)[^\\]|\\.)*)\1/g)]
    .map(m=>m[2].replace(/\\'/g,"'").replace(/\{[^}]+\}/g,'600'));
}
test('every Chat V2 server message has an Arabic translation',()=>{
  const files=['app/chat_workspace.py','app/chat_deletion.py','app/native_runtime.py'];
  const src=fs.readFileSync('app/chat_workspace.py','utf8');
  const start=src.indexOf('INCOMPLETE_CHECKS = {');
  const block=src.slice(start,src.indexOf('\n}',start));
  // Each predicate has a fixed message (PR #21 wording) and an optional fixed hint.
  const fixed=[...block.matchAll(/'((?:[^'\\]|\\.)*)'/g)].map(m=>m[1].replace(/\\'/g,"'")).filter(t=>/[a-z] /.test(t));
  const native=fs.readFileSync('app/native_runtime.py','utf8');
  const startup=[...native.matchAll(/'NATIVE_[A-Z_]+',\s*\n?\s*'((?:[^'\\]|\\.)*)'\)/g)].map(m=>m[1].replace(/\\'/g,"'"));
  const all=[...files.flatMap(pythonMessages),...fixed,...startup];
  assert.ok(fixed.length>=7,'expected the completion messages and hints: '+fixed.length);
  assert.ok(all.length>40,'expected to find the server messages: '+all.length);
  const missing=untranslated(all);
  assert.deepEqual(missing,[],'missing Arabic:\n'+missing.join('\n'));
});
