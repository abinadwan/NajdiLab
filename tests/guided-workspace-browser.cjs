/* Real user acceptance. Every mutation uses UI controls against a disposable fixture. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const path=require('node:path');
const fs=require('node:fs');
const {test}=require('node:test');
const puppeteer=require('puppeteer-core');
const evidence=path.resolve('.test-tmp/guided-acceptance');

function untranslatedInterface(){
  const skipped='script,style,code,pre,textarea,bdi,kbd,samp,time,[dir="auto"],[translate="no"],[data-i18n-skip]';
  const allowed=['NajdiLab Native','NajdiLab','Unsloth Studio','Unsloth','TRL','Python','Alpaca','Gold','SFT','DPO','JSONL','JSON','SHA-256','API','GPU','RAM','VRAM','HTTP','LM Studio','Ollama','Hugging Face','GGUF','Native','completion_only_loss=True','packing=False','Train on completions'];
  const missing=[];const walker=document.createTreeWalker(document.querySelector('.view.active'),NodeFilter.SHOW_TEXT);
  while(walker.nextNode()){
    const n=walker.currentNode,p=n.parentElement;if(!p||p.closest(skipped)||!p.checkVisibility())continue;
    let text=n.nodeValue.trim().replace(/(?:manual_sft_items|direct_language_texts|preference_pairs|review):\d+/g,' ');for(const term of allowed)text=text.split(term).join(' ');
    if(/[A-Za-z]{2,}/.test(text))missing.push(n.nodeValue.trim());
  }
  return [...new Set(missing)];
}

function fixture(){
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe'],windowsHide:true});
  const ready=new Promise((resolve,reject)=>{let out='',err='';const timer=setTimeout(()=>reject(Error(err||'fixture timeout')),20000);
    child.stdout.on('data',c=>{out+=c;const match=out.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
    child.stderr.on('data',c=>err+=c);child.once('exit',code=>{clearTimeout(timer);reject(Error('fixture exited '+code+': '+err));});});
  return {child,ready};
}

test('complete guided workflow and isolated version management',{timeout:360000},async t=>{
  fs.mkdirSync(evidence,{recursive:true});const shots=[];
  const browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
  try{
    for(const language of (process.env.NAJDILAB_ACCEPTANCE_LANGUAGES||'en,ar').split(','))await t.test(`actual user journey (${language})`,async()=>{
      const service=fixture(),context=await browser.createBrowserContext();let page;
      try{
        const base=await service.ready;assert.ok(![8770,8870,8871].includes(Number(new URL(base).port)));
        page=await context.newPage();await page.evaluateOnNewDocument(()=>localStorage.setItem('najdilab.advancedMode','1'));await page.setViewport({width:1440,height:1000});
        const downloads=path.join(evidence,'downloads',language);fs.mkdirSync(downloads,{recursive:true});
        const cdp=await page.createCDPSession();await cdp.send('Page.setDownloadBehavior',{behavior:'allow',downloadPath:downloads});
        const errors=[],consoleErrors=[],serverErrors=[],requests=[],legacyRequests=[];
        page.on('request',request=>{if(/advanced-workspace\.(js|css|html)/.test(request.url()))legacyRequests.push(request.url());});
        page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text());});
        page.on('response',r=>{if(r.url().includes('/api/v1/')){requests.push({method:r.request().method(),path:new URL(r.url()).pathname,status:r.status()});if(r.status()>=500)serverErrors.push(r.url());}});
        const click=async selector=>{const handle=await page.waitForSelector(selector,{visible:true});await handle.scrollIntoView();await handle.click();};
        const type=async(selector,value)=>{await click(selector);await page.keyboard.down('Control');await page.keyboard.press('a');await page.keyboard.up('Control');await page.keyboard.type(value);};
        const response=(suffix,method='GET')=>page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(suffix)&&r.request().method()===method,{timeout:15000});
        const read=async suffix=>{const result=await page.evaluate(async suffix=>{const r=await fetch(suffix);return {status:r.status,body:await r.json()};},suffix);assert.equal(result.status,200,suffix);return result.body;};
        const stage=async n=>page.waitForSelector(`#prepare-panel-${n}:not([hidden])`);
        const settledRecord=async id=>page.waitForSelector(`#prepare-records input[data-id="${id}"]`);
        const textClean=async()=>assert.doesNotMatch(await page.$eval('.view.active',e=>e.innerText),/\bnull\b|\bundefined\b|NaN|An internal error|خطأ داخلي/);
        const capture=async(label,matrix=false)=>{
          for(const theme of matrix?['light','dark']:['light'])for(const width of matrix?[320,390,1440]:[1440]){
            await page.setViewport({width,height:1000});await page.select('#theme-select',theme);
            await page.waitForSelector('#toast:not(.show)');
            await page.evaluate(async()=>{
              await document.fonts.ready;
              window.scrollTo(0,0);
              await Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})));
              await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
            });
            await textClean();
            if(language==='ar')assert.deepEqual(await page.evaluate(untranslatedInterface),[],label+' has untranslated interface text');
            const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);assert.ok(overflow<=1,`${label}/${language}/${theme}/${width} overflows by ${overflow}`);
            const layout=await page.evaluate(()=>({scrollX,offset:visualViewport.offsetLeft,rects:['body','.shell','.main','.view.active'].map(selector=>{const r=document.querySelector(selector).getBoundingClientRect();return {selector,x:r.x,width:r.width,right:r.right};})}));
            fs.writeFileSync(path.join(evidence,`${language}-${label}-${theme}-${width}-layout.json`),JSON.stringify(layout,null,2));
            const name=`${language}-${label}-${theme}-${width}.png`;
            const displayVersion=await page.$eval('#app-version',element=>element.textContent);
            assert.equal(displayVersion,'V2.3.0','current screenshot source version');
            await page.screenshot({path:path.join(evidence,name),fullPage:!await page.$('dialog[open]'),captureBeyondViewport:false});
            shots.push({language,label,theme,width,name,displayVersion,capturedAt:new Date().toISOString()});
          }
          await page.setViewport({width:1440,height:1000});await page.select('#theme-select','light');
        };
        const setCheck=async(selector,value)=>{if(await page.$eval(selector,e=>e.checked)!==value)await click(selector);};
        const add=async(question,answer,{evaluation=false}={})=>{
          await click('#wizard-add-record');await click('[data-add-tab="sft"]');
          await type('#sft-turns .turn-row:nth-child(1) textarea',question);await type('#sft-turns .turn-row:nth-child(2) textarea',answer);
          await page.select('#form-sft select[name="language"]','en');
          await setCheck('#form-sft input[name="training_eligible"]',!evaluation);await setCheck('#form-sft input[name="evaluation_only"]',evaluation);
          const saved=response('/api/v1/manual-data/sft','POST');await click('#form-sft button[type="submit"]');const r=await saved;assert.equal(r.status(),201);
          const id=(await r.json()).item.id;await settledRecord('manual_sft_items:'+id);return id;
        };
        const edit=async(id,answer)=>{
          await click(`[data-record-action="edit"][data-record-id="manual_sft_items:${id}"]`);
          await page.waitForSelector('#manual-edit-form');await type('#manual-edit-turns .turn-row:nth-child(2) textarea',answer);
          await capture('record-edit');const saved=response(`/manual-data/sft/${id}`,'PATCH');await click('#manual-edit-form button[type="submit"]');assert.equal((await saved).status(),200);
          await page.waitForSelector('#manual-dialog .detail-actions');await click('#close-manual-dialog');await settledRecord('manual_sft_items:'+id);
        };
        const doCheck=async(selector='#prepare-check')=>{const checked=response('/api/v1/prepare/check','POST');await click(selector);const r=await checked;assert.equal(r.status(),200);await stage(2);await page.waitForSelector('#prepare-status .prepare-badge');return r.json();};
        const approve=async()=>{await click('#prepare-next-3');await stage(3);assert.equal(await page.$eval('#prepare-create',e=>e.disabled),true);await capture('approve',true);await click('#prepare-confirm');
          const created=response('/api/v1/exports','POST');await click('#prepare-create');const r=await created;assert.equal(r.status(),201);const version=(await r.json()).export.version;
          await stage(4);await page.waitForSelector('#prepare-raw-exports a');await textClean();return version;};
        const versionFiles=async v=>(await read(`/api/v1/dataset-versions/${v}`)).files;
        await page.goto(base+'/');await page.waitForSelector('#dashboard-stats button');await page.select('#language-select',language);await capture('start');
        await click('#view-dashboard .button.primary[data-go="prepare"]');await stage(1);await page.waitForFunction(()=>document.querySelector('#prepare-records .workspace-empty'));
        assert.equal(await page.$$eval('.prepare-stepper-item',els=>els.length),4);assert.equal(await page.$('#workspace-mode'),null);assert.equal(await page.$('#advanced-mode'),null);
        await capture('data-empty',true);
        await page.setViewport({width:390,height:1000});
        await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
        await page.focus('#mobile-menu');await page.keyboard.press('Enter');
        await page.waitForFunction(()=>{
          const label=document.getElementById('app-version').getBoundingClientRect();
          return document.querySelector('.sidebar.open')&&label.left>=0&&label.right<=innerWidth;
        });
        await page.evaluate(async()=>{
          await Promise.all(document.getAnimations().map(animation=>animation.finished.catch(()=>{})));
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        });
        const mobileVersion=await page.$eval('#app-version',element=>({text:element.textContent,visible:element.checkVisibility()}));
        assert.deepEqual(mobileVersion,{text:'V2.3.0',visible:true});
        const mobileName=`${language}-mobile-version-light-390.png`;
        await page.screenshot({path:path.join(evidence,mobileName),fullPage:false});
        shots.push({language,label:'mobile-version',theme:'light',width:390,name:mobileName,displayVersion:mobileVersion.text,capturedAt:new Date().toISOString()});
        await page.keyboard.press('Escape');await page.setViewport({width:1440,height:1000});
        const first=await add('Explain a synthetic refund rule.','Incorrect draft answer.');
        await edit(first,'Refunds are available within fourteen days with a receipt.');
        assert.ok((await read(`/api/v1/manual-data/sft/${first}/versions`)).items.length>=2);
        const temporary=await add('Temporary question for safe deletion.','Temporary answer to remove.');
        page.once('dialog',d=>d.accept());const removed=response(`/manual-data/sft/${temporary}`,'DELETE');
        await click(`[data-record-action="delete"][data-record-id="manual_sft_items:${temporary}"]`);assert.equal((await removed).status(),200);
        await page.waitForFunction(id=>!document.querySelector(`#prepare-records input[data-id="manual_sft_items:${id}"]`),{},temporary);
        const clone=response(`/manual-data/sft/${first}/clone`,'POST');await click(`[data-record-action="clone"][data-record-id="manual_sft_items:${first}"]`);assert.equal((await clone).status(),201);
        const evaluation=await add('An independent held-out question.','Refunds are available within fourteen days with a receipt.',{evaluation:true});
        await click('#prepare-none');await click(`#prepare-records input[data-id="manual_sft_items:${first}"]`);await click(`#prepare-records input[data-id="manual_sft_items:${evaluation}"]`);
        // An unsaved entry survives both modes and a full reload, independently of the chosen source records.
        await type('#sft-turns .turn-row:nth-child(1) textarea','Unsaved question kept through guided navigation.');
        await type('#sft-turns .turn-row:nth-child(2) textarea','Unsaved answer kept through reload.');
        await capture('data-selected',true);
        const bad=await doCheck();assert.notEqual(bad.status,'ready');assert.equal(await page.$eval('#prepare-next-3',e=>e.disabled),true);await capture('check-problem',true);
        await click('#prepare-problems [data-record-action="edit"]');await page.waitForSelector('#manual-edit-form');
        await type('#manual-edit-turns .turn-row:nth-child(2) textarea','An independent evaluation answer with different content.');
        const corrected=response(`/manual-data/sft/${evaluation}`,'PATCH');await click('#manual-edit-form button[type="submit"]');assert.equal((await corrected).status(),200);
        await page.waitForSelector('#manual-dialog .detail-actions');await click('#close-manual-dialog');
        const good=await doCheck('#prepare-recheck');assert.equal(good.status,'ready');await capture('check-ready',true);
        const selection=await page.evaluate(()=>[...NajdiPrepare.state.chosen].sort());
        await page.reload();await stage(2);await page.waitForSelector('#prepare-status .prepare-badge.ready');
        assert.equal(await page.$('#advanced-workspace'),null);
        assert.equal(await page.$eval('#guided-wizard',e=>e.checkVisibility()),true);
        assert.deepEqual(await page.evaluate(()=>[...NajdiPrepare.state.chosen].sort()),selection);
        await page.reload();await stage(2);await page.waitForSelector('#prepare-status .prepare-badge.ready');
        assert.deepEqual(await page.evaluate(()=>[...NajdiPrepare.state.chosen].sort()),selection);
        assert.equal(await page.$eval('#sft-turns .turn-row:nth-child(2) textarea',e=>e.value),'Unsaved answer kept through reload.');await capture('guided-restored');
        const firstGold=await approve();const before=await versionFiles(firstGold);const detail=await read(`/api/v1/dataset-versions/${firstGold}`);
        for(const [name,digest] of Object.entries(detail.manifest.sha256))assert.equal(before.find(f=>f.name===name)?.sha256,digest,name);
        assert.equal(detail.eval.leakage_free,true);assert.equal(detail.eval.eval_count,1);
        await capture('export',true);
        const handoff=response('/api/v1/unsloth-exports','POST');await click('#prepare-export-go');assert.equal((await handoff).status(),201);await page.waitForSelector('#prepare-export-result a[download="dataset.jsonl"]');
        await click('#prepare-export-result a[download="dataset.jsonl"]');
        for(let i=0;i<100&&!fs.existsSync(path.join(downloads,'dataset.jsonl'));i++)await new Promise(r=>setTimeout(r,50));
        const training=fs.readFileSync(path.join(downloads,'dataset.jsonl'),'utf8');assert.match(training,/Refunds are available/);assert.doesNotMatch(training,/independent evaluation answer/);
        await click('#prepare-new-version');await stage(1);await edit(first,'A revised source answer used only in the second Gold version.');
        assert.deepEqual(await versionFiles(firstGold),before,'source editing preserves Frozen Gold');
        assert.equal((await doCheck()).status,'ready');const secondGold=await approve();assert.notEqual(secondGold,firstGold);
        await click('#prepare-created a');await page.waitForSelector('#view-my-versions.active');await page.waitForSelector(`.version-delete[data-version="${secondGold}"]`);await capture('versions');
        await click(`.version-delete[data-version="${secondGold}"]`);await page.waitForSelector('#gold-delete-dialog[open]');await page.waitForSelector('#gold-delete-files li');await page.$eval('#gold-delete-dialog',dialog=>dialog.scrollTop=0);await capture('delete-confirm');
        assert.equal(await page.$eval('#gold-delete-submit',e=>e.disabled),true);await click('#gold-delete-cancel');assert.ok((await read('/api/v1/dataset-versions')).items.some(v=>v.version===secondGold));
        await click(`.version-delete[data-version="${secondGold}"]`);await page.waitForSelector('#gold-delete-files li');await type('#gold-delete-confirm',secondGold);
        const deleted=response(`/dataset-versions/${secondGold}/delete`,'POST');await click('#gold-delete-submit');assert.equal((await deleted).status(),200);
        await page.waitForFunction(v=>!document.querySelector(`.version-delete[data-version="${v}"]`),{},secondGold);
        assert.deepEqual(await versionFiles(firstGold),before,'deleting one version preserves the other');assert.ok((await read(`/api/v1/manual-data/sft/${first}`)).id===first);
        await click(`.version-export[data-version="${firstGold}"]`);await stage(4);await page.waitForSelector('#prepare-raw-exports a');assert.equal(await page.$('#workspace-mode'),null);assert.equal(await page.$('#advanced-mode'),null);await capture('existing-version-export');
        // Empty selection is blocked and standalone formats retain their own downloadable files.
        await click('#prepare-new-version');await stage(1);await click('#prepare-none');assert.equal(await page.$eval('#prepare-check',e=>e.disabled),true);
        await click('#wizard-add-record');await click('[data-add-tab="direct"]');await type('#form-direct textarea[name="text"]','اااا بببب نص مستقل اصطناعي');
        await setCheck('#form-direct input[name="training_eligible"]',true);const directSaved=response('/api/v1/manual-data/direct','POST');await click('#form-direct button[type="submit"]');const directResponse=await directSaved;assert.equal(directResponse.status(),201);const directId=(await directResponse.json()).item.id;
        await settledRecord('direct_language_texts:'+directId);await click('#prepare-none');await click(`#prepare-records input[data-id="direct_language_texts:${directId}"]`);
        assert.equal((await doCheck()).status,'ready');const directGold=await approve();await page.waitForFunction(()=>document.querySelector('#prepare-export-go').disabled);
        assert.ok(await page.$('#prepare-raw-exports a[download="direct_language.jsonl"]'));assert.equal(await page.$('#prepare-raw-exports a[download="sft.jsonl"]'),null);await capture('standalone-export');
        assert.equal((await read(`/api/v1/dataset-versions/${directGold}`)).manifest.files['direct_language.jsonl'],1);
        assert.deepEqual(errors,[]);assert.deepEqual(consoleErrors,[]);assert.deepEqual(serverErrors,[]);assert.deepEqual(legacyRequests,[],'the official journey never requests the legacy bundle');
        fs.writeFileSync(path.join(evidence,`http-${language}.json`),JSON.stringify(requests,null,2));
        console.log('GUIDED_ACCEPTANCE '+JSON.stringify({language,versions:[firstGold,secondGold,directGold],deleted:secondGold,errors:errors.length,consoleErrors:consoleErrors.length,serverErrors:serverErrors.length}));
      }catch(error){if(page)await page.screenshot({path:path.join(evidence,`failure-${language}.png`),fullPage:true}).catch(()=>{});throw error;}
      finally{await context.close();service.child.kill();}
    });
  }finally{
    await browser.close();fs.writeFileSync(path.join(evidence,'screenshots.json'),JSON.stringify(shots,null,2));
    fs.writeFileSync(path.join(evidence,'visual-report.html'),'<!doctype html><html lang="en"><meta charset="utf-8"><title>NajdiLab guided workflow acceptance</title><style>body{font:16px system-ui;background:#eee;color:#222;padding:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:24px}figure{margin:0;background:white;padding:16px}img{width:100%;height:360px;object-fit:contain;object-position:top}figcaption{padding:12px 0}</style><h1>NajdiLab actual browser evidence</h1><p>Synthetic data. Captured from the running application.</p><main>'+shots.map(s=>`<figure><a href="${s.name}"><img src="${s.name}" alt="${s.language} ${s.label} ${s.theme} ${s.width}"></a><figcaption>${s.language} · ${s.label} · ${s.theme} · ${s.width}px</figcaption></figure>`).join('')+'</main></html>');
  }
});
