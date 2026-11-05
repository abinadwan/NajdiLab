/* Direct-language-only Gold acceptance through the real UI and disposable synthetic fixture. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const {test}=require('node:test');
const puppeteer=require('puppeteer-core');

test('Direct language Gold health acceptance in Arabic and English',{timeout:180000},async t=>{
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{
    cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe'],windowsHide:true});
  let browser;
  try{
    const base=await new Promise((resolve,reject)=>{
      let out='',err='';const timer=setTimeout(()=>reject(Error('fixture timeout: '+err)),20000);
      child.stdout.on('data',chunk=>{out+=chunk;const m=out.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
      child.stderr.on('data',chunk=>err+=chunk);
      child.once('exit',code=>{clearTimeout(timer);reject(Error('fixture exited '+code+': '+err));});
    });
    assert.ok(![8770,8870,8871].includes(Number(new URL(base).port)));
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    const allSnapshots=new Map();
    for(const language of ['ar','en'])await t.test(`single direct record, deliberate second version, diagnostic navigation (${language})`,async()=>{
      const context=await browser.createBrowserContext();
      try{
        const page=await context.newPage();await page.setViewport({width:1440,height:1000});
        const errors=[],consoleErrors=[],failures=[],statuses=[];
        page.on('pageerror',e=>errors.push(e.message));
        page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
        page.on('response',r=>{if(r.url().includes('/api/v1/')){
          statuses.push({path:new URL(r.url()).pathname,status:r.status()});
          if(r.status()>=400)failures.push({path:new URL(r.url()).pathname,status:r.status()});
        }});
        const click=async selector=>{const handle=await page.waitForSelector(selector,{visible:true});await handle.scrollIntoView();await handle.click();};
        const responseFor=(suffix,method='GET')=>page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(suffix)&&r.request().method()===method,{timeout:15000});
        const read=async suffix=>{
          const result=await page.evaluate(async suffix=>{const r=await fetch(suffix);return {status:r.status,body:await r.json()};},suffix);
          assert.equal(result.status,200,suffix+' must be readable');return result.body;
        };
        const assertCleanText=async()=>assert.doesNotMatch(await page.$eval('.view.active',e=>e.innerText),/\bnull\b|\bundefined\b|NaN|An internal error|خطأ داخلي/);
        await page.goto(base+'/');await page.waitForSelector('#dashboard-stats button');
        await page.select('#language-select',language);
        assert.equal(await page.$eval('html',e=>e.dir),language==='ar'?'rtl':'ltr');
        await click('.nav-item[data-view="add-data"]');await click('[data-add-tab="direct"]');
        await page.type('#form-direct textarea[name="text"]',language==='ar'?'اااا بببب تتتت':'ثثثث جججج حححح');
        await page.waitForSelector('#form-direct select[name="language"]');await page.select('#form-direct select[name="language"]','ar');
        await click('#form-direct input[name="training_eligible"]');
        const saved=responseFor('/api/v1/manual-data/direct','POST');await click('#form-direct button[type="submit"]');
        const savedResponse=await saved;assert.equal(savedResponse.status(),201);
        const recordId='direct_language_texts:'+(await savedResponse.json()).item.id;
        const created=[];
        for(let attempt=0;attempt<2;attempt++){
          await click('.nav-item[data-view="prepare"]');await page.waitForSelector(`#prepare-records input[data-id="${recordId}"]`);
          await click('#prepare-none');await click(`#prepare-records input[data-id="${recordId}"]`);
          const checked=responseFor('/api/v1/prepare/check','POST');await click('#prepare-check');
          const checkResponse=await checked;assert.equal(checkResponse.status(),200);assert.equal((await checkResponse.json()).status,'ready');
          await page.waitForSelector('#prepare-next-3:not([disabled])');await click('#prepare-next-3');
          assert.equal(await page.$eval('#prepare-confirm',e=>e.checked),false,'each version requires fresh confirmation');
          assert.equal(await page.$eval('#prepare-create',e=>e.disabled),true);
          await click('#prepare-confirm');
          const exported=responseFor('/api/v1/exports','POST');
          const healthResponse=page.waitForResponse(r=>/\/dataset-versions\/gold-v\d+\/health$/.test(new URL(r.url()).pathname));
          await click('#prepare-create');const exportResponse=await exported;assert.equal(exportResponse.status(),201);
          const version=(await exportResponse.json()).export.version;
          assert.ok(!created.includes(version),'the second confirmed build creates a distinct version');created.push(version);
          assert.equal((await healthResponse).status(),200,'new Gold readiness must not crash');
          await page.waitForSelector('#prepare-created a');await assertCleanText();
          const detail=await read(`/api/v1/dataset-versions/${version}`);
          assert.equal(detail.state,'Frozen');assert.equal(detail.manifest.files['direct_language.jsonl'],1);
          assert.equal(detail.manifest.files['sft.jsonl']||0,0);assert.equal(detail.manifest.files['multi_turn.jsonl']||0,0);
          assert.equal(detail.eval.eval_count,0);assert.equal(detail.eval.leakage_free,true);
          assert.equal(detail.health.highest_record_share,null);
          const fileHashes=Object.fromEntries(detail.files.map(file=>[file.name,file.sha256]));
          for(const [name,digest] of Object.entries(detail.manifest.sha256))assert.equal(fileHashes[name],digest,name);
          allSnapshots.set(version,detail.files);
          await click('#prepare-created a');await page.waitForSelector('#view-my-versions.active');
          await page.waitForFunction(v=>[...document.querySelectorAll('.version-card')].some(c=>c.querySelector('h3')?.textContent===v),{},version);
          const card=await page.evaluateHandle(v=>[...document.querySelectorAll('.version-card')].find(c=>c.querySelector('h3')?.textContent===v),version);
          const button=await card.$('button');await button.scrollIntoView();await button.click();
          await page.waitForFunction(v=>[...document.querySelectorAll('.version-card')].find(c=>c.querySelector('h3')?.textContent===v)?.querySelector('.version-details h4'),{},version);
          await assertCleanText();
          await click('.nav-item[data-view="settings"]');
          if(!(await page.$eval('#advanced-mode',e=>e.checked)))await click('#advanced-mode');
          await click('[data-advanced-view="dataset-health"]');
          await page.waitForSelector(`#health-version option[value="${version}"]`);
          const healthSelected=responseFor(`/dataset-versions/${version}/health`);await page.select('#health-version',version);assert.equal((await healthSelected).status(),200);
          await page.waitForSelector('#health-results:not(.hidden)');await assertCleanText();
          const concentration=await page.$$eval('#health-checks [data-health-detail="balance"]',els=>{
            const card=els.at(-1);return {status:card.querySelector('.health-card-status').textContent,value:card.querySelector('strong').textContent};
          });
          assert.deepEqual(concentration,{status:language==='ar'?'غير متاح':'Unavailable',value:'—'});
          await click('.nav-item[data-view="settings"]');
          const balanced=responseFor(`/dataset-versions/${version}/balance`);await click('[data-advanced-view="balancer"]');assert.equal((await balanced).status(),200);
          await page.waitForSelector('#balance-results:not(.hidden)');await assertCleanText();
          await click('.nav-item[data-view="settings"]');await click('[data-advanced-view="dataset-versions"]');
          const detailed=responseFor(`/dataset-versions/${version}`);await click(`#version-list [data-version-name="${version}"]`);assert.equal((await detailed).status(),200);
          await page.waitForFunction(v=>document.querySelector('#version-detail .version-hero h2')?.textContent===v,{},version);await assertCleanText();
          await click('.nav-item[data-view="settings"]');await click('#advanced-mode');await click('.nav-item[data-view="my-versions"]');
          await page.waitForSelector('#view-my-versions.active');assert.equal(await page.$eval('html',e=>e.classList.contains('advanced-mode')),false);
          for(const [name,files] of allSnapshots)assert.deepEqual((await read(`/api/v1/dataset-versions/${name}`)).files,files,`${name} stays byte-identical after navigation and another build`);
        }
        fs.mkdirSync('.test-tmp/gold-health-screens',{recursive:true});
        await page.screenshot({path:`.test-tmp/gold-health-screens/versions-${language}.png`,fullPage:true});
        assert.deepEqual(errors,[]);assert.deepEqual(consoleErrors,[]);assert.deepEqual(failures,[]);
        fs.writeFileSync(`.test-tmp/gold-health-screens/http-${language}.json`,JSON.stringify(statuses,null,2));
        const statusCounts={};for(const item of statuses)statusCounts[item.status]=(statusCounts[item.status]||0)+1;
        console.log('GOLD_HEALTH_ACCEPTANCE '+JSON.stringify({language,versions:created,statusCounts,manifest_hashes_verified:true,frozen_unchanged:true}));
      }finally{await context.close();}
    });
  }finally{await browser?.close();child.kill();}
});
