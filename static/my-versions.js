/* Data → My versions: frozen Gold versions, what is in them, how ready they are, and their exports.
   Frozen content is never edited here. Deletion requires a server-verified preview and explicit confirmation. */
(function(global){
  'use strict';
  const el=id=>document.getElementById(id);
  function node(tag,attrs={},...children){const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs||{})){if(v==null||v===false)continue;if(k==='class')n.className=v;else n.setAttribute(k,v===true?'':v);}
    for(const c of children.flat())if(c!=null&&c!==false)n.append(c instanceof Node?c:document.createTextNode(String(c)));return n;}
  const ident=text=>node('bdi',{dir:'ltr',translate:'no','data-i18n-skip':''},text);
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
          ...x.files.map(f=>node('a',{href:f,download:f.split('/').pop(),translate:'no','data-i18n-skip':''},f.split('/').pop()+' '))))):node('p',{class:'muted'},'No export yet. Choose Export to create one in step 4.'),
        node('p',{'data-advanced-only':''},Object.assign(node('a',{href:`/datasets/health?version=${encodeURIComponent(version)}`},'Open full diagnostics'),{onclick:e=>{e.preventDefault();global.switchView?.('dataset-health',{version});}})));
    }catch(error){host.replaceChildren(node('p',{role:'alert'},error.message));}
    finally{button.disabled=false;}
  }

  function fileList(files){
    return node('ul',{class:'hash-list'},...files.map(file=>node('li',{},
      ident(file.name),' · ',ident(String(file.bytes)),' ','bytes',
      node('div',{},node('code',{dir:'ltr',translate:'no','data-i18n-skip':''},file.sha256))
    )));
  }

  async function viewVersion(version,host,button){
    if(host.childNodes.length&&!host.hidden){
      host.hidden=true;
      button.setAttribute('aria-expanded','false');
      return;
    }
    host.hidden=false;
    button.setAttribute('aria-expanded','true');
    button.disabled=true;
    host.replaceChildren(node('p',{},'Loading…'));
    try{
      const data=await global.api(`/api/v1/dataset-versions/${encodeURIComponent(version)}`);
      host.replaceChildren(
        node('h4',{},'Files & SHA-256'),fileList(data.files||[]),
        node('details',{},node('summary',{},'Manifest JSON'),
          node('pre',{dir:'ltr',translate:'no','data-i18n-skip':''},JSON.stringify(data.manifest,null,2))),
        node('p',{'data-advanced-only':''},Object.assign(node('a',{href:`/datasets/versions?version=${encodeURIComponent(version)}`},'Open full version details'),{
          onclick:event=>{event.preventDefault();global.switchView?.('dataset-versions',{version});}
        }))
      );
    }catch(error){host.replaceChildren(node('p',{role:'alert'},error.message));}
    finally{button.disabled=false;}
  }

  let activeDelete=null;
  function deleteVersion(version,opener){
    if(activeDelete){activeDelete.focus();return;}
    const title=node('h2',{id:'gold-delete-title'},'Delete version permanently');
    const summary=node('p',{id:'gold-delete-description'},'Version selected for permanent deletion',' ',ident(version));
    const targets=node('div',{id:'gold-delete-files'});
    const blockers=node('div',{id:'gold-delete-blockers'});
    const status=node('p',{id:'gold-delete-status',role:'status','aria-live':'polite'});
    const input=node('input',{id:'gold-delete-confirm',dir:'ltr',autocomplete:'off',spellcheck:'false',translate:'no','data-i18n-skip':'','aria-describedby':'gold-delete-description',disabled:true});
    const cancel=node('button',{id:'gold-delete-cancel',type:'button',class:'button ghost'},'Cancel');
    const submit=node('button',{id:'gold-delete-submit',type:'button',class:'button delete-action',disabled:true},'Delete permanently');
    const retry=node('button',{id:'gold-delete-retry',type:'button',class:'button ghost',hidden:true},'Refresh deletion preview');
    const dialog=node('dialog',{id:'gold-delete-dialog',class:'chatv2-dialog','aria-labelledby':'gold-delete-title','aria-describedby':'gold-delete-description'},
      node('div',{class:'chatv2-dialog-body'},node('div',{class:'dialog-head'},title),summary,
        node('h3',{},'Files selected for deletion'),targets,blockers,
        node('label',{for:'gold-delete-confirm'},'Type the version name to confirm'),input,status,
        node('div',{class:'confirmation-actions'},cancel,retry,submit)));
    let preview=null,pending=false;
    const updateSubmit=()=>{submit.disabled=pending||!preview||input.value!==version;};
    const close=()=>{if(!pending)dialog.close();};
    input.oninput=updateSubmit;
    cancel.onclick=close;
    dialog.oncancel=event=>{if(pending)event.preventDefault();};
    dialog.onclose=()=>{
      activeDelete=null;
      dialog.remove();
      if(opener.isConnected)opener.focus();
    };
    async function refreshPreview(){
      preview=null;
      input.value='';
      input.disabled=true;
      retry.hidden=true;
      submit.disabled=true;
      targets.replaceChildren();
      blockers.replaceChildren();
      status.textContent='Checking deletion safety…';
      status.setAttribute('role','status');
      try{
        const data=await global.api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/delete-preview`);
        if(!dialog.open)return;
        const files=Array.isArray(data.files)?data.files:[];
        targets.replaceChildren(files.length?fileList(files):node('p',{},'No files selected.'));
        const reasons=Array.isArray(data.blockers)?data.blockers:[];
        if(reasons.length)blockers.replaceChildren(node('h3',{},'Deletion is blocked'),node('ul',{},...reasons.map(reason=>node('li',{},reason))));
        const completeFiles=(files.length||data.recovery===true)&&files.every(file=>typeof file.name==='string'&&file.name&&Number.isFinite(file.bytes)&&file.bytes>=0&&/^[a-f0-9]{64}$/i.test(file.sha256));
        if(data.version!==version||data.allowed!==true||reasons.length||!completeFiles||typeof data.token!=='string'||!data.token){
          status.textContent='This version cannot be safely deleted.';
          return;
        }
        preview=data;
        input.disabled=false;
        status.textContent='Review the files, then type the exact version name.';
        input.focus();
      }catch(error){
        if(!dialog.open)return;
        status.setAttribute('role','alert');
        status.textContent=error.message;
        retry.hidden=false;
      }
    }
    retry.onclick=refreshPreview;
    submit.onclick=async()=>{
      if(pending||!preview||input.value!==version)return;
      pending=true;
      updateSubmit();
      input.disabled=true;
      cancel.disabled=true;
      status.setAttribute('role','status');
      status.textContent='Deleting version…';
      try{
        await global.api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/delete`,{
          method:'POST',body:JSON.stringify({token:preview.token,confirm_version:version})
        });
      }catch(error){
        pending=false;
        preview=null;
        input.value='';
        cancel.disabled=false;
        status.setAttribute('role','alert');
        status.textContent=error.message;
        retry.hidden=false;
        return;
      }
      pending=false;
      dialog.close();
      await load();
      el('versions-list')?.prepend(node('p',{role:'status'},'Version deleted.'));
      global.dispatchEvent(new global.CustomEvent('najdilab:versionschange',{detail:{version,deleted:true}}));
    };
    activeDelete=dialog;
    document.body.append(dialog);
    dialog.showModal();
    cancel.focus();
    refreshPreview();
  }

  async function load(){
    const list=el('versions-list');list.replaceChildren(node('p',{},'Loading versions…'));
    try{
      const data=await global.api('/api/v1/dataset-versions');
      list.replaceChildren(...(data.items.length?data.items.map(v=>{
        const counts=v.counts||{},total=Object.values(counts).reduce((a,b)=>a+(Number(b)||0),0);
        const more=node('div',{class:'version-details'}),button=node('button',{type:'button',class:'button ghost'},'Readiness and exports');
        const versionDetails=node('div',{class:'version-details',hidden:true});
        const view=node('button',{type:'button',class:'button ghost version-view','data-version':v.version,'aria-expanded':'false'},'View version');
        const exportButton=node('button',{type:'button',class:'button ghost version-export','data-version':v.version},'Export');
        const deleteButton=node('button',{type:'button',class:'button ghost version-delete','data-version':v.version,'aria-haspopup':'dialog'},'Delete version');
        button.onclick=()=>details(v.version,more,button);
        view.onclick=()=>viewVersion(v.version,versionDetails,view);
        exportButton.onclick=async()=>{
          exportButton.disabled=true;
          try{
            if(!global.NajdiPrepare?.openVersion)throw new Error('Export is unavailable. Reload and try again.');
            await global.NajdiPrepare.openVersion(v.version);
          }catch(error){more.replaceChildren(node('p',{role:'alert'},error.message));}
          finally{exportButton.disabled=false;}
        };
        if(v.deletion_pending)deleteButton.textContent='Resume deletion';
        deleteButton.onclick=()=>deleteVersion(v.version,deleteButton);
        return node('article',{class:'panel version-card'},
          node('h3',{},ident(v.version)),
          node('p',{class:'muted'},v.state==='Frozen'?'Frozen — cannot be changed':(v.state||'—'),' · ',ident((v.created_at||'').slice(0,19).replace('T',' ')),' · ',ident(String(total)),' ','records'),
          node('ul',{class:'version-files'},...Object.entries(counts).filter(([,n])=>n).map(([f,n])=>node('li',{},FILE_LABEL[f]||ident(f),': ',ident(String(n))))),
          node('div',{class:'workflow-actions'},...(v.readable?[view,button,exportButton]:[]),deleteButton),
          v.readable?null:node('p',{role:'alert'},v.error?.message||v.error||'This version cannot be read.'),versionDetails,more);
      }):[node('p',{},'No versions yet. Create the first one in Prepare data.')]));
    }catch(error){list.replaceChildren(node('p',{role:'alert'},error.message));}
  }
  global.NajdiVersions={load};
})(typeof window!=='undefined'?window:globalThis);
