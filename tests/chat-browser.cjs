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
    const page=await browser.newPage();await page.evaluateOnNewDocument(()=>{try{localStorage.setItem('najdilab.chat.legacyProviders','1');}catch{}});// The synthetic fixture has no llama-server: Chat checks here use its LM Studio/Ollama runtimes via the Settings opt-in.
   await page.setViewport({width:1280,height:1000});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    const clickChat=async selector=>{await page.$eval(selector,e=>e.scrollIntoView({block:'center'}));await page.click(selector);};
    await page.goto(base+'/chat');
    try {await page.waitForSelector('#view-chat.active #chat-list',{timeout:15000});await page.waitForFunction(()=>document.querySelector('#chat-saved-count').textContent.length>0,{timeout:15000});}
    catch (error) {
      console.error('INITIAL CHAT UI DIAGNOSTIC',JSON.stringify({
        url:page.url(),pageErrors:errors,
        toast:await page.$eval('#toast',e=>e.textContent).catch(()=>'(missing)'),
        chatNotice:await page.$eval('#chat-notice',e=>e.textContent).catch(()=>'(missing)'),
        models:await page.evaluate(async()=>(await (await fetch('/api/v1/chat/models')).json()).items.map(i=>i.provider+':'+i.model)),
        text:await page.$eval('body',e=>e.textContent.slice(0,700)).catch(()=>'(missing)')
      }));
      throw error;
    }
    assert.equal(await page.$('[data-view="training"]'),null);
    // V2.2.0 Native-first: without the Settings opt-in, the model menu offers NajdiLab Native only.
    const plainContext=await browser.createBrowserContext();const plain=await plainContext.newPage();
    // Root cause of the old flake: waiting for the label text (already in the static HTML) let the click land before
    // the chat view had bound its controls whenever the server was slow (other suites running). The view now says
    // when it is ready (aria-busy), and every API answer is delayed here so the race is exercised on every run.
    await plain.setRequestInterception(true);
    plain.on('request',r=>{if(r.url().includes('/api/v1/'))setTimeout(()=>r.continue().catch(()=>{}),600);else r.continue().catch(()=>{});});
    await plain.goto(base+'/chat');
    assert.equal(await plain.$eval('#view-chat',v=>v.getAttribute('aria-busy')),'true','the chat view starts busy');
    await plain.waitForSelector('#view-chat[aria-busy="false"]');
    await plain.evaluate(()=>document.querySelector('#chat-model-button').click());await plain.waitForSelector('#chat-model-menu:not([hidden])');
    const offered=await plain.$eval('#chat-model-menu',m=>({groups:[...m.querySelectorAll('[role="group"]')].map(x=>x.getAttribute('aria-label')),text:m.textContent}));
    assert.ok(offered.groups.every(g=>g==='NajdiLab Native')&&!/LM Studio|Ollama/.test(offered.text),'only NajdiLab Native is offered: '+JSON.stringify(offered.groups));
    assert.match(offered.text,/Model library/);
    await plainContext.close();
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
    // V2.1.0 composer: New chat opens an empty chat at once; model and context are chosen in the
    // message box; the conversation is created by the first send, after any approval it needs.
    const pickModel=async provider=>{
      await page.click('#chat-model-button');await page.waitForSelector('#chat-model-menu:not([hidden]) .chatv2-model-item');
      await page.evaluate(name=>{const heading=[...document.querySelectorAll('#chat-model-menu h4')].find(h=>h.textContent===name);heading.nextElementSibling.click();},
        {lmstudio:'LM Studio',ollama:'Ollama'}[provider]);
      await page.waitForFunction(()=>document.querySelector('#chat-model-menu').hidden);
    };
    const pickContext=async(context,reserve)=>{
      await page.click('#chat-context-button');await page.waitForSelector('#chat-context-menu:not([hidden])');
      await page.evaluate(()=>{document.querySelector('#chat-context-advanced').open=true;});
      await page.$eval('#chat-budget',(e,v)=>{e.value=v;e.dispatchEvent(new Event('input'));},String(context));
      await page.$eval('#chat-reserve',(e,v)=>{e.value=v;e.dispatchEvent(new Event('input'));},String(reserve));
      await page.click('#chat-budget-apply');await page.waitForFunction(()=>document.querySelector('#chat-context-menu').hidden);
    };
    const newChat=async({provider='lmstudio',context=4096,reserve=1024}={})=>{
      await page.click('#chat-new');
      await page.waitForFunction(()=>document.querySelector('#chat-session-identity').textContent.startsWith('New conversation')&&!document.querySelector('.chatv2-msg'));
      assert.equal(await page.$('dialog[open]'),null,'New chat opens no dialog');
      await pickModel(provider);await pickContext(context,reserve);
    };
    const approveCard=async()=>{await page.waitForSelector('#chat-prepare:not([hidden]) #chat-prepare-go:not([hidden])');await page.click('#chat-prepare-go');};

    // New chat is immediate: no configuration dialog, collection off, nothing created yet.
    await page.click('#chat-new');
    assert.equal(await page.$('#chat-setup'),null,'the New chat dialog is gone');
    assert.equal(await page.$('dialog[open]'),null);
    assert.match(await page.$eval('#chat-session-identity',e=>e.textContent),/New conversation/);
    assert.equal(await page.$eval('#chat-collect',e=>e.checked),false);
    // Ollama: a new chat asks before Ollama loads anything; "Not now" creates nothing and keeps the draft.
    await pickModel('ollama');
    const before=(await read('/api/v1/chat/sessions?limit=100')).items.length;
    await page.$eval('#chat-draft',e=>{e.value='Draft before approval';e.dispatchEvent(new Event('input'));});
    await page.click('#chat-send');
    await page.waitForSelector('#chat-prepare:not([hidden])');
    assert.match(await page.$eval('#chat-prepare',e=>e.textContent),/Allow Ollama to load this model\?/);
    await page.click('#chat-prepare-cancel');
    assert.equal((await read('/api/v1/chat/sessions?limit=100')).items.length,before,'no conversation without approval');
    assert.equal(await page.$eval('#chat-draft',e=>e.value),'Draft before approval','the draft stays');
    await page.$eval('#chat-draft',e=>{e.value='';e.dispatchEvent(new Event('input'));});

    await newChat({context:4096,reserve:1024});
    assert.equal(await page.$eval('#chat-context-label',e=>e.textContent),'4K');
    assert.equal(await page.$eval('#chat-model-label',e=>e.textContent),'fixture');
    assert.equal(await page.$eval('#chat-collect',e=>e.checked),false);

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
    const sid=(await read('/api/v1/chat/sessions?limit=1')).items[0].id;
    assert.match(await page.$eval('#chat-session-identity',e=>e.textContent),/LM Studio · fixture · Open/);
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
      // The conversation list refreshes just after a reply; click once it has settled.
      await page.waitForNetworkIdle({idleTime:300});
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
    await newChat({context:4096,reserve:1024});
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
    await newChat({context:128,reserve:127});
    assert.equal(await page.$eval('#chat-context-label',e=>e.textContent),'128');
    await page.type('#chat-draft','Unsent overflow draft');await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelector('#chat-notice').textContent.includes('Context limit reached'));
    assert.equal(await page.$$eval('.chatv2-msg',es=>es.length),0);
    assert.equal(await page.$eval('#chat-draft',e=>e.value),'Unsent overflow draft');
    assert.equal(await page.$eval('#chat-collect',e=>e.checked),false);

    // Stop: partial text is visible, marked, and never saved.
    await newChat({context:4096,reserve:1024});
    await page.$eval('#chat-draft',e=>{e.value='STOP_FIXTURE';e.dispatchEvent(new Event('input'));});await page.click('#chat-send');
    await page.waitForFunction(()=>document.querySelector('.chatv2-msg.streaming .chatv2-answer')?.textContent.includes('Partial synthetic'));
    assert.equal(await page.$eval('#chat-send',e=>e.hidden),true,'Stop takes the Send place while a reply runs');
    await page.click('#chat-stop');
    await page.waitForFunction(()=>document.querySelector('.chatv2-msg.incomplete')?.textContent.includes('Stopped'));
    await page.waitForFunction(()=>!document.querySelector('#chat-send').disabled);
    const newest=()=>page.evaluate(async()=>{const r=await fetch('/api/v1/chat/sessions?limit=50');return (await r.json()).items.find(i=>!i.pinned_at).id;});
    const stopped=(await read('/api/v1/chat/sessions/'+await newest())).turns.length;
    assert.equal(stopped,0);

    // Ollama, approved explicitly for this chat only.
    await newChat({provider:'ollama',context:4096,reserve:1024});
    await page.type('#chat-draft','Synthetic Ollama question');await page.keyboard.press('Enter');
    await approveCard();await settled(1);
    await page.waitForFunction(()=>document.querySelector('#chat-session-identity').textContent.startsWith('Ollama'));
    // Chat information is read only: facts, no controls.
    await page.click('#chat-info-open');await page.waitForSelector('#chat-panel[open]');
    await page.waitForFunction(()=>document.querySelector('#chat-info').textContent.includes('Token usage'));
    const info=await page.$eval('#chat-panel',e=>({text:e.textContent,controls:[...e.querySelectorAll('input,select,textarea,button')].map(c=>c.id)}));
    assert.deepEqual(info.controls,['chat-panel-close'],'Chat information has no controls');
    assert.match(info.text,/Chat information/);assert.match(info.text,/Conversation context budget4096 tokens/);assert.match(info.text,/Reply reserve1024 tokens/);
    assert.match(info.text,/CollectionOff/);assert.match(info.text,/Prompt tokens/);
    // A long unbreakable value (a SHA-256 identity or file path) wraps; it never squeezes its label to nothing or overlaps it.
    const squeeze=await page.$eval('#chat-info .chatv2-dl',dl=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent='Probe label';dd.textContent='native:'+'a'.repeat(64);dl.append(dt,dd);
      const a=dt.getBoundingClientRect(),b=dd.getBoundingClientRect(),w=dl.getBoundingClientRect().width;dt.remove();dd.remove();
      return {ratio:a.width/w,overlap:a.right>b.left+1&&a.left<b.right-1};});
    assert.ok(squeeze.ratio>0.25&&!squeeze.overlap,'Chat information label keeps its space next to a long value: '+JSON.stringify(squeeze));
    await page.click('#chat-panel-close');
    // Reading information must not stale the conversation that is already open.
    await page.type('#chat-draft','Second question after reading specs');await page.keyboard.press('Enter');await settled(2);
    // UX-08: completing an earlier request cannot erase text typed while it ran.
    await page.$eval('#chat-draft',e=>{e.value='DELAY_FIXTURE';e.dispatchEvent(new Event('input'));});await page.click('#chat-send');
    await page.waitForFunction(()=>!document.querySelector('#chat-stop').hidden);
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
      const send=await page.$eval('#chat-send',e=>{const r=e.getBoundingClientRect();return r.width>=40&&r.height>=40&&r.right<=innerWidth&&r.left>=0;});
      assert.ok(send,'a visible, tappable Send button on mobile');
      await page.screenshot({path:path.join(evidence,`chat-v2-${width}.png`)});
    }
    // 400% zoom (360×225 CSS px): the model menu stays inside the screen and scrolls; Send stays reachable.
    await page.setViewport({width:360,height:225});await page.evaluate(()=>document.querySelector('#chat-new-header').click());
    await page.evaluate(()=>document.querySelector('#chat-model-button').scrollIntoView({block:'center'}));
    await page.click('#chat-model-button');await page.waitForSelector('#chat-model-menu:not([hidden])');
    const reach=await page.$eval('#chat-model-menu',m=>{const r=m.getBoundingClientRect();return {fits:r.top>=-1&&r.bottom<=innerHeight+1&&r.left>=-1&&r.right<=innerWidth+1&&getComputedStyle(m).overflowY==='auto',
      rect:[r.left,r.top,r.right,r.bottom],view:[innerWidth,innerHeight],overflow:getComputedStyle(m).overflowY};});
    assert.ok(reach.fits,'the model menu fits and scrolls at 400% zoom: '+JSON.stringify(reach));
    await page.keyboard.press('Escape');
    assert.equal(await page.$eval('#chat-model-menu',e=>e.hidden),true,'Escape closes the menu');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'chat-model-button','focus returns to the model button');
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
    // V2.2.0 language metadata: English shows no Arabic dialects; "Other…" takes a custom value; nothing Arabic is forced.
    await page.click('[data-add-tab="direct"]');await page.waitForSelector('#form-direct.active select[data-taxonomy="language"]');
    await page.select('#form-direct select[data-taxonomy="language"]','en');
    const dialects=await page.$$eval('#form-direct select[data-taxonomy="dialect"] option',o=>o.map(x=>x.value));
    assert.ok(!dialects.includes('najdi')&&dialects.includes('uk'),'English offers English varieties, not Arabic dialects: '+dialects);
    await page.select('#form-direct select[data-taxonomy="domain"]','__custom');
    assert.equal(await page.$eval('#form-direct input[name="domain_custom"]',e=>e.classList.contains('hidden')),false);
    await page.type('#form-direct input[name="domain_custom"]','Tourism');
    await page.type('#form-direct textarea[name="text"]','A synthetic English paragraph for metadata.');
    await page.click('#form-direct button[type="submit"]');
    await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Record saved'));
    const savedText=await page.evaluate(async()=>(await window.api('/api/v1/manual-data?type=direct&search=synthetic%20English%20paragraph')).items[0]);
    assert.deepEqual([savedText.language,savedText.dialect,savedText.domain,savedText.language_layer],['en',null,'Tourism',null]);
    // V2.2.0 optional presets prefill new records only; "None" (the default) prefills nothing.
    const presetValues=()=>page.$eval('#form-direct',f=>['language','dialect','style','domain'].map(n=>f.querySelector(`select[data-taxonomy="${n}"]`).value));
    await page.select('#data-preset','najdi');
    await page.waitForFunction(()=>document.querySelector('#form-direct select[data-taxonomy="dialect"]').value==='najdi_riyadh');
    assert.deepEqual(await presetValues(),['ar','najdi_riyadh','conversational','general']);
    await page.select('#data-preset','');
    await page.waitForFunction(()=>document.querySelector('#form-direct select[data-taxonomy="language"]').value==='');
    assert.deepEqual(await presetValues(),['','','','']);
    await page.click('[data-add-tab="sft"]');await page.waitForSelector('#form-sft.active');
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
    // The Export center is an advanced tool of My versions (V2.2.0: three Data destinations).
    await page.click('.nav-item[data-view="my-versions"]');await page.waitForSelector('#view-my-versions.active');
    await page.click('.nav-item[data-view="settings"]');await page.click('#advanced-mode');await page.click('[data-advanced-view="exports"]');
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
    console.log('PASS: Chat V2 keyboard/duplicates, streaming+thinking, safe Markdown, titles/rename/pin/search/archive/restore, sidebar preference, 320/390px, rollover, Stop, Ollama approval, read-only Chat information, no New chat dialog, draft preservation, permanent delete; manual tabs/empty turns, export blockers and absent training routes; synthetic fixtures only.');
  }finally{
    if(browser)await browser.close();child.kill();
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
