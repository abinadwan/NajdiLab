/* Chat controls own only NajdiLab sessions. The server owns consent/admission. */
(function(global){
  'use strict';
  function canSend(text,session,pending,modelReady){
    return typeof text==='string'&&!!text.trim()&&session?.status==='OPEN'&&!session.busy&&!pending&&modelReady===true;
  }
  function shouldSendOnEnter(event){
    return event.key==='Enter'&&!event.shiftKey&&!event.isComposing&&!event.composing&&event.keyCode!==229&&!event.repeat;
  }
  function validBudgets(context,reply){
    return Number.isInteger(context)&&context>=128&&context<=1048576&&Number.isInteger(reply)&&reply>=1&&reply<=Math.min(8192,context-1);
  }
  function budgetPresets(snapshot){
    const r=snapshot?.recommendation||{},ceiling=r.budget_ceiling;
    return [{id:'light',label:'Light budget',context:4096,reply:1024},{id:'balanced',label:'Balanced',context:8192,reply:2048},{id:'long',label:'Long',context:16384,reply:3072}].map(p=>{
      const estimate=r.candidates?.find(c=>c.context===p.context);
      const reason=!Number.isInteger(ceiling)||ceiling<1?'Engine ceiling unknown':p.context>ceiling?'Above engine ceiling':!estimate||!Number.isFinite(estimate.estimated_required_bytes)||estimate.estimated_required_bytes<=0?'Memory estimate unavailable':estimate.assessment!=='ESTIMATE_FITS_FREE_VRAM'?'Memory estimate does not fit':'Unverified memory estimate';
      return {...p,enabled:reason==='Unverified memory estimate',reason,estimatedBytes:estimate?.estimated_required_bytes};
    });
  }
  // Restricted presentation only: source text, escapes, entities and link targets
  // are never decoded. All output is built with text nodes, never HTML parsing.
  function inlineMarkdown(text){
    const parts=[];let offset=0;
    const escaped=index=>{let slashes=0;while(index>0&&text[--index]==='\\')slashes++;return slashes%2===1;};
    for(const match of text.matchAll(/`([^`\n]+)`|\*\*([^*\n]+)\*\*|\*([^*\n]+)\*/g)){
      const width=match[2]!==undefined?2:1;
      if(escaped(match.index)||escaped(match.index+match[0].length-width))continue;
      if(match.index>offset)parts.push({tag:null,text:text.slice(offset,match.index)});
      parts.push({tag:match[1]!==undefined?'code':match[2]!==undefined?'strong':'em',text:match[1]??match[2]??match[3]});offset=match.index+match[0].length;
    }
    if(offset<text.length)parts.push({tag:null,text:text.slice(offset)});
    return parts;
  }
  function markdownBlocks(source){
    const lines=source.split('\n'),blocks=[];let i=0;
    const special=line=>/^(?:```|#{1,6} |[-*] |\d+\. |> ?)/.test(line);
    while(i<lines.length){
      const line=lines[i];if(!line.trim()){i++;continue;}
      if(/^```/.test(line)){
        const code=[];i++;while(i<lines.length&&!/^```\s*$/.test(lines[i]))code.push(lines[i++]);
        if(i<lines.length)i++;blocks.push({tag:'pre',text:code.join('\n')});continue;
      }
      const heading=line.match(/^(#{1,6}) (.*)$/);if(heading){blocks.push({tag:'h'+heading[1].length,text:heading[2]});i++;continue;}
      const list=line.match(/^([-*] |\d+\. )(.*)$/);if(list){
        const ordered=/^\d/.test(list[1]),items=[],pattern=ordered?/^\d+\. (.*)$/:/^[-*] (.*)$/;let item;
        while(i<lines.length&&(item=lines[i].match(pattern))){items.push(item[1]);i++;}
        blocks.push({tag:ordered?'ol':'ul',items});continue;
      }
      if(/^> ?/.test(line)){const quote=[];while(i<lines.length&&/^> ?/.test(lines[i]))quote.push(lines[i++].replace(/^> ?/,''));blocks.push({tag:'blockquote',text:quote.join('\n')});continue;}
      const paragraph=[line];i++;while(i<lines.length&&lines[i].trim()&&!special(lines[i]))paragraph.push(lines[i++]);
      blocks.push({tag:'p',text:paragraph.join('\n')});
    }
    return blocks;
  }
  class ChatController {
    constructor(api,render,uuid=()=>global.crypto.randomUUID()){
      this.api=api;this.render=render;this.uuid=uuid;this.session=null;this.pending=false;this.selectionRevision=null;this.modelReady=true;
    }
    post(path,data){return this.api(path,{method:'POST',body:JSON.stringify(data)});}
    path(action=''){return `/api/v1/chat/sessions/${this.session.id}${action?'/'+action:''}`;}
    async refresh(){if(this.session)this.session=await this.api(this.path());this.render();}
    async send(text){
      if(!canSend(text,this.session,this.pending,this.modelReady))throw Error('Refresh or stop the current turn first.');
      const path=this.path('send'),sid=this.session.id;
      const data={request_id:this.uuid(),revision:this.session.revision,selection_revision:this.selectionRevision,text};
      this.pending=true;this.render();
      try{
        const result=await this.post(path,data);
        this.session=result.new_session||result.session;
        return result;
      }catch(error){
        try{this.session=await this.api(`/api/v1/chat/sessions/${sid}`);}catch{}
        throw error;
      }finally{this.pending=false;this.render();}
    }
    async stop(){return this.post(this.path('stop'),{});}
    async collect(enabled){
      // Refresh to obtain the server's in-flight reservation revision. This
      // toggle is always a new explicit choice, never a replayed preference.
      await this.refresh();
      this.session=await this.post(this.path('collect'),{enabled,revision:this.session.revision});this.render();
    }
  }
  /* Each evidence tier stays on its own line: an estimate must never read as a measurement. */
  function hardwareReport(data){
    const gib=n=>typeof n==='number'?`${(n/1024**3).toFixed(1)} GiB`:'Unknown';
    const r=data.recommendation||{},m=data.model,lines=[`Available RAM: ${gib(data.ram_available_bytes)} / ${gib(data.ram_total_bytes)}`];
    lines.push(...(data.gpus||[]).map(g=>`${g.name}: ${gib(g.free_bytes)} free / ${gib(g.total_bytes)}`));
    if(!data.gpus?.length)lines.push('GPU memory unavailable');
    if(typeof data.gpu_compute_processes==='number')lines.push(`Other GPU compute processes now: ${data.gpu_compute_processes}`);
    if(m){
      lines.push(`Model: ${m.architecture||'Unknown'} · ${m.quantization||'Unknown quantization'} · weights ${gib(m.weights_bytes)}`);
      if(m.other_loaded_models?.length)lines.push(`Also loaded in this runtime: ${m.other_loaded_models.join(', ')}`);
      if(m.model_system_prompt)lines.push('This model defines its own system prompt. That is part of the model, not added by NajdiLab.');
    }
    lines.push(`Model maximum context: ${r.model_max_context??'Unknown'}`,`Runtime context now: ${r.runtime_context??'Not loaded'}`);
    lines.push(`Proven engine ceiling: ${Number.isInteger(r.budget_ceiling)&&r.budget_ceiling>0?r.budget_ceiling:'Unknown'}`);
    const seen=r.measured;
    if(typeof seen?.size_bytes==='number')lines.push(`Measured now at ${seen.context}: ${gib(seen.size_bytes)} loaded, ${gib(seen.size_vram_bytes)} on GPU`);
    for(const c of r.candidates||[])lines.push(`Estimate ${c.context}: ${{ABOVE_MODEL_MAX:'above model maximum',ESTIMATE_FITS_FREE_VRAM:`may fit (~${gib(c.estimated_required_bytes)})`,ESTIMATE_EXCEEDS_FREE_VRAM:`likely exceeds free VRAM (~${gib(c.estimated_required_bytes)})`}[c.assessment]}`);
    lines.push(r.recommended_context?`Suggested starting context: ${r.recommended_context}. ${r.label}`:`No reliable recommendation. ${r.reason||''}`);
    if(r.recommended_context)lines.push(r.reason);
    lines.push('No stress test was run.');
    return lines.join('\n');
  }
  // Clear only the exact draft submitted to this request. A user may continue
  // typing during inference; a later completion must never erase that newer draft.
  function shouldClearDraft(submitted,current,status){
    return status==='COMPLETED' && current===submitted;
  }
  if(typeof module!=='undefined'&&module.exports){module.exports={ChatController,hardwareReport,shouldClearDraft,budgetPresets,validBudgets,canSend,shouldSendOnEnter,markdownBlocks,inlineMarkdown};return;}
  const el=id=>document.getElementById(id);
  let integrations=[],bound=false,notice='',hardwareEvidence=null,composing=false;
  const controller=new ChatController((...args)=>api(...args),render);
  // literal=true marks identifiers (model, provider, session) that the localizer must not translate.
  function option(select,value,label,literal=false){const item=new Option(label,value);if(literal)item.setAttribute('translate','no');select.add(item);}
  const i18n=text=>window.NajdiI18n?window.NajdiI18n.t(text):text;
  function compose(target,parts){target.replaceChildren(...parts.map(part=>{if(typeof part==='string')return document.createTextNode(part);const id=document.createElement('bdi');id.dir='ltr';id.textContent=part.id;return id;}));}
  const sessionStatus={OPEN:'Open',CONTEXT_LIMIT:'Context limit reached',ARCHIVED:'Archived'};
  function provider(){return integrations.find(x=>x.id===el('chat-provider').value);}
  function evidenceKey(){const p=provider();return JSON.stringify([p?.id,el('chat-model').value,p?.selection_revision]);}
  function currentEvidence(){return hardwareEvidence?.key===evidenceKey()?hardwareEvidence.data:undefined;}
  function renderBudgets(){
    const selected=el('chat-preset').value||'manual';el('chat-preset').replaceChildren();option(el('chat-preset'),'manual','Advanced / manual');
    for(const p of budgetPresets(currentEvidence())){
      option(el('chat-preset'),p.id,`${i18n(p.label)} · ${p.context} / ${p.reply} · ${i18n(p.reason)}`);
      el('chat-preset').lastElementChild.disabled=!p.enabled;
    }
    el('chat-preset').value=selected==='manual'||budgetPresets(currentEvidence()).some(p=>p.id===selected&&p.enabled)?selected:'manual';
    const r=currentEvidence()?.recommendation;
    el('chat-budget-evidence').textContent=r?`Proven engine ceiling: ${Number.isInteger(r.budget_ceiling)&&r.budget_ceiling>0?r.budget_ceiling:'Unknown'}`:'Read device specs to check presets. The engine ceiling and memory estimate are unknown until then.';
    el('chat-hardware-result').textContent=currentEvidence()?hardwareReport(currentEvidence()):'';
  }
  function models(){const p=provider();el('chat-model').replaceChildren();for(const model of p?.models||[])option(el('chat-model'),model,model,true);if(p?.selected_model)el('chat-model').value=p.selected_model;el('chat-load-row').hidden=p?.id!=='ollama';el('chat-load-approved').checked=false;renderBudgets();}
  /* A select bumps the revision, so reuse a current one: it would otherwise stale the open conversation. */
  async function select(p,model){
    if(p.selected_model===model)return p.selection_revision;
    const snap=await api(`/api/v1/integrations/${p.id}/select`,{method:'POST',body:JSON.stringify({approved:true,model})});
    Object.assign(p,snap.items.find(x=>x.id===p.id));
    if(controller.session?.provider===p.id)controller.selectionRevision=p.selection_revision;
    return p.selection_revision;
  }
  function message(role,content,reviewStatus=''){
    const article=document.createElement('article'),label=document.createElement('strong'),text=document.createElement('p');
    article.className='chat-message';label.textContent=role;text.dir='auto';text.textContent=content;
    article.append(label,text);
    if(role==='Model'){
      const rich=document.createElement('div'),toggle=document.createElement('button');rich.className='chat-markdown';rich.dir='auto';rich.setAttribute('translate','no');
      const inline=(target,value)=>{for(const part of inlineMarkdown(value)){if(!part.tag)target.append(document.createTextNode(part.text));else{const node=document.createElement(part.tag);node.textContent=part.text;target.append(node);}}};
      for(const block of markdownBlocks(content)){
        const node=document.createElement(block.tag);
        if(block.items){for(const item of block.items){const li=document.createElement('li');inline(li,item);node.append(li);}}
        else if(block.tag==='pre'){const code=document.createElement('code');code.textContent=block.text;node.append(code);}
        else inline(node,block.text);
        rich.append(node);
      }
      text.hidden=true;toggle.type='button';toggle.className='button ghost chat-raw-toggle';toggle.textContent='Show raw text';
      toggle.onclick=()=>{text.hidden=!text.hidden;rich.hidden=!rich.hidden;toggle.textContent=text.hidden?'Show raw text':'Show Markdown';};article.append(rich,toggle);
    }
    if(reviewStatus){
      const state=document.createElement('small');state.className='chat-review-status';
      state.textContent=reviewStatus;article.append(state);
    }
    el('chat-messages').append(article);
  }
  function render(){
    const s=controller.session,busy=controller.pending||s?.busy,open=s?.status==='OPEN';
    const sessionRuntime=s && integrations.find(p=>p.id===s.provider);
    const sessionModelReady=!!sessionRuntime&&sessionRuntime.selected_model===s?.model;
    controller.modelReady=sessionModelReady;
    el('chat-new').disabled=!!busy||!provider();el('chat-saved').disabled=!!busy;el('chat-hardware').disabled=!!busy;
    el('chat-provider').disabled=!!busy;el('chat-model').disabled=!!busy;
    el('chat-send').disabled=!canSend(el('chat-draft').value,s,controller.pending,sessionModelReady);el('chat-stop').disabled=!busy;
    el('chat-preset').disabled=!!busy;el('chat-budget').disabled=!!busy;el('chat-reserve').disabled=!!busy;
    el('chat-collect').disabled=!open;el('chat-collect').checked=!!s?.collect;
    el('chat-archive').disabled=!s||s.status==='ARCHIVED';
    el('chat-messages').replaceChildren();
    for(const t of s?.turns||[]){
      message('You',t.user);
      message('Model',t.assistant,t.collected ? 'Collected for human review (not training-approved)' : 'Not collected for review');
    }
    const last=s?.turns?.at(-1);
    // UX-09: never imply the "new conversation" selectors will change a saved
    // session's immutable provider, model or context. Show the actual binding.
    if(s){
      // UX-21: identifiers are isolated left-to-right; the surrounding text stays translatable.
      compose(el('chat-session-identity'),['Current conversation: ',{id:s.id},' · ',s.status,' · ',{id:s.provider},' / ',{id:s.model},
        ` · Context ${s.context_budget}, reserved reply ${s.reply_reserve} tokens.`]);
      compose(el('chat-usage'),[{id:s.provider},' / ',{id:s.model},
        ` · Budget ${s.context_budget} · Reply reserve ${s.reply_reserve}${last?` · Last turn: ${last.input_tokens} input + ${last.output_tokens} output tokens (${last.input_tokens+last.output_tokens} of ${s.context_budget})`:''}`]);
    }else{
      el('chat-session-identity').textContent='No active conversation selected. Choose a provider/model above for a new conversation.';
      el('chat-usage').textContent='';
    }
    el('chat-notice').textContent=notice||(busy?'Waiting for the model. Stop discards this turn.'
      : open&&!sessionModelReady?'This saved conversation is pinned to its original model. Connect and select that exact model in Settings to continue; no model was changed automatically.'
      : s?'Ready. Complete history is sent unchanged.':'Connect a runtime in Settings, then create a conversation.');
  }
  // UX-20: saved sessions are paged; the count line states how many are loaded out of how many exist.
  let savedLoaded=0;
  async function saved(more=false){
    const offset=more?savedLoaded:0;
    const data=await api(`/api/v1/chat/sessions?limit=100&offset=${offset}`);
    if(!more){el('chat-saved').replaceChildren();option(el('chat-saved'),'','Choose a saved conversation');}
    const when=value=>window.NajdiI18n?window.NajdiI18n.date(value):value;
    for(const s of data.items)option(el('chat-saved'),s.id,`${s.model} · ${when(s.created_at)} · ${i18n(sessionStatus[s.status]||s.status)}`,true);
    savedLoaded=offset+data.items.length;
    el('chat-saved-count').textContent=data.page.total?`${savedLoaded} of ${data.page.total} saved conversations loaded`:'No saved conversations';
    el('chat-saved-more').hidden=!data.page.has_more;
    if(controller.session)el('chat-saved').value=controller.session.id;
  }
  async function load(){
    if(!bound)bind();
    integrations=(await api('/api/v1/integrations')).items.filter(x=>x.kind==='model_runtime'&&x.connection==='CONNECTED');
    const previous=el('chat-provider').value;el('chat-provider').replaceChildren();for(const p of integrations)option(el('chat-provider'),p.id,p.name,true);
    if(integrations.some(p=>p.id===previous))el('chat-provider').value=previous;models();
    if(controller.session){const p=integrations.find(x=>x.id===controller.session.provider);controller.selectionRevision=p?.selection_revision;await controller.refresh();}
    await saved();render();
  }
  function act(fn){return async event=>{try{await fn(event);}catch(error){notice=error.message;render();}};}
  function bind(){
    bound=true;
    el('chat-provider').onchange=models;
    el('chat-model').onchange=()=>{el('chat-load-approved').checked=false;renderBudgets();};
    el('chat-preset').onchange=()=>{
      const preset=budgetPresets(currentEvidence()).find(p=>p.id===el('chat-preset').value&&p.enabled);if(!preset)return;
      el('chat-budget').value=preset.context;el('chat-reserve').value=preset.reply;el('chat-load-approved').checked=false;
    };
    for(const id of ['chat-budget','chat-reserve'])el(id).oninput=()=>{el('chat-preset').value='manual';el('chat-load-approved').checked=false;};
    el('chat-new').onclick=act(async()=>{
      const p=provider(),model=el('chat-model').value;if(!p||!model)throw Error('Connect and select a model in Settings first.');
      if(!validBudgets(Number(el('chat-budget').value),Number(el('chat-reserve').value)))throw Error('Context must be an integer from 128 to 1048576; reply must be an integer from 1 to 8192 and smaller than context.');
      controller.selectionRevision=await select(p,model);
      controller.session=await controller.post('/api/v1/chat/sessions',{provider:p.id,model,selection_revision:controller.selectionRevision,context_budget:Number(el('chat-budget').value),reply_reserve:Number(el('chat-reserve').value),load_approved:p.id==='ollama'&&el('chat-load-approved').checked});
      notice='';el('chat-load-approved').checked=false;await saved();render();
    });
    el('chat-saved').onchange=act(async()=>{const id=el('chat-saved').value;if(!id)return;controller.session=await api(`/api/v1/chat/sessions/${id}`);controller.selectionRevision=integrations.find(x=>x.id===controller.session.provider)?.selection_revision;notice='';render();});
    el('chat-refresh').onclick=act(async()=>{notice='';await load();});
    el('chat-saved-more').onclick=act(async()=>{await saved(true);});
    window.addEventListener('najdilab:languagechange',()=>{renderBudgets();saved().catch(()=>{});});
    el('chat-draft').oninput=()=>{el('chat-send').disabled=!canSend(el('chat-draft').value,controller.session,controller.pending,controller.modelReady);};
    el('chat-draft').addEventListener('compositionstart',()=>{composing=true;});
    el('chat-draft').addEventListener('compositionend',()=>{composing=false;});
    el('chat-draft').addEventListener('keydown',event=>{
      if(event.key!=='Enter'||event.shiftKey||event.isComposing||composing||event.keyCode===229)return;
      event.preventDefault();
      if(shouldSendOnEnter(event)&&canSend(el('chat-draft').value,controller.session,controller.pending,controller.modelReady))el('chat-form').requestSubmit();
    });
    el('chat-form').onsubmit=act(async event=>{
      event.preventDefault();
      const submitted=el('chat-draft').value;
      if(composing||!canSend(submitted,controller.session,controller.pending,controller.modelReady))return;
      notice='';
      const result=await controller.send(submitted);
      if(result.status==='CONTEXT_LIMIT')notice=`Context limit reached: ${result.input_tokens} prompt tokens + ${result.reply_reserve} reserved for the reply exceed the ${result.context_budget} budget. The conversation was saved and a new empty conversation opened. Your unsent draft remains below; it was not sent or copied automatically.`;
      else if(shouldClearDraft(submitted,el('chat-draft').value,result.status))el('chat-draft').value='';
      await saved();render();
    });
    el('chat-stop').onclick=act(async()=>{await controller.stop();notice='Stop requested. No partial response will be saved. Engine cancellation is best effort; its service stays running.';render();});
    el('chat-collect').onchange=act(async()=>{await controller.collect(el('chat-collect').checked);notice='Collection choice saved for this server process. Only future completed pairs can enter PENDING review.';render();});
    el('chat-archive').onclick=act(async()=>{
      if(!confirm(window.NajdiI18n?window.NajdiI18n.t('Archive this conversation and exclude its collected pairs from future dataset selection? Local text and previous exports are retained.'):'Archive this conversation and exclude its collected pairs from future dataset selection? Local text and previous exports are retained.'))return;
      await controller.refresh();controller.session=await controller.post(controller.path('archive'),{revision:controller.session.revision});notice='Conversation archived. Data and earlier exports are retained.';await saved();render();
    });
    el('chat-hardware').onclick=act(async()=>{
      const p=provider(),model=el('chat-model').value,body={approved:true};
      // Reading evidence must never select or load a model, even if a different
      // model is currently highlighted in the new-conversation controls.
      const key=evidenceKey();
      if(p&&model)Object.assign(body,{provider:p.id,model,selection_revision:p.selection_revision});
      const data=await controller.post('/api/v1/chat/hardware',body);
      hardwareEvidence={key,data};renderBudgets();
    });
  }
  global.NajdiChat={load};
  document.addEventListener('DOMContentLoaded',()=>{
    el('unsloth-create').onclick=async()=>{
      const button=el('unsloth-create'),host=el('unsloth-result');button.disabled=true;host.replaceChildren();
      try{
        const data=await api('/api/v1/unsloth-exports',{method:'POST',body:JSON.stringify({version:el('unsloth-version').value.trim()})});
        host.textContent=`${data.record_count} conversational targets. `;
        for(const name of ['dataset.jsonl','provenance.jsonl','manifest.json']){
          const link=document.createElement('a');link.textContent=`Download ${name} `;link.href=`/api/v1/unsloth-exports/${data.id}/${name}`;link.download=name;host.append(link);
        }
      }catch(error){host.textContent=error.message;}finally{button.disabled=false;}
    };
  });
})(typeof window!=='undefined'?window:globalThis);
