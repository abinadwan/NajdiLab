const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

// Hugging Face Direct and the Chat context indicator: every fixed text the Model library shows
// (models.js), and every server message of the new modules, has an Arabic translation.
function loadI18n(){
  const store={};
  const window={document:{documentElement:{lang:'en',dir:'ltr',setAttribute(){},removeAttribute(){}},readyState:'complete',
    querySelectorAll:()=>[],addEventListener(){},body:null},localStorage:{getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=v;}},
    addEventListener(){},MutationObserver:class{observe(){}}};
  window.window=window;vm.createContext(window);
  vm.runInContext(fs.readFileSync('static/i18n-ar.js','utf8'),window);
  vm.runInContext(fs.readFileSync('static/localization.js','utf8'),window);
  return window.NajdiI18n;
}
const I18N=loadI18n();
// Format names stay in Latin script in both languages (docs/localization.md).
const SAME={'SHA-256':true,'GPU':true};
const missing=strings=>[...new Set(strings)].filter(t=>!SAME[t]&&I18N.translate(t,'ar')===t);

// UI text in models.js: quoted literals that read as English sentences or labels.
function modelStrings(){
  const src=fs.readFileSync('static/models.js','utf8');
  const out=[];
  for(const m of src.matchAll(/'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`/g)){
    let text=(m[1]??m[2]).replace(/\\'/g,"'");
    if(m[2]!=null&&/\$\{/.test(text))continue; // URLs, selectors and ids are built with templates
    if(!/^[A-Z][a-z]/.test(text)||!/[a-z]/.test(text)||/^(GET|POST|ArrowLeft|ArrowRight|Tiny|GGUF$)/.test(text))continue;
    if(/[{}<>=;]|\/api\/|^[A-Z][a-z]+[A-Z]/.test(text))continue;
    out.push(text.trim());
  }
  return out;
}

function pythonMessages(file){
  const src=fs.readFileSync(file,'utf8');
  const found=[];
  for(const re of [/(?:IntegrationError|HubError)\(\s*'[A-Z_]+',\s*f?'((?:[^'\\]|\\.)*)'/g,/_reason\('[A-Z_]+',\s*'((?:[^'\\]|\\.)*)'/g,
                   /'message':\s*'((?:[^'\\]|\\.)*)'/g])
    for(const m of src.matchAll(re))found.push(m[1].replace(/\\'/g,"'").replace(/\{[^}]+\}/g,'600'));
  return found;
}

test('every fixed Model library text has an Arabic translation',()=>{
  const strings=modelStrings();
  assert.ok(strings.length>60,'expected the Model library texts: '+strings.length);
  const absent=missing(strings);
  assert.deepEqual(absent,[],'missing Arabic:\n'+absent.join('\n'));
});

test('every Hugging Face Direct server message and advisor reason has an Arabic translation',()=>{
  const strings=['app/hf_hub.py','app/model_store.py','app/model_service.py','app/model_advisor.py'].flatMap(pythonMessages);
  assert.ok(strings.length>45,'expected the server messages: '+strings.length);
  const absent=missing(strings);
  assert.deepEqual(absent,[],'missing Arabic:\n'+absent.join('\n'));
});

test('context indicator sentences translate with their measured numbers kept',()=>{
  // Exact output, so a generic pattern (for example "{a} of {b}") can never capture these sentences.
  assert.equal(I18N.translate('Context used: 13 + 1024 reserved of 4096 tokens (25%)','ar'),'السياق المستخدم: 13 + 1024 محجوزة من 4096 رمزًا (25٪)');
  assert.equal(I18N.translate('About 3059 tokens left for the next message (estimate)','ar'),'نحو 3059 رمزًا متبقية للرسالة التالية (تقدير)');
  const samples=['Context used: 1700 + 1024 reserved of 4096 tokens (67%)','About 1372 tokens left for the next message (estimate)',
    '2000 tokens left after this prompt (measured)','About 3072 tokens available for the first message (estimate)',
    'This conversation has used 72% of its context. About 1100 tokens remain for new messages.',
    'Approaching the context limit: 87% used, about 500 tokens left. Consider starting a new chat soon.',
    'Context almost full: 96% used, about 100 tokens left. A longer message will not fit; NajdiLab then keeps this conversation read-only and opens a new chat with your draft kept.',
    'The previous conversation needed 3900 prompt tokens + 1024 reserved for the reply, more than its 4096-token context. It is saved unchanged and read-only; nothing was summarised or dropped. This new chat starts empty, with collection off.'];
  for(const text of samples){
    const ar=I18N.translate(text,'ar');
    assert.notEqual(ar,text,text);
    for(const number of text.match(/\d+/g))assert.ok(ar.includes(number),`${number} kept in: ${ar}`);
  }
});
