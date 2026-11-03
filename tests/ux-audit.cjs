/* UX/UI audit (Phase UX/UI). Synthetic fixture only. Optional tool, not in CI:
 * needs puppeteer-core and axe-core (MPL-2.0, test-time only, not shipped) on NODE_PATH.
 * For every view × viewport × theme × language it records axe WCAG 2 A/AA
 * violations, horizontal page overflow and a screenshot. Usage:
 *   node tests/ux-audit.cjs <output-dir> [--quick]
 */
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const puppeteer=require('puppeteer-core');
const axeSource=fs.readFileSync(require.resolve('axe-core/axe.min.js'),'utf8');

const VIEWS=['dashboard','chat','review-queue','conversations','reviewed','add-data','manual-data','dataset',
  'dataset-health','balancer','dataset-versions','eval-sets','exports','analytics','settings'];
const VIEWPORTS={desktop:[1440,900],tablet:[820,1180],'mobile-390':[390,844],'mobile-320':[320,700],'zoom-200':[720,450],'zoom-400':[360,225]};

(async()=>{
  const out=path.resolve(process.argv[2]||'ux-audit');fs.mkdirSync(out,{recursive:true});
  const quick=process.argv.includes('--quick');
  const child=spawn(process.env.PYTHON||'python',['-u','tests/chat_browser_fixture.py'],{cwd:path.resolve(__dirname,'..'),stdio:['ignore','pipe','pipe']});
  let browser;const report=[];
  try{
    const base=await new Promise((resolve,reject)=>{let t='';const timer=setTimeout(()=>reject(Error('fixture timeout')),20000);
      child.stdout.on('data',c=>{t+=c;const m=t.match(/BROWSER_FIXTURE=(\S+)/);if(m){clearTimeout(timer);resolve(m[1]);}});});
    browser=await puppeteer.launch({executablePath:process.env.NAJDILAB_BROWSER_EXECUTABLE,headless:true,args:['--no-sandbox']});
    const page=await browser.newPage();
    const wait=ms=>new Promise(r=>setTimeout(r,ms));
    await page.setViewport({width:1440,height:900});
    await page.goto(base+'/chat');await page.waitForSelector('#view-chat.active');
    // Synthetic content: a chat with a Markdown reply and thinking, a second titled chat.
    await page.click('#chat-new');await page.waitForSelector('#chat-setup[open] #chat-provider option');
    await page.click('#chat-create');await page.waitForFunction(()=>!document.querySelector('#chat-setup').open&&!document.querySelector('#chat-collect').disabled);
    await page.type('#chat-draft','MARKDOWN_FIXTURE');await page.keyboard.press('Enter');
    await page.waitForFunction(()=>document.querySelectorAll('.chatv2-msg.assistant:not(.streaming)').length===1,{timeout:10000});
    const audit=async(label)=>{
      await page.evaluate(axeSource);
      const result=await page.evaluate(async()=>{
        const r=await window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']},resultTypes:['violations']});
        return r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.length,targets:v.nodes.slice(0,3).map(n=>n.target.join(' ')),
          colors:v.id==='color-contrast'?v.nodes.slice(0,6).map(n=>{const d=(n.any[0]||{}).data||{};return [n.target.join(' '),d.fgColor,d.bgColor,d.contrastRatio,d.expectedContrastRatio];}):undefined}));
      });
      const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
      const file=label.replace(/[^a-z0-9-]+/gi,'_')+'.png';
      await page.screenshot({path:path.join(out,file)});
      report.push({label,overflow,violations:result,screenshot:file});
    };
    const combos=quick?[['desktop','light','en'],['mobile-390','dark','ar']]:[];
    if(!quick)for(const vp of Object.keys(VIEWPORTS))for(const theme of ['light','dark'])for(const lang of ['en','ar'])combos.push([vp,theme,lang]);
    for(const [vp,theme,lang] of combos){
      const [w,h]=VIEWPORTS[vp];await page.setViewport({width:w,height:h});
      await page.evaluate((theme,lang)=>{document.documentElement.setAttribute('data-theme',theme);try{localStorage.setItem('najdilab.theme',theme);}catch{}window.NajdiI18n.setLanguage(lang);},theme,lang);
      const views=(vp==='desktop'&&theme==='light')||(vp==='mobile-390'&&theme==='dark')?VIEWS:['dashboard','chat','review-queue','settings'];
      for(const view of views){
        await page.evaluate(v=>switchView(v),view);await page.waitForSelector(`#view-${view}.active`);await wait(350);
        await page.evaluate(()=>window.scrollTo(0,0));
        await audit(`${vp}-${theme}-${lang}-${view}`);
      }
      // Chat dialogs and the action menu, per combination.
      await page.evaluate(()=>switchView('chat'));await page.waitForSelector('#view-chat.active');await wait(300);
      await page.evaluate(()=>document.querySelector('#chat-new').click());await page.waitForSelector('#chat-setup[open]');await wait(300);await audit(`${vp}-${theme}-${lang}-chat-setup-dialog`);
      await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#chat-setup').open);
      await page.evaluate(()=>document.querySelector('#chat-settings-open').click());await page.waitForSelector('#chat-panel[open]');await wait(200);
      await audit(`${vp}-${theme}-${lang}-chat-settings-drawer`);
      await page.evaluate(()=>document.querySelector('#chat-panel-close').click());
      await page.evaluate(()=>document.querySelector('#chat-actions').click());await wait(150);
      await page.evaluate(()=>document.querySelector('#chat-action-menu [data-chat-action="delete"]').click());
      await page.waitForSelector('#chat-delete[open]');await wait(200);await audit(`${vp}-${theme}-${lang}-chat-delete-dialog`);
      await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#chat-delete').open);
    }
    fs.writeFileSync(path.join(out,'ux-audit.json'),JSON.stringify(report,null,1));
    const rules={};for(const r of report)for(const v of r.violations){const k=`${v.id} (${v.impact})`;rules[k]=(rules[k]||0)+1;}
    console.log(JSON.stringify({pages:report.length,overflow:report.filter(r=>r.overflow>1).map(r=>[r.label,r.overflow]),rules},null,1));
  }finally{if(browser)await browser.close();child.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});
