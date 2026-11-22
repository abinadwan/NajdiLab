/* PR #21 (95e7604) chat-enhancement acceptance, ported to the Chat V2 interface.
 * Only the disposable fixture and synthetic replies; hardware evidence is mocked in
 * the page. Same guarantees, on the V2.1.0 composer: choosing a model or context is
 * read-only (no /select, no approved preparation), approval is never reused for another
 * chat, Enter/Shift+Enter/IME/repeat/blank guards, exact safe
 * Markdown with a raw view, failed and newer drafts preserved, wrong model never
 * sends, Arabic labels around untranslated content, mobile fit. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const puppeteer=require('puppeteer-core');

(async()=>{
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe'],windowsHide:true});
  let browser;
  try{
    const base=await new Promise((resolve,reject)=>{
      let output='',error='';const timer=setTimeout(()=>reject(Error('Synthetic fixture startup timed out: '+error)),15000);
      child.stdout.on('data',chunk=>{output+=chunk;const match=output.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
      child.stderr.on('data',chunk=>{error+=chunk;});
      child.once('error',reject);child.once('exit',code=>{clearTimeout(timer);reject(Error('Fixture exited '+code+': '+error));});
    });
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    const page=await browser.newPage();await page.evaluateOnNewDocument(()=>{try{localStorage.setItem('najdilab.chat.legacyProviders','1');}catch{}});// The synthetic fixture has no llama-server: Chat checks here use its LM Studio/Ollama runtimes via the Settings opt-in.
   await page.setViewport({width:1280,height:1000});const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.evaluateOnNewDocument(()=>{
      const original=window.fetch.bind(window);window.fixtureCalls=[];window.failNextSend=false;window.wrongModel=false;
      window.fetch=async(route,options={})=>{
        const url=String(route);
        if(options.method==='POST')window.fixtureCalls.push({route:url,body:options.body?JSON.parse(options.body):null});
        if(url.endsWith('/send-stream')&&window.failNextSend){window.failNextSend=false;
          return new Response(JSON.stringify({ok:false,error:'Synthetic send failure',code:'ENGINE_FAILED'}),{status:502,headers:{'Content-Type':'application/json'}});}
        // The runtime selection moved elsewhere: preparation says so, and sending waits for approval.
        if(url==='/api/v1/chat/prepare'&&window.wrongModel)return new Response(JSON.stringify({state:'NEEDS_APPROVAL',needs_select:true,needs_load:false,
          message:'LM Studio must already have this model loaded; NajdiLab will select it for chat.'}),{status:200,headers:{'Content-Type':'application/json'}});
        return original(route,options);
      };
    });
    await page.goto(base+'/chat');await page.waitForSelector('#view-chat.active');
    const setDraft=async value=>page.$eval('#chat-draft',(e,value)=>{e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}));},value);
    const sendCount=()=>page.evaluate(()=>window.fixtureCalls.filter(c=>c.route.endsWith('/send-stream')||c.route.endsWith('/send')).length);
    const value=id=>page.$eval('#'+id,e=>e.value);
    const settled=async n=>{try{await page.waitForFunction(n=>document.querySelectorAll('.chatv2-msg.assistant:not(.streaming):not(.incomplete)').length===n,{timeout:10000},n);}catch(e){console.error('STATE',JSON.stringify(await page.evaluate(()=>({notice:document.querySelector('#chat-notice').textContent,calls:window.fixtureCalls.map(c=>c.route),draft:document.querySelector('#chat-draft').value,msgs:document.querySelectorAll('.chatv2-msg').length,send:document.querySelector('#chat-send').disabled}))));throw e;}};

    // V2.1.0: New chat is immediate; choosing model and context only reads, never selects or approves.
    await page.click('#chat-new');assert.equal(await page.$('dialog[open]'),null);
    await page.click('#chat-context-button');await page.waitForSelector('#chat-context-menu:not([hidden])');
    assert.deepEqual(await page.$$eval('#chat-context-options input',es=>es.map(e=>e.value)),['4096','8192','16384','32768']);
    assert.equal(await value('chat-reserve'),'1024','default reply reserve');
    await page.keyboard.press('Escape');
    const pick=async name=>{await page.click('#chat-model-button');await page.waitForSelector('#chat-model-menu:not([hidden]) .chatv2-model-item');
      await page.evaluate(name=>[...document.querySelectorAll('#chat-model-menu h4')].find(h=>h.textContent===name).nextElementSibling.click(),name);};
    await pick('Ollama');
    await page.click('#chat-context-button');await page.click('#chat-context-options label:first-child');
    assert.equal(await page.$eval('#chat-context-label',e=>e.textContent),'4K');
    // An Ollama approval belongs to one new chat: refusing it creates nothing; nothing is reused.
    await setDraft('Ollama needs approval');await page.click('#chat-send');await page.waitForSelector('#chat-prepare:not([hidden])');
    await page.click('#chat-prepare-cancel');
    await page.click('#chat-context-button');await page.click('#chat-context-options label:nth-child(2)');
    await page.click('#chat-send');await page.waitForSelector('#chat-prepare:not([hidden])');
    assert.match(await page.$eval('#chat-prepare',e=>e.textContent),/Allow Ollama to load this model/,'a changed context asks again');
    await page.click('#chat-prepare-cancel');
    assert.equal(await page.evaluate(()=>window.fixtureCalls.filter(c=>c.route.includes('/select')).length),0,'choosing is read-only');
    assert.equal(await page.evaluate(()=>window.fixtureCalls.filter(c=>c.route.endsWith('/chat/prepare')&&c.body.approved).length),0,'nothing approved yet');
    assert.equal(await page.evaluate(()=>window.fixtureCalls.filter(c=>c.route.endsWith('/chat/sessions')).length),0,'no conversation created');
    await pick('LM Studio');
    await page.click('#chat-context-button');await page.click('#chat-context-options label:first-child');
    await setDraft('');
    assert.equal(await page.$eval('#chat-send',e=>e.disabled),true,'blank draft cannot be sent');assert.equal(await page.$eval('#chat-collect',e=>e.checked),false);

    // Keyboard guards: repeat, composition and IME keyCode never send.
    await setDraft('keyboard guard');
    for(const properties of [{repeat:true},{isComposing:true},{keyCode:229}])await page.$eval('#chat-draft',(e,properties)=>e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,...properties})),properties);
    await page.$eval('#chat-draft',e=>{e.dispatchEvent(new CompositionEvent('compositionstart'));e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));e.dispatchEvent(new CompositionEvent('compositionend'));});
    assert.equal(await sendCount(),0);
    await setDraft('first');await page.focus('#chat-draft');await page.keyboard.press('End');await page.keyboard.down('Shift');await page.keyboard.press('Enter');await page.keyboard.up('Shift');await page.keyboard.type('second');
    assert.equal(await value('chat-draft'),'first\nsecond');assert.equal(await sendCount(),0);
    await page.keyboard.press('Enter');await settled(1);
    assert.equal(await sendCount(),1);assert.equal(await value('chat-draft'),'');assert.equal(await page.$eval('.chatv2-msg.user .chatv2-text',e=>e.textContent),'first\nsecond');

    // Exact safe Markdown and the raw view.
    await setDraft('MARKDOWN_EXACT_FIXTURE');await page.focus('#chat-draft');await page.keyboard.press('Enter');await settled(2);
    const model='.chatv2-msg.assistant:last-of-type';
    assert.equal(await page.$eval(model+' .chatv2-answer .md-heading',e=>e.textContent),'Heading');
    assert.equal(await page.$eval(model+' .chatv2-answer strong',e=>e.textContent),'bold');assert.equal(await page.$$eval(model+' .chatv2-answer li',es=>es.length),2);
    assert.equal(await page.$eval(model+' .md-code code',e=>e.textContent),'<img src=x onerror=alert(1)>\\n');
    assert.equal(await page.$eval(model+' .chatv2-answer > p:last-of-type',e=>e.textContent),String.raw`\*\*literal\*\*`,'escapes are never decoded');
    assert.match(await page.$eval(model+' .chatv2-answer',e=>e.textContent),/&lt;b&gt;/,'entities are never decoded');
    for(const selector of ['img','script','a'])assert.equal(await page.$(model+' .chatv2-answer '+selector),null,selector);
    await page.click(model+' .chatv2-raw-toggle');
    const raw=await page.$eval(model+' .chatv2-raw',e=>e.textContent);
    assert.match(raw,/\*\*bold\*\*/);assert.match(raw,/&lt;b&gt;/);assert.equal(await page.$eval(model+' .chatv2-raw',e=>e.hidden),false);
    assert.equal(await page.$eval(model+' .chatv2-answer',e=>e.hidden),true);
    const sid=await page.evaluate(async()=>{const r=await fetch('/api/v1/chat/sessions?limit=1');return (await r.json()).items[0].id;});
    const stored=await page.evaluate(async sid=>fetch('/api/v1/chat/sessions/'+sid).then(r=>r.json()),sid);assert.equal(stored.turns.at(-1).assistant,raw,'raw view equals the stored reply');

    // A failed send keeps the draft; a wrong selected model never sends.
    await page.evaluate(()=>{window.failNextSend=true;});await setDraft('Keep failed draft');await page.click('#chat-send');
    await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('Synthetic send failure'));assert.equal(await value('chat-draft'),'Keep failed draft');assert.equal(await sendCount(),3);
    await page.evaluate(async()=>{window.wrongModel=true;await window.NajdiChat.load();});
    await page.waitForFunction(()=>!document.querySelector('#chat-prepare').hidden&&document.querySelector('#chat-prepare').textContent.includes('Select this model in LM Studio'));
    await page.focus('#chat-draft');await page.keyboard.press('Enter');assert.equal(await sendCount(),3,'wrong selected model never sends');
    assert.equal(await value('chat-draft'),'Keep failed draft','the draft stays while the runtime is prepared');
    await page.click('#chat-prepare-cancel');
    await page.evaluate(async()=>{window.wrongModel=false;await window.NajdiChat.load();});await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled);

    // A completion never clears text typed while it ran.
    await setDraft('DELAY_FIXTURE');await page.click('#chat-send');await page.waitForFunction(()=>!document.querySelector('#chat-stop').hidden);
    await setDraft('Newer draft');await page.focus('#chat-draft');await page.keyboard.press('Enter');
    await settled(3);assert.equal(await sendCount(),4);assert.equal(await value('chat-draft'),'Newer draft');

    // Arabic labels stay separate from raw/model content.
    await page.select('#language-select','ar');await page.waitForFunction(()=>document.documentElement.lang==='ar');
    assert.equal(await page.$eval('.chatv2-msg.assistant:nth-of-type(4) .chatv2-raw',e=>e.textContent),raw);
    assert.match(await page.$eval('#chat-keys',e=>e.textContent),/[؀-ۿ]/);
    await page.select('#language-select','en');await page.waitForFunction(()=>document.documentElement.lang==='en');
    const artifacts=process.env.NAJDILAB_BROWSER_ARTIFACTS||'.test-tmp/browser';fs.mkdirSync(artifacts,{recursive:true});
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.screenshot({path:path.join(artifacts,'chat-enhancements-desktop.png')});
    await page.setViewport({width:390,height:844});await page.evaluate(()=>window.scrollTo(0,0));
    const bounds=await page.$eval('.chatv2-main',e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}));assert.ok(bounds.left>=0&&bounds.right<=391,JSON.stringify(bounds));
    await page.screenshot({path:path.join(artifacts,'chat-enhancements-mobile.png')});
    assert.deepEqual(errors,[]);console.log('PASS: (PR #21 port, V2.1.0 composer) read-only model/context choice, approval never reused, Enter/Shift+Enter/IME/repeat/blank guards, exact safe Markdown + raw view, failure/new-typing drafts, wrong-model block, Arabic and mobile chat.');
  }finally{if(browser)await browser.close();child.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
