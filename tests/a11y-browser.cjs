/* UX-22 / QA-05 keyboard, focus, names, dialogs and reflow acceptance in Chromium (synthetic data). */
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {test}=require('node:test');
const puppeteer=require('puppeteer-core');

const VIEWS=['dashboard','chat','models','review-queue','conversations','reviewed','add-data','manual-data','dataset',
  'dataset-health','balancer','dataset-versions','eval-sets','exports','analytics','settings'];
const FOCUSABLE='a[href],button,input,select,textarea,summary,[tabindex]:not([tabindex="-1"])';

test('keyboard and assistive technology acceptance in Chromium',async t=>{
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{stdio:['ignore','pipe','pipe']});
  let browser;
  try{
    const base=await new Promise((resolve,reject)=>{
      let out='',err='';const timer=setTimeout(()=>reject(Error('fixture timeout: '+err)),20000);
      child.stdout.on('data',c=>{out+=c;const m=out.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
      child.stderr.on('data',c=>err+=c);child.once('exit',code=>{clearTimeout(timer);reject(Error('fixture exited '+code+': '+err));});
    });
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    const page=await browser.newPage();
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.setViewport({width:1440,height:1000});
    await page.goto(base+'/');await page.waitForSelector('#view-dashboard.active');
    await page.evaluate(async()=>{
      const conv=await api('/api/v1/conversations',{method:'POST',body:JSON.stringify({title:'Synthetic accessibility conversation',channel:'manual'})});
      await api('/api/v1/messages',{method:'POST',body:JSON.stringify({conversation_id:conv.conversation.id,role:'user',content:'Synthetic question'})});
      await api('/api/v1/messages',{method:'POST',body:JSON.stringify({conversation_id:conv.conversation.id,role:'assistant',content:'Synthetic answer'})});
      await api('/api/v1/manual-data/direct',{method:'POST',body:JSON.stringify({text:'Synthetic direct text',language_layer:'najdi_riyadh',source_type:'human_written'})});
    });
    const settle=()=>new Promise(r=>setTimeout(r,500));
    const open=async view=>{await page.evaluate(v=>switchView(v),view);await page.waitForSelector(`#view-${view}.active`);await settle();};
    const cdp=await page.target().createCDPSession();await cdp.send('Accessibility.enable');await cdp.send('DOM.enable');

    async function unnamedFocusable(){
      await cdp.send('DOM.getDocument');
      const {nodes}=await cdp.send('Accessibility.getFullAXTree');
      const out=[];
      for(const n of nodes){
        if(n.ignored)continue;
        const focusable=(n.properties||[]).some(p=>p.name==='focusable'&&p.value.value);
        const role=n.role&&n.role.value,name=(n.name&&n.name.value||'').trim();
        if(!focusable||name||['RootWebArea','generic','none','dialog'].includes(role))continue;
        const {object}=await cdp.send('DOM.resolveNode',{backendNodeId:n.backendDOMNodeId});
        const html=await cdp.send('Runtime.callFunctionOn',{objectId:object.objectId,functionDeclaration:'function(){return this.outerHTML.slice(0,160)}',returnByValue:true});
        out.push(`${role}: ${html.result.value}`);
      }
      return out;
    }

    for(const language of ['en','ar']){
      await t.test(`every focusable control has an accessible name and a visible focus indicator (${language})`,async()=>{
        await page.evaluate(l=>NajdiI18n.setLanguage(l),language);
        const report={};
        for(const view of VIEWS){
          await open(view);
          const unnamed=await unnamedFocusable();
          const noFocus=await page.evaluate(selector=>{
            const out=[];
            for(const el of document.querySelectorAll(selector)){
              if(el.disabled||!(el.checkVisibility?el.checkVisibility():el.offsetParent))continue;
              el.focus({focusVisible:true});if(document.activeElement!==el)continue;
              const cs=getComputedStyle(el);
              if(!((cs.outlineStyle!=='none'&&parseFloat(cs.outlineWidth)>0)||cs.boxShadow!=='none'))out.push(el.outerHTML.slice(0,120));
            }
            document.activeElement.blur();return out;
          },FOCUSABLE);
          if(unnamed.length||noFocus.length)report[view]={unnamed,noFocus};
        }
        assert.deepEqual(report,{},JSON.stringify(report,null,1));
      });
    }
    await page.evaluate(()=>NajdiI18n.setLanguage('en'));

    await t.test('skip link is the first stop and moves focus to the main content',async()=>{
      await page.goto(base+'/');await page.waitForSelector('#view-dashboard.active');
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(()=>document.activeElement.className),'skip-link');
      assert.ok(await page.evaluate(()=>document.activeElement.getBoundingClientRect().top>=0),'visible when focused');
      await page.keyboard.press('Enter');
      assert.equal(await page.evaluate(()=>document.activeElement.id),'main-content');
    });

    await t.test('navigation works from the keyboard and marks the current page',async()=>{
      await page.focus('.nav-item[data-view="reviewed"]');await page.keyboard.press('Enter');
      await page.waitForSelector('#view-reviewed.active');
      assert.equal(await page.$eval('.nav-item[data-view="reviewed"]',e=>e.getAttribute('aria-current')),'page');
      assert.equal(await page.$$eval('.nav-item[aria-current="page"]',els=>els.length),1);
      await page.focus('.nav-item[data-view="manual-data"]');await page.keyboard.press('Space');
      await page.waitForSelector('#view-manual-data.active');
      assert.equal(await page.$eval('.nav-item[data-view="reviewed"]',e=>e.hasAttribute('aria-current')),false);
    });

    await t.test('collapsed sidebar keeps every destination named',async()=>{
      await page.click('#collapse-sidebar');
      const names=await page.$$eval('.nav-item',els=>els.map(e=>{const label=e.querySelector('.nav-label');return [label.textContent.trim(),getComputedStyle(label).display!=='none',label.getBoundingClientRect().width<=1];}));
      assert.equal(names.length,16);
      for(const [name,rendered,hidden] of names)assert.ok(name&&rendered&&hidden,'label is visually hidden but present: '+name);
      const unnamed=(await unnamedFocusable()).filter(x=>x.includes('nav-item'));
      assert.deepEqual(unnamed,[]);
      await page.click('#collapse-sidebar');
    });

    await t.test('dialog opens from the keyboard, traps focus, closes with Escape and returns focus',async()=>{
      await open('manual-data');
      await page.waitForSelector('#manual-list [data-action="view"]');
      await page.focus('#manual-list [data-action="view"]');await page.keyboard.press('Enter');
      await page.waitForSelector('#manual-dialog[open]');
      assert.ok(await page.evaluate(()=>document.querySelector('#manual-dialog').contains(document.activeElement)),'focus moved into the dialog');
      for(let i=0;i<25;i++){await page.keyboard.press('Tab');
        assert.ok(await page.evaluate(()=>document.querySelector('#manual-dialog').contains(document.activeElement)||document.activeElement===document.body),'focus stays in the modal dialog');}
      await page.keyboard.press('Escape');
      await page.waitForFunction(()=>!document.querySelector('#manual-dialog').open);
      assert.equal(await page.evaluate(()=>document.activeElement.dataset.action),'view','focus returns to the control that opened the dialog');
    });

    await t.test('single-key review shortcuts are off by default and never act behind a dialog',async()=>{
      const pending=async()=>(await page.evaluate(()=>api('/api/v1/review-queue?include_demo=1'))).items.length;
      await open('review-queue');await page.waitForFunction(()=>!document.querySelector('#review-workspace').classList.contains('hidden'));
      const before=await pending();assert.ok(before>=1);
      await page.evaluate(()=>document.activeElement.blur());await page.keyboard.press('4');await settle();
      assert.equal(await pending(),before,'a stray "4" must not approve while shortcuts are off');
      await open('settings');await page.click('#review-shortcuts');
      assert.equal(await page.evaluate(()=>localStorage.getItem('najdilab.reviewShortcuts')),'on');
      await open('review-queue');await page.waitForFunction(()=>!document.querySelector('#review-workspace').classList.contains('hidden'));
      assert.match(await page.$eval('#review-shortcut-hint',e=>e.textContent),/4 approve/);
      await page.click('#delete-review');await page.waitForSelector('#review-delete-dialog[open]');
      await page.keyboard.press('4');await settle();
      assert.equal(await pending(),before,'shortcuts never act behind an open dialog');
      await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#review-delete-dialog').open);
      await page.focus('#review-notes');await page.keyboard.press('4');await settle();
      assert.equal(await pending(),before,'typing in a field never triggers a shortcut');
      await page.evaluate(()=>{document.querySelector('#review-notes').value='';document.activeElement.blur();});
      await page.keyboard.press('4');
      await page.waitForFunction(n=>api('/api/v1/review-queue?include_demo=1').then(d=>d.items.length===n-1),{},before);
      await open('settings');await page.click('#review-shortcuts');
      assert.equal(await page.evaluate(()=>localStorage.getItem('najdilab.reviewShortcuts')),'off');
    });

    await t.test('UX-05 review context is continuous and long text is available in full',async()=>{
      const long='بداية الرد الطويل. '+'جملة اصطناعية لاختبار اكتمال النص. '.repeat(18)+'نهاية الرد الطويل.';
      const ids=await page.evaluate(async long=>{
        const conv=await api('/api/v1/conversations',{method:'POST',body:JSON.stringify({title:'Synthetic continuity conversation',channel:'manual'})});
        const id=conv.conversation.id,send=(role,content)=>api('/api/v1/messages',{method:'POST',body:JSON.stringify({conversation_id:id,role,content})});
        await send('user','السؤال الأول');await send('assistant','الرد الأول');await send('user','السؤال الثاني');await send('assistant',long);
        return id;
      },long);
      const queue=(await page.evaluate(()=>api('/api/v1/review-queue?include_demo=1'))).items;
      const target=queue.find(item=>item.conversation_id===ids&&item.original_response===long);
      assert.deepEqual(target.context.map(m=>m.content),['السؤال الأول','الرد الأول','السؤال الثاني',long],'context is complete and in order');
      // Show that exact item in the review workspace and compare the rendered context.
      await open('review-queue');
      await page.evaluate(id=>{state.queueIndex=state.queue.findIndex(item=>item.id===id);renderReview();},target.id);
      const rendered=await page.$$eval('#context-messages .message p',els=>els.map(e=>e.textContent));
      assert.deepEqual(rendered,['السؤال الأول','الرد الأول','السؤال الثاني',long]);
      assert.equal(await page.$eval('#original-response',e=>e.textContent),long);
      await page.evaluate(async item=>{await api(`/api/v1/reviews/${item.id}/approve`,{method:'POST',body:JSON.stringify({expected_updated_at:item.updated_at,training_eligible:true,reviewer:'human'})});},target);

      await open('reviewed');
      await page.waitForSelector('.reviewed-card .full-text');
      const card=await page.$$eval('.reviewed-card',(cards,long)=>{const c=cards.find(x=>x.textContent.includes('بداية الرد الطويل'));return {preview:c.querySelector('.answer > p').textContent,full:c.querySelector('.full-text p').textContent};},long);
      assert.ok(card.preview.endsWith('…')&&card.preview.length<long.length,'the card shows a preview');
      assert.equal(card.full,long,'the complete text is available, unchanged');
      const summary=await page.evaluateHandle(()=>[...document.querySelectorAll('.reviewed-card')].find(c=>c.textContent.includes('بداية الرد الطويل')).querySelector('.full-text summary'));
      await summary.focus();await page.keyboard.press('Enter');
      assert.equal(await summary.evaluate(s=>s.parentElement.open),true,'opens from the keyboard');

      await open('dataset');
      await page.waitForSelector('#dataset-list .full-text');
      const preview=await page.$$eval('#dataset-list .dataset-item',items=>items.map(i=>i.querySelector('.full-text p')?.textContent||'').find(text=>text.includes('نهاية الرد الطويل'))||'');
      assert.ok(preview.includes(long),'the dataset record exposes its complete text');
    });

    for(const [width,label] of [[640,'200% zoom'],[320,'400% zoom']]){
      for(const language of ['en','ar']){
        await t.test(`content reflows without page-level horizontal scrolling at ${width}px (${label}, ${language})`,async()=>{
          await page.setViewport({width,height:900});
          await page.evaluate(l=>NajdiI18n.setLanguage(l),language);
          const overflow={};
          for(const view of VIEWS){
            await open(view);
            const scroll=await page.evaluate(()=>document.documentElement.scrollWidth);
            if(scroll>width)overflow[view]=scroll;
          }
          assert.deepEqual(overflow,{});
        });
      }
    }
    await page.setViewport({width:1440,height:1000});
    await page.evaluate(()=>NajdiI18n.setLanguage('en'));
    assert.deepEqual(errors,[]);
  }finally{
    if(browser)await browser.close();
    child.kill();
  }
});
