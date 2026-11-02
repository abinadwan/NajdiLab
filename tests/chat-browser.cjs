/* Root app acceptance against disposable synthetic engines only. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const puppeteer=require('puppeteer-core');

(async()=>{
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe'],windowsHide:true});
  let browser;
  try{
    const base=await new Promise((resolve,reject)=>{
      let text='';const timer=setTimeout(()=>reject(Error('Synthetic browser fixture startup timed out')),15000);
      child.stdout.on('data',chunk=>{text+=chunk;const m=text.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
      child.once('error',reject);child.once('exit',code=>{clearTimeout(timer);reject(Error('Fixture exited: '+code));});
    });
    assert.ok(!base.endsWith(':8770'));
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    const page=await browser.newPage();await page.setViewport({width:1280,height:1000});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base+'/chat');await page.waitForSelector('#chat-provider option');
    assert.equal(await page.$('[data-view="training"]'),null);
    assert.equal(await page.$eval('#chat-load-row',e=>getComputedStyle(e).display),'none');
    await page.click('#chat-new');await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled);
    assert.equal(await page.$eval('#chat-collect',e=>e.checked),false);
    const sid=await page.$eval('#chat-saved',e=>e.value);
    const raw='  <img src=x onerror=alert(1)> synthetic private-before-optin 🙂  ';
    await page.type('#chat-draft',raw);await page.click('#chat-send');
    await page.waitForFunction(()=>document.querySelectorAll('.chat-message').length===2);
    assert.equal(await page.$eval('.chat-message p',e=>e.textContent),raw);
    assert.equal(await page.$('.chat-message img'),null);
    assert.match(await page.$eval('.chat-message:nth-child(2) .chat-review-status',e=>e.textContent),/Not collected for review/);
    const read=route=>page.evaluate(async route=>{const r=await fetch(route);return r.json();},route);
    assert.equal((await read('/api/v1/review-queue')).items.length,0);
    await page.click('#chat-collect');await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('Collection choice saved'));
    await page.type('#chat-draft','Synthetic opted-in question');await page.click('#chat-send');
    await page.waitForFunction(()=>document.querySelectorAll('.chat-message').length===4);
    const queue=(await read('/api/v1/review-queue')).items;
    assert.equal(queue.length,1);assert.equal(queue[0].review_status,'PENDING');assert.equal(queue[0].training_eligible,0);
    assert.ok(!JSON.stringify(queue).includes('private-before-optin'));
    assert.match(await page.$eval('.chat-message:nth-child(4) .chat-review-status',e=>e.textContent),/Collected for human review/);
    await page.reload();await page.waitForSelector(`#chat-saved option[value="${sid}"]`);await page.select('#chat-saved',sid);
    await page.waitForFunction(()=>document.querySelectorAll('.chat-message').length===4);
    const evidence=process.env.NAJDILAB_BROWSER_ARTIFACTS||'.test-tmp/browser';fs.mkdirSync(evidence,{recursive:true});
    await page.screenshot({path:path.join(evidence,'chat-complete.png'),fullPage:true});
    // A budget overflow must open empty context and retain, never replay, draft.
    await page.$eval('#chat-budget',e=>e.value='128');await page.$eval('#chat-reserve',e=>e.value='127');await page.click('#chat-new');
    await page.waitForFunction(()=>document.querySelector('#chat-usage').textContent.includes('Budget 128'));
    await page.type('#chat-draft','Unsent overflow draft');await page.click('#chat-send');
    await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('Context limit reached'));
    assert.equal(await page.$$eval('.chat-message',es=>es.length),0);
    assert.equal(await page.$eval('#chat-draft',e=>e.value),'Unsent overflow draft');
    assert.equal(await page.$eval('#chat-collect',e=>e.checked),false);
    // Stop acknowledgement is usable while generation is waiting.
    await page.$eval('#chat-budget',e=>e.value='512');await page.$eval('#chat-reserve',e=>e.value='32');await page.click('#chat-new');
    await page.waitForFunction(()=>document.querySelector('#chat-usage').textContent.includes('Budget 512'));
    await page.$eval('#chat-draft',e=>e.value='STOP_FIXTURE');await page.click('#chat-send');
    await page.waitForFunction(()=>!document.querySelector('#chat-stop').disabled);await page.click('#chat-stop');
    await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled);
    assert.equal(await page.$$eval('.chat-message',es=>es.length),0);
    // Ollama loads on request, so it needs its own approval before any session.
    await page.select('#chat-provider','ollama');
    assert.notEqual(await page.$eval('#chat-load-row',e=>getComputedStyle(e).display),'none');
    await page.click('#chat-new');
    await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('Approve Ollama'));
    await page.click('#chat-load-approved');await page.click('#chat-new');
    await page.waitForFunction(()=>document.querySelector('#chat-usage').textContent.startsWith('ollama'));
    await page.type('#chat-draft','Synthetic Ollama question');await page.click('#chat-send');
    await page.waitForFunction(()=>document.querySelectorAll('.chat-message').length===2);
    await page.click('#chat-hardware');
    await page.waitForFunction(()=>document.querySelector('#chat-hardware-result').textContent.includes('Model maximum context: 131072'));
    // Reading specs must not stale the conversation that is already open.
    await page.type('#chat-draft','Second question after reading specs');await page.click('#chat-send');
    await page.waitForFunction(()=>document.querySelectorAll('.chat-message').length===4);
    await page.goto(base+'/training/setup');await page.waitForSelector('#view-dashboard.active');
    assert.equal(await page.$('#view-retired'),null);
    assert.equal(await page.$('#view-human-review'),null);
    assert.equal((await page.evaluate(async()=>fetch('/api/v1/training/jobs').then(r=>r.status))),404);
    assert.equal(await page.$('#training-setup-form'),null);
    assert.deepEqual(errors,[]);
    console.log('PASS: real browser raw text/HTML escaping, opt-in pending queue/privacy, reload/history, overflow/no replay, Stop, Ollama load approval and absent training views/routes. Synthetic engines only.');
  }finally{
    if(browser)await browser.close();child.kill();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
