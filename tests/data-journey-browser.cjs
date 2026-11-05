/* The data journey through the three Data destinations, driven with real mouse clicks (V2.2.0 UX + QA P2).
 *   Add data → Prepare data (choose, check, create, export) → My versions, on the synthetic fixture.
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
    const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setViewport({width:1280,height:900});
    const metrics={clicks:0,pages:new Set(),navigations:0};
    page.on('load',()=>metrics.navigations++);
    // A real click: the pointer goes to the element's centre, and whatever is drawn there receives it.
    const click=async selector=>{const handle=await page.waitForSelector(selector,{visible:true});await handle.scrollIntoView();
      const box=await handle.boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2);metrics.clicks++;};
    const view=()=>page.evaluate(()=>document.querySelector('.view.active')?.id);
    const record=async()=>metrics.pages.add(await view());
    await page.goto(base+'/');

    await t.test('the sidebar shows three Data destinations; the old pages stay reachable',async()=>{
      const data=await page.$$eval('.nav-section',s=>s.filter(x=>x.querySelector('#nav-group-data')).flatMap(x=>[...x.querySelectorAll('.nav-item')].map(b=>b.dataset.view)));
      assert.deepEqual(data,['add-data','prepare','my-versions']);
      for(const old of ['dataset-health','balancer','eval-sets','exports','dataset-versions','dataset','manual-data']){
        await page.evaluate(v=>switchView(v),old);await page.waitForSelector(`#view-${old}.active`);
        const active=await page.$eval('.nav-item[aria-current="page"]',b=>b.dataset.view);
        assert.equal(active,old==='manual-data'?'add-data':'my-versions',`${old} is shown under its destination`);
      }
      await page.evaluate(()=>switchView('dashboard'));
    });

    await t.test('Add data: create single-turn, multi-turn and evaluation-only records through the forms',async()=>{
      metrics.clicks=0;metrics.pages.clear();
      await click('.nav-item[data-view="add-data"]');await page.waitForSelector('#view-add-data.active');await record();
      const add=async(turns,{evaluation=false}={})=>{
        await page.waitForSelector('#form-sft.active');
        await page.evaluate(()=>{document.querySelector('#sft-turns').replaceChildren();});
        for(const [role,text] of turns){await click('#add-sft-turn');const rows=await page.$$('#sft-turns .turn-row');const row=rows[rows.length-1];
          await row.$eval('select',(s,r)=>{s.value=r;s.dispatchEvent(new Event('change'));},role);await row.$eval('textarea',(a,v)=>{a.value=v;},text);}
        const eligible=await page.$('#form-sft input[name="training_eligible"]');if(!evaluation&&!(await eligible.evaluate(e=>e.checked)))await click('#form-sft input[name="training_eligible"]');
        if(evaluation)await click('#form-sft input[name="evaluation_only"]');
        await click('#form-sft button[type="submit"]');
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
      await page.waitForFunction(()=>document.querySelectorAll('#prepare-records input[data-id]').length>0);
      const total=await page.$$eval('#prepare-records input[data-id]',b=>b.length);
      const chosenIds=()=>page.evaluate(()=>[...window.NajdiPrepare.state.chosen].sort());
      const all=await chosenIds();assert.equal(all.length,total,'every eligible record starts chosen');
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
          // Keyboard works too.
          await handle.focus();await page.keyboard.press('Space');assert.equal(await handle.evaluate(e=>e.checked),!before);await page.keyboard.press('Space');
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
        const leave=await page.$('#prepare-problems button');assert.ok(leave,'every problem on a chosen record offers a way out: '+text);
        await leave.evaluate(b=>b.scrollIntoView());const box=await leave.boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2);metrics.clicks++;
        await click('#prepare-check');text=await status();
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
      const button=await card.$('button');await button.evaluate(b=>b.scrollIntoView());const bb=await button.boundingBox();await page.mouse.click(bb.x+bb.width/2,bb.y+bb.height/2);
      await page.waitForFunction(v=>{const d=[...document.querySelectorAll('.version-card')].find(c=>c.querySelector('h3').textContent===v)?.querySelector('.version-details');return d&&d.children.length>1||d?.querySelector('[role="alert"]');},{},version);
      const details=await card.$eval('.version-details',d=>({text:d.textContent,downloads:d.querySelectorAll('a[download]').length}));
      assert.ok(details.downloads>0,'the export made in step 3 can be downloaded again from My versions: '+details.text);
      console.log('JOURNEY_METRICS '+JSON.stringify({pages_in_data_journey:[...metrics.pages],clicks_from_check_to_export:clicksToExport,full_page_loads:metrics.navigations,version}));
    });

    await t.test('no page errors',()=>assert.deepEqual(errors,[]));
  }finally{
    await browser?.close();child?.kill();
  }
});
