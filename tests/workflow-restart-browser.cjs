/* Restart acceptance uses synthetic state and the same browser origin across real server processes. */
'use strict';
const assert=require('node:assert/strict');
const {spawn,execFileSync}=require('node:child_process');
const {once}=require('node:events');
const fs=require('node:fs');
const path=require('node:path');
const {createHash}=require('node:crypto');
const {test}=require('node:test');
const puppeteer=require('puppeteer-core');
const root=path.resolve(__dirname,'..');
const scratch=path.join(root,'.test-tmp');
const evidence=path.join(scratch,'workflow-restart-acceptance');
const forbiddenPorts=[8770,8870,8871];

function fixture(args=[]){
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py',...args],{cwd:root,stdio:['ignore','pipe','pipe'],windowsHide:true});
  const ready=new Promise((resolve,reject)=>{
    let out='',err='';
    const timer=setTimeout(()=>reject(Error(err||'fixture startup timed out')),20000);
    child.stdout.on('data',chunk=>{out+=chunk;const match=out.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(match){clearTimeout(timer);resolve(match[1]);}});
    child.stderr.on('data',chunk=>err+=chunk);
    child.once('error',error=>{clearTimeout(timer);reject(error);});
    child.once('exit',code=>{clearTimeout(timer);reject(Error(`fixture exited ${code}: ${err}`));});
  });
  return {child,ready};
}

async function stop(service){
  if(!service||service.child.exitCode!==null||service.child.signalCode!==null)return;
  const exited=once(service.child,'exit');
  assert.equal(service.child.kill(),true,'the actual Python fixture process receives termination');
  await exited;
}

function seedDigests(stateRoot){
  const digests={};
  for(const version of ['gold-v001-synthetic','gold-v002-synthetic-draft']){
    const directory=path.join(stateRoot,'exports',version);
    for(const file of fs.readdirSync(directory,{recursive:true})){
      const absolute=path.join(directory,file);
      if(fs.statSync(absolute).isFile())digests[`${version}/${file}`]=createHash('sha256').update(fs.readFileSync(absolute)).digest('hex');
    }
  }
  return digests;
}

test('fixture defaults remain ephemeral and unsafe persistent options are refused',{timeout:90000},async()=>{
  const isolation=execFileSync(process.env.PYTHON||'python',['-c',[
    'import sys',
    'from pathlib import Path',
    "sys.path.insert(0,str(Path('tests').resolve()))",
    'from chat_browser_fixture import fixture_root',
    'with fixture_root() as (root,reused):',
    '    assert root.is_dir() and not reused',
    "    assert root.name.startswith('najdilab-browser-')",
    "    assert not root.is_relative_to(Path('.test-tmp').resolve())",
    'assert not root.exists()',
    "print('EPHEMERAL_DEFAULT_CLEANED')"
  ].join('\n')],{cwd:root,encoding:'utf8',windowsHide:true});
  assert.equal(isolation.trim(),'EPHEMERAL_DEFAULT_CLEANED');
  const service=fixture();
  try{
    const origin=await service.ready;
    assert.equal(new URL(origin).hostname,'127.0.0.1');
    assert.ok(!forbiddenPorts.includes(Number(new URL(origin).port)));
  }finally{await stop(service);}
  fs.mkdirSync(scratch,{recursive:true});
  const unmarked=fs.mkdtempSync(path.join(scratch,'restart-unmarked-'));
  fs.writeFileSync(path.join(unmarked,'unrelated.txt'),'Synthetic safety sentinel.');
  for(const args of [
    ['--state-root',root],['--state-root',scratch],['--state-root',unmarked],
    ...forbiddenPorts.map(port=>['--port',String(port)])
  ]){
    const refused=fixture(args);
    try{await assert.rejects(refused.ready,/fixture exited/);}finally{await stop(refused);}
    assert.notEqual(refused.child.exitCode,0);
  }
  assert.equal(fs.readFileSync(path.join(unmarked,'unrelated.txt'),'utf8'),'Synthetic safety sentinel.');
  fs.rmSync(unmarked,{recursive:true});
});

test('Wizard draft, selected record, check stage, Arabic survive application restart with the legacy mode preference ignored',{timeout:180000},async()=>{
  fs.mkdirSync(evidence,{recursive:true});
  const stateRoot=fs.mkdtempSync(path.join(scratch,'workflow-restart-state-'));
  const browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
  const context=await browser.createBrowserContext();
  let service=fixture(['--state-root',stateRoot,'--port','0']),page;
  const question='Unsaved restart draft — سؤال اصطناعي\nSecond line remains exact.';
  const answer='Unsaved restart answer — جواب اصطناعي\nWhitespace and Unicode survive.';
  const errors=[],serverErrors=[];
  try{
    const origin=await service.ready;
    const port=Number(new URL(origin).port);
    assert.ok(!forbiddenPorts.includes(port));
    const firstPid=service.child.pid;
    page=await context.newPage();await page.setViewport({width:1440,height:1000});
    page.on('pageerror',error=>errors.push(error.message));
    page.on('response',response=>{if(response.url().includes('/api/v1/')&&response.status()>=500)serverErrors.push(response.url());});
    const click=async selector=>{const element=await page.waitForSelector(selector,{visible:true});await element.scrollIntoView();await element.click();};
    const type=async(selector,value)=>{await click(selector);await page.keyboard.down('Control');await page.keyboard.press('a');await page.keyboard.up('Control');await page.keyboard.type(value);};
    const response=(suffix,method)=>page.waitForResponse(r=>new URL(r.url()).pathname.endsWith(suffix)&&r.request().method()===method);
    const stage=number=>page.waitForSelector(`#prepare-panel-${number}:not([hidden])`);
    const stored=()=>page.evaluate(()=>({advanced:localStorage.getItem('najdilab.advancedMode'),language:localStorage.getItem('najdilab.language'),workflow:JSON.parse(localStorage.getItem('najdilab.workflow.v1'))}));
    const check=async()=>{const pending=response('/api/v1/prepare/check','POST');await click('#prepare-check');assert.equal((await pending).status(),200);await stage(2);await page.waitForSelector('#prepare-status .prepare-badge');};
    await page.goto(origin+'/');await page.waitForSelector('#dashboard-stats button');
    await click('#view-dashboard .button.primary[data-go="prepare"]');await stage(1);
    assert.equal(await page.$('#workspace-mode,#advanced-mode'),null);
    await click('#wizard-add-record');await click('[data-add-tab="sft"]');
    await type('#sft-turns .turn-row:nth-child(1) textarea','Synthetic saved restart question.');
    await type('#sft-turns .turn-row:nth-child(2) textarea','Synthetic saved restart answer.');
    await page.select('#form-sft select[name="language"]','en');
    if(!await page.$eval('#form-sft input[name="training_eligible"]',element=>element.checked))await click('#form-sft input[name="training_eligible"]');
    const saved=response('/api/v1/manual-data/sft','POST');await click('#form-sft button[type="submit"]');
    const savedResponse=await saved;assert.equal(savedResponse.status(),201);
    const id=(await savedResponse.json()).item.id,selectedId=`manual_sft_items:${id}`;
    await page.waitForSelector(`#prepare-records input[data-id="${selectedId}"]`);
    await click('#prepare-none');await click(`#prepare-records input[data-id="${selectedId}"]`);
    await check();await click('#prepare-back-1');await stage(1);
    await click('#wizard-add-record');await click('[data-add-tab="sft"]');
    await type('#sft-turns .turn-row:nth-child(1) textarea',question);
    await type('#sft-turns .turn-row:nth-child(2) textarea',answer);
    await check();
    await page.evaluate(()=>localStorage.setItem('najdilab.advancedMode','1'));
    await page.select('#language-select','ar');
    const before=await stored();
    assert.equal(before.advanced,'1');assert.equal(before.language,'ar');
    assert.equal(before.workflow.stage,2);assert.deepEqual(before.workflow.chosen,[selectedId]);
    assert.deepEqual(before.workflow.drafts['form-sft'].turns.map(turn=>turn.content),[question,answer]);
    assert.equal(await page.$eval('html',element=>element.dir),'rtl');
    const seeds=seedDigests(stateRoot);
    const workspaceUrl=page.url();
    await page.screenshot({path:path.join(evidence,'before-restart.png'),fullPage:true});
    // Unload the app and its connections before terminating the actual server process.
    await page.goto('about:blank');await stop(service);
    assert.ok(service.child.exitCode!==null||service.child.signalCode!==null,'first Python process has exited');
    service=fixture(['--state-root',stateRoot,'--port',String(port)]);
    assert.equal(await service.ready,origin,'restart retains the browser storage origin');
    assert.notEqual(service.child.pid,firstPid,'restart launches a new Python process');
    await page.goto(workspaceUrl);await page.waitForSelector('#guided-wizard',{visible:true});
    assert.equal(await page.$('#workspace-mode,#advanced-mode,#advanced-workspace'),null);
    assert.equal(await page.$eval('#language-select',element=>element.value),'ar');
    assert.deepEqual(await page.$eval('html',element=>({language:element.lang,direction:element.dir})),{language:'ar',direction:'rtl'});
    await stage(2);await page.waitForSelector('#prepare-status .prepare-badge');
    assert.equal(await page.$eval('#guided-wizard',element=>element.checkVisibility()),true);
    assert.deepEqual(await page.evaluate(()=>[...NajdiPrepare.state.chosen]),[selectedId]);
    assert.equal(await page.$eval('#sft-turns .turn-row:nth-child(1) textarea',element=>element.value),question);
    assert.equal(await page.$eval('#sft-turns .turn-row:nth-child(2) textarea',element=>element.value),answer);
    const after=await stored();assert.equal(after.advanced,'1');assert.equal(after.language,'ar');
    assert.equal(after.workflow.stage,2);assert.deepEqual(after.workflow.chosen,[selectedId]);
    assert.deepEqual(after.workflow.drafts['form-sft'],before.workflow.drafts['form-sft']);
    assert.deepEqual(seedDigests(stateRoot),seeds,'restart preserves every existing synthetic seed byte');
    await page.screenshot({path:path.join(evidence,'after-restart.png'),fullPage:true});
    await click('#prepare-back-1');await stage(1);
    assert.equal(await page.$eval(`#prepare-records input[data-id="${selectedId}"]`,element=>element.checked),true);
    assert.equal(await page.$eval('#sft-turns .turn-row:nth-child(2) textarea',element=>element.value),answer);
    assert.deepEqual(errors,[]);assert.deepEqual(serverErrors,[]);
    const proof={origin,firstPid,restartedPid:service.child.pid,stateRoot,selectedIds:[selectedId],restoredStage:2,language:'ar',direction:'rtl',legacyPreferenceIgnored:true,draftExact:true,seedFilesUnchanged:Object.keys(seeds).length,pageErrors:errors.length,serverErrors:serverErrors.length};
    fs.writeFileSync(path.join(evidence,'proof.json'),JSON.stringify(proof,null,2));
    console.log('WORKFLOW_RESTART_ACCEPTANCE '+JSON.stringify(proof));
  }catch(error){if(page)await page.screenshot({path:path.join(evidence,'failure.png'),fullPage:true}).catch(()=>{});throw error;}
  finally{await context.close();await browser.close();await stop(service);}
});
