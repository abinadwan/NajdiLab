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
    const page=await browser.newPage();await page.evaluateOnNewDocument(()=>{try{localStorage.setItem('najdilab.chat.legacyProviders','1');}catch{}});// The fixture has no llama-server: its Chat checks use the LM Studio fixture via the Settings opt-in.
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setViewport({width:1280,height:900});
    await page.goto(base+'/models');await page.waitForSelector('#view-models.active');
    const requests=[];page.on('request',r=>requests.push(r.url()));

    await t.test('nothing reaches Hugging Face until the user searches',async()=>{
      assert.equal(await page.$('.models-result'),null);
      assert.ok(!requests.some(u=>u.includes('/api/v1/models/hub')),'no hub request on page load, not even for the default tab');
    });

    await t.test('recommended for your device is the default tab and needs the hardware approval',async()=>{
      assert.equal(await page.$eval('#models-tab-recommended',e=>e.getAttribute('aria-selected')),'true');
      assert.equal(await page.$eval('#models-recommended',e=>e.hidden),false);
      assert.equal(await page.$eval('#rec-size',e=>e.value),'all');assert.equal(await page.$eval('#rec-source',e=>e.value),'official');
      assert.equal(await page.$eval('#rec-purpose',e=>e.value),'chat');
      assert.equal(await page.$eval('#models-recommend-refresh',e=>getComputedStyle(e).display),'none','refresh appears only after a first result');
      await page.click('#models-recommend-form .button.primary');
      assert.match(await page.$eval('#models-recommend-status',e=>e.textContent),/Allow reading this computer/);
      assert.ok(!requests.some(u=>u.includes('/hub/recommended')),'nothing is checked without the approval');
      await page.click('#rec-hardware');await page.click('#models-recommend-form .button.primary');
      await page.waitForSelector('#models-recommend-list .models-discovery-item',{timeout:20000});
      const cards=await page.$$eval('#models-recommend-list .models-discovery-item',c=>c.map(x=>x.innerText));
      assert.equal(cards.length,3);
      assert.match(cards[0],/Compatibility \(estimate\)[\s\S]*BLOCKED/,'no llama-server in the fixture: compatibility is blocked, and says so');
      assert.match(cards[0],/Expected performance:/);assert.match(cards[0],/Verified official publisher/);
      assert.match(await page.$eval('#models-recommend-summary',e=>e.innerText),/Popularity only chooses which models are checked/);
    });

    await t.test('trending keeps Hugging Face order, with provenance and size labels',async()=>{
      await page.click('#models-tab-trending');await page.waitForSelector('#models-trending:not([hidden])');
      await page.click('#models-trending-form .button.primary');
      await page.waitForSelector('#models-trending-list .models-discovery-item');
      const ids=await page.$$eval('#models-trending-list h3',h=>h.map(x=>x.textContent));
      assert.deepEqual(ids,['najdi-labs/Najm-3B-Instruct-GGUF','najdi-labs/Najm-0.5B-Chat-GGUF','najdi-labs/Najm-11B-Instruct-GGUF']);
      const first=await page.$eval('#models-trending-list .models-discovery-item',e=>e.innerText);
      assert.match(first,/#3/);assert.match(first,/trending score/);assert.match(first,/community-quant/);assert.match(first,/not the original unmodified weights/);
      assert.match(await page.$eval('#models-trending-summary',e=>e.innerText),/Rankings fetched from Hugging Face at[\s\S]*above 12B parameters/);
      await page.select('#trend-source','all');await page.click('#trend-unknown');await page.click('#models-trending-form .button.primary');
      await page.waitForFunction(()=>/Fine-tuned \/ modified/.test(document.querySelector('#models-trending-list')?.innerText||''));
      const all=await page.$eval('#models-trending-list',e=>e.innerText);
      assert.match(all,/UNVERIFIED size/);assert.match(all,/Unverified source/);
      assert.ok(!all.includes('Najm-MoE-30B-A3B'),'a mixture of experts above 12B total is never shown as small');
      await page.setViewport({width:390,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no horizontal scrolling on a phone');
      await page.evaluate(()=>window.NajdiI18n.setLanguage('ar'));await page.waitForFunction(()=>document.documentElement.dir==='rtl');
      assert.equal(await page.$eval('#models-tab-trending',e=>e.textContent),'الرائجة');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no horizontal scrolling in Arabic');
      await page.evaluate(()=>window.NajdiI18n.setLanguage('en'));await page.setViewport({width:1280,height:900});
    });

    await t.test('search, details and unsupported files are explained',async()=>{
      await page.click('#models-tab-discover');
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

    await t.test('Use in Chat opens an empty chat with the model chosen and starts nothing',async()=>{
      assert.match(await page.$eval('.models-library-item .button.primary',e=>e.textContent),/Use in Chat/);
      assert.equal(await page.$('.models-load'),null,'the library has no load or runtime-context form any more');
      await page.click('.models-library-item .button.primary');
      await page.waitForSelector('#view-chat.active');
      await page.waitForFunction(()=>/Tiny-Chat/.test(document.querySelector('#chat-model-label').textContent));
      assert.match(await page.$eval('#chat-session-identity',e=>e.textContent),/New conversation/);
      assert.equal(await page.$('dialog[open]'),null);
      const native=await page.evaluate(async()=>(await window.api('/api/v1/native/status')).state);
      assert.equal(native,'STOPPED','nothing was started');
      // Sending explains why it cannot run here (no llama.cpp runtime in the fixture) and keeps the draft.
      await page.$eval('#chat-draft',e=>{e.value='Synthetic draft';e.dispatchEvent(new Event('input'));});
      await page.click('#chat-send');await page.waitForSelector('#chat-prepare:not([hidden])');
      assert.match(await page.$eval('#chat-prepare',e=>e.textContent),/This model cannot be used now[\s\S]*NATIVE_SERVER_MISSING/);
      assert.equal(await page.$eval('#chat-draft',e=>e.value),'Synthetic draft');
      await page.click('#chat-prepare-cancel');
      await page.evaluate(()=>switchView('models'));await page.click('#models-tab-library');
      await page.waitForSelector('#models-library:not([hidden]) .models-library-item');
      await page.waitForNetworkIdle({idleTime:400});
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
      await page.click('#chat-new');
      await page.click('#chat-model-button');await page.waitForSelector('#chat-model-menu:not([hidden]) .chatv2-model-item');
      await page.evaluate(()=>[...document.querySelectorAll('#chat-model-menu h4')].find(h=>h.textContent==='LM Studio').nextElementSibling.click());
      await page.click('#chat-context-button');await page.click('#chat-context-options label:first-child');
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

    await t.test('copyright: once, in the sidebar under the local address, translated, quiet and accessible',async()=>{
      await page.setViewport({width:1280,height:900});
      assert.equal(await page.$$eval('.app-footer',e=>e.length),0,'no page footer');
      assert.equal(await page.$$eval('#copyright-year',e=>e.length),1);
      const where=()=>page.$eval('.sidebar-copyright',e=>{const r=e.getBoundingClientRect(),badge=document.querySelector('.local-badge').getBoundingClientRect(),nav=getComputedStyle(document.querySelector('.nav-label'));
        return {inSidebar:!!e.closest('.sidebar'),below:r.top>=badge.bottom-1,smaller:parseFloat(getComputedStyle(e).fontSize)<parseFloat(nav.fontSize),text:e.textContent.trim(),align:getComputedStyle(e).textAlign};});
      const year=String(new Date().getFullYear());
      for(const theme of ['light','dark']){
        await page.evaluate(th=>{document.documentElement.setAttribute('data-theme',th);window.NajdiI18n.setLanguage('en');},theme);
        const en=await where();
        assert.deepEqual([en.inSidebar,en.below,en.smaller,en.text],[true,true,true,`© ${year} Najdi Lab. All rights reserved.`],theme);
        await page.evaluate(()=>window.NajdiI18n.setLanguage('ar'));
        const ar=await where();
        assert.deepEqual([ar.inSidebar,ar.below,ar.text],[true,true,`© ${year} نجدي لاب. جميع الحقوق محفوظة.`],theme+' Arabic');
      }
      await page.evaluate(()=>window.NajdiI18n.setLanguage('en'));
      await page.click('#collapse-sidebar');
      const collapsed=await page.$eval('.sidebar-copyright',e=>({width:e.getBoundingClientRect().width,text:e.textContent.trim().length>0}));
      assert.ok(collapsed.width<=1&&collapsed.text,'collapsed sidebar: hidden visually, still read by screen readers');
      await page.click('#collapse-sidebar');
    });

    await t.test('training models: GGUF and Safetensors are told apart; a download needs a reviewed, complete checkpoint and the license',async()=>{
      await page.evaluate(()=>switchView('models'));await page.waitForSelector('#view-models.active');
      await page.click('#models-tab-training');await page.waitForSelector('#models-training:not([hidden])');
      assert.match(await page.$eval('#models-training',e=>e.textContent),/A GGUF file is not a training checkpoint/);
      await page.waitForFunction(()=>document.querySelector('#training-models-list').textContent.includes('No training checkpoints yet.'));
      const check=async repo=>{await page.$eval('#training-models-repo',(e,v)=>{e.value=v;},repo);await page.click('#training-models-form button[type="submit"]');
        await page.waitForFunction(()=>!document.querySelector('#training-models-review').textContent.includes('Checking'));
        return page.$eval('#models-training',e=>({review:document.querySelector('#training-models-review').textContent,confirm:!document.querySelector('#training-models-confirm').hidden,
          download:document.querySelector('#training-models-download').disabled}));};
      const good=await check('najdi-synthetic/Tiny-Train');
      assert.ok(good.confirm&&good.download,'offered, but disabled until the license is acknowledged');
      assert.match(good.review,/config\.json[\s\S]*model\.safetensors/);assert.doesNotMatch(good.review,/modeling_custom\.py/,'code files are never offered');
      await page.click('#training-models-ack');assert.equal(await page.$eval('#training-models-download',e=>e.disabled),false);
      const gguf=await check('najdi-synthetic/Tiny-Chat-GGUF');
      assert.ok(!gguf.confirm);assert.match(gguf.review,/not a training checkpoint/);assert.match(gguf.review,/complete training checkpoint/);
    });

    await t.test('prepare training data: choose records, fix blockers by leaving records out, create a version, export',async()=>{
      await page.evaluate(async()=>{for(const [q,a] of [['Synthetic prepare question one','Synthetic approved answer one'],['Synthetic prepare question two','Synthetic approved answer two']])
        await window.api('/api/v1/manual-data/sft',{method:'POST',body:JSON.stringify({messages:[{role:'user',content:q},{role:'assistant',content:a}],origin:'manual',training_eligible:true,language:'en'})});});
      await page.goto(base+'/datasets/prepare');await page.waitForSelector('#view-prepare.active');
      await page.waitForFunction(()=>!document.querySelector('#prepare-records').textContent.includes('Loading'));
      const total=await page.$$eval('#prepare-records input[data-id]',b=>b.length);
      assert.ok(total>0,'the synthetic records are listed');
      await page.click('#prepare-none');
      assert.match(await page.$eval('#prepare-count',e=>e.textContent),/^0 of /);
      const run=async()=>{await page.click('#prepare-check');await page.waitForFunction(()=>{const t=document.querySelector('#prepare-check-status').textContent;return t&&!t.startsWith('Checking');});
        return page.$eval('#prepare-check-status',e=>e.textContent);};
      assert.match(await run(),/problem/,'nothing chosen cannot be built');
      assert.equal(await page.$eval('#prepare-create',e=>e.disabled),true);
      await page.click('#prepare-all');
      let status=await run();
      for(let i=0;i<6&&!/All checks passed/.test(status);i++){
        const leave=await page.$('#prepare-problems button');assert.ok(leave,'every blocker offers a way out: '+status);
        await leave.click();status=await run();
      }
      assert.match(status,/All checks passed/);
      assert.match(await page.$eval('#prepare-split',e=>e.textContent),/training records[\s\S]*Conversations shared between training and evaluation: 0/);
      // Changing the choice after a check requires checking again.
      const first=await page.$('#prepare-records input[data-id]:checked');await first.click();
      assert.equal(await page.$eval('#prepare-create',e=>e.disabled),true);await first.click();
      assert.match(await run(),/All checks passed/);
      await page.click('#prepare-create');
      await page.waitForFunction(()=>/Created and frozen|Error|error/.test(document.querySelector('#prepare-created').textContent));
      const created=await page.$eval('#prepare-created',e=>e.textContent);
      assert.match(created,/Created and frozen: gold-v\d+[\s\S]*Structural validity: Valid/);
      await page.waitForSelector('#prepare-export:not([hidden])');
      await page.click('#prepare-export-go');
      await page.waitForFunction(()=>document.querySelector('#prepare-export-result a'));
      assert.match(await page.$eval('#prepare-export-result',e=>e.textContent),/Download dataset\.jsonl/);
    });

    await t.test('local address: the sidebar shows the host and port actually serving the page, never a fixed one',async()=>{
      const served=new URL(base);
      assert.ok(!['8770','8870'].includes(served.port),'the fixture runs on an ephemeral port, so a hard-coded default cannot pass');
      const shown=()=>page.$eval('#local-address',e=>e.textContent.trim());
      assert.equal(await shown(),served.host);
      // The HTML itself carries no address; only the running page fills it in.
      const html=await page.evaluate(async()=>(await fetch('/')).text());
      assert.doesNotMatch(html.match(/id="local-address"[^>]*>[^<]*/)[0],/\d+\.\d+\.\d+\.\d+|localhost|:\d{2,5}/);
      // Opened under another accepted host name, the same server shows that name and port.
      const other=await browser.newPage();
      try{
        await other.goto(`http://localhost:${served.port}/models`);await other.waitForSelector('#view-models.active');
        assert.equal(await other.$eval('#local-address',e=>e.textContent.trim()),`localhost:${served.port}`);
      }finally{await other.close();}
    });

    await t.test('version label: one value from the server, in both languages, themes and layouts',async()=>{
      const served=await page.evaluate(async()=>(await window.api('/api/v1/config')).app_version_display);
      assert.equal(served,'V2.2.0');
      const label=()=>page.$eval('#app-version',e=>{const r=e.getBoundingClientRect();return {text:e.textContent,visible:r.width>0&&r.height>0,
        inside:r.right<=e.closest('.sidebar').getBoundingClientRect().right+0.5&&r.left>=e.closest('.sidebar').getBoundingClientRect().left-0.5,
        below:r.top>=document.querySelector('.brand-mark').getBoundingClientRect().top};});
      for(const lang of ['en','ar'])for(const theme of ['light','dark']){
        await page.evaluate((l,th)=>{document.documentElement.setAttribute('data-theme',th);window.NajdiI18n.setLanguage(l);},lang,theme);
        const v=await label();
        assert.deepEqual(v,{text:'V2.2.0',visible:true,inside:true,below:true},`${lang} ${theme}`);
      }
      assert.equal(await page.$eval('#settings-version',e=>e.textContent),'V2.2.0','Settings shows the same version');
      await page.click('#collapse-sidebar');
      assert.deepEqual(await label(),{text:'V2.2.0',visible:true,inside:true,below:true},'collapsed sidebar');
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
