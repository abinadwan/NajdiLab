/* Developer restoration is exercised only in a marked temporary static tree. */
'use strict';
const assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
const fs=require('node:fs');
const path=require('node:path');
const {createHash,randomUUID}=require('node:crypto');
const {test}=require('node:test');
const puppeteer=require('puppeteer-core');
const root=path.resolve(__dirname,'..');
const digest=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');

test('preserved workspace restores in an isolated static tree and shares the existing backend', {timeout:120000},async t=>{
  const original=digest(path.join(root,'static/app.js'));
  const output=path.join(root,'.test-tmp','legacy-restoration-'+randomUUID());
  execFileSync(process.env.PYTHON||'python',['scripts/restore_advanced_workspace.py','--output',output],{cwd:root,windowsHide:true});
  assert.ok(fs.existsSync(path.join(output,'NAJDILAB_LEGACY_RESTORE_TEST')));
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py','--static-root',output],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
  let browser;
  try{
    const base=await new Promise((resolve,reject)=>{
      let stdout='',stderr='';const timer=setTimeout(()=>reject(Error(stderr||'fixture timeout')),20000);
      child.stdout.on('data',chunk=>{stdout+=chunk;const match=stdout.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
      child.stderr.on('data',chunk=>stderr+=chunk);
      child.once('error',reject);
    });
    assert.ok(![8770,8870,8871].includes(Number(new URL(base).port)));
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    for(const language of ['en','ar'])await t.test('restored mode, tools and guided return ('+language+')',async()=>{
      const context=await browser.createBrowserContext();const page=await context.newPage();
      const errors=[],failures=[];
      page.on('pageerror',error=>errors.push(error.message));
      page.on('response',response=>{if(response.url().includes('/api/v1/')&&response.status()>=500)failures.push(response.url());});
      try{
        await page.evaluateOnNewDocument(()=>localStorage.setItem('najdilab.advancedMode','1'));
        await page.setViewport({width:1440,height:1000});await page.goto(base+'/datasets/prepare');
        await page.waitForSelector('#advanced-workspace',{visible:true});await page.select('#language-select',language);
        assert.equal(await page.$eval('#guided-wizard',element=>element.checkVisibility()),false);
        assert.equal(await page.$eval('#workspace-mode',element=>element.checked),true);
        const destinations=['manual-data','dataset-health','balancer','eval-sets','dataset-versions','exports','add-data'];
        for(const view of destinations){
          await page.click(`#advanced-workspace [data-advanced-view="${view}"]`);
          await page.waitForSelector(`#view-${view}.active`);
          await page.evaluate(()=>switchView('prepare'));await page.waitForSelector('#advanced-workspace',{visible:true});
        }
        await page.click('#workspace-mode');await page.waitForSelector('#guided-wizard',{visible:true});
        await page.waitForSelector('#prepare-records .workspace-empty');
        assert.equal(await page.$eval('#advanced-workspace',element=>element.checkVisibility()),false);
        await page.click('#workspace-mode');await page.waitForSelector('#advanced-workspace',{visible:true});
        await page.reload();await page.waitForSelector('#advanced-workspace',{visible:true});
        assert.equal(await page.$eval('html',element=>element.dir),language==='ar'?'rtl':'ltr');
        assert.deepEqual(errors,[]);assert.deepEqual(failures,[]);
      }finally{await context.close();}
    });
  }finally{
    if(browser)await browser.close();child.kill();
    assert.equal(digest(path.join(root,'static/app.js')),original,'restoration never modifies the official static tree');
  }
});
