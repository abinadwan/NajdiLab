/* Model library → Training models (V2.2.0): Safetensors checkpoints for external fine-tuning.
   Inference models (GGUF, NajdiLab Native) and training models (config + tokenizer + Safetensors, used by
   Unsloth/TRL outside NajdiLab) are different files. Nothing downloads without approval and a license check. */
(function(global){
  'use strict';
  const el=id=>document.getElementById(id);
  function node(tag,attrs={},...children){const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs||{})){if(v==null||v===false)continue;if(k==='class')n.className=v;else n.setAttribute(k,v===true?'':v);}
    for(const c of children.flat())if(c!=null&&c!==false)n.append(c instanceof Node?c:document.createTextNode(String(c)));return n;}
  const ident=text=>node('bdi',{dir:'ltr',translate:'no'},text);
  const size=bytes=>typeof bytes==='number'?(bytes>=1024**3?`${(bytes/1024**3).toFixed(2)} GiB`:`${(bytes/1024**2).toFixed(1)} MiB`):'—';
  let review=null,timer=null;

  function row(item){
    const status={READY:'Verified',CHANGED:'Files changed since download',READ_ONLY:'In the Hugging Face cache (read only)'}[item.status]||item.status;
    return node('div',{class:'models-library-item'},
      node('div',{},node('strong',{},ident(item.repo_id)),node('small',{},' · ',ident(item.revision.slice(0,12)))),
      node('p',{},status,' · ',ident(size(item.total_bytes)),' · ',item.complete?'Complete checkpoint':['Incomplete: ',ident(item.missing.join(', '))]),
      ...(item.notes||[]).map(n=>node('p',{class:'muted'},n.message)),
      node('p',{class:'muted'},ident(item.path)));
  }

  async function refresh(){
    clearTimeout(timer);
    try{
      const data=await global.api('/api/v1/checkpoints');
      const list=el('training-models-list');
      const all=[...data.models,...data.cache];
      list.replaceChildren(...(all.length?all.map(row):[node('p',{},'No training checkpoints yet.')]));
      renderJob(data.job);
      if(data.job&&data.job.state==='DOWNLOADING')timer=setTimeout(refresh,1000);
    }catch(error){el('training-models-list').replaceChildren(node('p',{role:'alert'},error.message));}
  }

  function renderJob(job){
    const host=el('training-models-job');
    if(!job){host.replaceChildren();return;}
    const label={DOWNLOADING:'Downloading',READY:'Downloaded and verified',ERROR:'Download stopped',CANCELLED:'Cancelled'}[job.state]||job.state;
    host.replaceChildren(node('p',{},label,': ',ident(job.repo_id),' · ',ident(`${size(job.done_bytes)} / ${size(job.total_bytes)}`)),
      job.error?node('p',{role:'alert'},job.error.message):null,
      job.state==='DOWNLOADING'?node('progress',{max:String(job.total_bytes||1),value:String(job.done_bytes||0),'aria-label':'Download progress'}):null,
      job.state==='DOWNLOADING'?Object.assign(node('button',{type:'button',class:'button ghost'},'Cancel'),{onclick:cancel}):null);
  }

  async function inspect(event){
    event.preventDefault();
    const repo=el('training-models-repo').value.trim(),host=el('training-models-review');
    el('training-models-download').disabled=true;el('training-models-ack').checked=false;review=null;
    host.replaceChildren(node('p',{},'Checking the repository…'));
    try{
      review=await global.api(`/api/v1/checkpoints/inspect?repo=${encodeURIComponent(repo)}`);
      host.replaceChildren(
        node('p',{},node('strong',{},ident(review.repo_id)),' · ','revision',' ',ident(review.revision.slice(0,12))),
        node('p',{},'License',': ',ident(review.license||'not stated'),' · ','Download size',': ',ident(size(review.total_bytes))),
        node('ul',{class:'unsloth-result-list'},...review.files.map(f=>node('li',{},ident(f.name),' · ',ident(size(f.size_bytes))))),
        ...review.notes.map(n=>node('p',{class:'muted'},n.message)),
        review.downloadable?(review.already_present?node('p',{},'This revision is already downloaded.'):null):node('p',{role:'alert'},review.blocked_reason));
      el('training-models-confirm').hidden=!review.downloadable||review.already_present;
    }catch(error){host.replaceChildren(node('p',{role:'alert'},error.message));el('training-models-confirm').hidden=true;}
  }

  async function download(){
    if(!review)return;
    el('training-models-download').disabled=true;
    try{
      await global.api('/api/v1/checkpoints/downloads',{method:'POST',body:JSON.stringify({approved:true,license_acknowledged:true,repo_id:review.repo_id,revision:review.revision})});
      el('training-models-confirm').hidden=true;refresh();
    }catch(error){el('training-models-review').append(node('p',{role:'alert'},error.message));}
  }
  async function cancel(){try{await global.api('/api/v1/checkpoints/downloads/cancel',{method:'POST',body:'{}'});}catch{}refresh();}

  let bound=false;
  function bind(){
    if(bound)return;bound=true;
    el('training-models-form').onsubmit=inspect;
    el('training-models-ack').onchange=()=>{el('training-models-download').disabled=!el('training-models-ack').checked;};
    el('training-models-download').onclick=download;
  }
  global.NajdiTraining={refresh(){bind();refresh();}};
})(typeof window!=='undefined'?window:globalThis);
