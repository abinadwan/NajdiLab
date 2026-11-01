/* Chat controls own only NajdiLab sessions. The server owns consent/admission. */
(function(global){
  'use strict';
  class ChatController {
    constructor(api,render,uuid=()=>global.crypto.randomUUID()){
      this.api=api;this.render=render;this.uuid=uuid;this.session=null;this.pending=false;this.selectionRevision=null;
    }
    post(path,data){return this.api(path,{method:'POST',body:JSON.stringify(data)});}
    path(action=''){return `/api/v1/chat/sessions/${this.session.id}${action?'/'+action:''}`;}
    async refresh(){if(this.session)this.session=await this.api(this.path());this.render();}
    async send(text){
      if(!this.session||this.pending||this.session.busy)throw Error('Refresh or stop the current turn first.');
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
    const seen=r.measured;
    if(typeof seen?.size_bytes==='number')lines.push(`Measured now at ${seen.context}: ${gib(seen.size_bytes)} loaded, ${gib(seen.size_vram_bytes)} on GPU`);
    for(const c of r.candidates||[])lines.push(`Estimate ${c.context}: ${{ABOVE_MODEL_MAX:'above model maximum',ESTIMATE_FITS_FREE_VRAM:`may fit (~${gib(c.estimated_required_bytes)})`,ESTIMATE_EXCEEDS_FREE_VRAM:`likely exceeds free VRAM (~${gib(c.estimated_required_bytes)})`}[c.assessment]}`);
    lines.push(r.recommended_context?`Suggested starting context: ${r.recommended_context}. ${r.label}`:`No reliable recommendation. ${r.reason||''}`);
    if(r.recommended_context)lines.push(r.reason);
    lines.push('No stress test was run.');
    return lines.join('\n');
  }
  if(typeof module!=='undefined'&&module.exports){module.exports={ChatController,hardwareReport};return;}
  const el=id=>document.getElementById(id);
  let integrations=[],bound=false,notice='';
  const controller=new ChatController((...args)=>api(...args),render);
  function option(select,value,label){select.add(new Option(label,value));}
  function provider(){return integrations.find(x=>x.id===el('chat-provider').value);}
  function models(){const p=provider();el('chat-model').replaceChildren();for(const model of p?.models||[])option(el('chat-model'),model,model);if(p?.selected_model)el('chat-model').value=p.selected_model;el('chat-load-row').hidden=p?.id!=='ollama';el('chat-load-approved').checked=false;}
  /* A select bumps the revision, so reuse a current one: it would otherwise stale the open conversation. */
  async function select(p,model){
    if(p.selected_model===model)return p.selection_revision;
    const snap=await api(`/api/v1/integrations/${p.id}/select`,{method:'POST',body:JSON.stringify({approved:true,model})});
    Object.assign(p,snap.items.find(x=>x.id===p.id));
    if(controller.session?.provider===p.id)controller.selectionRevision=p.selection_revision;
    return p.selection_revision;
  }
  function message(role,content){const article=document.createElement('article'),label=document.createElement('strong'),text=document.createElement('p');article.className='chat-message';label.textContent=role;text.dir='auto';text.textContent=content;article.append(label,text);el('chat-messages').append(article);}
  function render(){
    const s=controller.session,busy=controller.pending||s?.busy,open=s?.status==='OPEN';
    el('chat-new').disabled=!!busy||!provider();el('chat-saved').disabled=!!busy;el('chat-hardware').disabled=!!busy;
    el('chat-provider').disabled=!!busy;el('chat-model').disabled=!!busy;
    el('chat-send').disabled=!open||!!busy;el('chat-stop').disabled=!busy;
    el('chat-collect').disabled=!open;el('chat-collect').checked=!!s?.collect;
    el('chat-archive').disabled=!s||s.status==='ARCHIVED';
    el('chat-messages').replaceChildren();
    for(const t of s?.turns||[]){message('You',t.user);message('Model',t.assistant);}
    const last=s?.turns?.at(-1);
    el('chat-usage').textContent=s?`${s.provider} / ${s.model} · Budget ${s.context_budget} · Reply reserve ${s.reply_reserve}${last?` · Last turn: ${last.input_tokens} input + ${last.output_tokens} output tokens (${last.input_tokens+last.output_tokens} of ${s.context_budget})`:''}`:'';
    el('chat-notice').textContent=notice||(busy?'Waiting for the model. Stop discards this turn.':s?'Ready. Complete history is sent unchanged.':'Connect a runtime in Settings, then create a conversation.');
  }
  async function saved(){const data=await api('/api/v1/chat/sessions');el('chat-saved').replaceChildren();option(el('chat-saved'),'','Choose a saved conversation');for(const s of data.items)option(el('chat-saved'),s.id,`${s.model} · ${s.created_at} · ${s.status}`);if(controller.session)el('chat-saved').value=controller.session.id;}
  async function load(){
    if(!bound)bind();
    integrations=(await api('/api/v1/integrations')).items.filter(x=>x.kind==='model_runtime'&&x.connection==='CONNECTED');
    const previous=el('chat-provider').value;el('chat-provider').replaceChildren();for(const p of integrations)option(el('chat-provider'),p.id,p.name);
    if(integrations.some(p=>p.id===previous))el('chat-provider').value=previous;models();
    if(controller.session){const p=integrations.find(x=>x.id===controller.session.provider);controller.selectionRevision=p?.selection_revision;await controller.refresh();}
    await saved();render();
  }
  function act(fn){return async event=>{try{await fn(event);}catch(error){notice=error.message;render();}};}
  function bind(){
    bound=true;
    el('chat-provider').onchange=models;
    el('chat-new').onclick=act(async()=>{
      const p=provider(),model=el('chat-model').value;if(!p||!model)throw Error('Connect and select a model in Settings first.');
      controller.selectionRevision=await select(p,model);
      controller.session=await controller.post('/api/v1/chat/sessions',{provider:p.id,model,selection_revision:controller.selectionRevision,context_budget:Number(el('chat-budget').value),reply_reserve:Number(el('chat-reserve').value),load_approved:p.id==='ollama'&&el('chat-load-approved').checked});
      notice='';el('chat-load-approved').checked=false;await saved();render();
    });
    el('chat-saved').onchange=act(async()=>{const id=el('chat-saved').value;if(!id)return;controller.session=await api(`/api/v1/chat/sessions/${id}`);controller.selectionRevision=integrations.find(x=>x.id===controller.session.provider)?.selection_revision;notice='';render();});
    el('chat-refresh').onclick=act(async()=>{notice='';await load();});
    el('chat-form').onsubmit=act(async event=>{
      event.preventDefault();notice='';const result=await controller.send(el('chat-draft').value);
      if(result.status==='CONTEXT_LIMIT')notice=`Context limit reached: ${result.input_tokens} prompt tokens + ${result.reply_reserve} reserved for the reply exceed the ${result.context_budget} budget. The conversation was saved and a new empty conversation opened. Your unsent draft remains below; it was not sent or copied automatically.`;
      else el('chat-draft').value='';await saved();render();
    });
    el('chat-stop').onclick=act(async()=>{await controller.stop();notice='Stop requested. No partial response will be saved. Engine cancellation is best effort; its service stays running.';render();});
    el('chat-collect').onchange=act(async()=>{await controller.collect(el('chat-collect').checked);notice='Collection choice saved for this server process. Only future completed pairs can enter PENDING review.';render();});
    el('chat-archive').onclick=act(async()=>{
      if(!confirm('Archive this conversation and exclude its collected pairs from future dataset selection? Local text and previous exports are retained.'))return;
      await controller.refresh();controller.session=await controller.post(controller.path('archive'),{revision:controller.session.revision});notice='Conversation archived. Data and earlier exports are retained.';await saved();render();
    });
    el('chat-hardware').onclick=act(async()=>{
      const p=provider(),model=el('chat-model').value,body={approved:true};
      if(p&&model)Object.assign(body,{provider:p.id,model,selection_revision:await select(p,model)});
      const data=await controller.post('/api/v1/chat/hardware',body);
      el('chat-hardware-result').textContent=hardwareReport(data);
      const offered=(data.recommendation?.candidates||[]).filter(c=>c.assessment==='ESTIMATE_FITS_FREE_VRAM');
      if(offered.length)el('chat-budget-options').replaceChildren(...offered.map(c=>new Option(`${c.context}`,c.context)));
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
