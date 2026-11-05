/* Model library → Customization models: Safetensors checkpoints for fine-tuning in external tools.
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
    const status={READY:'Verified',CHANGED:'Files changed or incomplete',READ_ONLY:'Read only',PARTIAL:'Interrupted download'}[item.status]||item.status;
    const title=item.repo_id?[node('strong',{},ident(item.repo_id)),node('small',{},' · ',ident((item.revision||'').slice(0,12)))]:[node('strong',{},'Interrupted download')];
    const box=node('div',{class:'models-library-item'},node('div',{},...title),
      node('p',{},status,' · ',ident(size(item.total_bytes)),' · ',item.complete?'Complete checkpoint':['Incomplete: ',ident((item.missing||[]).join(', '))]),
      ...(item.notes||[]).map(n=>node('p',{class:'muted'},n.message)),
      node('p',{class:'muted'},ident(item.path)));
    if(item.source==='najdilab'){const del=node('button',{type:'button',class:'button ghost'},'Delete…');del.onclick=()=>openDelete(item,box);box.append(del);}
    return box;
  }

  // Delete: show what is removed and the space freed, then require the exact name. Only NajdiLab's own folders.
  async function openDelete(item,box){
    box.querySelector('.delete-panel')?.remove();
    const panel=node('div',{class:'delete-panel',role:'group','aria-label':'Delete this customization model'},node('p',{},'Checking what will be removed…'));box.append(panel);
    try{
      const plan=await global.api(`/api/v1/checkpoints/delete-plan?id=${encodeURIComponent(item.id)}`);
      const input=node('input',{dir:'ltr',autocomplete:'off',spellcheck:'false','aria-label':'Type the name to confirm'});
      const go=node('button',{type:'button',class:'button delete-action',disabled:true},'Delete permanently');
      const cancel=node('button',{type:'button',class:'button ghost'},'Cancel');
      const message=node('p',{role:'alert',class:'chatv2-error'});
      input.oninput=()=>{go.disabled=!!plan.blocked||input.value!==plan.confirm_text;};
      cancel.onclick=()=>panel.remove();
      go.onclick=async()=>{go.disabled=true;try{await global.api('/api/v1/checkpoints/delete',{method:'POST',body:JSON.stringify({approved:true,confirm:input.value,id:item.id})});refresh();}
        catch(error){message.textContent=error.message;go.disabled=false;}};
      panel.replaceChildren(node('p',{},plan.action==='delete_checkpoint'?'Deletes this checkpoint folder and every file in it.':'Removes the files of this interrupted download.'),
        node('p',{},ident(String(plan.files.length)),' ','files',' · ','Space freed:',' ',node('strong',{},ident(size(plan.frees_bytes)))),
        plan.blocked?node('p',{class:'chatv2-warning'},'This model is still downloading. Cancel the download first.'):null,
        node('label',{},'Type to confirm:',' ',ident(plan.confirm_text)),input,node('div',{class:'confirmation-actions'},cancel,go),message);
      input.focus();
    }catch(error){panel.replaceChildren(node('p',{role:'alert'},error.message));}
  }

  async function refresh(){
    clearTimeout(timer);
    try{
      const data=await global.api('/api/v1/checkpoints');
      el('training-models-list').replaceChildren(...(data.models.length?data.models.map(row):[node('p',{},'No customization models downloaded by NajdiLab yet.')]));
      el('training-models-cache').replaceChildren(...(data.cache.length?data.cache.map(row):[node('p',{},'No checkpoints found in the Hugging Face cache.')]));
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
