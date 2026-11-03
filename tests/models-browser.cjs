/* Hugging Face Direct + Chat context indicator, in Chromium against the synthetic fixture
 * (fake Hugging Face, tiny synthetic GGUF, isolated folder; no network, no real model). Usage:
 *   NAJDILAB_BROWSER_EXECUTABLE=<chromium> NODE_PATH=<dir with puppeteer-core> node tests/models-browser.cjs
 */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const path=require('node:path');
const {spawn}=require('node:child_process');
const puppeteer=require('puppeteer-core');

test('Model library and context indicator in Chromium',async t=>{
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe'],windowsHide:true});
  let browser;
  try{
    const base=await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('fixture timeout')),20000);
      child.stdout.on('data',c=>{text+=c;const m=text.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});});
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setViewport({width:1280,height:900});
    await page.goto(base+'/models');await page.waitForSelector('#view-models.active');
    const requests=[];page.on('request',r=>requests.push(r.url()));

    await t.test('nothing reaches Hugging Face until the user searches',async()=>{
      assert.equal(await page.$('.models-result'),null);
      assert.ok(!requests.some(u=>u.includes('/api/v1/models/hub')),'no hub request on page load');
    });

    await t.test('search, details and unsupported files are explained',async()=>{
      await page.type('#models-query','tiny');await page.keyboard.press('Enter');
      await page.waitForSelector('.models-result');
      assert.equal(await page.$$eval('.models-result',b=>b.length),1,'the hostile search entry is not shown');
      await page.click('.models-result');await page.waitForSelector('.models-variants');
      const rows=await page.$$eval('.models-variants tbody tr',r=>r.map(x=>x.innerText));
      assert.equal(rows.length,3);
      assert.match(rows.join('\n'),/Split file — not supported/);assert.match(rows.join('\n'),/Vision projector — not a text model/);
      assert.equal(await page.$$eval('.models-variants tbody button',b=>b.length),1,'only the supported file can be checked');
    });

    await t.test('the advisor separates download from loading and labels its numbers',async()=>{
      await page.click('#models-hardware');await page.click('.models-variants tbody button');
      await page.waitForSelector('.models-advice-card');
      const card=await page.$eval('.models-advice-card',e=>e.innerText);
      assert.match(card,/BLOCKED/,'no llama-server in the fixture: loading is blocked');
      assert.match(card,/No llama\.cpp runtime is installed/);
      assert.match(card,/Set up the llama\.cpp runtime/,'the advisor offers the runtime setup, it does not start it');
      assert.match(card,/Download allowed/);
      assert.match(card,/estimate/);assert.match(card,/measured/);
    });

    await t.test('the download needs a license acknowledgement, then an explicit start',async()=>{
      await page.click('.models-download-check .button.primary');await page.waitForSelector('#models-download-dialog[open]');
      assert.equal(await page.$eval('#models-download-start',b=>b.disabled),true);
      await page.click('#models-license-ack');
      assert.equal(await page.$eval('#models-download-start',b=>b.disabled),false);
      await page.click('#models-download-start');
      await page.waitForSelector('#models-library:not([hidden]) .models-library-item');
      await page.waitForFunction(()=>/Ready — verified/.test(document.querySelector('.models-library-item .status-pill')?.textContent||''),{timeout:15000});
      assert.match(await page.$eval('.models-library-item',e=>e.innerText),/verified/);
    });

    await t.test('loading stays an approved step and is refused while blocked',async()=>{
      await page.click('.models-library-item .button.primary');await page.waitForSelector('.models-load .models-check-settings');
      await page.click('.models-load .models-check-settings .button');await page.waitForSelector('.models-load .models-advice-card');
      assert.equal(await page.$eval('.models-load-confirm input',e=>e.disabled),true);
      assert.equal(await page.$eval('.models-load-confirm .button',e=>e.disabled),true);
      const native=await page.evaluate(async()=>(await window.api('/api/v1/native/status')).state);
      assert.equal(native,'STOPPED','nothing was started');
    });

    await t.test('delete requires the exact file name',async()=>{
      await page.click('.models-library-item .delete-action');await page.waitForSelector('#models-delete-dialog[open]');
      await page.type('#models-delete-confirm','wrong.gguf');
      assert.equal(await page.$eval('#models-delete-go',b=>b.disabled),true);
      await page.$eval('#models-delete-confirm',e=>{e.value='';});await page.type('#models-delete-confirm','Tiny-Chat-Q4_K_M.gguf');
      await page.click('#models-delete-go');
      await page.waitForSelector('#models-library-list .compact-empty');
    });

    await t.test('Arabic shows the same screen right to left',async()=>{
      await page.evaluate(()=>window.NajdiI18n.setLanguage('ar'));
      await page.evaluate(()=>switchView('models'));await page.waitForSelector('#view-models.active');
      assert.equal(await page.evaluate(()=>document.documentElement.dir),'rtl');
      assert.equal(await page.$eval('#models-tab-discover',e=>e.textContent),'الاكتشاف في Hugging Face');
      await page.evaluate(()=>window.NajdiI18n.setLanguage('en'));
    });

    await t.test('context indicator: measured usage, thresholds from Settings, one notice per level',async()=>{
      await page.evaluate(()=>switchView('settings'));await page.waitForSelector('#view-settings.active');
      for(const [id,v] of [['context-warn-info','80'],['context-warn-warn','60'],['context-warn-critical','90']]){await page.$eval('#'+id,(e,x)=>{e.value=x;},v);}
      await page.click('#context-warnings-form button');
      assert.match(await page.$eval('#context-warnings-status',e=>e.textContent),/increase/,'non-increasing thresholds are refused');
      for(const [id,v] of [['context-warn-info','10'],['context-warn-warn','20'],['context-warn-critical','30']]){await page.$eval('#'+id,(e,x)=>{e.value=x;},v);}
      await page.click('#context-warnings-form button');
      assert.equal(await page.$eval('#context-warnings-status',e=>e.textContent),'Context warnings saved.');
      await page.evaluate(()=>switchView('chat'));await page.waitForSelector('#view-chat.active');
      await page.click('#chat-new');await page.waitForSelector('#chat-setup[open] #chat-provider option');
      await page.click('#chat-create');await page.waitForFunction(()=>!document.querySelector('#chat-setup').open&&!document.querySelector('#chat-collect').disabled);
      const before=await page.$eval('#chat-usage',e=>e.textContent);
      assert.match(before,/Context used: 0 \+ 1024 reserved of 4096 tokens \(25%\)/);
      assert.match(await page.$eval('#chat-context-left',e=>e.textContent),/estimate/);
      await page.type('#chat-draft','Synthetic context check');await page.keyboard.press('Enter');
      await page.waitForFunction(()=>document.querySelectorAll('.chatv2-msg.assistant:not(.streaming)').length===1,{timeout:10000});
      const usage=await page.$eval('#chat-usage',e=>e.textContent);
      const [,used,reserve,budget,percent]=usage.match(/Context used: (\d+) \+ (\d+) reserved of (\d+) tokens \((\d+)%\)/);
      const turn=await page.evaluate(async()=>{const s=(await window.api('/api/v1/chat/sessions?limit=1')).items[0];const full=await window.api('/api/v1/chat/sessions/'+s.id);return full.turns.at(-1);});
      assert.equal(Number(used),turn.input_tokens+turn.output_tokens,'history is the engine-measured prompt plus reply');
      assert.equal(Number(percent),Math.round((Number(used)+Number(reserve))/Number(budget)*100));
      assert.equal(await page.$eval('#chat-context-meter',e=>Number(e.value)),Number(percent));
      assert.match(await page.$eval('#chat-context-alert',e=>e.className),/critical|warn|info/);
      assert.ok((await page.$eval('#chat-context-alert',e=>e.textContent)).length>20);
      await page.evaluate(()=>localStorage.removeItem('najdilab.contextWarnings'));
    });

    await t.test('version label: one value from the server, in both languages, themes and layouts',async()=>{
      const served=await page.evaluate(async()=>(await window.api('/api/v1/config')).app_version_display);
      assert.equal(served,'V2.0.0');
      const label=()=>page.$eval('#app-version',e=>{const r=e.getBoundingClientRect();return {text:e.textContent,visible:r.width>0&&r.height>0,
        inside:r.right<=e.closest('.sidebar').getBoundingClientRect().right+0.5&&r.left>=e.closest('.sidebar').getBoundingClientRect().left-0.5,
        below:r.top>=document.querySelector('.brand-mark').getBoundingClientRect().top};});
      for(const lang of ['en','ar'])for(const theme of ['light','dark']){
        await page.evaluate((l,th)=>{document.documentElement.setAttribute('data-theme',th);window.NajdiI18n.setLanguage(l);},lang,theme);
        const v=await label();
        assert.deepEqual(v,{text:'V2.0.0',visible:true,inside:true,below:true},`${lang} ${theme}`);
      }
      assert.equal(await page.$eval('#settings-version',e=>e.textContent),'V2.0.0','Settings shows the same version');
      await page.click('#collapse-sidebar');
      assert.deepEqual(await label(),{text:'V2.0.0',visible:true,inside:true,below:true},'collapsed sidebar');
      await page.click('#collapse-sidebar');
      await page.setViewport({width:390,height:844});
      // Crossing the phone breakpoint slides the sidebar off-screen (0.2 s); click once it is out of the way.
      await page.waitForFunction(()=>{const r=document.querySelector('.sidebar').getBoundingClientRect();return r.right<=0||r.left>=innerWidth;});
      await page.click('#mobile-menu');await page.waitForFunction(()=>document.querySelector('.sidebar').classList.contains('open'));
      await new Promise(r=>setTimeout(r,300));
      assert.equal((await label()).visible,true,'phone navigation sheet');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal overflow');
      await page.keyboard.press('Escape');
      await page.evaluate(()=>{window.NajdiI18n.setLanguage('en');document.documentElement.setAttribute('data-theme','light');});
      await page.setViewport({width:1280,height:900});
    });

    await t.test('runtime: nothing is read or downloaded until approved, then each step is explicit',async()=>{
      await page.setViewport({width:1280,height:900});
      await page.evaluate(()=>switchView('models'));await page.waitForSelector('#view-models.active');
      const before=requests.length;
      await page.click('#models-tab-runtime');await page.waitForSelector('#runtime-status h2');
      assert.match(await page.$eval('#runtime-status .status-pill',e=>e.textContent),/Not installed/);
      assert.ok(!requests.slice(before).some(u=>/runtime\/(detect|install)/.test(u)),'opening the tab reads and downloads nothing');
      assert.match(await page.$eval('#runtime-packages',e=>e.innerText),/nvidia-smi/);
      const check=await page.$$eval('#runtime-status .models-actions button',b=>b.map(x=>x.textContent));
      assert.deepEqual(check,['Check this computer']);
      await page.click('#runtime-status .models-actions .button.primary');
      await page.waitForSelector('#runtime-packages .models-library-item');
      const rows=await page.$$eval('#runtime-packages .models-library-item',r=>r.map(x=>x.innerText));
      assert.equal(rows.length,3);
      assert.match(rows[0],/NVIDIA GPU \(CUDA 13\.4\)[\s\S]*Recommended/);
      assert.match(rows[1],/Not compatible[\s\S]*compute capability/,'a toolkit older than the GPU is explained, not offered');
      assert.equal(await page.$$eval('#runtime-packages .models-library-item',r=>r[1].querySelector('button')),null);
      await page.click('#runtime-packages .button.primary');await page.waitForSelector('#runtime-dialog[open]');
      const dialog=await page.$eval('#runtime-dialog',e=>e.innerText);
      assert.match(dialog,/SHA-256/);assert.match(dialog,/NVIDIA CUDA Toolkit End User License Agreement/);assert.match(dialog,/No model is loaded/);
      assert.equal(await page.$eval('#runtime-dialog-go',b=>b.disabled),true,'the licenses must be acknowledged first');
      await page.click('#runtime-license-ack');await page.click('#runtime-dialog-go');
      await page.waitForFunction(()=>/Ready — verified/.test(document.querySelector('#runtime-status .status-pill')?.textContent||''),{timeout:15000});
      const status=await page.$eval('#runtime-status',e=>e.innerText);
      assert.match(status,/2\/2/);assert.match(status,/layers on the GPU/);assert.match(status,/build 12059/);
      const native=await page.evaluate(async()=>(await window.api('/api/v1/native/status')).state);
      assert.equal(native,'STOPPED','installing the runtime loads no model');
    });

    await t.test('runtime: Arabic, then uninstall needs the typed confirmation',async()=>{
      await page.evaluate(()=>window.NajdiI18n.setLanguage('ar'));
      await page.waitForFunction(()=>document.documentElement.dir==='rtl');
      assert.equal(await page.$eval('#models-tab-runtime',e=>e.textContent),'بيئة تشغيل llama.cpp');
      assert.equal(await page.$eval('#runtime-status h2',e=>e.textContent),'بيئة تشغيل llama.cpp المُدارة');
      await page.evaluate(()=>window.NajdiI18n.setLanguage('en'));
      await page.click('#runtime-status .delete-action');await page.waitForSelector('#runtime-dialog[open]');
      await page.type('#runtime-dialog-confirm','uninstall');
      assert.equal(await page.$eval('#runtime-dialog-go',b=>b.disabled),true);
      await page.$eval('#runtime-dialog-confirm',e=>{e.value='';});await page.type('#runtime-dialog-confirm','UNINSTALL');
      await page.click('#runtime-dialog-go');
      await page.waitForFunction(()=>/Not installed/.test(document.querySelector('#runtime-status .status-pill')?.textContent||''),{timeout:15000});
      assert.match(await page.$eval('#runtime-status',e=>e.innerText),/managed runtime was removed/);
    });

    await t.test('no page errors',async()=>{assert.deepEqual(errors,[]);});
  }finally{if(browser)await browser.close();child.kill();}
});
