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
  if(typeof module!=='undefined'&&module.exports){module.exports={ChatController};return;}
  const el=id=>document.getElementById(id);
  let integrations=[],bound=false,notice='';
  const controller=new ChatController((...args)=>api(...args),render);
  function option(select,value,label){select.add(new Option(label,value));}
  function provider(){return integrations.find(x=>x.id===el('chat-provider').value);}
  function models(){const p=provider();el('chat-model').replaceChildren();for(const model of p?.models||[])option(el('chat-model'),model,model);if(p?.selected_model)el('chat-model').value=p.selected_model;}
  function message(role,content){const article=document.createElement('article'),label=document.createElement('strong'),text=document.createElement('p');article.className='chat-message';label.textContent=role;text.dir='auto';text.textContent=content;article.append(label,text);el('chat-messages').append(article);}
  function render(){
    const s=controller.session,busy=controller.pending||s?.busy,open=s?.status==='OPEN';
    el('chat-new').disabled=!!busy||!provider();el('chat-saved').disabled=!!busy;
    el('chat-provider').disabled=!!busy;el('chat-model').disabled=!!busy;
    el('chat-send').disabled=!open||!!busy||s?.provider==='ollama';el('chat-stop').disabled=!busy;
    el('chat-collect').disabled=!open;el('chat-collect').checked=!!s?.collect;
    el('chat-archive').disabled=!s||s.status==='ARCHIVED';
    el('chat-messages').replaceChildren();
    for(const t of s?.turns||[]){message('You',t.user);message('Model',t.assistant);}
    const last=s?.turns?.at(-1);
    el('chat-usage').textContent=s?`${s.provider} / ${s.model} · Budget ${s.context_budget} · Reply reserve ${s.reply_reserve}${last?` · Last turn: ${last.input_tokens} input + ${last.output_tokens} output tokens`:''}`:'';
    el('chat-notice').textContent=notice||(s?.provider==='ollama'?'Ollama Chat is blocked: exact template-token preflight is unavailable. Connectivity tests remain in Settings.':busy?'Waiting for the model. Stop discards this turn.':s?'Ready. Complete history is sent unchanged.':'Connect a runtime in Settings, then create a conversation.');
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
      const snap=await api(`/api/v1/integrations/${p.id}/select`,{method:'POST',body:JSON.stringify({approved:true,model})});
      const current=snap.items.find(x=>x.id===p.id);controller.selectionRevision=current.selection_revision;
      controller.session=await controller.post('/api/v1/chat/sessions',{provider:p.id,model,selection_revision:current.selection_revision,context_budget:Number(el('chat-budget').value),reply_reserve:Number(el('chat-reserve').value)});
      notice='';await saved();render();
    });
    el('chat-saved').onchange=act(async()=>{const id=el('chat-saved').value;if(!id)return;controller.session=await api(`/api/v1/chat/sessions/${id}`);controller.selectionRevision=integrations.find(x=>x.id===controller.session.provider)?.selection_revision;notice='';render();});
    el('chat-refresh').onclick=act(async()=>{notice='';await load();});
    el('chat-form').onsubmit=act(async event=>{
      event.preventDefault();notice='';const result=await controller.send(el('chat-draft').value);
      if(result.status==='CONTEXT_LIMIT')notice='Context limit reached. The conversation was saved and a new empty conversation opened. Your unsent draft remains below; it was not sent or copied automatically.';
      else el('chat-draft').value='';await saved();render();
    });
    el('chat-stop').onclick=act(async()=>{await controller.stop();notice='Stop requested. No partial response will be saved. Engine cancellation is best effort; its service stays running.';render();});
    el('chat-collect').onchange=act(async()=>{await controller.collect(el('chat-collect').checked);notice='Collection choice saved for this server process. Only future completed pairs can enter PENDING review.';render();});
    el('chat-archive').onclick=act(async()=>{
      if(!confirm('Archive this conversation and exclude its collected pairs from future training? Local text and previous exports are retained.'))return;
      await controller.refresh();controller.session=await controller.post(controller.path('archive'),{revision:controller.session.revision});notice='Conversation archived. Data and earlier exports are retained.';await saved();render();
    });
    el('chat-hardware').onclick=act(async()=>{
      const data=await controller.post('/api/v1/chat/hardware',{approved:true});
      const gib=n=>typeof n==='number'?`${(n/1024**3).toFixed(1)} GiB`:'Unknown';
      el('chat-hardware-result').textContent=`Available RAM: ${gib(data.ram_available_bytes)} / ${gib(data.ram_total_bytes)}\n${data.gpus.map(g=>`${g.name}: ${gib(g.free_bytes)} free / ${gib(g.total_bytes)}`).join('\n')||'GPU memory unavailable'}\nNo numeric safe context recommendation: KV cache, placement and runtime overhead are unverified. No stress test was run.`;
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
