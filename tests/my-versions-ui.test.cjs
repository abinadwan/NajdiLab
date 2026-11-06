// Synthetic controller checks. Real-browser dialog, localization and reflow are checked separately.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

class DomNode {
  constructor(tag,text=''){
    this.tagName=tag;
    this.text=text;
    this.childNodes=[];
    this.attributes={};
    this.disabled=false;
    this.hidden=false;
    this.value='';
    this.parentNode=null;
  }
  setAttribute(name,value){
    this.attributes[name]=String(value);
    if(name==='class')this.className=value;
    if(name==='hidden'||name==='disabled')this[name]=true;
  }
  getAttribute(name){return this.attributes[name];}
  append(...children){for(const child of children){child.parentNode=this;this.childNodes.push(child);}}
  prepend(child){child.parentNode=this;this.childNodes.unshift(child);}
  replaceChildren(...children){for(const child of this.childNodes)child.parentNode=null;this.childNodes=[];this.append(...children);}
  remove(){this.parentNode.childNodes=this.parentNode.childNodes.filter(child=>child!==this);this.parentNode=null;}
  get textContent(){return this.text+this.childNodes.map(child=>child.textContent).join('');}
  set textContent(text){this.replaceChildren();this.text=String(text);}
  get isConnected(){return this.tagName==='body'||Boolean(this.parentNode?.isConnected);}
  focus(){this.focused=true;}
  showModal(){this.open=true;}
  close(){this.open=false;this.onclose?.();}
}
const all=root=>[root,...root.childNodes.flatMap(all)];
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const files=[{name:'manifest.json',bytes:42,sha256:'a'.repeat(64)},{name:'sft.jsonl',bytes:84,sha256:'b'.repeat(64)}];
const version='gold-synthetic-one';

function harness(){
  const body=new DomNode('body'),list=new DomNode('div');
  list.setAttribute('id','versions-list');body.append(list);
  const calls=[],events=[],opened=[];
  const state={items:[{version,state:'Frozen',readable:true,counts:{'sft.jsonl':1}},
    {version:'gold-synthetic-other',state:'Frozen',readable:true,counts:{'sft.jsonl':2}}],
    preview:{version,allowed:true,blockers:[],files,token:'verified-preview-token'},failure:null,deletion:null};
  const document={body,createElement:tag=>new DomNode(tag),createTextNode:text=>new DomNode('#text',text),
    getElementById:id=>all(body).find(node=>node.getAttribute('id')===id)||null};
  const window={NajdiPrepare:{openVersion:async value=>opened.push(value)},dispatchEvent:event=>events.push(event),
    CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},
    api:async(path,options={})=>{
      calls.push([path,options]);
      if(path.endsWith('/delete-preview')){
        if(state.failure==='preview')throw Error('Preview unavailable');
        return structuredClone(state.preview);
      }
      if(path.endsWith('/delete')){
        if(state.deletion)await state.deletion;
        if(state.failure==='delete')throw Error('Files changed. Refresh the preview.');
        state.items=state.items.filter(item=>item.version!==version);
        return {version,deleted:true};
      }
      if(path==='/api/v1/dataset-versions')return {items:structuredClone(state.items)};
      if(path.includes('/unsloth-exports'))return {items:[{profile:'studio_chat',record_count:1,files:['/exports/example/train.jsonl']}]};
      if(path.endsWith('/health'))return {readiness:{structural:{status:'VALID'},training_compatibility:{status:'STRUCTURE_CHECKED'},evaluation:{status:'NO_EVALUATION_DATA'}},statistics:{training_records:1,independent_source_conversations:1}};
      return {version,files,manifest:{version,files:{'sft.jsonl':1}}};
    }};
  vm.runInNewContext(fs.readFileSync('static/my-versions.js','utf8'),{window,document,Node:DomNode});
  const id=name=>document.getElementById(name);
  const button=(className,value=version)=>all(list).find(node=>node.className?.split(' ').includes(className)&&node.getAttribute('data-version')===value);
  const open=async()=>{button('version-delete').onclick();await tick();};
  const confirm=value=>{id('gold-delete-confirm').value=value;id('gold-delete-confirm').oninput();};
  return {window,list,state,calls,events,opened,id,button,open,confirm};
}

test('version actions show manifest inline and send export directly to the Wizard',async()=>{
  const f=harness();await f.window.NajdiVersions.load();
  await f.button('version-view').onclick();
  assert.match(f.list.textContent,/Manifest JSON/);
  assert.match(f.list.textContent,/a{64}/);
  assert.equal(f.button('version-view').getAttribute('aria-expanded'),'true');
  await f.button('version-export').onclick();
  assert.deepEqual(f.opened,[version]);
  const readiness=all(f.list).find(node=>node.tagName==='button'&&node.textContent==='Readiness and exports');
  await readiness.onclick();
  assert.ok(all(f.list).some(node=>node.getAttribute('download')==='train.jsonl'));
  assert.ok(all(f.list).some(node=>node.getAttribute('href')===`/datasets/health?version=${version}`));
});

test('delete preview lists actual filenames and hashes and requires the exact typed version',async()=>{
  const f=harness();await f.window.NajdiVersions.load();await f.open();
  assert.match(f.id('gold-delete-files').textContent,/manifest.json/);
  assert.match(f.id('gold-delete-files').textContent,/b{64}/);
  assert.equal(f.id('gold-delete-submit').disabled,true);
  f.confirm(version+' ');assert.equal(f.id('gold-delete-submit').disabled,true);
  f.confirm(version);assert.equal(f.id('gold-delete-submit').disabled,false);
  assert.equal(f.calls.filter(([path])=>path.endsWith('/delete')).length,0);
});

test('canceling deletion makes no mutation and dismisses the dialog',async()=>{
  const f=harness();await f.window.NajdiVersions.load();await f.open();f.confirm(version);
  f.id('gold-delete-cancel').onclick();
  assert.equal(f.id('gold-delete-dialog'),null);
  assert.equal(f.calls.filter(([,options])=>options.method==='POST').length,0);
  assert.equal(f.state.items.length,2);
  assert.equal(f.events.length,0);
});

test('blocked deletion shows the server reasons and never submits',async()=>{
  const f=harness();f.state.preview.allowed=false;f.state.preview.blockers=['Another version references these files.'];
  await f.window.NajdiVersions.load();await f.open();f.confirm(version);
  assert.match(f.id('gold-delete-blockers').textContent,/Another version references/);
  assert.equal(f.id('gold-delete-submit').disabled,true);
  await f.id('gold-delete-submit').onclick();
  assert.equal(f.calls.filter(([,options])=>options.method==='POST').length,0);
});

test('missing preview identity, token, hashes, or target files fails closed',async()=>{
  for(const invalid of [{version:'another-version'},{token:''},{files:[]},{files:[{name:'manifest.json',bytes:42,sha256:''}]}]){
    const f=harness();Object.assign(f.state.preview,invalid);
    await f.window.NajdiVersions.load();await f.open();f.confirm(version);
    assert.equal(f.id('gold-delete-submit').disabled,true);
    assert.match(f.id('gold-delete-status').textContent,/cannot be safely deleted/);
  }
});

test('successful deletion submits once, retains the other version and emits an invalidation event',async()=>{
  const f=harness();await f.window.NajdiVersions.load();await f.open();f.confirm(version);
  let release;f.state.deletion=new Promise(resolve=>{release=resolve;});
  const submit=f.id('gold-delete-submit'),first=submit.onclick();
  await submit.onclick();assert.equal(f.id('gold-delete-cancel').disabled,true);
  let prevented=false;f.id('gold-delete-dialog').oncancel({preventDefault(){prevented=true;}});assert.equal(prevented,true);
  release();await first;
  const mutations=f.calls.filter(([,options])=>options.method==='POST');assert.equal(mutations.length,1);
  assert.deepEqual(JSON.parse(mutations[0][1].body),{token:'verified-preview-token',confirm_version:version});
  assert.equal(f.button('version-delete'),undefined);
  assert.ok(f.button('version-delete','gold-synthetic-other'));
  assert.match(f.list.textContent,/Version deleted/);
  assert.equal(f.events.length,1);assert.equal(f.events[0].type,'najdilab:versionschange');
  assert.equal(f.events[0].detail.version,version);assert.equal(f.events[0].detail.deleted,true);
});

test('failed deletion keeps readable feedback and demands a fresh preview and confirmation to retry',async()=>{
  const f=harness();await f.window.NajdiVersions.load();await f.open();f.confirm(version);f.state.failure='delete';
  await f.id('gold-delete-submit').onclick();
  assert.match(f.id('gold-delete-status').textContent,/Files changed/);
  assert.equal(f.id('gold-delete-submit').disabled,true);
  assert.equal(f.id('gold-delete-retry').hidden,false);
  assert.equal(f.id('gold-delete-cancel').disabled,false);
  assert.equal(f.events.length,0);
  f.state.failure=null;await f.id('gold-delete-retry').onclick();
  assert.equal(f.id('gold-delete-confirm').value,'');
  assert.equal(f.id('gold-delete-submit').disabled,true);
  f.confirm(version);await f.id('gold-delete-submit').onclick();
  assert.equal(f.events.length,1);
});

test('preview errors can be retried and repeated Delete clicks open one dialog',async()=>{
  const f=harness();f.state.failure='preview';await f.window.NajdiVersions.load();await f.open();
  assert.match(f.id('gold-delete-status').textContent,/Preview unavailable/);
  f.button('version-delete').onclick();
  assert.equal(all(f.list.parentNode).filter(node=>node.getAttribute('id')==='gold-delete-dialog').length,1);
  f.state.failure=null;await f.id('gold-delete-retry').onclick();
  f.confirm(version);assert.equal(f.id('gold-delete-submit').disabled,false);
});

test('an attested empty recovery plan can be explicitly confirmed and finalized',async()=>{
  const f=harness();f.state.preview.files=[];f.state.preview.recovery=true;
  await f.window.NajdiVersions.load();await f.open();
  assert.equal(f.id('gold-delete-submit').disabled,true);
  f.confirm(version);assert.equal(f.id('gold-delete-submit').disabled,false);
  await f.id('gold-delete-submit').onclick();assert.equal(f.events.length,1);
});
