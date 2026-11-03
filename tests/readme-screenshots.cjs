/* Regenerates the README screenshots from the disposable synthetic browser fixture.
 * Never points at an installed instance or real conversations. Usage:
 *   NAJDILAB_BROWSER_EXECUTABLE=<chromium> NODE_PATH=<dir with puppeteer-core> node tests/readme-screenshots.cjs
 */
const {spawn}=require('node:child_process');
const path=require('node:path');
const puppeteer=require('puppeteer-core');
const OUT=path.resolve(__dirname,'..','docs','images','screenshots');

(async()=>{
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe'],windowsHide:true});
  let browser;
  try{
    const base=await new Promise((resolve,reject)=>{
      let text='';const timer=setTimeout(()=>reject(Error('fixture timeout')),20000);
      child.stdout.on('data',c=>{text+=c;const m=text.match(/BROWSER_FIXTURE=(http:\/\/127\.0\.0\.1:\d+)/);if(m){clearTimeout(timer);resolve(m[1]);}});
      child.once('exit',code=>reject(Error('fixture exited '+code)));
    });
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox','--lang=en-US']});
    const page=await browser.newPage();
    await page.setViewport({width:1440,height:900,deviceScaleFactor:1});
    const wait=ms=>new Promise(r=>setTimeout(r,ms));
    await page.goto(base+'/');await page.waitForSelector('#view-dashboard.active');await wait(800);
    await page.screenshot({path:path.join(OUT,'dashboard.png')});

    await page.goto(base+'/chat');await page.waitForSelector('#view-chat.active');
    const chat=async(text)=>{await page.type('#chat-draft',text);await page.keyboard.press('Enter');
      await page.waitForFunction(()=>!document.querySelector('.chatv2-msg.streaming')&&!document.querySelector('#chat-collect').disabled,{timeout:10000});};
    await page.click('#chat-new');await page.waitForSelector('#chat-setup[open] #chat-provider option');
    await page.click('#chat-create');await page.waitForFunction(()=>!document.querySelector('#chat-setup').open);
    await page.waitForFunction(()=>!document.querySelector('#chat-collect').disabled);
    await chat('MARKDOWN_FIXTURE');
    await page.evaluate(()=>{const d=document.querySelector('.chatv2-thinking');if(d)d.open=true;});
    for(const text of ['Synthetic question about a weekend plan','Second synthetic topic'])
      await page.evaluate(async t=>{const tok=await sessionToken();const h={'Content-Type':'application/json','X-NajdiLab-CSRF':tok};
        const s=await (await fetch('/api/v1/chat/sessions',{method:'POST',headers:h,body:JSON.stringify({provider:'lmstudio',model:'fixture',selection_revision:(await (await fetch('/api/v1/integrations')).json()).items.find(i=>i.id==='lmstudio').selection_revision,context_budget:4096,reply_reserve:1024,load_approved:false})})).json();
        await fetch(`/api/v1/chat/sessions/${s.id}/rename`,{method:'POST',headers:h,body:JSON.stringify({title:t})});},text);
    await page.evaluate(()=>document.querySelector('#chat-search').dispatchEvent(new Event('input')));await wait(600);
    await page.evaluate(()=>{window.scrollTo(0,0);document.querySelector('#chat-messages').scrollTop=0;});
    await page.screenshot({path:path.join(OUT,'chat-v2-desktop.png')});

    await page.select('#language-select','ar');await wait(900);
    await page.evaluate(()=>{window.scrollTo(0,0);document.querySelector('#chat-messages').scrollTop=0;});
    await page.screenshot({path:path.join(OUT,'chat-v2-arabic.png')});

    await page.select('#language-select','en');
    await page.setViewport({width:390,height:844,deviceScaleFactor:2});
    await page.reload();await page.waitForSelector('#view-chat.active');await wait(800);
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.screenshot({path:path.join(OUT,'chat-v2-mobile.png')});
    console.log('Screenshots written to '+OUT+' from the synthetic fixture.');
  }finally{if(browser)await browser.close();child.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
