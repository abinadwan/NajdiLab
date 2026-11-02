/* Only a disposable fixture and synthetic model replies; hardware evidence is mocked. */
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
    const page=await browser.newPage();await page.setViewport({width:1280,height:1000});const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/chat');await page.waitForSelector('#chat-provider option');
    await page.evaluate(()=>{
      const original=window.api;window.fixtureCalls=[];window.failNextSend=false;window.wrongModel=false;
      window.api=async(route,options)=>{
        if(options)window.fixtureCalls.push({route,body:JSON.parse(options.body)});
        if(route.endsWith('/send')&&window.failNextSend){window.failNextSend=false;throw Error('Synthetic send failure');}
        if(route==='/api/v1/chat/hardware')return {gpus:[],recommendation:{model_max_context:131072,runtime_context:4096,budget_ceiling:4096,candidates:[
          {context:4096,assessment:'ESTIMATE_FITS_FREE_VRAM',estimated_required_bytes:5*1024**3},
          {context:8192,assessment:'ESTIMATE_FITS_FREE_VRAM',estimated_required_bytes:6*1024**3}],reason:'Synthetic evidence only.'}};
        const result=await original(route,options);
        if(route==='/api/v1/integrations'&&window.wrongModel)for(const item of result.items)if(item.id==='lmstudio')item.selected_model='different-fixture';
        return result;
      };
    });
    const setDraft=async value=>page.$eval('#chat-draft',(e,value)=>{e.value=value;e.dispatchEvent(new Event('input',{bubbles:true}));},value);
    const sendCount=()=>page.evaluate(()=>window.fixtureCalls.filter(c=>c.route.endsWith('/send')).length);
    const value=id=>page.$eval('#'+id,e=>e.value);
    assert.equal(await value('chat-budget'),'4096');assert.equal(await value('chat-reserve'),'1024');
    assert.equal(await page.$$eval('#chat-preset option:not([value="manual"])',options=>options.every(e=>e.disabled)),true);
    await setDraft('No conversation');await page.focus('#chat-draft');await page.keyboard.press('Enter');assert.equal(await sendCount(),0);await setDraft('');
    await page.click('#chat-hardware');await page.waitForFunction(()=>!document.querySelector('#chat-preset option[value="light"]').disabled);
    assert.equal(await page.$eval('#chat-preset option[value="balanced"]',e=>e.disabled),true);
    assert.equal(await page.$eval('#chat-preset option[value="long"]',e=>e.disabled),true);
    assert.match(await page.$eval('#chat-hardware-result',e=>e.textContent),/Proven engine ceiling: 4096/);
    assert.equal(await page.evaluate(()=>window.fixtureCalls.filter(c=>c.route.includes('/select')).length),0,'hardware is read-only');
    assert.equal(await value('chat-budget'),'4096');assert.equal(await value('chat-reserve'),'1024');
    await page.select('#chat-preset','light');await page.select('#chat-provider','ollama');
    assert.equal(await page.$eval('#chat-preset option[value="light"]',e=>e.disabled),true,'never reuse a different provider snapshot');
    await page.select('#chat-provider','lmstudio');await page.click('#chat-new');await page.waitForFunction(()=>!document.querySelector('#chat-collect').disabled);
    assert.equal(await page.$eval('#chat-send',e=>e.disabled),true);assert.equal(await page.$eval('#chat-collect',e=>e.checked),false);
    await setDraft('keyboard guard');
    for(const properties of [{repeat:true},{isComposing:true},{keyCode:229}])await page.$eval('#chat-draft',(e,properties)=>e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true,...properties})),properties);
    await page.$eval('#chat-draft',e=>{e.dispatchEvent(new CompositionEvent('compositionstart'));e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));e.dispatchEvent(new CompositionEvent('compositionend'));});
    assert.equal(await sendCount(),0);
    await setDraft('first');await page.focus('#chat-draft');await page.keyboard.press('End');await page.keyboard.down('Shift');await page.keyboard.press('Enter');await page.keyboard.up('Shift');await page.keyboard.type('second');
    assert.equal(await value('chat-draft'),'first\nsecond');assert.equal(await sendCount(),0);
    await page.keyboard.press('Enter');await page.waitForFunction(()=>document.querySelectorAll('.chat-message').length===2);
    assert.equal(await sendCount(),1);assert.equal(await value('chat-draft'),'');assert.equal(await page.$eval('.chat-message p',e=>e.textContent),'first\nsecond');
    await setDraft('MARKDOWN_FIXTURE');await page.focus('#chat-draft');await page.keyboard.press('Enter');await page.waitForFunction(()=>document.querySelectorAll('.chat-message').length===4);
    const model='.chat-message:nth-child(4)';
    assert.equal(await page.$eval(model+' h1',e=>e.textContent),'Heading');assert.equal(await page.$eval(model+' .chat-markdown strong',e=>e.textContent),'bold');assert.equal(await page.$$eval(model+' li',es=>es.length),2);
    assert.equal(await page.$eval(model+' pre code',e=>e.textContent),'<img src=x onerror=alert(1)>\\n');
    assert.equal(await page.$eval(model+' .chat-markdown p:last-child',e=>e.textContent),String.raw`\*\*literal\*\*`);
    for(const selector of ['img','script','a'])assert.equal(await page.$(model+' '+selector),null);
    await page.click(model+' .chat-raw-toggle');
    const raw=await page.$eval(model+'>p',e=>e.textContent);
    assert.match(raw,/\*\*bold\*\*/);assert.match(raw,/&lt;b&gt;/);assert.equal(await page.$eval(model+'>p',e=>e.hidden),false);
    const stored=await page.evaluate(async()=>{const sid=document.querySelector('#chat-saved').value;return fetch('/api/v1/chat/sessions/'+sid).then(r=>r.json());});assert.equal(stored.turns.at(-1).assistant,raw);
    await page.evaluate(()=>{window.failNextSend=true;});await setDraft('Keep failed draft');await page.click('#chat-send');
    await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent==='Synthetic send failure');assert.equal(await value('chat-draft'),'Keep failed draft');assert.equal(await sendCount(),3);
    await page.evaluate(()=>{window.wrongModel=true;});await page.click('#chat-refresh');await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('pinned to its original model'));
    await page.focus('#chat-draft');await page.keyboard.press('Enter');assert.equal(await sendCount(),3,'wrong selected model never sends');
    await page.evaluate(()=>{window.wrongModel=false;});await page.click('#chat-refresh');await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled);
    await setDraft('DELAY_FIXTURE');await page.click('#chat-send');await page.waitForFunction(()=>!document.querySelector('#chat-stop').disabled);
    await setDraft('Newer draft');await page.focus('#chat-draft');await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelectorAll('.chat-message').length===6);assert.equal(await sendCount(),4);assert.equal(await value('chat-draft'),'Newer draft');
    // Arabic labels stay separate from raw/model content.
    await page.select('#language-select','ar');await page.waitForFunction(()=>document.documentElement.lang==='ar');
    assert.equal(await page.$eval(model+'>p',e=>e.textContent),raw);assert.match(await page.$eval('label[for="chat-preset"]',e=>e.textContent),/[\u0600-\u06ff]/);
    await page.select('#language-select','en');await page.waitForFunction(()=>document.documentElement.lang==='en');
    const artifacts=process.env.NAJDILAB_BROWSER_ARTIFACTS||'.test-tmp/browser';fs.mkdirSync(artifacts,{recursive:true});
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.screenshot({path:path.join(artifacts,'chat-enhancements-desktop.png'),fullPage:true});
    await page.setViewport({width:390,height:844});
    await page.waitForFunction(()=>{const r=document.querySelector('.sidebar').getBoundingClientRect();return r.right<=0||r.left>=innerWidth;});
    await page.evaluate(()=>window.scrollTo(0,0));
    const bounds=await page.$eval('.chat-controls',e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}));assert.ok(bounds.left>=0&&bounds.right<=391);
    await page.screenshot({path:path.join(artifacts,'chat-enhancements-mobile.png'),fullPage:true});
    assert.deepEqual(errors,[]);console.log('PASS: synthetic preset gates/read-only snapshot, Enter/Shift+Enter/IME/repeat/send guards, exact safe Markdown, failure/new-typing drafts, Arabic and mobile chat.');
  }finally{if(browser)await browser.close();child.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
