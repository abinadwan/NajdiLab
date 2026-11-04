/* UX-21 Arabic RTL / English LTR acceptance in Chromium against the disposable chat fixture. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {test}=require('node:test');
const puppeteer=require('puppeteer-core');

const VIEWS=['dashboard','chat','models','review-queue','conversations','reviewed','add-data','manual-data','dataset',
  'dataset-health','balancer','dataset-versions','eval-sets','exports','analytics','settings'];
// Product, protocol and format names stay in Latin script in both languages.
const LATIN_ALLOWED=['NajdiLab','llama.cpp','Ollama','LM Studio','Unsloth Studio','Unsloth','TRL','Hugging Face','SFT','DPO','JSONL','JSON','SHA-256',
  'API','GPU','RAM','VRAM','HTTP','UUID','RAG','p90','p95','Gold','completion_only_loss=True','packing=False','Reply with OK.',
  '127.0.0.1','application/json','gold-v009-remediation-draft','Ctrl + Enter','Shift+Enter','Enter','Markdown','HTML',
  // Model library: the GGUF file format, the Hugging Face host name, and the product name
  // "NajdiLab Native", which the catalog writes as "نجدي لاب Native" in Arabic.
  'GGUF','huggingface.co','Native',
  // Export Center: the trainer's dataset format, Python, and Studio's own option label (shown in English there).
  'Alpaca','Python','Train on completions'];

function scanUntranslated(allowed){
  const skip='script,style,code,pre,textarea,bdi,kbd,samp,time,[dir="auto"],[dir="ltr"],[translate="no"],[data-i18n-skip]';
  // Identifiers (dataset version and file names) stay in Latin script in every language.
  const identifiers=[/gold-v\d+[\w.-]*/g,/[\w-]+\.(?:jsonl|json)\b/g];
  const residue=text=>{let rest=text;for(const word of allowed)rest=rest.split(word).join(' ');for(const re of identifiers)rest=rest.replace(re,' ');return /[A-Za-z]{2,}/.test(rest);};
  const found=new Set();
  const visible=el=>el.checkVisibility?el.checkVisibility({checkOpacity:false,checkVisibilityCSS:true}):!!el.offsetParent;
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){
    const node=walker.currentNode,parent=node.parentElement,text=node.nodeValue.trim();
    if(!text||!parent||parent.closest(skip)||!visible(parent))continue;
    if(residue(text))found.add(text);
  }
  for(const el of document.querySelectorAll('[placeholder],[aria-label],[title],[alt]')){
    if(el.closest('code,pre,bdi,[translate="no"],[data-i18n-skip]')||!visible(el))continue;
    for(const name of ['placeholder','aria-label','title','alt']){
      const value=el.getAttribute(name);
      if(value&&residue(value))found.add(`@${name}: ${value}`);
    }
  }
  return [...found];
}

test('Arabic and English interface in Chromium',async t=>{
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{stdio:['ignore','pipe','pipe']});
  let browser;
  try{
    const base=await new Promise((resolve,reject)=>{
      let out='',err='';const timer=setTimeout(()=>reject(Error('fixture timeout: '+err)),20000);
      child.stdout.on('data',c=>{out+=c;const m=out.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
      child.stderr.on('data',c=>err+=c);child.once('exit',code=>{clearTimeout(timer);reject(Error('fixture exited '+code+': '+err));});
    });
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    const page=await browser.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setViewport({width:1440,height:1000});
    await page.goto(base+'/');
    await page.waitForSelector('#view-dashboard.active');
    const doc=()=>page.evaluate(()=>({lang:document.documentElement.lang,dir:document.documentElement.dir}));

    await t.test('English is the default and left-to-right',async()=>{
      assert.deepEqual(await doc(),{lang:'en',dir:'ltr'});
      assert.equal(await page.$eval('[data-view="dashboard"] .nav-label',e=>e.textContent.trim().split('\n')[0].trim()).catch(()=>null)!==null,true);
    });

    await t.test('choosing Arabic switches language and direction immediately and persists',async()=>{
      await page.select('#language-select','ar');
      assert.deepEqual(await doc(),{lang:'ar',dir:'rtl'});
      assert.equal(await page.evaluate(()=>localStorage.getItem('najdilab.language')),'ar');
      await page.reload();await page.waitForSelector('#view-dashboard.active');
      assert.deepEqual(await doc(),{lang:'ar',dir:'rtl'});
      assert.equal(await page.$eval('#language-select',e=>e.value),'ar');
      assert.equal(await page.$eval('#language-select-settings',e=>e.value),'ar');
    });

    await t.test('no untranslated English remains in any view',async()=>{
      const report={};
      for(const view of VIEWS){
        await page.click(`.nav-item[data-view="${view}"]`).catch(async()=>{await page.evaluate(v=>switchView(v),view);});
        await page.waitForSelector(`#view-${view}.active`);
        await new Promise(r=>setTimeout(r,700));
        const found=await page.evaluate(scanUntranslated,LATIN_ALLOWED);
        if(found.length)report[view]=found;
      }
      assert.deepEqual(report,{},'untranslated text:\n'+JSON.stringify(report,null,1));
    });

    const settle=()=>new Promise(r=>setTimeout(r,600));
    const scanInto=async(report,label)=>{const found=await page.evaluate(scanUntranslated,LATIN_ALLOWED);if(found.length)report[label]=found;};

    await t.test('data states, dialogs and messages are fully Arabic; user content is never translated',async()=>{
      // Synthetic data through the real API. The assistant text equals a catalog key on purpose.
      await page.evaluate(async()=>{
        const conv=await api('/api/v1/conversations',{method:'POST',body:JSON.stringify({title:'Synthetic RTL conversation',channel:'manual'})});
        const id=conv.conversation.id;
        await api('/api/v1/messages',{method:'POST',body:JSON.stringify({conversation_id:id,role:'user',content:'Please answer in English'})});
        await api('/api/v1/messages',{method:'POST',body:JSON.stringify({conversation_id:id,role:'assistant',content:'Approve'})});
        await api('/api/v1/manual-data/direct',{method:'POST',body:JSON.stringify({text:'Synthetic direct text',language_layer:'najdi_riyadh',source_type:'human_written',source:'synthetic'})});
      });
      const report={};
      const open=async view=>{await page.evaluate(v=>switchView(v),view);await page.waitForSelector(`#view-${view}.active`);await settle();};

      await open('review-queue');
      await page.waitForFunction(()=>!document.querySelector('#review-workspace').classList.contains('hidden'));
      assert.equal(await page.$eval('#original-response',e=>e.textContent),'Approve','user content must stay exactly as stored');
      await scanInto(report,'review-queue');
      await page.click('#edit-review');await page.click('[data-status="CONTENT_CORRECTION"]');await settle();
      await scanInto(report,'review-queue: correction editor');
      await page.click('#cancel-edit-review');

      await open('conversations');
      await page.click('.conversation-item');await page.waitForSelector('#conversation-detail .chat-stream');await settle();
      const texts=await page.$$eval('#conversation-detail .message p',els=>els.map(e=>e.textContent));
      assert.deepEqual(texts,['Please answer in English','Approve']);
      await scanInto(report,'conversations: detail');

      await open('manual-data');
      await page.waitForSelector('#manual-list [data-action="view"]');
      await scanInto(report,'manual-data');
      await page.click('#manual-list [data-action="view"]');await page.waitForSelector('#manual-dialog[open]');await settle();
      await scanInto(report,'manual-data: dialog');
      await page.evaluate(()=>document.querySelector('#manual-dialog').close());

      await open('dataset-health');
      await page.waitForSelector('#refresh-health:not([disabled])');
      await page.click('#refresh-health');await page.waitForSelector('#health-results:not(.hidden)');await settle();
      await scanInto(report,'dataset-health: results');
      await open('balancer');
      await page.waitForSelector('#run-balance:not([disabled])');
      await page.click('#run-balance');await page.waitForSelector('#balance-results:not(.hidden)');await settle();
      await scanInto(report,'balancer: results');
      await open('dataset-versions');
      await page.waitForSelector('#version-list [data-version-name]');
      await page.click('#version-list [data-version-name]');await settle();
      await scanInto(report,'dataset-versions: detail');
      await open('eval-sets');await settle();
      await scanInto(report,'eval-sets: results');
      await open('exports');await settle();
      await scanInto(report,'exports');

      // Client validation message and an unknown server message.
      await open('add-data');
      await page.evaluate(()=>document.querySelectorAll('#sft-turns .turn-row button').forEach(b=>b.click()));
      await page.click('#form-sft button[type="submit"]');
      await page.waitForFunction(()=>document.querySelector('#toast .toast-message')?.textContent.includes('أضف'));
      await page.evaluate(()=>toast('Disk quota exceeded on the synthetic store',true));
      assert.equal(await page.$eval('#toast .toast-message',e=>e.firstChild.nodeValue),'رسالة الخادم: ');
      assert.equal(await page.$eval('#toast .toast-message bdi',e=>[e.dir,e.textContent].join('|')),'ltr|Disk quota exceeded on the synthetic store');
      await scanInto(report,'toast');
      // Wait for the slide-in transition so the button is fully inside the viewport, as for a real user.
      await page.waitForFunction(()=>{const r=document.querySelector('.toast-dismiss').getBoundingClientRect();return r.bottom<=innerHeight&&r.top>=0;});
      await page.click('.toast-dismiss');
      assert.deepEqual(report,{},'untranslated text:\n'+JSON.stringify(report,null,1));
    });

    await t.test('chat session in Arabic keeps messages verbatim and translates its status',async()=>{
      await page.evaluate(()=>switchView('chat'));await page.waitForSelector('#view-chat.active');
      await page.click('#chat-new');await settle();
      const pick=async name=>{await page.evaluate(()=>document.querySelector('#chat-model-button').click());await page.waitForSelector('#chat-model-menu:not([hidden]) .chatv2-model-item');
      await page.evaluate(name=>[...document.querySelectorAll('#chat-model-menu h4')].find(h=>h.textContent===name).nextElementSibling.click(),name);};
      const setup={};
      await page.click('#chat-model-button');await page.waitForSelector('#chat-model-menu:not([hidden])');await settle();await scanInto(setup,'chat: model menu');
      await page.keyboard.press('Escape');
      await page.click('#chat-context-button');await page.evaluate(()=>{document.querySelector('#chat-context-advanced').open=true;});await settle();
      await scanInto(setup,'chat: context menu');await page.keyboard.press('Escape');
      await pick('Ollama');await page.$eval('#chat-draft',e=>{e.value='Synthetic';e.dispatchEvent(new Event('input'));});
      await page.click('#chat-send');await page.waitForSelector('#chat-prepare:not([hidden])');await settle();await scanInto(setup,'chat: preparation card');
      await page.click('#chat-prepare-cancel');await page.$eval('#chat-draft',e=>{e.value='';e.dispatchEvent(new Event('input'));});
      assert.deepEqual(setup,{},'untranslated text:\n'+JSON.stringify(setup,null,1));
      await pick('LM Studio');
      await page.type('#chat-draft','Approve');await page.click('#chat-send');
      await page.waitForFunction(()=>document.querySelectorAll('.chat-message').length===2&&!document.querySelector('.chatv2-msg.streaming'));
      const first=await page.$eval('.chat-message [dir="auto"], .chat-message p',e=>e.textContent);
      assert.equal(first.trim(),'Approve','the user message must not be translated');
      await page.$eval('#chat-collect',e=>e.scrollIntoView({block:'center'}));await page.click('#chat-collect');
      await page.waitForFunction(()=>/[؀-ۿ]/.test(document.querySelector('#chat-notice').textContent));
      await settle();
      const report={};await scanInto(report,'chat: active session');
      await page.click('#chat-info-open');await page.waitForSelector('#chat-panel[open]');
      await page.waitForFunction(()=>document.querySelector('#chat-info').children.length>2);await settle();
      await scanInto(report,'chat: information');
      // Numbers stay untranslated identifiers, but their unit is text: "32768 tokens" must read "32768 رمزًا".
      const units=await page.$eval('#chat-info',e=>[...e.querySelectorAll('[translate="no"]')].map(n=>n.textContent).filter(t=>/\d\s*tokens/.test(t)));
      assert.deepEqual(units,[],'token counts with an untranslated unit in Chat information');
      await page.click('#chat-panel-close');
      assert.deepEqual(report,{},'untranslated text:\n'+JSON.stringify(report,null,1));
    });

    await t.test('right-to-left layout on desktop and at 390px',async()=>{
      await page.evaluate(()=>switchView('dashboard'));await page.waitForSelector('#view-dashboard.active');
      const sides=await page.evaluate(()=>{const s=document.querySelector('.sidebar').getBoundingClientRect(),m=document.querySelector('.main').getBoundingClientRect();return {sidebar:s.left,main:m.left};});
      assert.ok(sides.sidebar>sides.main,'sidebar is on the right in Arabic: '+JSON.stringify(sides));
      await page.setViewport({width:390,height:844});
      const overflow={};
      for(const view of VIEWS){
        await page.evaluate(v=>switchView(v),view);await page.waitForSelector(`#view-${view}.active`);await settle();
        const width=await page.evaluate(()=>document.documentElement.scrollWidth);
        if(width>390)overflow[view]=width;
      }
      assert.deepEqual(overflow,{},'horizontal page overflow at 390px in Arabic');
      const closed=await page.$eval('.sidebar',e=>e.getBoundingClientRect().left);
      assert.ok(closed>=390,'closed mobile menu is off-screen to the right, got left='+closed);
      await page.click('#mobile-menu');
      await page.waitForFunction(()=>document.querySelector('.sidebar').classList.contains('open'));
      await new Promise(r=>setTimeout(r,400));
      const opened=await page.$eval('.sidebar',e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right};});
      assert.ok(Math.abs(opened.right-390)<=1,'open mobile menu is anchored to the right edge: '+JSON.stringify(opened));
      await page.evaluate(()=>document.querySelector('.sidebar').classList.remove('open'));
      await page.setViewport({width:1440,height:1000});
    });

    await t.test('switching back to English restores the source text',async()=>{
      await page.evaluate(()=>switchView('settings'));await page.waitForSelector('#view-settings.active');
      await page.select('#language-select-settings','en');
      assert.deepEqual(await doc(),{lang:'en',dir:'ltr'});
      const arabic=await page.evaluate(()=>/[؀-ۿ]/.test(document.querySelector('.sidebar').innerText+document.querySelector('.topbar').innerText.replace('العربية','')));
      assert.equal(arabic,false);
      assert.equal(await page.$eval('#page-title',e=>e.textContent),'Settings');
    });
    await t.test('blocked browser storage keeps the interface usable in English',async()=>{
      const blocked=await browser.newPage();const blockedErrors=[];blocked.on('pageerror',e=>blockedErrors.push(e.message));
      await blocked.evaluateOnNewDocument(()=>{Object.defineProperty(window,'localStorage',{get(){throw new DOMException('blocked','SecurityError');}});});
      await blocked.goto(base+'/');await blocked.waitForSelector('#view-dashboard.active');
      assert.equal(await blocked.evaluate(()=>document.documentElement.lang),'en');
      // The interface must actually start: navigation is bound and no startup error is shown.
      await blocked.click('.nav-item[data-view="settings"]');
      await blocked.waitForSelector('#view-settings.active',{timeout:5000});
      assert.doesNotMatch(await blocked.$eval('#toast',e=>e.textContent),/Unable to start interface/);
      await blocked.select('#language-select','ar');
      assert.equal(await blocked.evaluate(()=>document.documentElement.dir),'rtl','switching still works for this page view');
      assert.deepEqual(blockedErrors,[]);
      await blocked.close();
    });

    await t.test('remediation redirect page is localized before it redirects',async()=>{
      const stub=await browser.newPage();
      await stub.evaluateOnNewDocument(()=>{try{localStorage.setItem('najdilab.language','ar');}catch{}});
      await stub.setRequestInterception(true);
      stub.on('request',r=>r.url().endsWith('/phase38-review.js')?r.respond({status:200,contentType:'application/javascript',body:''}):r.continue());
      await stub.goto(base+'/phase38-review.html');
      assert.equal(await stub.evaluate(()=>document.documentElement.dir),'rtl');
      assert.equal(await stub.$eval('h1',e=>e.textContent),'مراجعة المعالجة');
      await stub.close();
    });
    assert.deepEqual(errors,[]);
  }finally{
    if(browser)await browser.close();
    child.kill();
  }
});
