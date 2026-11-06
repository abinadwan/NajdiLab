/* One guided data workspace. Backend planning owns validation and Frozen files own exports. */
(function(global){
  'use strict';
  const el=id=>document.getElementById(id);
  const STORE='najdilab.workflow.v1';
  const TABLE={sft:'manual_sft_items',direct:'direct_language_texts',dpo:'preference_pairs'};
  const TYPE={sft:'Single-turn',multi_turn:'Multi-turn',direct_language:'Direct language',preference_pair:'Preference pair'};
  const FILE_LABEL={'sft.jsonl':'Single-turn','multi_turn.jsonl':'Multi-turn','direct_language.jsonl':'Direct language','preference_pairs.jsonl':'Preference pairs','evaluation_holdout.jsonl':'Evaluation'};
  const HINT={EVALUATION_DUPLICATES_ANOTHER_RECORD:'Its answer is the same as another chosen record, so evaluation would measure memory, not quality. Leave this evaluation record out, or change its answer.',EXPORT_PRIVATE_TARGET:'It is marked as containing personal or sensitive data. Leave it out, or change the flag in Add data → My records.'};
  const READY={VALID:'Valid',INVALID:'Invalid',STRUCTURE_CHECKED:'Structure checked',BLOCKED:'Blocked',NO_EVALUATION_DATA:'No evaluation data',LEAKAGE_DETECTED:'Leakage detected',INDEPENDENT_SAMPLES_AVAILABLE:'Independent samples'};
  function node(tag,attrs={},...children){
    const n=document.createElement(tag);
    for(const [key,value] of Object.entries(attrs)){if(value==null||value===false)continue;if(key==='class')n.className=value;else n.setAttribute(key,value===true?'':value);}
    for(const child of children.flat())if(child!=null&&child!==false)n.append(child instanceof Node?child:document.createTextNode(String(child)));
    return n;
  }
  const fill=(host,...children)=>host.replaceChildren(...children.flat().filter(c=>c!=null&&c!==false));
  const ident=text=>node('bdi',{dir:'ltr',translate:'no'},text);
  const state={records:[],chosen:new Set(),check:null,checkedKey:null,created:null,stage:1,revision:0,initialized:false,options:null};
  let bound=false,restored=false,drafts={},editDraft=null,loadPromise=null;
  const key=()=>JSON.stringify([...state.chosen].sort());
  const advanced=()=>document.documentElement.classList.contains('advanced-mode');
  const translated=text=>global.NajdiI18n?.t(text)||text;

  function readStored(){
    try{
      const saved=JSON.parse(localStorage.getItem(STORE)||'null');
      if(!saved||saved.schema!==1)return;
      state.stage=[1,2,3,4].includes(saved.stage)?saved.stage:1;
      state.chosen=new Set(Array.isArray(saved.chosen)?saved.chosen.filter(x=>typeof x==='string'):[]);
      state.created=typeof saved.created==='string'?saved.created:null;
      state.initialized=true;drafts=saved.drafts||{};editDraft=saved.editDraft||null;
      for(const [id,value] of Object.entries(saved.filters||{})){if(el(id))el(id).value=String(value);}
      if(el('wizard-entry'))el('wizard-entry').open=!!saved.entryOpen;
    }catch{ /* Missing or blocked storage leaves a usable in-memory workspace. */ }
  }
  function formSnapshot(form){
    const fields={};
    for(const input of form.elements)if(input.name)fields[input.name]=input.type==='checkbox'?input.checked:input.value;
    const turns=[...form.querySelectorAll('.turn-row')].map(row=>({role:row.querySelector('select').value,content:row.querySelector('textarea').value}));
    return {fields,turns};
  }
  function restoreFields(form,snapshot){
    if(!snapshot)return;
    if(Array.isArray(snapshot.turns)){
      const host=form.querySelector('.turn-builder');
      if(host){host.replaceChildren();for(const turn of snapshot.turns){
        if(form.id==='form-sft')global.addSftTurn(turn.role,turn.content);
        else host.insertAdjacentHTML('beforeend',global.manualTurnRow(turn.role,turn.content));
      }}
    }
    for(const input of form.elements){
      if(!input.name||!Object.hasOwn(snapshot.fields||{},input.name))continue;
      const value=snapshot.fields[input.name];
      if(input.type==='checkbox')input.checked=!!value;
      else{
        if(input.tagName==='SELECT'&&value&&![...input.options].some(o=>o.value===value))input.add(new Option(value,value));
        input.value=String(value??'');
      }
    }
    for(const select of form.querySelectorAll('[data-taxonomy]'))select.nextElementSibling?.classList.toggle('hidden',select.value!=='__custom');
  }
  function save(){
    if(!restored)return;
    for(const form of document.querySelectorAll('form.data-form'))drafts[form.id]=formSnapshot(form);
    const edit=el('manual-edit-form');
    if(edit)editDraft={type:edit.dataset.itemType,id:Number(edit.dataset.itemId),snapshot:formSnapshot(edit),open:!!el('manual-dialog')?.open};
    const filters=Object.fromEntries(['prepare-type','prepare-source','prepare-split-filter','prepare-language'].map(id=>[id,el(id)?.value||'']));
    try{
      localStorage.setItem(STORE,JSON.stringify({schema:1,stage:state.stage,chosen:[...state.chosen],created:state.created,drafts,editDraft,filters,entryOpen:!!el('wizard-entry')?.open}));
      el('workflow-save-status').textContent='Draft saved in this browser';
    }catch{if(el('workflow-save-status'))el('workflow-save-status').textContent='Browser storage is unavailable. Keep this page open to retain your draft.';}
  }
  async function restoreDrafts(){
    if(restored)return;
    await Promise.all([...document.querySelectorAll('form.data-form [data-taxonomy-host]')].map(host=>global.mountTaxonomy(host,global.dataDefaults())));
    for(const [id,snapshot] of Object.entries(drafts))if(el(id))restoreFields(el(id),snapshot);
    if(editDraft?.open&&editDraft?.type&&editDraft?.id){
      try{await global.showManualItem(editDraft.type,editDraft.id,true);restoreFields(el('manual-edit-form'),editDraft.snapshot);}
      catch(error){editDraft=null;global.toast(error.message,true);}
    }
    restored=true;
  }
  function mountEditor(view='prepare'){
    const content=el('data-entry-content');
    const host=view==='add-data'?el('view-add-data'):el('wizard-editor');
    if(content&&host&&content.parentElement!==host)host.append(content);
  }
  function step(n,{persist=true}={}){
    const changed=state.stage!==n;state.stage=n;
    for(const i of [1,2,3,4])el(`prepare-panel-${i}`).hidden=i!==n;
    for(const button of document.querySelectorAll('.prepare-stepper-item')){
      const i=Number(button.dataset.step);button.toggleAttribute('aria-current',i===n);
      if(i===n)button.setAttribute('aria-current','step');
      button.disabled=i===1?false:i===2?!state.chosen.size:i===3?!(state.check?.fingerprint&&state.checkedKey===key()):!state.created;
    }
    if(changed&&!advanced()&&el('view-prepare').classList.contains('active'))el(`prepare-step${n}`)?.focus();
    if(persist)save();
  }
  function invalidate(){
    state.revision++;state.check=null;state.checkedKey=null;
    el('prepare-confirm').checked=false;el('prepare-next-3').disabled=true;el('prepare-create').disabled=true;
    if(state.stage===2){el('prepare-status').textContent='The records or selection changed. Run checks again.';fill(el('prepare-summary'));fill(el('prepare-problems'));}
    if(state.stage===3)step(2);else step(state.stage);
  }
  const shown=()=>state.records.filter(r=>(!el('prepare-type').value||r.type===el('prepare-type').value)&&(!el('prepare-source').value||r.source===el('prepare-source').value)&&(!el('prepare-split-filter').value||r.split===el('prepare-split-filter').value)&&(!el('prepare-language').value||r.language===el('prepare-language').value));
  function updateCount(){
    const visible=new Set(shown().map(r=>r.id)),hidden=[...state.chosen].filter(id=>!visible.has(id)).length;
    fill(el('prepare-count'),ident(String(state.chosen.size)),' ','of',' ',ident(String(state.records.length)),' ','records chosen',hidden?[' · ',ident(String(hidden)),' ','not shown by the filters']:null);
    fill(el('prepare-selection-list'),...state.records.filter(r=>state.chosen.has(r.id)).map(r=>node('li',{},ident(r.id),' · ',TYPE[r.type]||r.type,r.split==='evaluation_only'?[' · ','Evaluation only']:null)));
    el('prepare-check').disabled=!state.chosen.size;
  }
  function actionButton(label,action,r){
    const button=node('button',{type:'button',class:'button ghost','data-record-action':action,'data-record-id':r.id},label);
    button.onclick=async()=>{
      button.disabled=true;
      try{
        if(action==='edit')await global.showManualItem(r.manualType,r.manualId,true);
        else await global.manualAction(action,r.manualType,r.manualId);
      }catch(error){global.toast(error.message,true);}finally{if(button.isConnected)button.disabled=false;}
    };
    return button;
  }
  function renderRecords(){
    const rows=shown();
    fill(el('prepare-records'),...(rows.length?rows.map(r=>{
      const box=node('input',{type:'checkbox','data-id':r.id,'aria-label':`Include ${r.id}`});box.checked=state.chosen.has(r.id);
      box.onchange=()=>{if(box.checked)state.chosen.add(r.id);else state.chosen.delete(r.id);invalidate();updateCount();};
      const status=r.split==='evaluation_only'?'Evaluation only':r.eligible?'Eligible for checking':'Needs approval';
      return node('article',{class:'prepare-record'},
        node('div',{class:'record-heading'},node('label',{class:'inline-check'},box,' ',ident(r.id)),node('span',{class:'record-kind'},TYPE[r.type]||r.type),node('span',{class:'status-pill'},status)),
        node('p',{dir:'auto',class:'record-preview'},r.answer||r.preview||'—'),
        node('details',{},node('summary',{},'Preview'),r.question?node('p',{dir:'auto'},r.question):null,node('p',{dir:'auto'},r.answer||r.preview||'—')),
        r.manualType?node('div',{class:'record-actions'},actionButton('Edit','edit',r),actionButton('Duplicate as new','clone',r),actionButton('Delete','delete',r)):node('p',{class:'muted'},'Collected records retain their human review history.'));
    }):[node('div',{class:'workspace-empty'},node('h3',{},state.records.length?'No record matches these filters.':'Your first dataset starts with one example.'),node('p',{},'Add a record above, then choose the examples you want to check.'))]));
    updateCount();
  }
  async function refreshRecords({selectNew=false}={}){
    const oldIds=new Set(state.records.map(r=>r.id));
    const data=await global.api('/api/v1/prepare/records');
    const records=new Map(data.items.map(r=>[r.id,{...r,eligible:true}]));
    let offset=0;
    while(true){
      const manual=await global.api(`/api/v1/manual-data?limit=100&offset=${offset}`);
      for(const item of manual.items){
        const id=`${TABLE[item.item_type]}:${item.id}`,existing=records.get(id)||{};
        records.set(id,{...existing,id,type:item.item_type==='sft'?(item.messages?.length>2?'multi_turn':'sft'):item.item_type==='direct'?'direct_language':'preference_pair',
          source:'manual',split:item.evaluation_only?'evaluation_only':'training',eligible:!!item.training_eligible_effective||!!item.evaluation_only,language:item.language||'',
          answer:existing.answer||item.preview,preview:item.preview,manualType:item.item_type,manualId:item.id});
      }
      offset+=manual.items.length;
      if(!manual.items.length||offset>=(manual.page?.total??offset))break;
    }
    state.records=[...records.values()];
    if(!state.initialized){state.chosen=new Set(state.records.filter(r=>r.eligible).map(r=>r.id));state.initialized=true;}
    else{
      state.chosen=new Set([...state.chosen].filter(id=>records.has(id)));
      if(selectNew)for(const r of state.records)if(!oldIds.has(r.id)&&r.eligible)state.chosen.add(r.id);
    }
    const language=el('prepare-language').value;
    fill(el('prepare-language'),node('option',{value:''},'All languages'),...[...new Set(state.records.map(r=>r.language).filter(Boolean))].sort().map(value=>node('option',{value,translate:'no'},value)));
    el('prepare-language').value=language;renderRecords();save();
  }
  function issueControls(f){
    const r=state.records.find(r=>r.id===f.sample_id);
    if(!r)return null;
    const leave=node('button',{type:'button',class:'button ghost'},'Leave this record out');
    leave.onclick=()=>{state.chosen.delete(r.id);invalidate();renderRecords();};
    return node('div',{class:'record-actions'},r.manualType?actionButton('Edit','edit',r):null,leave);
  }
  function renderCheck(result){
    const s=result.summary,blocking=result.readiness.blocking_findings||[],notes=(result.readiness.findings||[]).filter(f=>!f.blocking);
    fill(el('prepare-status'),node('span',{class:`prepare-badge ${result.status}`},result.status==='ready'?'Ready':result.status==='needs_attention'?'Needs attention':'Rejected'),' ',result.status==='ready'?'The selected data passed the required build checks.':'Resolve the blocking findings before continuing.');
    fill(el('prepare-summary'),
      node('p',{},ident(String(s.accepted)),' ','records accepted',' · ',ident(String(s.rejected_records)),' ','records need attention'),
      s.files?node('ul',{class:'check-distribution'},...Object.entries(s.files).filter(([,n])=>n).map(([file,count])=>node('li',{},FILE_LABEL[file]||file,': ',ident(String(count))))):null,
      result.status==='ready'?node('ul',{class:'check-successes'},...['Privacy and eligibility checks passed.','Training and evaluation are separated.','Record structure and loss masks checked.'].map(text=>node('li',{},text))):null,
      s.files?node('p',{},'Evaluation records:',' ',ident(String(s.evaluation))):null,
      s.files&&!s.evaluation?node('p',{class:'warning'},'No independent evaluation samples. This version cannot measure a training quality change.'):null,
      s.files&&!(s.files['sft.jsonl']||s.files['multi_turn.jsonl'])?node('p',{class:'muted'},'Conversation concentration is not applicable to standalone data.'):null,
      s.files?node('p',{},'Exact duplicates removed:',' ',ident(String(s.exact_duplicates_removed)),' · ','Near duplicates to review:',' ',ident(String(s.near_duplicates))):null,
      s.evaluation_note?node('p',{class:'warning'},s.evaluation_note):null);
    fill(el('prepare-problems'),...blocking.map(f=>node('article',{class:'prepare-problem'},node('strong',{},'Blocks approval'),f.sample_id?ident(f.sample_id):null,node('p',{},HINT[f.code]||f.reason),issueControls(f))),
      ...notes.slice(0,20).map(f=>node('article',{class:'check-warning'},node('strong',{},'Review warning'),node('p',{},f.reason))));
    fill(el('prepare-advanced-body'),...blocking.concat(notes).map(f=>node('p',{},ident(f.code),' · ',f.reason)));
    el('prepare-next-3').disabled=result.status!=='ready'||!result.fingerprint;
  }
  async function check({restoreStage=null}={}){
    const revision=state.revision,chosen=[...state.chosen],chosenKey=key();state.check=null;state.checkedKey=null;
    step(2);el('prepare-status').textContent='Checking…';el('prepare-check').disabled=true;el('prepare-recheck').disabled=true;el('prepare-next-3').disabled=true;
    try{
      const result=await global.api('/api/v1/prepare/check',{method:'POST',body:JSON.stringify({selection:chosen})});
      if(revision!==state.revision||chosenKey!==key())return;
      state.check=result;state.checkedKey=chosenKey;renderCheck(result);
      if(restoreStage===3&&result.status==='ready')final();else step(2);
    }catch(error){fill(el('prepare-status'),node('span',{role:'alert'},error.message));}
    finally{el('prepare-check').disabled=!state.chosen.size;el('prepare-recheck').disabled=false;}
  }
  function final(){
    if(!state.check?.fingerprint||state.checkedKey!==key())return;
    el('prepare-create-status').textContent='';
    const s=state.check.summary;
    fill(el('prepare-final'),node('p',{},'The version will contain:'),node('ul',{},...Object.entries(s.files).filter(([,n])=>n).map(([file,count])=>node('li',{},FILE_LABEL[file]||file,': ',ident(String(count)))),node('li',{},'Evaluation',': ',ident(String(s.evaluation)))),
      !s.evaluation?node('p',{class:'warning'},'No independent evaluation samples. This version cannot measure a training quality change.'):null);
    el('prepare-confirm').checked=false;el('prepare-create').disabled=true;step(3);
  }
  async function create(){
    if(state.created||!state.check?.fingerprint||state.checkedKey!==key()||!el('prepare-confirm').checked)return;
    const button=el('prepare-create');button.disabled=true;el('prepare-create-status').textContent='Creating the version…';
    try{
      const result=await global.api('/api/v1/exports',{method:'POST',body:JSON.stringify({selection:[...state.chosen],fingerprint:state.check.fingerprint})});
      state.created=result.export.version;save();global.dispatchEvent(new CustomEvent('najdilab:versionschange',{detail:{version:state.created}}));
      await renderExport();step(4);
    }catch(error){el('prepare-create-status').textContent=error.message;if(!state.created)button.disabled=false;}
  }
  function compatibility(){
    const profile=document.querySelector('input[name="prepare-profile"]:checked')?.value||'studio_chat';
    const option=state.options?.profiles.find(p=>(p.id||p.profile)===profile);
    el('prepare-export-go').disabled=!option?.compatible;
    el('prepare-export-compatibility').textContent=option?.reason||'Only compatible SFT and multi-turn records enter an Unsloth export. Other types stay in their separate files.';
  }
  async function renderExport(){
    if(!state.created)return;
    fill(el('prepare-created'),node('p',{},'Loading…'));fill(el('prepare-export-result'));el('prepare-export-go').disabled=true;
    try{
      const version=state.created;
      const [health,options]=await Promise.all([global.api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/health`),global.api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/export-options`)]);
      if(version!==state.created)return;
      state.options=options;const r=health.readiness;
      const open=node('a',{href:'/versions',class:'button ghost'},'Open in My versions');open.onclick=e=>{e.preventDefault();global.switchView('my-versions');};
      fill(el('prepare-created'),node('p',{},'Created and frozen:',' ',ident(version)),node('p',{},'Structural validity:',' ',READY[r.structural.status]||r.structural.status,' · ','Training compatibility:',' ',READY[r.training_compatibility.status]||r.training_compatibility.status,' · ','Evaluation readiness:',' ',READY[r.evaluation.status]||r.evaluation.status),open);
      fill(el('prepare-raw-exports'),node('h3',{},'Dataset files'),node('p',{},'Download each data type separately. The private recovery archive is excluded.'),node('ul',{class:'raw-downloads'},...options.files.map(file=>node('li',{},node('a',{href:file.url,download:file.name},ident(file.name)),file.count!=null?[' · ',ident(String(file.count)),' ','records']:null))));
      compatibility();
    }catch(error){fill(el('prepare-created'),node('p',{role:'alert'},error.message),Object.assign(node('button',{type:'button',class:'button ghost'},'Retry'),{onclick:renderExport}));}
  }
  async function exportUnsloth(){
    if(el('prepare-export-go').disabled)return;
    const profile=document.querySelector('input[name="prepare-profile"]:checked').value,host=el('prepare-export-result');el('prepare-export-go').disabled=true;
    fill(host,node('p',{},'Creating the Unsloth export…'));
    try{
      const data=await global.api('/api/v1/unsloth-exports',{method:'POST',body:JSON.stringify({version:state.created,profile})});
      fill(host,node('p',{},ident(String(data.record_count)),' ','training records',' · ',data.target_trainer),...data.warnings.map(w=>node('p',{class:'muted'},w)),...['dataset.jsonl','provenance.jsonl','manifest.json'].map(name=>node('a',{href:`/api/v1/unsloth-exports/${data.id}/${name}`,download:name},`Download ${name} `)));
    }catch(error){fill(host,node('p',{role:'alert'},error.message));}finally{compatibility();}
  }
  async function load(){
    bind();mountEditor();await restoreDrafts();
    if(advanced())return;
    if(loadPromise)return loadPromise;
    const stage=state.stage;
    loadPromise=(async()=>{
      await refreshRecords();
      if(state.created&&stage===4){await renderExport();step(4);}
      else if(stage>=2)await check({restoreStage:stage});
      else step(1);
    })().catch(error=>fill(el('prepare-records'),node('p',{role:'alert'},error.message))).finally(()=>{loadPromise=null;});
    return loadPromise;
  }
  function bind(){
    if(bound)return;bound=true;readStored();
    for(const id of ['prepare-type','prepare-source','prepare-split-filter','prepare-language'])el(id).onchange=()=>{renderRecords();save();};
    el('prepare-all').onclick=()=>{shown().forEach(r=>state.chosen.add(r.id));invalidate();renderRecords();};
    el('prepare-none').onclick=()=>{state.chosen.clear();invalidate();renderRecords();};
    el('prepare-check').onclick=()=>check();el('prepare-recheck').onclick=()=>check();
    el('prepare-back-1').onclick=()=>step(1);el('prepare-back-2').onclick=()=>step(2);el('prepare-back-3').onclick=()=>{if(state.check)final();else step(1);};
    el('prepare-next-3').onclick=final;
    el('prepare-confirm').onchange=()=>{el('prepare-create').disabled=!el('prepare-confirm').checked||!state.check?.fingerprint||!!state.created;};
    el('prepare-create').onclick=create;el('prepare-export-go').onclick=exportUnsloth;
    for(const input of document.querySelectorAll('input[name="prepare-profile"]'))input.onchange=()=>{compatibility();save();};
    el('prepare-new-version').onclick=async()=>{
      const button=el('prepare-new-version');button.disabled=true;
      try{
        await refreshRecords();
        state.created=null;state.options=null;state.check=null;state.checkedKey=null;step(1);
      }catch(error){global.toast(error.message,true);}
      finally{button.disabled=false;}
    };
    el('wizard-add-record').onclick=()=>{el('wizard-entry').open=true;el('wizard-entry').scrollIntoView({block:'nearest'});save();};
    el('wizard-entry').addEventListener('toggle',save);el('manual-dialog').addEventListener('close',save);
    for(const button of document.querySelectorAll('.prepare-stepper-item'))button.onclick=()=>{const n=Number(button.dataset.step);if(n===2)check();else if(n===3)final();else if(n===4&&state.created){step(4);renderExport();}else step(1);};
    document.addEventListener('input',e=>{if(e.target.closest('form.data-form,#manual-edit-form'))save();});
    document.addEventListener('change',e=>{if(e.target.closest('form.data-form,#manual-edit-form'))save();});
    document.addEventListener('click',e=>{if(e.target.closest('#add-sft-turn,.remove-turn,#manual-add-turn,.remove-manual-turn'))setTimeout(save,0);});
    global.addEventListener('beforeunload',save);
    global.addEventListener('najdilab:recordschange',()=>{editDraft=null;invalidate();refreshRecords({selectNew:true}).catch(error=>global.toast(error.message,true));});
    global.addEventListener('najdilab:versionschange',e=>{if(e.detail?.deleted&&e.detail.version===state.created){state.created=null;state.options=null;step(1);}});
  }
  global.NajdiPrepare={state,load,save,async initialize(){bind();await restoreDrafts();},restoreManualDraft(type,id){if(editDraft?.type===type&&Number(editDraft.id)===Number(id))restoreFields(el('manual-edit-form'),editDraft.snapshot);},discardEditDraft(){editDraft=null;save();},mountEditor,async openVersion(version){bind();state.created=version;state.stage=4;save();global.setAdvancedMode(false,false);global.switchView('prepare');}};
})(typeof window!=='undefined'?window:globalThis);
