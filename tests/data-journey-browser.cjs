/* The four-stage data workspace and legacy deep links, driven with real mouse clicks (V2.2.0 UX + QA P2).
 *   Data → Check and correct → Approve Gold → Export → My versions, on the synthetic fixture.
 * Measures pages, clicks and page changes; proves that filters never change the choice (QA P2) and that the sticky
 * top bar never covers a checkbox scrolled into view (QA P2), in English, Arabic and on a narrow screen.
 * Usage: NAJDILAB_BROWSER_EXECUTABLE=<chromium> NODE_PATH=<dir with puppeteer-core> node --test tests/data-journey-browser.cjs */
'use strict';
const assert=require('node:assert/strict');
const test=require('node:test');
const {spawn}=require('node:child_process');
const path=require('node:path');
const puppeteer=require('puppeteer-core');

test('data journey in Chromium',{timeout:300000},async t=>{
  // NAJDILAB_JOURNEY_BASE runs the same journey against an already running, isolated NajdiLab (never the user's).
  const external=process.env.NAJDILAB_JOURNEY_BASE;
  const child=external?null:spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe'],windowsHide:true});
  let browser;
  try{
    const base=external||await new Promise((resolve,reject)=>{let text='';const timer=setTimeout(()=>reject(Error('fixture timeout')),20000);
      child.stdout.on('data',c=>{text+=c;const m=text.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});});
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    const page=await browser.newPage();const errors=[],apiFailures=[];page.on('pageerror',e=>errors.push(e.message));
    page.on('response',r=>{if(r.url().includes('/api/v1/')&&r.status()>=400)apiFailures.push({path:new URL(r.url()).pathname,status:r.status()});});
    await page.setViewport({width:1280,height:900});
    const metrics={clicks:0,pages:new Set(),navigations:0};
    page.on('load',()=>metrics.navigations++);
    // A real click: the pointer goes to the element's centre, and whatever is drawn there receives it.
    const click=async selector=>{const handle=await page.waitForSelector(selector,{visible:true});await handle.scrollIntoView();
      const box=await handle.boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2);metrics.clicks++;};
    const view=()=>page.evaluate(()=>document.querySelector('.view.active')?.id);
    const record=async()=>metrics.pages.add(await view());
    await page.goto(base+'/');

    await t.test('Dashboard opens preparation and frozen versions with keyboard controls',async()=>{
      assert.equal(await page.$$eval('#view-dashboard .workflow-steps li',els=>els.length),4);
      assert.equal(await page.$('#view-dashboard [data-go="exports"], #view-dashboard [data-go="balancer"], #view-dashboard [data-go="dataset-health"]'),null);
      await page.focus('#view-dashboard .button.primary[data-go="prepare"]');
      await page.keyboard.press('Enter');await page.waitForSelector('#view-prepare.active');
      await page.evaluate(()=>switchView('dashboard'));
      await click('#view-dashboard .panel-heading [data-go="my-versions"]');await page.waitForSelector('#view-my-versions.active');
      assert.equal(await page.$('#view-my-versions [data-advanced-view]'),null);
      await page.evaluate(()=>switchView('dashboard'));
      await click('#view-dashboard .workflow-card [data-go="review-queue"]');await page.waitForSelector('#view-review-queue.active');
    });

    await t.test('Advanced Mode is opt-in, persists, and leaves every deep link usable when disabled',async()=>{
      await page.evaluate(()=>switchView('settings'));
      assert.equal(await page.$eval('#advanced-mode',e=>e.checked),false);
      const visible=()=>page.$$eval('[data-advanced-view]',els=>els.filter(e=>e.checkVisibility()).map(e=>e.dataset.advancedView));
      assert.deepEqual(await visible(),[]);
      await page.focus('#advanced-mode');await page.keyboard.press('Space');
      await page.waitForSelector('#view-prepare.active');
      const expected=['manual-data','dataset-health','balancer','eval-sets','dataset-versions','exports','add-data'];
      assert.deepEqual(await visible(),expected);
      assert.equal(await page.$eval('#guided-wizard',e=>e.checkVisibility()),false);
      assert.equal(await page.$eval('#workspace-mode',e=>e.checked),true);
      await page.reload();await page.waitForSelector('#view-prepare.active');
      assert.equal(await page.$eval('#advanced-mode',e=>e.checked),true);
      assert.deepEqual(await visible(),expected);
      for(const view of expected){
        await click(`#advanced-workspace [data-advanced-view="${view}"]`);await page.waitForSelector(`#view-${view}.active`);
        await page.evaluate(()=>switchView('prepare'));
      }
      await page.focus('#workspace-mode');await page.keyboard.press('Space');
      await page.reload();await page.waitForSelector('#view-prepare.active');
      assert.equal(await page.$eval('#advanced-mode',e=>e.checked),false);
      assert.deepEqual(await visible(),[]);
      for(const [path,view] of [['/datasets/gold','dataset'],['/datasets/health','dataset-health'],['/datasets/balancer','balancer'],['/datasets/versions','dataset-versions'],['/datasets/eval','eval-sets'],['/exports','exports']]){
        await page.goto(base+path);await page.waitForSelector(`#view-${view}.active`);
        assert.equal(await page.$eval('#advanced-mode',e=>e.checked),false);
      }
      await page.evaluate(()=>switchView('dashboard'));
    });

    await t.test('changed screens reflow in both languages and themes at 320, 390 and 1440 pixels',async()=>{
      const fs=require('node:fs');const out=path.resolve('.test-tmp/ux-screens');fs.mkdirSync(out,{recursive:true});
      for(const language of ['en','ar'])for(const theme of ['light','dark'])for(const width of [320,390,1440]){
        await page.setViewport({width,height:900});
        await page.evaluate(({language,theme})=>{NajdiI18n.setLanguage(language);document.querySelector('#theme-select-settings').value=theme;document.querySelector('#theme-select-settings').dispatchEvent(new Event('change'));},{language,theme});
        for(const view of ['dashboard','settings','my-versions']){
          await page.evaluate(v=>switchView(v),view);await page.waitForSelector(`#view-${view}.active`);
          await new Promise(r=>setTimeout(r,100));
          const measured=await page.evaluate(()=>({lang:document.documentElement.lang,dir:document.documentElement.dir,theme:document.documentElement.dataset.theme,
            width:innerWidth,scroll:document.documentElement.scrollWidth,text:document.querySelector('.view.active').innerText}));
          assert.equal(measured.lang,language);assert.equal(measured.dir,language==='ar'?'rtl':'ltr');assert.equal(measured.theme,theme);
          assert.ok(measured.scroll<=measured.width+1,`${language}/${theme}/${width}/${view}: horizontal overflow ${measured.scroll}`);
          assert.doesNotMatch(measured.text,/\bnull\b|\bundefined\b|NaN/);
          await page.screenshot({path:path.join(out,`${view}-${language}-${theme}-${width}.png`),fullPage:true});
        }
      }
      await page.setViewport({width:1280,height:900});
      await page.evaluate(()=>{NajdiI18n.setLanguage('en');document.querySelector('#advanced-mode').checked=false;document.querySelector('#advanced-mode').onchange();});
      await page.evaluate(()=>switchView('dashboard'));
    });

    await t.test('blocked storage keeps Advanced Mode usable for the current page',async()=>{
      const isolated=await browser.createBrowserContext();
      try{
        const blocked=await isolated.newPage();
        await blocked.evaluateOnNewDocument(()=>{
          Storage.prototype.getItem=function(){throw Error('storage blocked');};
          Storage.prototype.setItem=function(){throw Error('storage blocked');};
        });
        await blocked.goto(base+'/settings');await blocked.waitForSelector('#view-settings.active');
        assert.equal(await blocked.$eval('#advanced-mode',e=>e.checked),false);
        await blocked.focus('#advanced-mode');await blocked.keyboard.press('Space');
        await blocked.waitForSelector('#view-prepare.active');
        assert.equal(await blocked.$$eval('#advanced-workspace [data-advanced-view]',els=>els.filter(e=>e.checkVisibility()).length),7);
        await blocked.reload();await blocked.waitForSelector('#view-prepare.active');
        assert.equal(await blocked.$eval('#advanced-mode',e=>e.checked),false);
      }finally{await isolated.close();}
    });

    await t.test('the guided sidebar shows workspace and versions; legacy pages stay reachable',async()=>{
      const data=await page.$$eval('.nav-section',s=>s.filter(x=>x.querySelector('#nav-group-data')).flatMap(x=>[...x.querySelectorAll('.nav-item')].map(b=>b.dataset.view)));
      assert.deepEqual(data,['add-data','prepare','my-versions']);
      const visible=await page.$$eval('.nav-section',s=>s.filter(x=>x.querySelector('#nav-group-data')).flatMap(x=>[...x.querySelectorAll('.nav-item')].filter(b=>b.checkVisibility()).map(b=>b.dataset.view)));
      assert.deepEqual(visible,['prepare','my-versions']);
      for(const old of ['dataset-health','balancer','eval-sets','exports','dataset-versions','dataset','manual-data']){
        await page.evaluate(v=>switchView(v),old);await page.waitForSelector(`#view-${old}.active`);
        const active=await page.$eval('.nav-item[aria-current="page"]',b=>b.dataset.view);
        assert.equal(active,old==='manual-data'?'add-data':'my-versions',`${old} is shown under its destination`);
      }
      await page.evaluate(()=>switchView('dashboard'));
    });

    await t.test('Add data: create single-turn, multi-turn and evaluation-only records through the forms',async()=>{
      metrics.clicks=0;metrics.pages.clear();
      await page.evaluate(()=>switchView('add-data'));await page.waitForSelector('#view-add-data.active');await record();
      const add=async(turns,{evaluation=false}={})=>{
        await page.waitForSelector('#form-sft.active');
        await page.evaluate(()=>{document.querySelector('#sft-turns').replaceChildren();});
        for(const [role,text] of turns){await click('#add-sft-turn');const rows=await page.$$('#sft-turns .turn-row');const row=rows[rows.length-1];
          await row.$eval('select',(s,r)=>{s.value=r;s.dispatchEvent(new Event('change'));},role);await row.$eval('textarea',(a,v)=>{a.value=v;},text);}
        const eligible=await page.$('#form-sft input[name="training_eligible"]');if(!evaluation&&!(await eligible.evaluate(e=>e.checked)))await click('#form-sft input[name="training_eligible"]');
        if(evaluation)await click('#form-sft input[name="evaluation_only"]');
        const saved=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/manual-data/sft'&&r.request().method()==='POST');
        await click('#form-sft button[type="submit"]');
        assert.equal((await saved).status(),201);
        await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Record saved'));
      };
      await add([['user','How do I report a phishing email at work?'],['assistant','Forward it to the security team and delete it.']]);
      await add([['user','Summarise our refund rule in one line.'],['assistant','Refunds within 14 days with a receipt.'],['user','And without a receipt?'],['assistant','Store credit only.']]);
      await add([['user','Is a long passphrase better than a short complex password?'],['assistant','Yes; length adds more strength.']],{evaluation:true});
      // One record flagged as personal data (through the public API): the check must stop on it and offer to leave it out.
      await page.evaluate(()=>api('/api/v1/manual-data/sft',{method:'POST',body:JSON.stringify({training_eligible:true,contains_personal_data:true,
        messages:[{role:'user',content:'My phone number is in this message; can you store it?'},{role:'assistant',content:'I would rather not keep personal numbers.'}]})}));
      // My records is a tab of the same destination.
      await click('#view-add-data [data-add-records]');await page.waitForSelector('#view-manual-data.active');
      assert.equal(await page.$eval('.nav-item[aria-current="page"]',b=>b.dataset.view),'add-data');
      await page.waitForFunction(()=>document.querySelector('#view-manual-data').textContent.includes('phishing'));
    });

    await t.test('Prepare data: a filter never changes the choice (QA P2)',async()=>{
      await click('.nav-item[data-view="prepare"]');await page.waitForSelector('#view-prepare.active');await record();
      await page.evaluate(()=>NajdiPrepare.load());
      await page.waitForFunction(()=>document.querySelectorAll('#prepare-records input[data-id]').length>0);
      const total=await page.$$eval('#prepare-records input[data-id]',b=>b.length);
      const chosenIds=()=>page.evaluate(()=>[...window.NajdiPrepare.state.chosen].sort());
      const eligible=await page.evaluate(()=>NajdiPrepare.state.records.filter(r=>r.eligible).map(r=>r.id).sort());
      const retained=await chosenIds();
      // The API-created example may be discovered by an in-flight form refresh.
      // Establish the full choice explicitly before testing filter preservation.
      assert.ok(retained.every(id=>eligible.includes(id)),'retained choices are eligible records');
      await click('#prepare-all');
      const all=await chosenIds();assert.equal(all.length,total,'explicitly choose every record, including the privacy-blocked example');
      await page.select('#prepare-type','sft');
      const shown=await page.$$eval('#prepare-records input[data-id]',b=>b.map(x=>x.dataset.id));
      assert.ok(shown.length<total,'the filter hides some records');
      assert.deepEqual(await chosenIds(),all,'hiding records does not leave them out');
      assert.match(await page.$eval('#prepare-count',e=>e.textContent),/not shown by the filters/);
      // Leaving out a shown record while filtered changes only that record.
      const first=shown[0];await click(`#prepare-records input[data-id="${first}"]`);
      assert.deepEqual(await chosenIds(),all.filter(x=>x!==first));
      await click(`#prepare-records input[data-id="${first}"]`);
      await page.select('#prepare-type','');
      assert.deepEqual(await chosenIds(),all,'back to all types: nothing was lost');
      // What the check sends is the full choice, not only what is shown.
      await page.select('#prepare-type','sft');
      // A success notice is showing over the bottom of the page; the real click must still reach the button under it.
      await page.evaluate(()=>toast('Record saved with source information.'));
      const sent=new Promise(resolve=>page.on('request',r=>{if(r.url().endsWith('/api/v1/prepare/check'))resolve(JSON.parse(r.postData()).selection.sort());}));
      await click('#prepare-check');
      assert.deepEqual(await sent,all,'the check covers every chosen record, including hidden ones');
      await page.waitForSelector('#prepare-status .prepare-badge, #prepare-status [role="alert"]');
      await click('.prepare-stepper-item[data-step="1"]');
      await page.select('#prepare-type','');
    });

    await t.test('the sticky top bar never covers a checkbox scrolled into view (QA P2)',async()=>{
      // The closed phone drawer slides away over 0.2 s after a resize or a language change; let it settle first.
      const settle=()=>page.evaluate(()=>Promise.all(document.getAnimations().map(a=>a.finished.catch(()=>{}))));
      const checkAll=async label=>{
        await settle();
        await page.evaluate(()=>window.NajdiPrepare.load());
        await page.waitForFunction(()=>document.querySelectorAll('#prepare-records input[data-id]').length>0);
        const ids=await page.$$eval('#prepare-records input[data-id]',b=>b.map(x=>x.dataset.id));
        for(const id of ids){
          // Scroll the checkbox to the very top, as keyboard focus or "scroll into view" does, then click where it is drawn.
          const handle=await page.$(`#prepare-records input[data-id="${id}"]`);
          await handle.evaluate(e=>e.scrollIntoView({block:'start'}));
          const box=await handle.boundingBox();const x=box.x+box.width/2,y=box.y+box.height/2;
          const hit=await page.evaluate((x,y)=>{const e=document.elementFromPoint(x,y);return e?.dataset?.id||e?.closest?.('label')?.querySelector('input')?.dataset?.id||e?.className;},x,y);
          assert.equal(hit,id,`${label}: ${id} is not covered (pointer reaches ${hit})`);
          const before=await handle.evaluate(e=>e.checked);await page.mouse.click(x,y);
          assert.equal(await handle.evaluate(e=>e.checked),!before,`${label}: a real click toggles ${id}`);
          await page.mouse.click(x,y);
          assert.equal(await handle.evaluate(e=>e.checked),before,`${label}: a second real click restores ${id}`);
          // Keyboard works too.
          await handle.focus();await page.keyboard.press('Space');assert.equal(await handle.evaluate(e=>e.checked),!before,`${label}: Space toggles ${id}`);
          assert.equal(await handle.evaluate(e=>document.activeElement===e),true,`${label}: the checkbox keeps keyboard focus`);
          await page.keyboard.press('Space');assert.equal(await handle.evaluate(e=>e.checked),before,`${label}: Space restores ${id}`);
        }
      };
      // A short window, so the page itself must scroll a record up to where the top bar sits.
      await page.setViewport({width:1280,height:420});await checkAll('English, desktop');
      await page.evaluate(()=>window.NajdiI18n.setLanguage('ar'));await checkAll('Arabic, desktop');
      await page.setViewport({width:390,height:420});await checkAll('Arabic, 390 px');
      await page.evaluate(()=>window.NajdiI18n.setLanguage('en'));await checkAll('English, 390 px');
      await page.setViewport({width:1280,height:900});
    });

    await t.test('check, fix by leaving records out, create with confirmation, export, open in My versions',async()=>{
      await page.evaluate(()=>window.NajdiPrepare.load());
      await page.waitForFunction(()=>document.querySelectorAll('#prepare-records input[data-id]').length>0);
      metrics.clicks=0;
      const status=async()=>{await page.waitForSelector('#prepare-status .prepare-badge, #prepare-status [role="alert"]');return page.$eval('#prepare-status',e=>e.textContent);};
      await click('#prepare-check');let text=await status();
      assert.ok(!(await page.$eval('#prepare-status .prepare-badge',b=>b.classList.contains('ready'))),'the privacy-flagged record stops the first check');
      const shownText=()=>page.$eval('#view-prepare',v=>v.innerText);
      assert.doesNotMatch(await shownText(),/null|undefined|NaN/,'a check that is not ready shows no empty values');
      const ready=()=>page.$eval('#prepare-status .prepare-badge',b=>b.classList.contains('ready'));
      for(let i=0;i<8&&!(await ready());i++){
        const leave=await page.$('#prepare-problems .record-actions button:last-child');assert.ok(leave,'every problem on a chosen record offers a way out: '+text);
        await leave.evaluate(b=>b.scrollIntoView());const box=await leave.boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2);metrics.clicks++;
        await click('#prepare-recheck');text=await status();
      }
      assert.ok(await ready(),text);
      assert.doesNotMatch(await shownText(),/null|undefined|NaN/);
      assert.match(await page.$eval('#prepare-summary',e=>e.textContent),/records accepted[\s\S]*Evaluation records:/);
      assert.equal(await page.$eval('#prepare-advanced',e=>e.open),false,'technical details stay folded');
      // Changing the choice invalidates the check.
      const one=await page.$('#prepare-records input[data-id]');
      await click('.prepare-stepper-item[data-step="1"]');await one.evaluate(e=>e.scrollIntoView());const b1=await one.boundingBox();
      await page.mouse.click(b1.x+b1.width/2,b1.y+b1.height/2);
      assert.equal(await page.$eval('.prepare-stepper-item[data-step="3"]',b=>b.disabled),true,'a changed choice must be checked again');
      await page.mouse.click(b1.x+b1.width/2,b1.y+b1.height/2);
      await click('#prepare-check');await status();assert.ok(await ready());
      await click('#prepare-next-3');await page.waitForSelector('#prepare-panel-3:not([hidden])');
      assert.equal(await page.$eval('#prepare-create',b=>b.disabled),true,'no version without the final confirmation');
      await click('#prepare-confirm');await click('#prepare-create');
      await page.waitForFunction(()=>/Created and frozen|alert/.test(document.querySelector('#prepare-created').innerHTML));
      const created=await page.$eval('#prepare-created',e=>e.textContent);
      assert.match(created,/Created and frozen: gold-v\d+[\s\S]*Structural validity: Valid/);
      const version=created.match(/gold-v\d+/)[0];
      await click('#prepare-export-go');await page.waitForFunction(()=>document.querySelector('#prepare-export-result a'));
      const clicksToExport=metrics.clicks;
      await click('#prepare-created a');await page.waitForSelector('#view-my-versions.active');await record();
      await page.waitForFunction(v=>document.querySelector('#versions-list').textContent.includes(v),{},version);
      const card=await page.evaluateHandle(v=>[...document.querySelectorAll('.version-card')].find(c=>c.querySelector('h3').textContent===v),version);
      const button=await card.$('.workflow-actions button:nth-child(2)');await button.evaluate(b=>b.scrollIntoView());const bb=await button.boundingBox();await page.mouse.click(bb.x+bb.width/2,bb.y+bb.height/2);
      await page.waitForFunction(v=>{const d=[...document.querySelectorAll('.version-card')].find(c=>c.querySelector('h3').textContent===v)?.querySelector('.version-details:last-child');return d&&d.children.length>1||d?.querySelector('[role="alert"]');},{},version);
      const details=await card.$eval('.version-details:last-child',d=>({text:d.textContent,downloads:d.querySelectorAll('a[download]').length}));
      assert.ok(details.downloads>0,'the export made in step 4 can be downloaded again from My versions: '+details.text);
      assert.equal(await card.$eval('[data-advanced-only]',e=>e.checkVisibility()),false,'ordinary versions hide specialist diagnostics');
      const downloads=await card.$$eval('a[download]',els=>els.map(e=>e.href));
      for(const url of downloads){
        const response=await page.evaluate(async url=>{const r=await fetch(url);return {status:r.status,text:await r.text()};},url);
        assert.equal(response.status,200,'saved export can actually be downloaded');
        assert.ok(response.text.length>0);
      }
      console.log('JOURNEY_METRICS '+JSON.stringify({pages_in_data_journey:[...metrics.pages],clicks_from_check_to_export:clicksToExport,full_page_loads:metrics.navigations,version}));
    });

    await t.test('no page errors or failed API requests',()=>{assert.deepEqual(errors,[]);assert.deepEqual(apiFailures,[]);});
  }finally{
    await browser?.close();child?.kill();
  }
});
