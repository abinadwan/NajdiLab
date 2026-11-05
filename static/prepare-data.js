/* Datasets → Prepare training data: one path from eligible records to a frozen Gold version and an Unsloth export.
   1 choose records (each can be left out, with a preview) → 2 run every build check for exactly that choice →
   3 see the training / evaluation split → 4 create the version, then export. The advanced pages stay available.
   User text is always set as text, never as HTML. */
(function(global){
  'use strict';
  const el=id=>document.getElementById(id);
  function node(tag,attrs={},...children){const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs||{})){if(v==null||v===false)continue;if(k==='class')n.className=v;else n.setAttribute(k,v===true?'':v);}
    for(const c of children.flat())if(c!=null&&c!==false)n.append(c instanceof Node?c:document.createTextNode(String(c)));return n;}
  const ident=text=>node('bdi',{dir:'ltr',translate:'no'},text);
  const TYPE={sft:'Single-turn',multi_turn:'Multi-turn',direct_language:'Direct language',preference_pair:'Preference pair'};
  const HINT={
    EXPORT_PRIVATE_CONTEXT:'Its conversation contains ignored, deleted, private or evaluation-only turns, which would be exported with it. Leave it out of this version, or resolve those turns in Review.',
    EXPORT_INCOMPLETE_CONTEXT:'Its earlier context is incomplete or unverifiable. Leave it out of this version.',
    EXPORT_PRIVATE_TARGET:'It is marked as containing personal or sensitive data. Leave it out, or change the flag in Manual data.',
    REVIEW_PENDING:'A review is waiting for a decision. Pending reviews block every version until they are resolved in the Review queue.',
    SELECTION_INVALID:'A chosen record is no longer eligible. Reload the list.',
    NO_EXPORTABLE_DATA:'Choose at least one record.'};
  let records=[],checked=null,created=null;

  function selection(){return [...document.querySelectorAll('#prepare-records input[type=checkbox][data-id]:checked')].map(b=>b.dataset.id);}
  function key(list){return JSON.stringify([...list].sort());}

  function renderRecords(){
    const filter=el('prepare-type').value,host=el('prepare-records');
    const rows=records.filter(r=>!filter||r.type===filter);
    host.replaceChildren(...(rows.length?rows.map(r=>{
      const box=node('input',{type:'checkbox','data-id':r.id,'aria-label':`Include ${r.id}`});box.checked=r.include!==false;
      box.onchange=()=>{r.include=box.checked;stale();};
      const meta=[TYPE[r.type]||r.type,r.split==='evaluation_only'?'Evaluation only':'Training',r.source==='manual'?'Manual':'Collected',
        [r.language,r.dialect,r.style,r.domain].filter(Boolean).join(' · ')||null].filter(Boolean);
      return node('div',{class:'prepare-record'},node('label',{class:'inline-check'},box,' ',ident(r.id)),
        node('p',{class:'muted'},meta.join(' · ')),
        node('details',{},node('summary',{},'Preview'),r.question?node('p',{dir:'auto'},node('strong',{},'Question: '),r.question):null,node('p',{dir:'auto'},node('strong',{},'Answer: '),r.answer||'—')));
    }):[node('p',{},'No eligible records. Approve records in Review or mark manual records dataset eligible first.')]));
    el('prepare-count').replaceChildren(ident(String(selection().length)),' ','of',' ',ident(String(records.length)),' ','records selected');
  }

  function stale(){
    el('prepare-count').replaceChildren(ident(String(selection().length)),' ','of',' ',ident(String(records.length)),' ','records selected');
    if(checked&&checked.key!==key(selection())){el('prepare-create').disabled=true;el('prepare-check-status').textContent='The selection changed. Run the checks again.';}
  }

  async function load(){
    el('prepare-records').replaceChildren(node('p',{},'Loading eligible records…'));
    try{const data=await global.api('/api/v1/prepare/records');records=data.items;renderRecords();}
    catch(error){el('prepare-records').replaceChildren(node('p',{role:'alert'},error.message));}
  }

  async function check(){
    const chosen=selection(),button=el('prepare-check');button.disabled=true;el('prepare-create').disabled=true;
    el('prepare-check-status').textContent='Checking…';el('prepare-problems').replaceChildren();el('prepare-split').replaceChildren();
    try{
      const result=await global.api('/api/v1/prepare/check',{method:'POST',body:JSON.stringify({selection:chosen})});
      const r=result.readiness,blocking=r.blocking_findings||[],warnings=(r.findings||[]).filter(f=>!f.blocking);
      checked={key:key(chosen),ok:r.ok};
      el('prepare-check-status').textContent=r.ok?'All checks passed for these records.':`${blocking.length} problem(s) must be fixed before a version can be created.`;
      el('prepare-problems').replaceChildren(...blocking.map(f=>{
        const id=f.sample_id,inList=id&&records.some(x=>x.id===id);
        const actions=inList?Object.assign(node('button',{type:'button',class:'button ghost'},'Leave this record out'),{onclick:()=>{const box=document.querySelector(`#prepare-records input[data-id="${CSS.escape(id)}"]`);if(box){box.checked=false;box.dispatchEvent(new Event('change'));}}}):null;
        return node('div',{class:'prepare-problem'},node('p',{},node('strong',{},ident(f.code)),id?[' · ',ident(id)]:null),
          node('p',{},HINT[f.code]||f.reason),actions);
      }),warnings.length?node('details',{},node('summary',{},`${warnings.length} note(s) that do not block this version`),
        ...warnings.slice(0,50).map(f=>node('p',{class:'muted'},ident(f.code),f.sample_id?[' · ',ident(f.sample_id)]:null,' — ',f.reason))):null);
      const p=result.preview,dup=p.duplicates||{};
      el('prepare-split').replaceChildren(
        node('p',{},ident(String(p.training)),' ','training records',' · ',ident(String(p.evaluation)),' ','evaluation records',' · ',ident(String(p.evaluation_conversations)),' ','evaluation conversations'),
        node('p',{},'Conversations shared between training and evaluation:',' ',ident(String(p.shared_conversations))),
        node('p',{},'Exact duplicates removed when the version is created:',' ',ident(String(dup.exact_duplicates_removed||0)),' · ','Near duplicates to review:',' ',ident(String(dup.near_duplicate_count||0))),
        p.evaluation?null:node('p',{class:'warning'},'No evaluation records: a training run on this version cannot show a quality change. Mark held-out records as evaluation only, or choose at least 20 records for an automatic held-out split by conversation.'));
      el('prepare-create').disabled=!r.ok;
    }catch(error){el('prepare-check-status').textContent=error.message;}
    finally{button.disabled=false;}
  }

  async function create(){
    const chosen=selection();
    if(!checked||checked.key!==key(chosen)||!checked.ok)return;
    const button=el('prepare-create');button.disabled=true;el('prepare-created').replaceChildren(node('p',{},'Creating the version…'));
    try{
      const data=await global.api('/api/v1/exports',{method:'POST',body:JSON.stringify({selection:chosen})});
      created=data.export.version;
      const health=await global.api(`/api/v1/dataset-versions/${encodeURIComponent(created)}/health`),rd=health.readiness;
      const label={VALID:'Valid',INVALID:'Invalid',STRUCTURE_CHECKED:'Structure checked',BLOCKED:'Blocked',NO_EVALUATION_DATA:'No evaluation data',LEAKAGE_DETECTED:'Leakage detected',INDEPENDENT_SAMPLES_AVAILABLE:'Independent samples'};
      el('prepare-created').replaceChildren(node('p',{},'Created and frozen:',' ',node('strong',{},ident(created))),
        node('p',{},'Structural validity:',' ',label[rd.structural.status]||rd.structural.status,' · ','Training compatibility:',' ',label[rd.training_compatibility.status]||rd.training_compatibility.status,' · ','Evaluation readiness:',' ',label[rd.evaluation.status]||rd.evaluation.status));
      el('prepare-export').hidden=rd.structural.status!=='VALID';
      global.dispatchEvent?.(new Event('najdilab:datasets-changed'));
    }catch(error){el('prepare-created').replaceChildren(node('p',{role:'alert'},error.message));button.disabled=false;}
  }

  async function exportUnsloth(){
    const profile=document.querySelector('input[name="prepare-profile"]:checked')?.value||'studio_chat',host=el('prepare-export-result');
    host.replaceChildren(node('p',{},'Creating the Unsloth handoff…'));
    try{
      const data=await global.api('/api/v1/unsloth-exports',{method:'POST',body:JSON.stringify({version:created,profile})});
      host.replaceChildren(node('p',{},ident(String(data.record_count)),' ','training records',' · ',data.target_trainer),
        ...data.warnings.map(w=>node('p',{class:'muted'},w)),
        ...['dataset.jsonl','provenance.jsonl','manifest.json'].map(name=>node('a',{href:`/api/v1/unsloth-exports/${data.id}/${name}`,download:name},`Download ${name} `)));
    }catch(error){host.replaceChildren(node('p',{role:'alert'},error.message));}
  }

  let bound=false;
  function bind(){
    if(bound)return;bound=true;
    el('prepare-all').onclick=()=>{document.querySelectorAll('#prepare-records input[data-id]').forEach(b=>{b.checked=true;b.dispatchEvent(new Event('change'));});};
    el('prepare-none').onclick=()=>{document.querySelectorAll('#prepare-records input[data-id]').forEach(b=>{b.checked=false;b.dispatchEvent(new Event('change'));});};
    el('prepare-type').onchange=renderRecords;
    el('prepare-check').onclick=check;el('prepare-create').onclick=create;el('prepare-export-go').onclick=exportUnsloth;
  }
  global.NajdiPrepare={load(){bind();checked=null;created=null;el('prepare-create').disabled=true;el('prepare-export').hidden=true;
    el('prepare-check-status').textContent='';el('prepare-problems').replaceChildren();el('prepare-split').replaceChildren();el('prepare-created').replaceChildren();el('prepare-export-result').replaceChildren();return load();}};
})(typeof window!=='undefined'?window:globalThis);
