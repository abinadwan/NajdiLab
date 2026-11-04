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
  const strings=['app/hf_hub.py','app/model_store.py','app/model_service.py','app/model_advisor.py','app/model_discovery.py'].flatMap(pythonMessages);
  assert.ok(strings.length>45,'expected the server messages: '+strings.length);
  const absent=missing(strings);
  assert.deepEqual(absent,[],'missing Arabic:\n'+absent.join('\n'));
});

test('every managed llama.cpp runtime message has an Arabic translation, numbers and names kept',()=>{
  const strings=['app/managed_runtime.py','app/runtime_catalog.py','app/native_runtime.py'].flatMap(pythonMessages);
  assert.ok(strings.length>50,'expected the runtime messages: '+strings.length);
  // Classified probe failures and built sentences are not IntegrationError literals.
  const src=fs.readFileSync('app/managed_runtime.py','utf8');
  const probe=[...src.matchAll(/'RUNTIME_GPU_[A-Z_]+',\s*\n\s*'((?:[^'\\]|\\.)*)'/g)].map(m=>m[1].replace(/\\'/g,"'"));
  assert.equal(probe.length,3);
  const absent=missing([...strings,...probe]);
  assert.deepEqual(absent,[],'missing Arabic:\n'+absent.join('\n'));
  for(const text of ['This NVIDIA driver supports CUDA up to 12.6; this package needs 13.4. Update the driver or choose another package.',
    'CUDA 12.4 supports compute capability 5.0 to 9.0; this GPU is outside that range.',
    'This CUDA build does not see a CUDA device here. Choose another package.',
    'llama-b12059-bin-win-cpu-x64.zip in the archives folder does not match the pinned SHA-256. Remove it; NajdiLab does not delete your files.',
    'cudart-llama-bin-win-cuda-13.4-x64.zip does not match the pinned SHA-256; nothing was installed.',
    'GitHub answered HTTP 404; nothing was installed.']){
    const ar=I18N.translate(text,'ar');
    assert.notEqual(ar,text,text);
    for(const kept of text.match(/\d+(?:\.\d+)?|[\w.-]+\.zip|CUDA/g))assert.ok(ar.includes(kept),`${kept} kept in: ${ar}`);
  }
});

test('provenance evidence sentences translate with repository names kept',()=>{
  for(const text of ['Declares that it is a finetune of najdi-labs/Najm-3B-Instruct, so its weights differ from the original.',
    'Its name says it was changed ("Uncensored"), although it declares only a quantized copy of najdi-labs/Najm-3B-Instruct.',
    'Published by najdi-labs, the Hugging Face account that also published najdi-labs/Najm-3B-Instruct. Only members of an account can publish under its name.',
    'This is a GGUF conversion (quantized weights) by the original publisher, not the original unmodified weights.',
    "It claims to convert google/gemma-4-12B-it, but its name does not contain that model's name.",
    'A GGUF conversion of najdi-labs/Najm-3B-Instruct by community-quant, a different account from the original publisher.',
    'The repository names other/Base but does not say how it relates to it.',
    'The origin of najdi-labs/Najm-3B-Instruct could not be checked on Hugging Face, so this source is not confirmed.',
    'partner-ai/Partner-4B-Instruct is a finetune of najdi-labs/Najm-3B-Instruct, which another account published; its weights differ from that original.',
    "Popularity only chooses which models are checked (Hugging Face's most downloaded and trending GGUF models). The order comes from the Smart Model Advisor on this computer: compatibility first, then provenance, license and where the model would run."]){
    const ar=I18N.translate(text,'ar');
    assert.notEqual(ar,text,text);
    for(const kept of text.match(/[\w-]+\/[\w.-]*\w/g)||[])assert.ok(ar.includes(kept),`${kept} kept in: ${ar}`);
  }
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
