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
    await page.goto(base+'/chat');
    try {await page.waitForSelector('#view-chat.active #chat-list',{timeout:15000});await page.waitForFunction(()=>document.querySelector('#chat-saved-count').textContent.length>0,{timeout:15000});}
    catch (error) {
      console.error('INITIAL CHAT UI DIAGNOSTIC',JSON.stringify({
        url:page.url(),pageErrors:errors,
        toast:await page.$eval('#toast',e=>e.textContent).catch(()=>'(missing)'),
        chatNotice:await page.$eval('#chat-notice',e=>e.textContent).catch(()=>'(missing)'),
        options:await page.evaluate(()=>Array.from(document.querySelectorAll('#chat-provider option'),e=>e.value)),
        text:await page.$eval('body',e=>e.textContent.slice(0,700)).catch(()=>'(missing)')
      }));
      throw error;
    }
    assert.equal(await page.$('[data-view="training"]'),null);
    assert.equal(await page.$eval('#local-address',e=>e.textContent),new URL(base).host);

    // UX-23: 390px layout acceptance for visible workflow panes.
    await page.setViewport({width:390,height:844});
    for(const [view,selector] of [
      ['add-data','#view-add-data .subtabs'],
      ['conversations','#view-conversations .split-list'],
      ['review-queue','#view-review-queue .review-workspace']
    ]){
      await page.$eval('[data-view="'+view+'"]',e=>e.click());
      await page.waitForFunction(v=>document.querySelector('#view-'+v).classList.contains('active'),{},view);
      const rect=await page.$eval(selector,e=>({right:e.getBoundingClientRect().right,left:e.getBoundingClientRect().left,width:e.getBoundingClientRect().width}));
      assert.ok(rect.right<=391&&rect.left>=-1&&rect.width<=391,view+' mobile content must fit: '+JSON.stringify(rect));
    }
    await page.setViewport({width:1280,height:1000});
    await page.$eval('[data-view="chat"]',e=>e.click());
    await page.waitForSelector('#view-chat.active');
    // UX-25: measure rendered dark-mode foreground/background pair, not string presence.
    const contrasts=await page.evaluate(()=>{
      const previous=document.documentElement.getAttribute('data-theme');
      document.documentElement.setAttribute('data-theme','dark');
      const host=document.createElement('div');
      host.innerHTML='<article class="phase38-message assistant"><span class="role">Assistant</span></article><div class="phase38-summary"><span>Summary</span></div>';
      document.body.append(host);
      const contrast=(a,b)=>{
        const rgb=text=>text.match(/[\d.]+/g).slice(0,3).map(x=>Number(x)/255);
        const lum=text=>rgb(text).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
        const v=[lum(a),lum(b)].sort((x,y)=>y-x);return (v[0]+.05)/(v[1]+.05);
      };
      const pairs=['.phase38-message.assistant','.phase38-summary span'].map(selector=>{
        const style=getComputedStyle(host.querySelector(selector));
        return {selector,ratio:contrast(style.color,style.backgroundColor)};
      });
      host.remove();
      if(previous===null)document.documentElement.removeAttribute('data-theme');
      else document.documentElement.setAttribute('data-theme',previous);
      return pairs;
    });
    for(const row of contrasts)assert.ok(row.ratio>=4.5,row.selector+' dark-mode ratio '+row.ratio);

    // UX-24: collapsing navigation must change the shell grid, not just hide text.
    const expanded=await page.$eval('.shell',e=>parseFloat(getComputedStyle(e).gridTemplateColumns.split(' ')[0]));
    await page.click('#collapse-sidebar');
    const collapsed=await page.$eval('.shell',e=>parseFloat(getComputedStyle(e).gridTemplateColumns.split(' ')[0]));
    assert.ok(collapsed<expanded, `sidebar widths expanded=${expanded}, collapsed=${collapsed}`);
    await page.click('#collapse-sidebar');
    const evidence=process.env.NAJDILAB_BROWSER_ARTIFACTS||'.test-tmp/browser';fs.mkdirSync(evidence,{recursive:true});
    const read=route=>page.evaluate(async route=>{const r=await fetch(route);return r.json();},route);
    const turns=()=>page.$$eval('.chatv2-msg.assistant:not(.streaming):not(.incomplete)',es=>es.length);
    const settled=async n=>{
      try{await page.waitForFunction(n=>document.querySelectorAll('.chatv2-msg.assistant:not(.streaming):not(.incomplete)').length===n&&!document.querySelector('.chatv2-msg.streaming'),{timeout:10000},n);}
      catch(error){console.error('CHAT STATE',JSON.stringify(await page.evaluate(()=>({notice:document.querySelector('#chat-notice').textContent,
        assistants:document.querySelectorAll('.chatv2-msg.assistant').length,title:document.querySelector('#chat-title').textContent,
        identity:document.querySelector('#chat-session-identity').textContent}))));throw error;}
    };
    const newChat=async({provider='lmstudio',preset='balanced',context,reserve,approve=false}={})=>{
      await page.click('#chat-new');await page.waitForSelector('#chat-setup[open] #chat-provider option');
      await page.select('#chat-provider',provider);
      if(preset==='custom'){await page.click('#chat-advanced summary').catch(()=>{});await page.$eval('#chat-budget',(e,v)=>{e.value=v;e.dispatchEvent(new Event('input'));},String(context));await page.$eval('#chat-reserve',(e,v)=>{e.value=v;e.dispatchEvent(new Event('input'));},String(reserve));}
      else await page.click(`input[name="chat-preset"][value="${preset}"]`);
      if(approve)await page.click('#chat-load-approved');
      await page.click('#chat-create');
      await page.waitForFunction(()=>!document.querySelector('#chat-setup').open,{timeout:8000});
      await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled&&!document.querySelector('.chatv2-msg'),{timeout:8000});
    };

    // Chat V2: the setup dialog explains the budget and keeps Ollama's load approval explicit.
    await page.click('#chat-new');await page.waitForSelector('#chat-setup[open] #chat-provider option');
    assert.equal(await page.$eval('#chat-load-row',e=>getComputedStyle(e).display),'none');
    assert.match(await page.$eval('#chat-budget-breakdown',e=>e.textContent),/8192.*6144.*2048/s);
    await page.select('#chat-provider','ollama');
    assert.notEqual(await page.$eval('#chat-load-row',e=>getComputedStyle(e).display),'none');
    assert.equal(await page.$eval('#chat-load-approved',e=>e.checked),false,'never pre-approved');
    await page.click('#chat-create');
    await page.waitForFunction(()=>document.querySelector('#chat-setup-error').textContent.includes('Approve Ollama'));
    await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#chat-setup').open);

    await newChat({preset:'light'});
    await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled);
    assert.match(await page.$eval('#chat-session-identity',e=>e.textContent),/LM Studio · fixture · Open · Context 4096 · Reply 1024/);
    assert.equal(await page.$eval('#chat-collect',e=>e.checked),false);
    const sid=await page.evaluate(async()=>{const r=await fetch('/api/v1/chat/sessions?limit=1');return (await r.json()).items[0].id;});

    // Keyboard: empty Enter does nothing, Shift+Enter is a newline, Enter sends once.
    await page.focus('#chat-draft');await page.keyboard.press('Enter');
    assert.equal(await turns(),0);
    const raw='  <img src=x onerror=alert(1)> synthetic private-before-optin 🙂';
    await page.type('#chat-draft',raw);
    await page.keyboard.down('Shift');await page.keyboard.press('Enter');await page.keyboard.up('Shift');
    await page.type('#chat-draft','second line');
    assert.equal(await page.$eval('#chat-draft',e=>e.value),raw+'\nsecond line');
    assert.equal(await turns(),0,'Shift+Enter never sends');
    await page.keyboard.press('Enter');await page.keyboard.press('Enter');await page.keyboard.press('Enter');
    await settled(1);
    assert.equal((await read('/api/v1/chat/sessions/'+sid)).turns.length,1,'repeated Enter while a reply runs creates one request');
    assert.equal(await page.$eval('.chatv2-msg.user .chatv2-text',e=>e.textContent),raw+'\nsecond line');
    assert.equal(await page.$('.chatv2-msg img'),null);
    assert.equal(await page.$eval('#chat-draft',e=>e.value),'','sent draft is cleared');
    assert.match(await page.$eval('.chatv2-msg.assistant .chat-review-status',e=>e.textContent),/Not collected for review/);
    assert.equal(await page.$eval('#chat-title',e=>e.textContent),'<img src=x onerror=alert(1)> synthetic private-before-optin…','local automatic title, cut at a word boundary');
    assert.equal((await read('/api/v1/review-queue')).items.length,0);

    // Consent: only later completed replies are collected.
    await page.click('#chat-collect');await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('Collection is on'));
    await page.type('#chat-draft','Synthetic opted-in question');await page.keyboard.press('Enter');
    await settled(2);
    const queue=(await read('/api/v1/review-queue')).items;
    assert.equal(queue.length,1);assert.equal(queue[0].review_status,'PENDING');assert.equal(queue[0].training_eligible,0);
    assert.ok(!JSON.stringify(queue).includes('private-before-optin'));
    assert.match(await page.$eval('.chatv2-msg.assistant:nth-of-type(4) .chat-review-status, .chatv2-msg.assistant:last-of-type .chat-review-status',e=>e.textContent),/Collected for human review/);

    // Streaming with separate thinking: open while thinking, collapsed for the answer, never saved.
    await page.click('#chat-collect');await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('Collection is off'));
    await page.type('#chat-draft','THINK_FIXTURE');await page.keyboard.press('Enter');
    await page.waitForFunction(()=>{const d=document.querySelector('.chatv2-msg.streaming .chatv2-thinking');return d&&!d.hidden&&d.open&&d.textContent.includes('Synthetic');},{timeout:5000});
    await settled(3);
    assert.equal(await page.$eval('.chatv2-msg.assistant:last-of-type .chatv2-thinking',e=>e.open),false,'thinking collapses once the answer is shown');
    assert.ok(!JSON.stringify(await read('/api/v1/chat/sessions/'+sid)).includes('thinking trace'),'thinking is not stored');

    // Safe Markdown: formatting renders, raw HTML and unsafe links stay text, code can be copied.
    await page.type('#chat-draft','MARKDOWN_FIXTURE');await page.keyboard.press('Enter');
    await settled(4);
    const markdown=await page.$eval('.chatv2-msg.assistant:last-of-type .chatv2-answer',e=>({h:e.querySelector('h4')?.textContent,strong:e.querySelector('strong')?.textContent,
      li:e.querySelectorAll('li').length,code:e.querySelector('.md-code code')?.textContent,links:[...e.querySelectorAll('a')].map(a=>[a.href,a.rel,a.target]),img:e.querySelectorAll('img,script').length}));
    assert.deepEqual(markdown,{h:'عنوان اصطناعي',strong:'نص غامق',li:2,code:'print("synthetic")',links:[['https://example.org/','noopener noreferrer nofollow','_blank']],img:0});
    assert.equal((await read('/api/v1/chat/sessions/'+sid)).turns.at(-1).assistant.startsWith('## عنوان اصطناعي'),true,'stored text stays raw Markdown');
    await page.screenshot({path:path.join(evidence,'chat-v2-desktop.png')});

    // Sidebar: rename, pin, search, archive, restore; preference survives reload.
    const menu=async(id,action)=>{
      await page.click(`[data-chat-more="${id}"]`);
      try{await page.waitForSelector('#chat-action-menu:not([hidden])',{timeout:5000});}
      catch(error){await page.screenshot({path:path.join(evidence,'menu-failure.png')});
        console.error('MENU STATE',JSON.stringify(await page.evaluate(id=>({exists:!!document.querySelector(`[data-chat-more="${id}"]`),
          notice:document.querySelector('#chat-notice').textContent,dialogs:[...document.querySelectorAll('dialog[open]')].map(d=>d.id)}),id)));throw error;}
      await page.click(`#chat-action-menu [data-chat-action="${action}"]`);
    };
    await menu(sid,'rename');await page.waitForSelector('#chat-rename[open]');
    await page.$eval('#chat-rename-input',e=>e.value='');await page.type('#chat-rename-input','عشاء الجمعة');await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelector('#chat-title').textContent==='عشاء الجمعة');
    await newChat({preset:'light'});await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled);
    await page.type('#chat-draft','second conversation');await page.keyboard.press('Enter');await settled(1);
    await menu(sid,'pin');
    await page.waitForFunction(id=>document.querySelector('.chatv2-group h3')?.textContent==='Pinned'&&document.querySelector('.chatv2-group [data-chat-open]').dataset.chatOpen===id,{},sid);
    await page.type('#chat-search','عشاء');
    await page.waitForFunction(()=>document.querySelectorAll('[data-chat-open]').length===1);
    await page.$eval('#chat-search',e=>{e.value='';e.dispatchEvent(new Event('input'));});
    await page.waitForFunction(()=>document.querySelectorAll('[data-chat-open]').length===2);
    page.once('dialog',d=>d.accept());await menu(sid,'archive');
    await page.waitForFunction(id=>!document.querySelector(`[data-chat-open="${id}"]`),{},sid);
    await page.click('#chat-show-archived');await page.waitForSelector(`[data-chat-open="${sid}"]`);
    await menu(sid,'restore');await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('Conversation restored'));
    await page.click('#chat-show-active');await page.waitForSelector(`[data-chat-open="${sid}"]`);
    await page.click('#chat-sidebar-toggle');
    assert.equal(await page.$eval('#chat-shell',e=>e.dataset.sidebar),'closed');
    await page.reload();await page.waitForSelector('#view-chat.active');
    assert.equal(await page.$eval('#chat-shell',e=>e.dataset.sidebar),'closed','sidebar preference persists');
    await page.click('#chat-sidebar-toggle');await page.waitForSelector(`[data-chat-open="${sid}"]`);
    await page.click(`[data-chat-open="${sid}"]`);await settled(4);
    assert.equal(await page.$eval('#chat-collect',e=>e.checked),false,'collection is off after reload');

    // A budget overflow opens empty context and keeps, never replays, the draft.
    await newChat({preset:'custom',context:128,reserve:127});
    await page.waitForFunction(()=>document.querySelector('#chat-session-identity').textContent.includes('Context 128'));
    await page.type('#chat-draft','Unsent overflow draft');await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('Context limit reached'));
    assert.equal(await page.$$eval('.chatv2-msg',es=>es.length),0);
    assert.equal(await page.$eval('#chat-draft',e=>e.value),'Unsent overflow draft');
    assert.equal(await page.$eval('#chat-collect',e=>e.checked),false);

    // Stop: partial text is visible, marked, and never saved.
    await newChat({preset:'light'});await page.waitForFunction(()=>document.querySelector('#chat-session-identity').textContent.includes('Context 4096'));
    await page.$eval('#chat-draft',e=>e.value='STOP_FIXTURE');await page.click('#chat-send');
    await page.waitForFunction(()=>document.querySelector('.chatv2-msg.streaming .chatv2-answer')?.textContent.includes('Partial synthetic'));
    await page.click('#chat-stop');
    await page.waitForFunction(()=>document.querySelector('.chatv2-msg.incomplete')?.textContent.includes('Stopped'));
    await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled);
    const newest=()=>page.evaluate(async()=>{const r=await fetch('/api/v1/chat/sessions?limit=50');return (await r.json()).items.find(i=>!i.pinned_at).id;});
    const stopped=(await read('/api/v1/chat/sessions/'+await newest())).turns.length;
    assert.equal(stopped,0);

    // Ollama, approved explicitly for this chat only.
    await newChat({provider:'ollama',preset:'light',approve:true});
    await page.waitForFunction(()=>document.querySelector('#chat-session-identity').textContent.startsWith('Ollama'));
    await page.type('#chat-draft','Synthetic Ollama question');await page.keyboard.press('Enter');await settled(1);
    await page.click('#chat-settings-open');await page.waitForSelector('#chat-panel[open]');
    await page.click('#chat-hardware-section summary');await page.click('#chat-hardware');
    await page.waitForFunction(()=>document.querySelector('#chat-hardware-result table'));
    const hw=await page.$eval('#chat-hardware-result',e=>e.textContent);
    assert.match(hw,/Maximum context131072Reported by the runtime/);
    assert.match(hw,/Memory estimates by context|No reliable recommendation/,'estimates appear only with GPU evidence; otherwise it says so');
    assert.match(hw,/GPUUnknown|Measured/,'device memory is labelled measured or unknown');
    await page.click('#chat-panel-close');
    // Reading specs must not stale the conversation that is already open.
    await page.type('#chat-draft','Second question after reading specs');await page.keyboard.press('Enter');await settled(2);
    // UX-08: completing an earlier request cannot erase text typed while it ran.
    await page.$eval('#chat-draft',e=>e.value='DELAY_FIXTURE');await page.click('#chat-send');
    await page.waitForFunction(()=>!document.querySelector('#chat-stop').disabled);
    await page.$eval('#chat-draft',e=>e.value='New draft typed while model was replying');
    await settled(3);
    assert.equal(await page.$eval('#chat-draft',e=>e.value),'New draft typed while model was replying');

    // Permanent deletion of a synthetic conversation: explicit word, then gone.
    const doomed=await newest();
    await page.click('#chat-actions');await page.waitForSelector('#chat-action-menu:not([hidden])');
    await page.click('#chat-action-menu [data-chat-action="delete"]');await page.waitForSelector('#chat-delete[open]');
    assert.match(await page.$eval('#chat-delete-preview',e=>e.textContent),/Messages to delete6/);
    assert.equal(await page.$eval('#chat-delete-go',e=>e.disabled),true);
    await page.type('#chat-delete-confirm','delete');assert.equal(await page.$eval('#chat-delete-go',e=>e.disabled),true,'case matters');
    await page.$eval('#chat-delete-confirm',e=>e.value='');await page.type('#chat-delete-confirm','DELETE');
    await page.click('#chat-delete-go');
    await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('permanently deleted'));
    assert.equal(await page.evaluate(async id=>(await fetch('/api/v1/chat/sessions/'+id)).status,doomed),404);
    assert.equal(await page.$(`[data-chat-open="${doomed}"]`),null);

    // Narrow screens: no page overflow at 320/390px; the list is an overlay, hidden by default.
    for(const width of [390,320]){
      await page.setViewport({width,height:780});await page.reload();await page.waitForSelector('#view-chat.active');
      await page.evaluate(()=>window.scrollTo(0,0));
      await page.waitForFunction(()=>document.querySelector('#chat-saved-count')!==null);
      assert.equal(await page.$eval('#chat-shell',e=>e.dataset.sidebar),'closed',width+'px starts with the list hidden');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth)<=width,'no horizontal page overflow at '+width);
      await page.click('#chat-sidebar-toggle');await page.waitForSelector(`[data-chat-open="${sid}"]`);
      const box=await page.$eval('#chat-sidebar',e=>{const r=e.getBoundingClientRect();return {left:r.left,right:r.right};});
      assert.ok(box.left>=-1&&box.right<=width+1,'overlay fits: '+JSON.stringify(box));
      const hit=await page.$eval(`[data-chat-open="${sid}"]`,e=>{const r=e.getBoundingClientRect();const top=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return {rect:[r.left,r.top,r.width,r.height],top:top&&(top.id||top.className),inner:innerHeight};});
      if(!hit.top||!String(hit.top).includes('chatv2')){await page.screenshot({path:path.join(evidence,'overlay-failure.png')});throw Error('overlay item covered: '+JSON.stringify(hit));}
      await page.click(`[data-chat-open="${sid}"]`);await settled(4);
      assert.equal(await page.$eval('#chat-shell',e=>e.dataset.sidebar),'closed','choosing a chat closes the overlay');
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth)<=width,'no overflow with messages at '+width);
      const send=await page.$eval('#chat-send',e=>{const r=e.getBoundingClientRect();return r.width>=40&&r.height>=40&&r.right<=innerWidth;});
      assert.ok(send,'a visible, tappable Send button on mobile');
      await page.screenshot({path:path.join(evidence,`chat-v2-${width}.png`)});
    }
    await page.setViewport({width:1280,height:1000});
    // UX-14: dialog tabs must never change Add Data tabs when they are outside the dialog.
    await page.click('[data-view="add-data"]');
    await page.waitForSelector('#form-sft.active');
    await page.evaluate(()=>document.querySelector('.dialog-tabs [data-manual-tab="details"]').click());
    assert.equal(await page.$eval('#form-sft',e=>e.classList.contains('active')),true);
    // UX-15: deleting all turns must produce a handled error, never a null .value crash.
    await page.evaluate(()=>document.querySelectorAll('#sft-turns .turn-row button').forEach(button=>button.click()));
    await page.click('#form-sft button[type="submit"]');
    await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Add at least a user turn'));
    // UX-19: errors stay visible beyond ordinary toast expiry and can be dismissed.
    assert.equal(await page.$eval('#toast',e=>e.getAttribute('role')),'alert');
    await new Promise(resolve=>setTimeout(resolve,3100));
    assert.equal(await page.$eval('#toast',e=>e.classList.contains('show')),true);
    await page.click('.toast-dismiss');
    assert.equal(await page.$eval('#toast',e=>e.classList.contains('show')),false);
    // UX-06: show every blocker and escape untrusted reasons in the persistent panel.
    await page.evaluate(()=>{
      const original=window.api;
      window.api=async (path,...args)=>{
        if(path.startsWith('/api/v1/exports/dedup-report'))return {record_count:5,exact_duplicate_groups:[],near_duplicates:[]};
        if(path.startsWith('/api/v1/exports/readiness'))return {
          ok:false,blocking_findings:Array.from({length:5},(_,i)=>({sample_id:'review:'+i,reason:i===4?'<img src=x onerror=alert(1)>':'reason-'+i}))
        };
        return original(path,...args);
      };
    });
    await page.click('[data-view="exports"]');
    await page.waitForSelector('#preview-dedup');
    await page.click('#preview-dedup');
    await page.waitForFunction(()=>document.querySelectorAll('.export-blockers li').length===5);
    assert.equal(await page.$('.export-blockers img'),null);
    assert.match(await page.$eval('.export-blockers li:last-child',e=>e.textContent),/<img src=x onerror/);
    // UX-26: Settings must not pretend /health checks SQLite corruption/backups.
    await page.click('[data-view="settings"]');
    await page.waitForFunction(()=>document.querySelector('#sqlite-status').textContent.includes('Application responding'));
    assert.match(await page.$eval('#sqlite-status',e=>e.textContent),/database not verified/);
    await page.goto(base+'/training/setup');await page.waitForSelector('#view-dashboard.active');
    assert.equal(await page.$('#view-retired'),null);
    assert.equal(await page.$('#view-human-review'),null);
    assert.equal((await page.evaluate(async()=>fetch('/api/v1/training/jobs').then(r=>r.status))),404);
    assert.equal(await page.$('#training-setup-form'),null);
    assert.deepEqual(errors,[]);
    console.log('PASS: Chat V2 keyboard/duplicates, streaming+thinking, safe Markdown, titles/rename/pin/search/archive/restore, sidebar preference, 320/390px, rollover, Stop, Ollama approval, hardware tables, draft preservation, permanent delete; manual tabs/empty turns, export blockers and absent training routes; synthetic fixtures only.');
  }finally{
    if(browser)await browser.close();child.kill();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
