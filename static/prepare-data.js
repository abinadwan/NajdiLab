/* Data → Prepare data: a three-step path from eligible records to a frozen Gold version and an export.
   1 Choose data: the choice lives in its own set; filters only change what is shown (QA P2).
   2 Check and prepare: the server runs every build step for exactly that choice without writing, and returns a
     fingerprint of what it checked; any later change of the choice invalidates the check.
   3 Create and export: explicit confirmation, a build bound to that fingerprint (refused if the data changed),
     readiness, then the Unsloth export. User text is always set as text, never as HTML. */
(function(global){
  'use strict';
  const el=id=>document.getElementById(id);
  function node(tag,attrs={},...children){const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs||{})){if(v==null||v===false)continue;if(k==='class')n.className=v;else n.setAttribute(k,v===true?'':v);}
    for(const c of children.flat())if(c!=null&&c!==false)n.append(c instanceof Node?c:document.createTextNode(String(c)));return n;}
  // replaceChildren() would print a null part as the text "null"; fill() leaves empty parts out.
  const fill=(host,...parts)=>host.replaceChildren(...parts.flat().filter(c=>c!=null&&c!==false));
  const ident=text=>node('bdi',{dir:'ltr',translate:'no'},text);
  const TYPE={sft:'Single-turn',multi_turn:'Multi-turn',direct_language:'Direct language',preference_pair:'Preference pair'};
  const FILE_LABEL={'sft.jsonl':'Single-turn','multi_turn.jsonl':'Multi-turn','direct_language.jsonl':'Direct language','preference_pairs.jsonl':'Preference pairs'};
  const STATUS={ready:'Ready',needs_attention:'Needs attention',rejected:'Rejected'};
  const POLICY={training_only:'Training only: no evaluation records',automatic_holdout:'Evaluation held out automatically by conversation',explicit_evaluation_only:'Evaluation: the records you marked evaluation only',explicit_plus_automatic:'Evaluation: the records you marked evaluation only, plus conversations held out automatically'};
  const HINT={
    EXPORT_PRIVATE_CONTEXT:'Its conversation contains ignored, deleted, private or evaluation-only turns, which would be exported with it. Leave it out, or resolve those turns in Review.',
    EXPORT_INCOMPLETE_CONTEXT:'Its earlier context is incomplete or unverifiable. Leave it out.',
    EXPORT_PRIVATE_TARGET:'It is marked as containing personal or sensitive data. Leave it out, or change the flag in Add data → My records.',
    REVIEW_PENDING:'A review is waiting for a decision. Pending reviews block every version until they are resolved in the Review queue.',
    SELECTION_INVALID:'A chosen record is no longer eligible. Reload the page.',
    NO_EXPORTABLE_DATA:'Choose at least one record.',
    EVALUATION_DUPLICATES_ANOTHER_RECORD:'Its answer is the same as another chosen record, so evaluation would measure memory, not quality. Leave this evaluation record out, or change its answer.'};
  const state={records:[],chosen:new Set(),check:null,checkedKey:null,created:null};

  const key=()=>JSON.stringify([...state.chosen].sort());
  const shown=()=>{const type=el('prepare-type').value,source=el('prepare-source').value,use=el('prepare-split-filter').value,lang=el('prepare-language').value;
    return state.records.filter(r=>(!type||r.type===type)&&(!source||r.source===source)&&(!use||r.split===use)&&(!lang||(r.language||'')===lang));};

  function step(n){
    for(const i of [1,2,3])el(`prepare-panel-${i}`).hidden=i!==n;
    document.querySelectorAll('.prepare-stepper-item').forEach(b=>{const i=Number(b.dataset.step);if(i===n)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');
      b.disabled=i===1?false:i===2?!state.check:!(state.check&&state.check.fingerprint&&state.checkedKey===key());});
    el(`prepare-step${n}`).focus?.();
  }

  function invalidate(){
    if(state.check&&state.checkedKey!==key()){state.check=null;state.checkedKey=null;}
    updateCount();step(1);
  }

  function updateCount(){
    const visible=shown(),hidden=[...state.chosen].filter(id=>!visible.some(r=>r.id===id)).length;
    fill(el('prepare-count'),ident(String(state.chosen.size)),' ','of',' ',ident(String(state.records.length)),' ','records chosen',
      ...(hidden?[' · ',ident(String(hidden)),' ','not shown by the filters']:[]));
    fill(el('prepare-selection-list'),...state.records.filter(r=>state.chosen.has(r.id)).map(r=>node('li',{},ident(r.id),' · ',TYPE[r.type]||r.type,r.split==='evaluation_only'?[' · ','Evaluation only']:null)));
    el('prepare-check').disabled=!state.chosen.size;
  }

  function renderRecords(){
    const rows=shown();
    fill(el('prepare-records'),...(rows.length?rows.map(r=>{
      const box=node('input',{type:'checkbox','data-id':r.id,'aria-label':`Include ${r.id}`});box.checked=state.chosen.has(r.id);
      box.onchange=()=>{if(box.checked)state.chosen.add(r.id);else state.chosen.delete(r.id);invalidate();};
      const meta=[TYPE[r.type]||r.type,r.split==='evaluation_only'?'Evaluation only':'Training',r.source==='manual'?'Manual':'Collected',
        [r.language,r.dialect,r.style,r.domain].filter(Boolean).join(' · ')||null].filter(Boolean);
      return node('div',{class:'prepare-record'},node('label',{class:'inline-check'},box,' ',ident(r.id)),node('p',{class:'muted'},meta.join(' · ')),
        node('details',{},node('summary',{},'Preview'),r.question?node('p',{dir:'auto'},node('strong',{},'Question: '),r.question):null,node('p',{dir:'auto'},node('strong',{},'Answer: '),r.answer||'—')));
    }):[node('p',{},state.records.length?'No record matches these filters.':'No eligible records yet. Add records in Add data, or approve them in Review.')]));
    updateCount();
  }

  async function load(){
    fill(el('prepare-records'),node('p',{},'Loading eligible records…'));
    try{
      const data=await global.api('/api/v1/prepare/records');
      state.records=data.items;state.chosen=new Set(data.items.map(r=>r.id));state.check=null;state.checkedKey=null;state.created=null;
      const languages=[...new Set(data.items.map(r=>r.language).filter(Boolean))].sort();
      fill(el('prepare-language'),node('option',{value:''},'All languages'),...languages.map(l=>node('option',{value:l},l)));
      renderRecords();step(1);
    }catch(error){fill(el('prepare-records'),node('p',{role:'alert'},error.message));}
  }

  async function check(){
    const chosen=[...state.chosen],button=el('prepare-check');button.disabled=true;
    el('prepare-status').textContent='Checking…';fill(el('prepare-summary'),);fill(el('prepare-problems'),);fill(el('prepare-advanced-body'),);
    state.check=null;step(2);
    try{
      const result=await global.api('/api/v1/prepare/check',{method:'POST',body:JSON.stringify({selection:chosen})});
      state.check=result;state.checkedKey=JSON.stringify([...chosen].sort());
      const s=result.summary,blocking=result.readiness.blocking_findings||[],notes=(result.readiness.findings||[]).filter(f=>!f.blocking);
      fill(el('prepare-status'),node('span',{class:`prepare-badge ${result.status}`},STATUS[result.status]||result.status),' ',
        result.status==='ready'?'Everything needed for a version is in place.':result.status==='needs_attention'?'Some chosen records need attention before a version can be created.':'A version cannot be created from this choice.');
      fill(el('prepare-summary'),
        node('p',{},ident(String(s.accepted)),' ','records accepted',' · ',ident(String(s.rejected_records)),' ','records need attention'),
        s.files?node('ul',{},...Object.entries(s.files).filter(([,n])=>n).map(([f,n])=>node('li',{},FILE_LABEL[f]||f,': ',ident(String(n))))):null,
        s.files?node('p',{},'Evaluation records:',' ',ident(String(s.evaluation)),' · ',POLICY[s.evaluation_policy]||s.evaluation_policy):null,
        s.evaluation_policy_reason?node('p',{class:'muted'},'Why:',' ',s.evaluation_policy_reason):null,
        s.evaluation_note?node('p',{class:'muted'},s.evaluation_note):null,
        s.files&&!s.evaluation?node('p',{class:'warning'},'Without evaluation records, a training run on this version cannot show a quality change. To evaluate, mark held-out records "Evaluation only" in Add data.'):null,
        s.files?node('p',{},'Conversations shared between training and evaluation:',' ',ident(String(s.shared_conversations)),' · ','Exact duplicates removed:',' ',ident(String(s.exact_duplicates_removed)),' · ','Near duplicates to review:',' ',ident(String(s.near_duplicates))):null);
      fill(el('prepare-problems'),...blocking.map(f=>{
        const id=f.sample_id,mine=id&&state.chosen.has(id);
        const leave=mine?Object.assign(node('button',{type:'button',class:'button ghost'},'Leave this record out'),{onclick:()=>{state.chosen.delete(id);renderRecords();invalidate();}}):null;
        return node('div',{class:'prepare-problem'},node('p',{},id?ident(id):'All chosen records'),node('p',{},HINT[f.code]||f.reason),leave);
      }));
      fill(el('prepare-advanced-body'),
        node('p',{},'Languages:',' ',Object.entries(s.languages||{}).map(([k,v])=>`${k} ${v}`).join(' · ')||'—'),
        ...blocking.concat(notes).slice(0,80).map(f=>node('p',{class:'muted'},ident(f.code),f.sample_id?[' · ',ident(f.sample_id)]:null,' — ',f.reason)));
      el('prepare-next-3').disabled=result.status!=='ready'||!result.fingerprint;
      step(2);
    }catch(error){fill(el('prepare-status'),node('span',{role:'alert'},error.message));}
    finally{button.disabled=!state.chosen.size;}
  }

  function final(){
    const s=state.check.summary;
    fill(el('prepare-final'),node('p',{},'The version will contain:'),
      node('ul',{},...Object.entries(s.files).filter(([,n])=>n).map(([f,n])=>node('li',{},FILE_LABEL[f]||f,': ',ident(String(n)))),node('li',{},'Evaluation',': ',ident(String(s.evaluation)))));
    el('prepare-confirm').checked=false;el('prepare-create').disabled=true;fill(el('prepare-created'),);el('prepare-export').hidden=true;fill(el('prepare-export-result'),);
    step(3);
  }

  async function create(){
    if(!state.check||state.checkedKey!==key()||!state.check.fingerprint||!el('prepare-confirm').checked)return;
    const button=el('prepare-create');button.disabled=true;fill(el('prepare-created'),node('p',{},'Creating the version…'));
    try{
      const data=await global.api('/api/v1/exports',{method:'POST',body:JSON.stringify({selection:[...state.chosen],fingerprint:state.check.fingerprint})});
      state.created=data.export.version;
      const health=await global.api(`/api/v1/dataset-versions/${encodeURIComponent(state.created)}/health`),rd=health.readiness;
      const label={VALID:'Valid',INVALID:'Invalid',STRUCTURE_CHECKED:'Structure checked',BLOCKED:'Blocked',NO_EVALUATION_DATA:'No evaluation data',LEAKAGE_DETECTED:'Leakage detected',INDEPENDENT_SAMPLES_AVAILABLE:'Independent samples'};
      const open=node('a',{href:'/versions',class:'button ghost'},'Open in My versions');open.onclick=e=>{e.preventDefault();global.switchView?.('my-versions');};
      fill(el('prepare-created'),node('p',{},'Created and frozen:',' ',node('strong',{},ident(state.created))),
        node('p',{},'Structural validity:',' ',label[rd.structural.status]||rd.structural.status,' · ','Training compatibility:',' ',label[rd.training_compatibility.status]||rd.training_compatibility.status,' · ','Evaluation readiness:',' ',label[rd.evaluation.status]||rd.evaluation.status),open);
      el('prepare-export').hidden=rd.structural.status!=='VALID';
    }catch(error){fill(el('prepare-created'),node('p',{role:'alert'},error.message));button.disabled=false;}
  }

  async function exportUnsloth(){
    const profile=document.querySelector('input[name="prepare-profile"]:checked')?.value||'studio_chat',host=el('prepare-export-result');
    host.replaceChildren(node('p',{},'Creating the Unsloth export…'));
    try{
      const data=await global.api('/api/v1/unsloth-exports',{method:'POST',body:JSON.stringify({version:state.created,profile})});
      host.replaceChildren(node('p',{},ident(String(data.record_count)),' ','training records',' · ',data.target_trainer),...data.warnings.map(w=>node('p',{class:'muted'},w)),
        ...['dataset.jsonl','provenance.jsonl','manifest.json'].map(name=>node('a',{href:`/api/v1/unsloth-exports/${data.id}/${name}`,download:name},`Download ${name} `)));
    }catch(error){host.replaceChildren(node('p',{role:'alert'},error.message));}
  }

  let bound=false;
  function bind(){
    if(bound)return;bound=true;
    for(const id of ['prepare-type','prepare-source','prepare-split-filter','prepare-language'])el(id).onchange=renderRecords;
    el('prepare-all').onclick=()=>{shown().forEach(r=>state.chosen.add(r.id));renderRecords();invalidate();};
    el('prepare-none').onclick=()=>{shown().forEach(r=>state.chosen.delete(r.id));renderRecords();invalidate();};
    el('prepare-check').onclick=check;el('prepare-back-1').onclick=()=>step(1);el('prepare-back-2').onclick=()=>step(2);
    el('prepare-next-3').onclick=()=>{if(state.check&&state.checkedKey===key())final();};
    el('prepare-confirm').onchange=()=>{el('prepare-create').disabled=!el('prepare-confirm').checked||state.checkedKey!==key();};
    el('prepare-create').onclick=create;el('prepare-export-go').onclick=exportUnsloth;
    document.querySelectorAll('.prepare-stepper-item').forEach(b=>b.onclick=()=>{const n=Number(b.dataset.step);if(n===3&&state.check)final();else step(n);});
  }
  global.NajdiPrepare={load(){bind();return load();},state};
})(typeof window!=='undefined'?window:globalThis);
