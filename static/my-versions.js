/* Data → My versions: frozen Gold versions, what is in them, how ready they are, and their exports.
   Read only: a frozen version is never edited here. Specialist tools are available through Settings in Advanced Mode. */
(function(global){
  'use strict';
  const el=id=>document.getElementById(id);
  function node(tag,attrs={},...children){const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs||{})){if(v==null||v===false)continue;if(k==='class')n.className=v;else n.setAttribute(k,v===true?'':v);}
    for(const c of children.flat())if(c!=null&&c!==false)n.append(c instanceof Node?c:document.createTextNode(String(c)));return n;}
  const ident=text=>node('bdi',{dir:'ltr',translate:'no'},text);
  const FILE_LABEL={'sft.jsonl':'Single-turn','multi_turn.jsonl':'Multi-turn','direct_language.jsonl':'Direct language','preference_pairs.jsonl':'Preference pairs','evaluation_holdout.jsonl':'Evaluation'};
  const READY={VALID:'Valid',INVALID:'Invalid',STRUCTURE_CHECKED:'Structure checked',BLOCKED:'Blocked',NO_EVALUATION_DATA:'No evaluation data',LEAKAGE_DETECTED:'Leakage detected',INDEPENDENT_SAMPLES_AVAILABLE:'Independent samples'};
  const PROFILE={studio_chat:'Unsloth Studio — SFT (chat)',studio_alpaca:'Unsloth Studio — SFT (Alpaca)',trl_prompt_completion:'Unsloth / TRL in Python'};

  async function details(version,host,button){
    button.disabled=true;host.replaceChildren(node('p',{},'Loading…'));
    try{
      const [health,exports]=await Promise.all([global.api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/health`),global.api(`/api/v1/unsloth-exports?version=${encodeURIComponent(version)}`)]);
      const r=health.readiness,s=health.statistics;
      host.replaceChildren(
        node('p',{},'Structural validity:',' ',READY[r.structural.status]||r.structural.status,' · ','Training compatibility:',' ',READY[r.training_compatibility.status]||r.training_compatibility.status,' · ','Evaluation readiness:',' ',READY[r.evaluation.status]||r.evaluation.status),
        node('p',{},ident(String(s.training_records)),' ','training records',' · ',ident(String(s.independent_source_conversations)),' ','independent source conversations'),
        node('h4',{},'Exports'),
        exports.items.length?node('ul',{},...exports.items.map(x=>node('li',{},PROFILE[x.profile]||x.profile,' · ',ident(x.created_at||''),' · ',ident(String(x.record_count)),' ','records',' · ',
          ...x.files.map(f=>node('a',{href:f,download:f.split('/').pop()},f.split('/').pop()+' '))))):node('p',{class:'muted'},'No export yet. Create one in Prepare data, step 3.'),
        node('p',{'data-advanced-only':''},Object.assign(node('a',{href:`/datasets/health?version=${encodeURIComponent(version)}`},'Open full diagnostics'),{onclick:e=>{e.preventDefault();global.switchView?.('dataset-health',{version});}})));
    }catch(error){host.replaceChildren(node('p',{role:'alert'},error.message));}
    finally{button.disabled=false;}
  }

  async function load(){
    const list=el('versions-list');list.replaceChildren(node('p',{},'Loading versions…'));
    try{
      const data=await global.api('/api/v1/dataset-versions');
      list.replaceChildren(...(data.items.length?data.items.map(v=>{
        const counts=v.counts||{},total=Object.values(counts).reduce((a,b)=>a+(Number(b)||0),0);
        const more=node('div',{class:'version-details'}),button=node('button',{type:'button',class:'button ghost'},'Readiness and exports');
        button.onclick=()=>details(v.version,more,button);
        return node('article',{class:'panel version-card'},
          node('h3',{},ident(v.version)),
          node('p',{class:'muted'},v.state==='Frozen'?'Frozen — cannot be changed':(v.state||'—'),' · ',ident((v.created_at||'').slice(0,19).replace('T',' ')),' · ',ident(String(total)),' ','records'),
          node('ul',{class:'version-files'},...Object.entries(counts).filter(([,n])=>n).map(([f,n])=>node('li',{},FILE_LABEL[f]||f,': ',ident(String(n))))),
          v.readable?button:node('p',{role:'alert'},v.error||'This version cannot be read.'),more);
      }):[node('p',{},'No versions yet. Create the first one in Prepare data.')]));
    }catch(error){list.replaceChildren(node('p',{role:'alert'},error.message));}
  }
  global.NajdiVersions={load};
})(typeof window!=='undefined'?window:globalThis);
