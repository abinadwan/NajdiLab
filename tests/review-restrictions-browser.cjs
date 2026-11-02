/* Real review UI + API against disposable synthetic SQLite; no inference. */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {test}=require('node:test');
const puppeteer=require('puppeteer-core');

test('review restriction integrity in Chromium',async t=>{
  const child=spawn(process.env.PYTHON||'python',['-u','-m','tests.test_review_restriction_integrity'],{stdio:['ignore','pipe','pipe']});
  let browser;
  try{
    const base=await new Promise((resolve,reject)=>{
      let out='',err='';const timer=setTimeout(()=>reject(Error('Review fixture timeout: '+err)),15000);
      child.stdout.on('data',chunk=>{out+=chunk;const m=out.match(/REVIEW_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
      child.stderr.on('data',chunk=>err+=chunk);
      child.once('error',reject);child.once('exit',code=>{clearTimeout(timer);reject(Error('Fixture exited '+code+': '+err));});
    });
    assert.ok(!base.endsWith(':8770'));
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    const page=await browser.newPage();
    await page.setViewport({width:1440,height:1000});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    const flags=['#exclude-training','#evaluation-only','#contains-sensitive','#contains-personal','#needs-fact-check'];
    const checked=()=>page.evaluate(selectors=>selectors.map(s=>document.querySelector(s).checked),flags);
    const read=()=>page.evaluate(()=>fetch('/api/v1/review-queue').then(r=>r.json()));
    await page.goto(base+'/review');
    try{await page.waitForFunction(()=>document.querySelector('#queue-position').textContent.includes('of 5'),{timeout:5000});}
    catch(error){throw Error(error.message+'; page errors='+JSON.stringify(errors)+'; toast='+await page.$eval('#toast',e=>e.textContent));}
    await t.test('UX-07 unsaved review changes block navigation until explicitly discarded',async()=>{
      await page.$eval('#review-notes',el=>{el.value='Unsaved synthetic review draft';el.dispatchEvent(new Event('input',{bubbles:true}));});
      const reject=dialog=>dialog.dismiss();
      page.on('dialog',reject);
      await page.click('[data-view="conversations"]');
      page.off('dialog',reject);
      assert.equal(await page.$eval('#view-review-queue',el=>el.classList.contains('active')),true);
      assert.equal(await page.$eval('#review-notes',el=>el.value),'Unsaved synthetic review draft');
      const accept=dialog=>dialog.accept();
      page.on('dialog',accept);
      await page.click('[data-view="conversations"]');
      page.off('dialog',accept);
      await page.waitForSelector('#view-conversations.active');
      await page.click('[data-view="review-queue"]');
      await page.waitForSelector('#view-review-queue.active');
      assert.equal(await page.$eval('#review-notes',el=>el.value),'');
    });
    await t.test('initial load and refresh show saved restrictions and tags',async()=>{
      assert.deepEqual(await checked(),[true,true,true,true,true]);
      assert.equal(await page.$eval('[data-tag="dialect_issue"]',e=>e.classList.contains('selected')),true);
      await page.click('#refresh-view');await page.waitForFunction(()=>document.querySelector('#toast').textContent==='Data refreshed.');
      assert.deepEqual(await checked(),[true,true,true,true,true]);
    });
    await t.test('eligibility selection never clears saved restrictions',async()=>{
      await page.click('#training-eligible');
      assert.deepEqual(await checked(),[true,true,true,true,true]);
      assert.equal(await page.$eval('#training-eligible',e=>e.checked),false);
    });
    await t.test('approval preserves restrictions and tags through persistence',async()=>{
      await page.click('#approve-review');await page.waitForFunction(()=>document.querySelector('#queue-position').textContent.includes('of 4'));
      const saved=await page.evaluate(()=>fetch('/api/v1/reviewed?review_status=APPROVED').then(r=>r.json()));
      const r=saved.items[0];
      assert.deepEqual([r.exclude_from_training,r.evaluation_only,r.contains_sensitive_data,r.contains_personal_data,r.needs_fact_check],[1,1,1,1,1]);
      assert.deepEqual(r.tags,['dialect_issue']);assert.equal(r.training_eligible,0);
    });
    await t.test('stale correction keeps editor draft and saved restrictions unchanged',async()=>{
      const r=(await read()).items[0];
      await page.click('#edit-review');await page.click('[data-status="CONTENT_CORRECTION"]');
      await page.$eval('#corrected-response',e=>e.value='تصحيح المتصفح');
      await page.evaluate(async r=>{
        const {csrf_token}=await fetch('/api/v1/session').then(x=>x.json());
        const response=await fetch(`/api/v1/reviews/${r.id}/correct`,{method:'POST',headers:{'Content-Type':'application/json','X-NajdiLab-CSRF':csrf_token},body:JSON.stringify({expected_updated_at:r.updated_at,review_status:'CONTENT_CORRECTION',corrected_response:'تصحيح متزامن'})});
        if(!response.ok)throw Error('Concurrent synthetic write failed');
      },r);
      await page.click('#save-review');await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('changed after'));
      assert.equal(await page.$eval('#corrected-response',e=>e.value),'تصحيح المتصفح');
      assert.deepEqual(await checked(),[true,true,true,true,true]);
      assert.equal(await page.$eval('#save-review',e=>e.disabled),false);
    });
    await t.test('correction and explicit flag change preserve unrelated restrictions',async()=>{
      await page.reload();await page.waitForFunction(()=>document.querySelector('#queue-position').textContent.includes('of 3'));
      assert.deepEqual(await checked(),[true,true,true,true,true]);
      await page.click('#contains-personal');
      await page.click('#edit-review');await page.click('[data-status="DIALECT_CORRECTION"]');
      await page.$eval('#corrected-response',e=>e.value='تصحيح محفوظ من المتصفح');
      await page.click('#save-review');await page.waitForFunction(()=>document.querySelector('#queue-position').textContent.includes('of 2'));
      const r=await page.evaluate(()=>fetch('/api/v1/reviewed?review_status=DIALECT_CORRECTION').then(r=>r.json()).then(x=>x.items[0]));
      assert.equal(r.contains_personal_data,0);assert.equal(r.contains_sensitive_data,1);
      assert.equal(r.evaluation_only,1);assert.equal(r.exclude_from_training,1);assert.equal(r.needs_fact_check,1);
      assert.deepEqual(r.tags,['dialect_issue']);assert.equal(r.training_eligible,0);
      assert.equal(r.original_response,'الأصل 2');
    });
    await t.test('request failure preserves draft and saved restrictions',async()=>{
      await page.click('#edit-review');await page.click('[data-status="FULL_CORRECTION"]');
      await page.$eval('#corrected-response',e=>e.value='مسودة غير محفوظة');
      const before=(await read()).items[0];
      await page.setRequestInterception(true);
      const intercept=request=>request.url().endsWith('/correct')?request.respond({status:500,contentType:'application/json',body:JSON.stringify({error:'Synthetic save failure'})}):request.continue();
      page.on('request',intercept);
      await page.click('#save-review');await page.waitForFunction(()=>document.querySelector('#toast').textContent==='Synthetic save failure');
      assert.equal(await page.$eval('#corrected-response',e=>e.value),'مسودة غير محفوظة');
      assert.deepEqual(await checked(),[true,true,true,true,true]);
      const after=(await read()).items[0];assert.deepEqual(after,before);
      page.off('request',intercept);await page.setRequestInterception(false);
    });
    await t.test('single-card restore preserves restrictions and returns to pending',async()=>{
      const pending=(await read()).items;
      await page.evaluate(async items=>{
        for(const r of items)await api(`/api/v1/reviews/${r.id}/exclude`,{method:'POST',body:JSON.stringify({reason:'Synthetic browser exclusion',expected_updated_at:r.updated_at})});
      },pending);
      await page.click('[data-view="reviewed"]');
      await page.select('#filter-status','IGNORED');await page.click('#apply-reviewed-filters');
      await page.waitForSelector(`[data-restore-review="${pending[0].id}"]`);
      await page.type('#bulk-review-reason','Synthetic single-card restoration');
      await page.click(`[data-restore-review="${pending[0].id}"]`);
      await page.waitForFunction(()=>document.querySelectorAll('[data-restore-review]').length===1);
      const r=(await read()).items[0];
      assert.equal(r.id,pending[0].id);assert.equal(r.training_eligible,0);
      assert.deepEqual([r.exclude_from_training,r.evaluation_only,r.contains_sensitive_data,r.contains_personal_data,r.needs_fact_check],[1,1,1,1,1]);
      assert.deepEqual(r.tags,['dialect_issue']);assert.equal(r.ignored_reason,'Synthetic single-card restoration');
    });
    await t.test('bulk restore sends loaded revisions and preserves restrictions',async()=>{
      await page.click('.reviewed-row-check');
      await page.$eval('#bulk-review-reason',e=>e.value='Synthetic bulk restoration');
      await page.click('#bulk-restore-reviews');
      await page.waitForFunction(()=>document.querySelectorAll('[data-restore-review]').length===0);
      const items=(await read()).items;
      assert.equal(items.length,2);
      for(const r of items){
        assert.deepEqual([r.exclude_from_training,r.evaluation_only,r.contains_sensitive_data,r.contains_personal_data,r.needs_fact_check],[1,1,1,1,1]);
        assert.equal(r.training_eligible,0);assert.deepEqual(r.tags,['dialect_issue']);
      }
      assert.equal(items[1].ignored_reason,'Synthetic bulk restoration');
    });
    await t.test('init race regression: exactly one queue fetch on /review init',async()=>{
      // Intercept fetch before navigation so the override is in place when app.js runs.
      // __rqDone chains a settled-promise for each review-queue fetch, so awaiting it
      // after waitForFunction ensures any second init-time fetch has also completed
      // before the count is read. Pre-fix: count=2 (direct call + switchView call).
      // Post-fix: count=1 (switchView call only, direct call skipped for review-queue view).
      const s=await page.evaluateOnNewDocument(()=>{
        window.__rqCount=0;
        window.__rqDone=Promise.resolve();
        const orig=window.fetch;
        window.fetch=(...a)=>{
          const p=orig(...a);
          if(String(a[0]).includes('review-queue?include_demo')){
            window.__rqCount++;
            window.__rqDone=window.__rqDone.then(()=>p.then(()=>{},()=>{}));
          }
          return p;
        };
      });
      await page.goto(base+'/review');
      await page.waitForFunction(()=>document.querySelector('#queue-position')?.textContent.includes('of'));
      // Await the chained promise: resolves only when all tracked fetches settle.
      // The init() microtask runs synchronously after the first fetch resolves, so
      // any second fetch is dispatched before Puppeteer receives the waitForFunction
      // notification — __rqDone already includes it by the time we read it here.
      await page.evaluate(()=>window.__rqDone);
      const count=await page.evaluate(()=>window.__rqCount);
      await page.removeScriptToEvaluateOnNewDocument(s.identifier);
      assert.equal(count,1,'init must call loadQueue exactly once on /review (pre-fix would be 2)');
      assert.equal(await page.$eval('#needs-fact-check',e=>e.checked),true);
      await page.click('#needs-fact-check');
      const q=await page.evaluate(()=>fetch('/api/v1/review-queue').then(r=>r.json()));
      assert.ok(q.items.length>0,'queue must have items');
      assert.equal(await page.$eval('#needs-fact-check',e=>e.checked),false,'checkbox must not reset after init (double-render regression)');
    });
    assert.deepEqual(errors,[]);
  }finally{if(browser)await browser.close();child.kill();}
});
