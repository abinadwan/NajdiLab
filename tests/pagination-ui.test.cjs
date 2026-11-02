// UX-20: synthetic controller acceptance for the shared list pager.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const src=fs.readFileSync('static/app.js','utf8');
const start=src.indexOf('function listPage(key)');
const end=src.indexOf('async function loadConversations(',start);
assert.ok(start>=0&&end>start,'expected the shared pager helpers before loadConversations');
const helpers=src.slice(start,end);

function harness(){
  const buttons={};
  const pager={innerHTML:'',querySelector(selector){
    const name=selector.match(/data-page="(\w+)"/)[1];
    return buttons[name]||(buttons[name]={onclick:null,disabled:this.innerHTML.includes(`data-page="${name}" disabled`)});
  }};
  const context={state:{pages:{}},$:selector=>selector==='#reviewed-pager'?pager:null,esc:String,toast(){}};
  vm.createContext(context);vm.runInContext(helpers,context);
  const render=page=>{for(const key of Object.keys(buttons))delete buttons[key];let calls=0;
    context.renderPager('reviewed',page,async()=>{calls++;});return {buttons,calls:()=>calls};};
  return {context,pager,render};
}
const page=(offset,returned,total,limit=100)=>({offset,returned,total,limit,has_more:offset+returned<total});

test('summary states the exact range and total',()=>{
  const {context}=harness();
  assert.equal(context.pageSummary(page(0,0,0)),'No records');
  assert.equal(context.pageSummary(page(0,100,250)),'Showing 1–100 of 250');
  assert.equal(context.pageSummary(page(200,50,250)),'Showing 201–250 of 250');
});

test('first page disables Previous; Next advances by one page',async()=>{
  const {context,pager,render}=harness();
  render(page(0,100,250));
  assert.match(pager.innerHTML,/data-page="prev" disabled/);
  assert.doesNotMatch(pager.innerHTML,/data-page="next" disabled/);
  pager.querySelector('[data-page="next"]').onclick();
  assert.equal(context.listPage('reviewed').offset,100);
});

test('last page disables Next; Previous goes back without going negative',()=>{
  const {context,pager,render}=harness();
  render(page(200,50,250));
  assert.match(pager.innerHTML,/data-page="next" disabled/);
  pager.querySelector('[data-page="prev"]').onclick();
  assert.equal(context.listPage('reviewed').offset,100);
  render(page(0,30,30));
  assert.match(pager.innerHTML,/data-page="prev" disabled/);
});

test('an empty page past the end is corrected to the last real page',()=>{
  const {context}=harness();
  context.listPage('reviewed').offset=300;
  assert.equal(context.correctedPage('reviewed',page(300,0,250)),true);
  assert.equal(context.listPage('reviewed').offset,200);
  assert.equal(context.correctedPage('reviewed',page(0,0,0)),false,'an empty list is not corrected');
  assert.equal(context.correctedPage('reviewed',page(0,10,10)),false);
});

test('summary is exposed as a polite status for assistive technology',()=>{
  const {pager,render}=harness();
  render(page(0,1,1));
  assert.match(pager.innerHTML,/class="pager-summary" role="status"/);
});
