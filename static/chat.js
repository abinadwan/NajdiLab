/* Chat V2. Controls own only NajdiLab sessions; the server owns consent, admission
 * and what is saved. Streamed text is display-only until the server's final
 * `done` event returns the committed session. */
(function(global){
  'use strict';
  const CONTEXTS=[4096,8192,16384,32768];
  const PHASES={
    engine_check:'Checking the model runtime…',
    admission:'Verifying the model and the full conversation context…',
    waiting_first_token:'Waiting for the first token…',
    thinking:'The model is thinking…',
    answering:'Writing the answer…',
    verifying:'Checking that the reply is complete…'
  };
  const SIDEBAR_KEY='najdilab.chat.sidebar';

  class ChatError extends Error{
    constructor(message,code,check,hint){super(message);this.code=code||null;this.check=check||null;this.hint=hint||null;}
  }

  /* NDJSON reader: complete lines only; a partial trailing line waits for more bytes. */
  function ndjsonSplitter(onEvent){
    let buffer='';
    return {
      push(text){
        buffer+=text;let index;
        while((index=buffer.indexOf('\n'))>=0){
          const line=buffer.slice(0,index).trim();buffer=buffer.slice(index+1);
          if(line)onEvent(JSON.parse(line));
        }
      },
      end(){const line=buffer.trim();buffer='';if(line)onEvent(JSON.parse(line));}
    };
  }

  class ChatController{
    constructor(request,render,uuid=()=>global.crypto.randomUUID(),stream=null){
      this.request=request;this.render=render;this.uuid=uuid;this.stream=stream;
      this.session=null;this.pending=false;this.selectionRevision=null;this.modelReady=true;
    }
    post(path,data){return this.request(path,{method:'POST',body:JSON.stringify(data)});}
    path(action=''){return `/api/v1/chat/sessions/${this.session.id}${action?'/'+action:''}`;}
    async refresh(){if(this.session)this.session=await this.request(this.path());this.render();}
    canSend(text){return canSend(text,this.session,this.pending,this.modelReady);}
    /* One turn. `pending` is set before any await, so a second Enter or click in
       the same tick is refused instead of creating a duplicate request. */
    async send(text,onEvent=()=>{}){
      if(!this.session||this.pending||this.session.busy)throw new ChatError('A reply is already in progress. Wait for it or stop it first.','CHAT_BUSY');
      if(typeof text!=='string'||!text.trim())throw new ChatError('Write a message first.','INVALID_TEXT');
      if(this.session.status!=='OPEN')throw new ChatError('This conversation is closed. Start a new one.','CHAT_CLOSED');
      if(this.modelReady!==true)throw new ChatError('This conversation is bound to its original model and runtime. Connect and select that exact model to continue; nothing was changed automatically.','MODEL_NOT_READY');
      const sid=this.session.id;
      const data={request_id:this.uuid(),revision:this.session.revision,selection_revision:this.selectionRevision,text};
      this.pending=true;this.render();
      try{
        let result;
        if(this.stream){
          result=await this.stream(`/api/v1/chat/sessions/${sid}/send-stream`,data,onEvent);
        }else{
          result=await this.post(`/api/v1/chat/sessions/${sid}/send`,data);
        }
        if(this.session&&this.session.id===sid)this.session=result.new_session||result.session;
        return result;
      }catch(error){
        try{if(this.session&&this.session.id===sid)this.session=await this.request(`/api/v1/chat/sessions/${sid}`);}catch{}
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

  /* Shared send guard (ported from PR #21, 95e7604): non-blank text, an open idle
     session, no pending request and the session's own model selected. */
  function canSend(text,session,pending,modelReady){
    return typeof text==='string'&&!!text.trim()&&session?.status==='OPEN'&&!session.busy&&!pending&&modelReady===true;
  }
  /* Enter sends; Shift+Enter (or any modifier) is a new line; IME composition and
     a held (auto-repeating) Enter never send. */
  function keyAction(event){
    if(event.key!=='Enter')return 'none';
    if(event.isComposing||event.composing||event.keyCode===229)return 'compose';
    if(event.shiftKey||event.altKey||event.ctrlKey||event.metaKey)return 'newline';
    if(event.repeat)return 'repeat';
    return 'send';
  }
  function shouldSendOnEnter(event){return keyAction(event)==='send';}
  function validBudgets(context,reply){
    return Number.isInteger(context)&&context>=128&&context<=1048576&&Number.isInteger(reply)&&reply>=1&&reply<=Math.min(8192,context-1);
  }
  /* Composer context choices: readable sizes, enabled only up to the model's own maximum when it is
     known. Hardware fit and the engine's real ceiling are checked when the chat is prepared. */
  function contextLabel(tokens){
    if(!Number.isInteger(tokens)||tokens<=0)return '—';
    return tokens%1024===0?`${tokens/1024}K`:String(tokens);
  }
  function contextOptions(maxContext,contexts=CONTEXTS){
    const known=Number.isInteger(maxContext)&&maxContext>0;
    return (contexts||CONTEXTS).map(value=>({value,label:contextLabel(value),enabled:!known||value<=maxContext}));
  }
  function sameSelection(a,b){
    return !!a&&!!b&&a.provider===b.provider&&a.model===b.model&&a.context===b.context&&a.reserve===b.reserve;
  }
  /* A conversation with saved turns never changes model or context; a different choice needs an
     explicit new conversation. An empty draft (or a conversation with no turns) can simply change. */
  function switchNeedsNewChat(session,next){
    return !!session&&(session.turns||[]).length>0&&!sameSelection({provider:session.provider,model:session.model,
      context:session.context_budget,reserve:session.reply_reserve},next);
  }

  // Clear only the exact draft submitted to this request. A user may continue
  // typing during inference; a later completion must never erase that newer draft.
  function shouldClearDraft(submitted,current,status){
    return status==='COMPLETED' && current===submitted;
  }

  function dayKey(date){return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;}
  /* Sidebar groups by local calendar day of the last activity; pinned first. */
  function groupSessions(items,now=new Date()){
    const order=['pinned','today','yesterday','week','month','older'];
    const labels={pinned:'Pinned',today:'Today',yesterday:'Yesterday',week:'Previous 7 days',month:'Previous 30 days',older:'Older'};
    const groups=Object.fromEntries(order.map(k=>[k,[]]));
    const startToday=new Date(now.getFullYear(),now.getMonth(),now.getDate());
    for(const item of items){
      if(item.pinned_at){groups.pinned.push(item);continue;}
      const when=new Date(item.last_activity_at||item.updated_at||item.created_at);
      if(Number.isNaN(when.valueOf())){groups.older.push(item);continue;}
      const days=Math.floor((startToday-new Date(when.getFullYear(),when.getMonth(),when.getDate()))/86400000);
      const key=days<=0?'today':days===1?'yesterday':days<7?'week':days<30?'month':'older';
      groups[key].push(item);
    }
    return order.filter(k=>groups[k].length).map(k=>({key:k,label:labels[k],items:groups[k]}));
  }

  function budgetBreakdown(context,reserve,modelMax=null){
    const ok=Number.isInteger(context)&&Number.isInteger(reserve)&&context>=128&&reserve>=1&&reserve<=8192&&reserve<context;
    const result={context,reserve,input:ok?context-reserve:null,valid:ok,warnings:[]};
    if(!ok)result.warnings.push('Reply space must be between 1 and 8192 tokens and smaller than the total context.');
    if(ok&&modelMax&&context>modelMax)result.warnings.push('This is larger than the model\'s maximum context.');
    if(ok&&reserve<512)result.warnings.push('Thinking models can use most of a small reply space before answering.');
    return result;
  }

  /* Error text keeps the readable message and the technical code for diagnosis. */
  function errorParts(error){
    const parts=[String(error&&error.message||'Something went wrong.')];
    if(error&&error.code)parts.push(' ',{id:error.check?`${error.code} · ${error.check}`:error.code});
    if(error&&error.hint)parts.push(' ',String(error.hint));
    return parts;
  }

  /* Context usage from the engine's own counts only. After a saved turn the history is exactly
     the last prompt plus its reply (both counted by the engine); the next prompt adds the new message
     and its few template tokens, so "left for the next message" is an estimate. During a turn the
     admitted prompt size is measured. Nothing here decides admission: the server still checks
     prompt + reply reserve against the budget exactly before every reply. */
  const CONTEXT_THRESHOLDS={info:70,warn:85,critical:95};
  function contextUsage(session,admitted){
    if(!session||!Number.isInteger(session.context_budget)||session.context_budget<=0)return null;
    const budget=session.context_budget,reserve=Number.isInteger(session.reply_reserve)?session.reply_reserve:0;
    const last=session.turns&&session.turns.length?session.turns[session.turns.length-1]:null;
    let used=0,kind='empty';
    if(admitted&&Number.isInteger(admitted.input_tokens)){used=admitted.input_tokens;kind='measured_prompt';}
    else if(last&&Number.isInteger(last.input_tokens)&&Number.isInteger(last.output_tokens)){used=last.input_tokens+last.output_tokens;kind='measured_history';}
    const committed=used+reserve;
    return {budget,reserve,used,kind,available:Math.max(budget-committed,0),
      percent:Math.min(100,Math.round(committed/budget*100)),availableKind:kind==='measured_prompt'?'measured':'estimate'};
  }
  function validThresholds(t){
    return !!t&&['info','warn','critical'].every(k=>Number.isInteger(t[k])&&t[k]>=1&&t[k]<=99)&&t.info<t.warn&&t.warn<t.critical;
  }
  function contextLevel(percent,thresholds=CONTEXT_THRESHOLDS){
    const t=validThresholds(thresholds)?thresholds:CONTEXT_THRESHOLDS;
    return percent>=t.critical?'critical':percent>=t.warn?'warn':percent>=t.info?'info':null;
  }
  /* What kind of failure ended a reply, shown before the engine's own message. */
  function failureCategory(error){
    const code=error&&error.code;
    if(code==='STOPPED')return 'Cancelled.';
    if(code==='INCOMPLETE_RESPONSE')return error.check==='STOP_REASON_LENGTH'?'Reply reserve reached.':'The runtime did not finish the reply.';
    if(code==='CONTEXT_SHRANK'||code==='ENGINE_CONTEXT_LIMIT'||code==='ENGINE_CONTEXT_MISMATCH')return 'Context capacity.';
    if(/^(ENGINE_|MODEL_CHANGED|NATIVE_|NOT_CONNECTED)/.test(code||''))return 'Runtime error.';
    return null;
  }

  if(typeof module!=='undefined'&&module.exports){
    module.exports={ChatController,ChatError,keyAction,shouldSendOnEnter,canSend,validBudgets,shouldClearDraft,groupSessions,budgetBreakdown,ndjsonSplitter,errorParts,PHASES,
      contextUsage,contextLevel,validThresholds,failureCategory,CONTEXT_THRESHOLDS,CONTEXTS,contextLabel,contextOptions,sameSelection,switchNeedsNewChat};
    return;
  }

  // ======================================================================= DOM
  const el=id=>document.getElementById(id);
  const tr=text=>global.NajdiI18n?global.NajdiI18n.t(text):text;
  const SELECTION_KEY='najdilab.chat.selection';
  // Native-first: new chats use NajdiLab Native. LM Studio and Ollama stay readable in existing
  // conversations and can be offered again from Settings → Models & Integrations.
  const LEGACY_PROVIDERS_KEY='najdilab.chat.legacyProviders';
  function legacyProviders(){try{return global.localStorage.getItem(LEGACY_PROVIDERS_KEY)==='1';}catch{return false;}}
  let catalog=null,selection=null,plan=null,pendingSend=false,preparing=false,draftCollect=false,bound=false,notice=[];
  let listMode='active',listQuery='',savedLoaded=0,menuTarget=null,live=null,pendingUse=null;
  const thinkingByRequest=new Map(),timingsByRequest=new Map();

  async function request(path,options={}){
    const method=(options.method||'GET').toUpperCase(),headers={'Content-Type':'application/json'};
    if(method!=='GET')headers['X-NajdiLab-CSRF']=await global.sessionToken();
    const response=await fetch(path,{...options,method,headers});
    let payload;try{payload=await response.json();}catch{payload={error:'Invalid server response'};}
    if(!response.ok)throw new ChatError(payload.error||`HTTP ${response.status}`,payload.code,payload.check,payload.hint);
    return payload;
  }
  async function stream(path,body,onEvent){
    const response=await fetch(path,{method:'POST',body:JSON.stringify(body),
      headers:{'Content-Type':'application/json','X-NajdiLab-CSRF':await global.sessionToken()}});
    if(!response.ok||!String(response.headers.get('Content-Type')).startsWith('application/x-ndjson')){
      let payload;try{payload=await response.json();}catch{payload={error:`HTTP ${response.status}`};}
      throw new ChatError(payload.error||`HTTP ${response.status}`,payload.code,payload.check,payload.hint);
    }
    let final=null,failure=null;
    const splitter=ndjsonSplitter(event=>{
      if(event.type==='done')final=event.result;
      else if(event.type==='error')failure=new ChatError(event.error,event.code,event.check,event.hint);
      else onEvent(event);
    });
    const reader=response.body.getReader(),decoder=new TextDecoder();
    for(;;){const {value,done}=await reader.read();if(done)break;splitter.push(decoder.decode(value,{stream:true}));}
    splitter.push(decoder.decode());splitter.end();
    if(failure)throw failure;
    if(!final)throw new ChatError('The connection ended before the reply was confirmed. Nothing was saved.','STREAM_INTERRUPTED');
    return final;
  }
  const controller=new ChatController(request,render,undefined,stream);
  controller.modelReady=false;

  function compose(target,parts){target.replaceChildren(...parts.map(part=>{if(typeof part==='string')return document.createTextNode(part);const id=document.createElement('bdi');id.dir='ltr';id.setAttribute('translate','no');id.textContent=part.id;return id;}));}
  function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
  function literal(tag,text,cls){const e=node(tag,cls,text);e.dir='auto';e.setAttribute('translate','no');return e;}
  function setNotice(parts){notice=Array.isArray(parts)?parts:[parts];renderNotice();}
  function renderNotice(){
    const s=controller.session,busy=controller.pending||s?.busy;
    if(notice.length&&!(notice.length===1&&notice[0]===''))return compose(el('chat-notice'),notice);
    el('chat-notice').textContent=busy?'':
      s&&s.status==='CONTEXT_LIMIT'?'This conversation reached its context limit. Start a new chat to continue.':
      s&&s.status==='ARCHIVED'?'This conversation is archived. Restore it to continue.':'';
  }
  function runtimeName(id){return {lmstudio:'LM Studio',ollama:'Ollama',native:'NajdiLab Native'}[id]||id;}
  function statusLabel(status){return {OPEN:'Open',CONTEXT_LIMIT:'Context limit reached',ARCHIVED:'Archived'}[status]||status;}

  // ------------------------------------------------------------ model and context selection
  /* One choice drives the composer: the open conversation's own settings, or the draft's. A
     conversation never changes model or context; a different choice starts a new chat. */
  function savedSelection(){try{return JSON.parse(global.localStorage.getItem(SELECTION_KEY)||'null');}catch{return null;}}
  function storeSelection(value){try{global.localStorage.setItem(SELECTION_KEY,JSON.stringify(value));}catch{}}
  function validSelection(value){return !!value&&typeof value==='object'&&validBudgets(value.context,value.reserve)&&['auto','all','0'].includes(value.gpu);}
  function defaultSelection(){const saved=savedSelection();if(!validSelection(saved))return {provider:null,model:null,context:8192,reserve:1024,gpu:'auto'};
    return saved.provider&&saved.provider!=='native'&&!legacyProviders()?{...saved,provider:null,model:null}:saved;}
  function sessionSelection(s){return {provider:s.provider,model:s.model,context:s.context_budget,reserve:s.reply_reserve,gpu:selection?.gpu||'auto'};}
  function current(){return controller.session?sessionSelection(controller.session):selection;}
  function catalogItem(value=current()){return catalog?.items.find(i=>i.provider===value?.provider&&i.model===value?.model)||null;}
  function modelLabel(value=current()){return catalogItem(value)?.label||(value?.model?value.model.split('/').pop().replace(/\.gguf$/i,''):null);}
  async function loadCatalog(){catalog=await request('/api/v1/chat/models');renderControls();}

  function confirmSwitch(next){
    return new Promise(resolve=>{
      const dialog=el('chat-switch');
      compose(el('chat-switch-text'),['New chat with ',{id:modelLabel(next)||next.model},' · ',{id:contextLabel(next.context)},'.']);
      // Settled by the buttons themselves; Escape and `close` are fallbacks (some embedded browsers never fire `close`).
      let settled=false;
      const finish=value=>{if(settled)return;settled=true;if(dialog.open)dialog.close();resolve(value);};
      el('chat-switch-go').onclick=event=>{event.preventDefault();finish(true);};
      el('chat-switch-cancel').onclick=event=>{event.preventDefault();finish(false);};
      dialog.oncancel=()=>finish(false);
      dialog.onclose=()=>finish(dialog.returnValue==='new');
      dialog.returnValue='';dialog.showModal();el('chat-switch-go').focus();
    });
  }
  /* The only way a choice changes: an empty draft simply takes it; a conversation with saved
     turns stays as it is and, after confirmation, a new empty chat starts with the choice. */
  async function choose(next){
    if(!validSelection(next))return;
    const s=controller.session;
    if(s&&sameSelection(sessionSelection(s),next))return;
    if(switchNeedsNewChat(s,next)&&!await confirmSwitch(next))return;
    if(s){controller.session=null;limit=null;lingering=[];}
    selection=next;storeSelection(next);draftCollect=false;plan=null;pendingSend=false;notice=[];
    hideCard();controller.modelReady=false;render();el('chat-draft').focus();
  }
  function newChat(){
    controller.session=null;selection=defaultSelection();draftCollect=false;plan=null;pendingSend=false;
    limit=null;lingering=[];notice=[];hideCard();controller.modelReady=false;render();
    if(narrow())setSidebar(false,false);
    el('chat-draft').focus();
  }

  // ------------------------------------------------------------ popovers
  let popover=null;
  function placePopover(panel,anchor){
    const rect=anchor.getBoundingClientRect(),rtl=document.documentElement.dir==='rtl';
    panel.hidden=false;
    const width=Math.min(panel.offsetWidth||320,global.innerWidth-16);
    let left=rtl?rect.right-width:rect.left;left=Math.max(8,Math.min(left,global.innerWidth-width-8));
    panel.style.left=`${left}px`;
    const below=global.innerHeight-rect.bottom,above=rect.top;
    // Open on the roomier side and never past the screen edge (the menu scrolls instead), even at 400% zoom.
    panel.style.maxHeight=`${Math.max(64,Math.min(520,Math.max(above,below)-14))}px`;
    if(above>=below){panel.style.top='';panel.style.bottom=`${global.innerHeight-rect.top+6}px`;}
    else{panel.style.bottom='';panel.style.top=`${rect.bottom+6}px`;}
  }
  function openPopover(panel,anchor,focus){
    closePopover(false);popover={panel,anchor};
    placePopover(panel,anchor);anchor.setAttribute('aria-expanded','true');
    (focus||panel.querySelector('button:not([aria-disabled="true"]),input:not(:disabled),select'))?.focus();
  }
  function closePopover(focusBack=true){
    if(!popover)return;const {panel,anchor}=popover;popover=null;
    panel.hidden=true;anchor.setAttribute('aria-expanded','false');if(focusBack)anchor.focus();
  }
  const VERIFICATION={VERIFIED:'Verified',LOCAL:'Local file',UNVERIFIED:'Not verified yet',RUNTIME:'Connected runtime'};
  const UNAVAILABLE={NATIVE_SERVER_MISSING:'llama.cpp runtime not installed',MODEL_NOT_VERIFIED:'Not verified yet'};
  function renderModelMenu(){
    const menu=el('chat-model-menu'),value=current(),locked=!!controller.session;menu.replaceChildren();
    const items=catalog?.items||[];
    for(const [provider,name] of [['native','NajdiLab Native'],...(legacyProviders()?[['lmstudio','LM Studio'],['ollama','Ollama']]:[])]){
      const group=items.filter(i=>i.provider===provider);if(!group.length)continue;
      // ARIA menu: one labelled group per runtime; the visible heading is decorative.
      const box=node('div','chatv2-menu-group');box.setAttribute('role','group');box.setAttribute('aria-label',name);
      const heading=node('h4',null,name);heading.setAttribute('translate','no');heading.setAttribute('aria-hidden','true');box.append(heading);menu.append(box);
      for(const item of group){
        const button=node('button','chatv2-model-item');button.type='button';button.setAttribute('role','menuitemradio');
        const checked=value?.provider===item.provider&&value?.model===item.model;
        button.setAttribute('aria-checked',String(checked));
        if(!item.available)button.setAttribute('aria-disabled','true');
        button.append(node('span','check','✓'),literal('strong',item.label));
        const meta=node('small');
        const parts=[item.available?VERIFICATION[item.verification]||item.verification:UNAVAILABLE[item.reason]||'Not usable now'];
        if(item.quantization)parts.push(' · ',{id:item.quantization});
        if(item.max_context)parts.push(' · ','up to',' ',{id:contextLabel(item.max_context)});
        if(item.state==='RUNNING')parts.push(' · ','loaded at',' ',{id:contextLabel(item.loaded_context)});
        if(item.state==='SELECTED')parts.push(' · ','selected in the runtime');
        compose(meta,parts);button.append(meta);
        button.onclick=()=>{
          if(!item.available)return;
          closePopover();
          if(locked&&checked)return;
          const base=current()||defaultSelection(),max=item.max_context;
          const context=max&&base.context>max?Math.max(...contextOptions(max).filter(o=>o.enabled).map(o=>o.value),128):base.context;
          choose({...base,provider:item.provider,model:item.model,context,reserve:Math.min(base.reserve,context-1)}).catch(error=>setNotice(errorParts(error)));
        };
        box.append(button);
      }
    }
    if(!items.length){const none=node('button','chatv2-menu-action muted','No local models yet. Download one in Model library, or connect LM Studio or Ollama in Settings.');
      none.type='button';none.setAttribute('role','menuitem');none.setAttribute('aria-disabled','true');menu.append(none);}
    const sep=node('div','chatv2-menu-sep');sep.setAttribute('role','separator');menu.append(sep);
    const library=node('button','chatv2-menu-action','Open Model library');library.type='button';library.setAttribute('role','menuitem');
    library.onclick=()=>{closePopover(false);global.switchView?.('models');};menu.append(library);
    const native=catalog?.native;
    if(native?.state==='RUNNING'){
      const stop=node('button','chatv2-menu-action','Stop NajdiLab Native (frees memory)');stop.type='button';stop.setAttribute('role','menuitem');
      if(native.busy)stop.setAttribute('aria-disabled','true');
      stop.onclick=act(async()=>{
        if(native.busy||!global.confirm(tr('Stop NajdiLab Native? Only the server process NajdiLab started is stopped; conversations keep their history.')))return;
        closePopover();await request('/api/v1/native/stop',{method:'POST',body:JSON.stringify({approved:true})});
        await loadCatalog();plan=null;controller.modelReady=false;render();
      });
      menu.append(stop);
    }
  }
  function renderContextMenu(){
    const value=current()||defaultSelection(),item=catalogItem(value),box=el('chat-context-options');box.replaceChildren();
    for(const option of contextOptions(item?.max_context,catalog?.contexts)){
      const label=node('label');const input=node('input');input.type='radio';input.name='chat-context-choice';input.value=String(option.value);
      input.checked=option.value===value.context;input.disabled=!option.enabled;
      if(!option.enabled)label.title=tr('Above this model\'s maximum context');
      input.onchange=()=>{closePopover();choose({...value,context:option.value,reserve:Math.min(value.reserve,option.value-1)}).catch(error=>setNotice(errorParts(error)));};
      label.append(input);const text=node('span',null,option.label);text.setAttribute('translate','no');label.append(text);box.append(label);
    }
    const note=el('chat-context-note');
    if(item?.provider==='native')compose(note,['Model maximum:',' ',{id:String(item.max_context)},' ','tokens','. ','Memory is checked before the model starts.']);
    else if(item)note.textContent='The runtime\'s own limit is checked when the chat starts.';
    else note.textContent='Choose a model first.';
    el('chat-budget').value=value.context;el('chat-reserve').value=value.reserve;el('chat-gpu').value=value.gpu||'auto';
    el('chat-gpu').disabled=item?.provider!=='native';
    updateBreakdown();
  }
  function updateBreakdown(){
    const context=Number(el('chat-budget').value),reserve=Number(el('chat-reserve').value);
    const b=budgetBreakdown(context,reserve,catalogItem()?.max_context||null);
    const ok=b.valid&&validBudgets(context,reserve)&&!b.warnings.some(w=>/maximum/.test(w));
    const box=el('chat-budget-breakdown');
    if(!ok)box.textContent=b.warnings[0]||'Reply space must be between 1 and 8192 tokens and smaller than the total context.';
    else compose(box,['Message and history space:',' ',{id:String(b.input)},' ','tokens',b.warnings.length?[' · ',b.warnings[0]].join(''):'']);
    el('chat-budget-apply').disabled=!ok;
  }
  function renderControls(){
    const value=current(),item=catalogItem(value),label=modelLabel(value),busy=controller.pending||!!controller.session?.busy;
    el('chat-model-label').textContent=label||tr('Choose a model');
    if(label)el('chat-model-label').setAttribute('translate','no');else el('chat-model-label').removeAttribute('translate');
    el('chat-model-state').dataset.state=item?.state||'';
    el('chat-context-label').textContent=value?contextLabel(value.context):'—';
    // The full name (often cut with an ellipsis) as a tooltip on the untranslated label itself.
    el('chat-model-label').title=label||'';
    el('chat-context-button').title=value?`${value.context} tokens · reply ${value.reserve}`:'';
    el('chat-model-button').disabled=busy||preparing;el('chat-context-button').disabled=busy||preparing;
  }

  // ------------------------------------------------------------ runtime preparation (one path)
  function showCard({kind='info',title,parts=[],action=null,error=null}){
    const card=el('chat-prepare');card.hidden=false;card.dataset.kind=kind;
    el('chat-prepare-title').textContent=title;compose(el('chat-prepare-text'),parts);
    if(error)compose(el('chat-prepare-error'),errorParts(error));else el('chat-prepare-error').textContent='';
    const go=el('chat-prepare-go');go.hidden=!action;if(action){go.textContent=action;go.disabled=preparing;}
  }
  function hideCard(){el('chat-prepare').hidden=true;}
  function describe(result,value){
    const what=[{id:modelLabel(value)||value.model},' · ',{id:contextLabel(value.context)}];
    if(result.state==='NEEDS_START')return {title:'Start the model?',action:'Start model',
      parts:[...what,'. ','NajdiLab Native is stopped. NajdiLab checks memory first, then loads the model on this computer only. Your message stays here.']};
    if(result.state==='NEEDS_RESTART'){
      const was=result.running?[' ','Now loaded:',' ',{id:modelLabel({provider:'native',model:result.running.model})||result.running.model},' · ',{id:contextLabel(result.running.context)},'.']:[];
      return {title:'Restart NajdiLab Native?',action:'Restart with this model',
        parts:[result.message,...was,' ','This chat needs',' ',...what,'. ','Restarting stops only NajdiLab\'s own model server; other conversations keep their history. Memory is checked first.']};
    }
    if(result.state==='NEEDS_APPROVAL')return {title:result.needs_load?'Allow Ollama to load this model?':'Select this model in LM Studio?',action:'Allow',parts:[...what,'. ',result.message]};
    if(result.state==='BUSY')return {kind:'blocked',title:'A reply is running',parts:[result.message]};
    const reasons=(result.advice?.reasons||[]).map(r=>r.message);
    return {kind:'blocked',title:'This model cannot be used now',parts:[result.message,...(reasons.length&&reasons[0]!==result.message?[' ',reasons[0]]:[]),' ',{id:result.code}],
      action:result.code==='NATIVE_SERVER_MISSING'?'Open Model library':null};
  }
  async function check(sendAfter){
    const value=current();
    if(!value?.model){showCard({kind:'blocked',title:'Choose a model',parts:['Pick a model in the message box. Download more in Model library.']});return null;}
    const body={provider:value.provider,model:value.model,context_budget:value.context,reply_reserve:value.reserve,gpu_layers:value.gpu||'auto',
      approved:false,new_session:!controller.session};
    const result=await controller.post('/api/v1/chat/prepare',body);
    plan={...result,body};
    if(result.state==='READY'){hideCard();controller.selectionRevision=result.selection_revision;controller.modelReady=true;return result;}
    controller.modelReady=false;pendingSend=!!sendAfter;showCard(describe(result,value));return null;
  }
  async function approvePlan(){
    if(!plan)return;
    if(plan.code==='NATIVE_SERVER_MISSING'){global.switchView?.('models');return;}
    preparing=true;const value=current();
    showCard({...describe(plan,value),title:plan.state==='NEEDS_APPROVAL'?describe(plan,value).title:'Preparing the model…',
      parts:['Checking memory and loading the model. This can take a minute; nothing else changes.']});
    el('chat-prepare-go').disabled=true;render();
    try{
      const result=await controller.post('/api/v1/chat/prepare',{...plan.body,approved:true});
      plan={...result,body:plan.body};
      await loadCatalog().catch(()=>{});
      if(result.state==='READY'){
        hideCard();controller.selectionRevision=result.selection_revision;controller.modelReady=true;
        // The approved result itself carries on (an Ollama load approval belongs to this one new chat).
        if(pendingSend){pendingSend=false;preparing=false;await submit(result);return;}
        setNotice(['Ready: ',{id:modelLabel(value)||value.model},' · ',{id:contextLabel(value.context)},'.']);
      }else showCard(describe(result,value));
    }catch(error){showCard({...describe(plan,value),error});}
    finally{preparing=false;render();}
  }
  async function createSession(ready){
    const value=current();
    const session=await controller.post('/api/v1/chat/sessions',{provider:value.provider,model:value.model,selection_revision:ready.selection_revision,
      context_budget:value.context,reply_reserve:value.reserve,load_approved:!!ready.load_approved});
    controller.session=session;controller.selectionRevision=ready.selection_revision;controller.modelReady=true;
    // Collection is this new chat's own explicit choice, made before its first message; never carried over.
    if(draftCollect){draftCollect=false;await controller.collect(true);}
    await saved();
  }

  // ------------------------------------------------------------ messages
  function bubble(role){
    const article=node('article','chat-message chatv2-msg '+role);
    article.append(node('strong','chatv2-role',role==='user'?'You':'Model'));
    return article;
  }
  function thinkingBlock(text,open){
    const details=node('details','chatv2-thinking');details.open=!!open;
    const summary=node('summary',null,'Thinking');const body=literal('div','','chatv2-thinking-text');
    body.append(document.createTextNode(text||''));
    details.append(summary,body);details.append(node('small','chatv2-thinking-note','Shown only while this page is open. Never saved or collected.'));
    return details;
  }
  function copyButton(text){const b=node('button','chatv2-copy','Copy');b.type='button';b.dataset.copy=text;return b;}
  function assistantBody(text){
    const body=node('div','chatv2-answer');body.dir='auto';body.setAttribute('translate','no');
    // Labels inside the reply (copy button) are translated here: the reply itself is never localized.
    body.append(global.NajdiMarkdown?global.NajdiMarkdown.render(text,document,{t:tr}):document.createTextNode(text));
    return body;
  }
  function renderTurn(turn){
    const user=bubble('user');user.append(literal('p',turn.user,'chatv2-text'));
    const model=bubble('assistant');
    const thinking=thinkingByRequest.get(turn.request_id);
    if(thinking)model.append(thinkingBlock(thinking,false));
    const rendered=assistantBody(turn.assistant),raw=literal('p',turn.assistant,'chatv2-text chatv2-raw');raw.hidden=true;
    model.append(rendered,raw);
    const foot=node('div','chatv2-msg-foot');
    foot.append(node('small','chat-review-status',turn.collected?'Collected for human review (not training-approved)':'Not collected for review'));
    const timings=timingsByRequest.get(turn.request_id);
    if(timings)foot.append(timingDetails(timings));
    // Exact stored reply on demand (ported from PR #21): what the model wrote, unrendered.
    const toggle=node('button','chatv2-copy chatv2-raw-toggle','Show raw text');toggle.type='button';
    toggle.onclick=()=>{raw.hidden=!raw.hidden;rendered.hidden=!rendered.hidden;toggle.textContent=raw.hidden?'Show raw text':'Show Markdown';};
    foot.append(toggle,copyButton(turn.assistant));
    model.append(foot);
    return [user,model];
  }
  const TIMING_ROWS=t=>[['Runtime check',t.engine_check_ms],['Model identity and context check',t.admission_ms],
    ['First token',t.generation?.first_token_ms],['Thinking',t.generation?.thinking_ms],['Answer',t.generation?.answer_ms],
    ['Whole generation',t.generation_total_ms],['Final check and save',t.verify_commit_ms]];
  function timingList(t){
    const list=node('dl','chatv2-dl');
    for(const [label,value] of TIMING_ROWS(t)){if(typeof value!=='number')continue;list.append(node('dt',null,label));const dd=node('dd');compose(dd,[{id:`${value} ms`}]);list.append(dd);}
    if(t.admission?.context_proof){list.append(node('dt',null,'Context proof'));list.append(node('dd',null,t.admission.context_proof==='reused'?'Reused (same engine version, model and context)':'Measured this turn'));}
    return list;
  }
  function timingDetails(t){const d=node('details','chatv2-timings');d.append(node('summary',null,'Performance details'),timingList(t));return d;}
  function renderMessages(){
    const box=el('chat-messages'),s=controller.session;
    const keepLive=live&&live.sid===s?.id?live.nodes:[];
    const nodes=[];
    for(const turn of s?.turns||[])nodes.push(...renderTurn(turn));
    if(!nodes.length&&!keepLive.length){box.replaceChildren(el('chat-empty')||emptyState());el('chat-empty').hidden=false;return;}
    const empty=el('chat-empty');if(empty)empty.hidden=true;
    box.replaceChildren(...(empty?[empty]:[]),...nodes,...keepLive);
  }
  function emptyState(){const e=node('div','chatv2-empty');e.id='chat-empty';return e;}
  function nearBottom(box){return box.scrollHeight-box.scrollTop-box.clientHeight<120;}
  function scrollDown(force){const box=el('chat-messages');if(force||nearBottom(box))box.scrollTop=box.scrollHeight;}

  /* Live turn: text nodes grow with appendData, so streaming never rebuilds the conversation. */
  function startLive(text){
    const user=bubble('user');user.append(literal('p',text,'chatv2-text'));
    const model=bubble('assistant');model.classList.add('streaming');
    const status=node('p','chatv2-live-status','Waiting for the model…');status.setAttribute('role','status');
    const thinking=thinkingBlock('',true);thinking.hidden=true;
    const answer=literal('div','','chatv2-answer chatv2-streaming-text');const answerText=document.createTextNode('');answer.append(answerText);
    model.append(status,thinking,answer);
    live={sid:controller.session.id,nodes:[user,model],model,status,thinking,thinkingText:thinking.querySelector('.chatv2-thinking-text').firstChild,
      answerText,thinkingAll:'',userToggled:false,requestId:null};
    thinking.addEventListener('toggle',()=>{if(live&&live.autoToggle!==true)live.userToggled=true;});
    const box=el('chat-messages');const empty=el('chat-empty');if(empty)empty.hidden=true;
    box.append(user,model);scrollDown(true);
  }
  function setThinkingOpen(open){if(!live)return;live.autoToggle=true;live.thinking.open=open;setTimeout(()=>{if(live)live.autoToggle=false;});}
  function onStreamEvent(event){
    if(!live)return;
    if(event.type==='accepted')live.requestId=event.request_id;
    else if(event.type==='phase'){live.status.textContent=PHASES[event.phase]||'Working…';if(event.phase==='verifying')live.status.classList.add('verifying');}
    else if(event.type==='admitted'){live.admitted={input_tokens:event.input_tokens};renderContext();}
    else if(event.type==='thinking'){
      if(live.thinking.hidden){live.thinking.hidden=false;setThinkingOpen(true);}
      live.thinkingText.appendData(event.text);live.thinkingAll+=event.text;scrollDown(false);
    }else if(event.type==='content'){
      if(!live.answerStarted){live.answerStarted=true;if(!live.thinking.hidden&&!live.userToggled)setThinkingOpen(false);}
      live.answerText.appendData(event.text);scrollDown(false);
    }
  }
  function endLive(result,error){
    if(!live)return;
    // The message was never sent: the draft stays in the box, so drop the bubble.
    if(result&&result.status==='CONTEXT_LIMIT'){live=null;lingering=[];return;}
    if(result&&result.status==='COMPLETED'){
      const turn=result.session.turns.at(-1);
      if(turn&&live.thinkingAll)thinkingByRequest.set(turn.request_id,live.thinkingAll);
      if(turn&&result.timings)timingsByRequest.set(turn.request_id,result.timings);
      live=null;return;
    }
    // Not saved: keep what was shown, clearly marked, until the next render.
    live.model.classList.remove('streaming');live.model.classList.add('incomplete');
    const label=node('p','chatv2-incomplete-label');
    compose(label,error?['Not saved — ',...errorParts(error)]:['Not saved.']);
    live.status.replaceWith(label);
    if(error&&error.code==='STOPPED')label.textContent='Stopped — this partial reply was not saved.';
    const kept=live;live=null;kept.sid=null;
    lingering=kept.nodes;
  }
  let lingering=[];

  // ------------------------------------------------------------ render
  function sendEnabled(){
    const s=controller.session,text=el('chat-draft').value;
    if(!text.trim()||controller.pending||preparing||s?.busy)return false;
    return s?s.status==='OPEN':!!selection?.model;
  }
  function render(){
    const s=controller.session,busy=controller.pending||!!s?.busy,open=s?s.status==='OPEN':true;
    el('chat-send').disabled=!sendEnabled();
    el('chat-send').hidden=busy;el('chat-stop').hidden=!busy;el('chat-stop').disabled=!busy;
    el('chat-collect').disabled=!open||busy||preparing;el('chat-collect').checked=s?!!s.collect:draftCollect;
    el('chat-actions').disabled=!s;
    el('chat-draft').setAttribute('aria-busy',busy||preparing?'true':'false');
    if(s){
      const title=s.display_title;
      if(title){el('chat-title').textContent=title;el('chat-title').setAttribute('translate','no');}
      else{el('chat-title').textContent='New chat';el('chat-title').removeAttribute('translate');}
      compose(el('chat-session-identity'),[{id:runtimeName(s.provider)},' · ',{id:modelLabel()||s.model},' · ',statusLabel(s.status)]);
    }else{
      el('chat-title').textContent='New chat';el('chat-title').removeAttribute('translate');
      el('chat-session-identity').textContent='New conversation. It is saved when you send the first message.';
    }
    renderControls();
    renderContext();
    renderLimit();
    if(!live)renderMessages();
    if(lingering.length&&!busy){el('chat-messages').append(...lingering);}
    renderNotice();
    renderListSelection();
  }
  /* Context indicator: one meter, one sentence, and a notice only when a threshold is first crossed. */
  let limit=null;
  const announced=new Map();
  function thresholds(){
    try{const t=JSON.parse(global.localStorage.getItem('najdilab.contextWarnings')||'null');return validThresholds(t)?t:CONTEXT_THRESHOLDS;}catch{return CONTEXT_THRESHOLDS;}
  }
  function renderContext(){
    const box=el('chat-context'),label=el('chat-usage'),meter=el('chat-context-meter'),alert=el('chat-context-alert');
    if(!box)return;
    // A draft shows its chosen budget too (nothing used yet); a conversation shows the engine's counts.
    const s=controller.session||(selection?.model?{id:'draft',status:'OPEN',context_budget:selection.context,reply_reserve:selection.reserve,turns:[]}:null);
    const u=contextUsage(s,live&&live.admitted);
    if(!u){box.hidden=true;alert.textContent='';alert.className='chatv2-context-alert';return;}
    const t=thresholds();
    box.hidden=false;meter.low=t.warn;meter.high=t.critical;meter.value=u.percent;
    box.dataset.level=contextLevel(u.percent,t)||'ok';
    label.textContent=`Context used: ${u.used} + ${u.reserve} reserved of ${u.budget} tokens (${u.percent}%)`;
    el('chat-context-left').textContent=u.kind==='empty'
      ?`About ${u.available} tokens available for the first message (estimate)`
      :u.availableKind==='measured'?`${u.available} tokens left after this prompt (measured)`:`About ${u.available} tokens left for the next message (estimate)`;
    const level=s.status==='OPEN'?contextLevel(u.percent,t):null,rank={info:1,warn:2,critical:3};
    const seen=announced.get(s.id)||0;
    if(level&&rank[level]>seen){
      announced.set(s.id,rank[level]);
      alert.className=`chatv2-context-alert ${level}`;
      alert.textContent={
        info:`This conversation has used ${u.percent}% of its context. About ${u.available} tokens remain for new messages.`,
        warn:`Approaching the context limit: ${u.percent}% used, about ${u.available} tokens left. Consider starting a new chat soon.`,
        critical:`Context almost full: ${u.percent}% used, about ${u.available} tokens left. A longer message will not fit; NajdiLab then keeps this conversation read-only and opens a new chat with your draft kept.`
      }[level];
    }else if(!level){alert.textContent='';alert.className='chatv2-context-alert';}
  }
  function renderLimit(){
    const box=el('chat-limit');if(!box)return;
    const s=controller.session;
    box.hidden=!limit||!s||s.id===limit.previous;
    if(box.hidden)return;
    el('chat-limit-text').textContent=`The previous conversation needed ${limit.input} prompt tokens + ${limit.reserve} reserved for the reply, more than its ${limit.budget}-token context. It is saved unchanged and read-only; nothing was summarised or dropped. This new chat starts empty, with collection off.`;
  }

  // ------------------------------------------------------------ sidebar
  function sidebarPreference(){try{return global.localStorage.getItem(SIDEBAR_KEY);}catch{return null;}}
  function setSidebar(open,store=true){
    el('chat-shell').dataset.sidebar=open?'open':'closed';
    el('chat-sidebar-toggle').setAttribute('aria-expanded',String(open));
    if(store){try{global.localStorage.setItem(SIDEBAR_KEY,open?'open':'closed');}catch{}}
  }
  const narrow=()=>global.matchMedia&&global.matchMedia('(max-width: 1100px)').matches;
  let listItems=[];
  async function saved(more=false){
    const offset=more?savedLoaded:0;
    const query=new URLSearchParams({limit:'100',offset:String(offset),archived:listMode==='archived'?'1':'0'});
    if(listQuery)query.set('q',listQuery);
    const data=await request(`/api/v1/chat/sessions?${query}`);
    listItems=more?listItems.concat(data.items):data.items;
    savedLoaded=offset+data.items.length;
    renderList();
    el('chat-saved-count').textContent=data.page.total?'':listQuery?'No conversations match this search.':listMode==='archived'?'No archived conversations.':'No saved conversations yet.';
    el('chat-saved-more').hidden=!data.page.has_more;
  }
  function renderList(){
    const nav=el('chat-list');nav.replaceChildren();
    for(const group of groupSessions(listItems)){
      const section=node('section','chatv2-group');const heading=node('h3',null,group.label);section.append(heading);
      const list=node('ul');
      for(const item of group.items){
        const li=node('li','chatv2-item');li.dataset.id=item.id;
        const open=node('button','chatv2-open');open.type='button';open.dataset.chatOpen=item.id;
        if(item.display_title)open.append(literal('span',item.display_title,'chatv2-item-title'));
        else open.append(node('span','chatv2-item-title','New chat'));
        const meta=node('small','chatv2-item-meta');
        compose(meta,[{id:modelLabel({provider:item.provider,model:item.model})||item.model}]);if(item.pinned_at)meta.prepend(node('span','chatv2-pin','Pinned'));
        open.append(meta);
        const more=node('button','chatv2-more','⋯');more.type='button';more.dataset.chatMore=item.id;
        more.setAttribute('aria-haspopup','menu');more.setAttribute('aria-expanded','false');more.setAttribute('aria-label','Conversation actions');
        li.append(open,more);list.append(li);
      }
      section.append(list);nav.append(section);
    }
    renderListSelection();
  }
  function renderListSelection(){
    for(const button of document.querySelectorAll('#chat-list [data-chat-open]')){
      const isCurrent=controller.session?.id===button.dataset.chatOpen;
      if(isCurrent)button.setAttribute('aria-current','true');else button.removeAttribute('aria-current');
    }
  }
  async function openSession(id){
    controller.session=await request(`/api/v1/chat/sessions/${id}`);
    controller.modelReady=false;draftCollect=false;plan=null;pendingSend=false;
    lingering=[];notice=[];hideCard();render();
    if(narrow())setSidebar(false,false);
    el('chat-draft').focus();
    // Explain a runtime mismatch now, before any message is sent.
    if(controller.session.status==='OPEN')await check(false).catch(error=>setNotice(errorParts(error)));
    render();
  }

  // ------------------------------------------------------------ action menu
  function menuItems(item){
    const archived=item.status==='ARCHIVED';
    for(const b of el('chat-action-menu').querySelectorAll('[data-chat-action]')){
      const a=b.dataset.chatAction;
      b.hidden=(a==='archive'&&archived)||(a==='restore'&&!archived);
      if(a==='pin')b.textContent=item.pinned_at?'Unpin':'Pin';
    }
  }
  function openMenu(anchor,item){
    menuTarget=item;menuItems(item);
    const menu=el('chat-action-menu');menu.hidden=false;
    const rect=anchor.getBoundingClientRect(),width=200;
    const rtl=document.documentElement.dir==='rtl';
    let left=rtl?rect.left:rect.right-width;left=Math.max(8,Math.min(left,global.innerWidth-width-8));
    menu.style.left=`${left+global.scrollX}px`;menu.style.top=`${rect.bottom+global.scrollY+4}px`;
    anchor.setAttribute('aria-expanded','true');menu.anchor=anchor;
    menu.querySelector('[data-chat-action]:not([hidden])').focus();
  }
  function closeMenu(focusBack=true){
    const menu=el('chat-action-menu');if(menu.hidden)return;
    menu.hidden=true;if(menu.anchor){menu.anchor.setAttribute('aria-expanded','false');if(focusBack)menu.anchor.focus();}
  }
  async function revisionOf(id){const s=await request(`/api/v1/chat/sessions/${id}`);return s;}
  async function runAction(action,item){
    closeMenu(false);
    const id=item.id;
    if(action==='rename'){
      el('chat-rename-input').value=item.title||'';el('chat-rename').showModal();el('chat-rename-input').focus();
      el('chat-rename').onclose=act(async()=>{
        if(el('chat-rename').returnValue!=='save')return;
        const value=el('chat-rename-input').value.trim();
        const s=await controller.post(`/api/v1/chat/sessions/${id}/rename`,{title:value||null});
        if(controller.session?.id===id)controller.session=s;
        await saved();render();
      });
      return;
    }
    if(action==='pin'){
      const s=await controller.post(`/api/v1/chat/sessions/${id}/pin`,{pinned:!item.pinned_at});
      if(controller.session?.id===id)controller.session=s;
      await saved();render();return;
    }
    if(action==='archive'||action==='restore'){
      const latest=await revisionOf(id);
      if(action==='archive'&&!global.confirm(tr('Archive this conversation? It is hidden from the list and its collected pairs are excluded from future dataset selection. You can restore it later.')))return;
      const s=await controller.post(`/api/v1/chat/sessions/${id}/${action}`,{revision:latest.revision});
      if(controller.session?.id===id)controller.session=s;
      setNotice(action==='archive'?'Conversation archived. You can restore it from Archived.':'Conversation restored. Collection is off; earlier collected pairs stay excluded until a new human decision.');
      await saved();render();return;
    }
    if(action==='delete')return openDelete(id);
  }

  // ------------------------------------------------------------ delete
  async function openDelete(id){
    const preview=await request(`/api/v1/chat/sessions/${id}/delete-preview`);
    const box=el('chat-delete-preview');box.replaceChildren();
    const list=node('dl','chatv2-dl');
    const row=(label,value)=>{list.append(node('dt',null,label));const dd=node('dd');compose(dd,[{id:String(value)}]);list.append(dd);};
    row('Messages to delete',preview.turns*2);
    row('Review copies to delete',preview.review_conversations-preview.review_conversations_to_redact);
    row('Reviewed copies to blank out',preview.review_conversations_to_redact);
    row('Audit events kept (no text, only status, time and a fingerprint)',preview.review_events_retained);
    if(preview.review_event_reasons_retained)row('Reviewer reasons that cannot be removed',preview.review_event_reasons_retained);
    row('Backups not changed',preview.backups_not_changed);
    box.append(list);
    if(preview.review_event_reasons_retained)box.append(node('p','chatv2-warning','Some review events have a reason written by a reviewer. Those reasons are locked by the audit trail and stay as written; check that they do not quote this conversation.'));
    if(preview.backups_not_changed)box.append(node('p','muted','Backups made earlier may still contain this conversation until you delete those backup files yourself.'));
    box.append(node('p','muted','Copies already moved to other devices or programs cannot be deleted by NajdiLab.'));
    let blocked=null;
    if(preview.busy)blocked='A reply is running in this conversation. Stop it and wait before deleting.';
    else if(preview.blocked==='EXPORTED')blocked='This conversation is already in NajdiLab exports or dataset folders, which are never rewritten. Archive it instead.';
    if(blocked){const p=node('p','chatv2-warning',blocked);box.append(p);}
    el('chat-delete-confirm').value='';el('chat-delete-error').textContent='';
    const go=el('chat-delete-go');go.disabled=true;
    el('chat-delete-confirm').oninput=()=>{go.disabled=!!blocked||el('chat-delete-confirm').value!=='DELETE';};
    go.onclick=act(async()=>{
      go.disabled=true;
      let result;
      try{
        result=await controller.post(`/api/v1/chat/sessions/${id}/delete`,{revision:preview.revision,confirm:el('chat-delete-confirm').value});
      }catch(error){compose(el('chat-delete-error'),errorParts(error));go.disabled=false;return;}
      el('chat-delete').close();
      thinkingByRequest.clear();
      if(controller.session?.id===id){controller.session=null;lingering=[];}
      // Report the real outcome: if the WAL could not be truncated, old copies can
      // remain in the -wal file until the next successful checkpoint (F4).
      setNotice(result&&result.wal_checkpoint!=='TRUNCATED'
        ?'Conversation deleted from the database, but the database journal could not be cleaned yet because another reader was using it. Old copies may remain in the journal file until NajdiLab restarts.'
        :'Conversation permanently deleted from NajdiLab\'s database.');
      await saved();render();
    });
    el('chat-delete').showModal();el('chat-delete-confirm').focus();
  }

  // ------------------------------------------------------------ chat information (read only)
  async function renderInfo(){
    const box=el('chat-info'),s=controller.session,value=current(),item=catalogItem(value);
    box.replaceChildren();
    const section=title=>{const sec=node('section');sec.append(node('h3',null,title));box.append(sec);return sec;};
    // A value is an identifier (never translated), text to translate (`false`), or compose() parts such as tokens(n).
    const rows=(sec,pairs)=>{const list=node('dl','chatv2-dl');for(const [label,v,lit] of pairs){if(v==null||v==='')continue;list.append(node('dt',null,label));const dd=node('dd');if(Array.isArray(v))compose(dd,v);else if(lit===false)dd.textContent=v;else compose(dd,[{id:String(v)}]);list.append(dd);}sec.append(list);};
    const tokens=n=>n==null?null:[{id:String(n)},' ','tokens'];
    const conv=section('Conversation');
    if(s){
      rows(conv,[['Model',modelLabel()||s.model],['Model file or name',s.model],['Runtime',runtimeName(s.provider)],['Status',statusLabel(s.status),false],
        ['Conversation ID',s.id],[s.provider==='native'?'Model identity (SHA-256)':'Model identity',s.model_fingerprint],['Conversation context budget',tokens(s.context_budget)],
        ['Reply reserve',tokens(s.reply_reserve)],['Message and history space',tokens(s.context_budget-s.reply_reserve)]]);
    }else{
      conv.append(node('p','muted','New conversation. It is saved when you send the first message.'));
      if(value?.model)rows(conv,[['Model',modelLabel(value)],['Runtime',runtimeName(value.provider)],['Conversation context budget',tokens(value.context)],['Reply reserve',tokens(value.reserve)]]);
    }
    const runtime=section('Runtime');
    if((s?.provider||value?.provider)==='native'){
      let status=null;try{status=await request('/api/v1/native/status');}catch{}
      if(status){
        const state={STOPPED:'Stopped',STARTING:'Starting',RUNNING:'Running',STOPPING:'Stopping',FAILED:'Failed'}[status.state]||status.state;
        rows(runtime,[['State',state,false],['Loaded model',status.model],['Actual loaded context',status.context?tokens(status.context):null],
          ['GPU use',status.gpu_layers],['Runtime version',status.build],['Loaded file SHA-256',status.sha256],
          ['Devices seen by llama-server',(status.devices||[]).map(d=>d.name).join(', ')||null],
          ['Measured GPU memory',typeof status.measured_vram_bytes==='number'?`${(status.measured_vram_bytes/1024**3).toFixed(2)} GiB`:null]]);
        if(status.state==='RUNNING'&&s&&(status.model!==s.model||status.context!==s.context_budget))
          runtime.append(node('p','chatv2-warning','NajdiLab Native is running a different model or context than this conversation. Sending asks to prepare it first.'));
        if(status.last_error){const p=node('p','chatv2-error');compose(p,[status.last_error.message,' ',{id:status.last_error.code}]);runtime.append(p);}
      }
      if(item)rows(runtime,[['Verification',VERIFICATION[item.verification]||item.verification,false],['Model maximum context',item.max_context?tokens(item.max_context):null]]);
    }else if(s||value?.model){
      runtime.append(node('p','muted','This runtime is managed by its own application. NajdiLab checks its context limit and model identity on every reply.'));
    }else runtime.append(node('p','muted','No model chosen yet.'));
    const usage=section('Token usage');
    if(s?.turns?.length){
      const table=node('table');const head=node('tr');for(const h of ['Turn','Prompt tokens','Reply tokens','Collected'])head.append(node('th',null,h));
      const thead=node('thead');thead.append(head);const body=node('tbody');
      s.turns.forEach((turn,index)=>{const row=node('tr');row.append(literal('td',String(index+1)),literal('td',String(turn.input_tokens)),literal('td',String(turn.output_tokens)),node('td',null,turn.collected?'Yes':'No'));body.append(row);});
      table.append(thead,body);usage.append(table);
      const u=contextUsage(s);if(u){const p=node('p','muted');compose(p,['Context used: ',{id:`${u.used} + ${u.reserve} / ${u.budget}`},' (',{id:`${u.percent}%`},')']);usage.append(p);}
      const timings=timingsByRequest.get(s.turns.at(-1).request_id);
      if(timings){usage.append(node('h4',null,'Last reply timing'),timingList(timings));}
    }else usage.append(node('p','muted','No saved turns yet.'));
    const privacy=section('Privacy and collection');
    rows(privacy,[['Collection',(s?s.collect:draftCollect)?'On for this conversation':'Off',false]]);
    privacy.append(node('p','muted','Collection is off by default and after restart; only future completed replies enter human review as pending items, never training-approved automatically. No system prompt, tools, retrieval or memory are added.'));
  }

  function act(fn){return async event=>{try{await fn(event);}catch(error){setNotice(errorParts(error));render();}};}
  function autosize(){const t=el('chat-draft');t.style.height='auto';t.style.height=Math.min(t.scrollHeight,240)+'px';}

  async function submit(prepared=null){
    const draft=el('chat-draft'),submitted=draft.value;
    if(!sendEnabled())return;
    notice=[];
    const ready=prepared||await check(true);
    if(!ready){render();return;}
    if(!controller.session)await createSession(ready);
    if(!controller.canSend(submitted))return render();
    lingering=[];
    startLive(submitted);render();
    let result=null,failure=null;
    try{result=await controller.send(submitted,onStreamEvent);}
    catch(error){failure=error;}
    endLive(result,failure);
    if(failure){const category=failureCategory(failure);setNotice(category?[category,' ',...errorParts(failure)]:errorParts(failure));}
    else if(result.status==='CONTEXT_LIMIT'){
      limit={previous:result.session.id,input:result.input_tokens,reserve:result.reply_reserve,budget:result.context_budget};
      setNotice(['Context limit reached: ',{id:`${result.input_tokens} + ${result.reply_reserve} > ${result.context_budget}`},
        '. The conversation was saved and a new empty conversation with the same settings opened. Your message was not sent and stays below.']);
    }else if(shouldClearDraft(submitted,draft.value,result.status)){draft.value='';autosize();}
    // Show the outcome at once (an unsent message's bubble disappears now), then refresh the lists.
    render();
    await saved();await loadCatalog().catch(()=>{});render();
    if(result&&result.status==='COMPLETED')scrollDown(true);
  }

  /* Model library → "Use in Chat": an empty draft with that model chosen. Nothing loads. */
  function useModel(choice){pendingUse=choice;}
  function applyPendingUse(){
    if(!pendingUse)return;
    const choice=pendingUse;pendingUse=null;
    const item=catalogItem({provider:choice.provider,model:choice.model}),base=defaultSelection();
    let context=base.context;
    if(item?.max_context&&context>item.max_context)context=Math.max(...contextOptions(item.max_context).filter(o=>o.enabled).map(o=>o.value),128);
    controller.session=null;selection={...base,provider:choice.provider,model:choice.model,context,reserve:Math.min(base.reserve,context-1)};
    storeSelection(selection);draftCollect=false;plan=null;pendingSend=false;limit=null;lingering=[];hideCard();controller.modelReady=false;
    notice=['Model chosen: ',{id:modelLabel(selection)||choice.model},'. ','Pick a context if needed, then send; NajdiLab asks before loading anything.'];
  }

  async function load(){
    if(!bound)bind();
    if(selection===null)selection=defaultSelection();
    // A refresh replaces stale notices, so a current binding warning is never hidden.
    notice=[];
    try{
      await loadCatalog();
      applyPendingUse();
      if(controller.session){await controller.refresh();if(controller.session.status==='OPEN'&&!controller.pending)await check(false).catch(()=>{});}
      await saved();render();
    }finally{
      // The view is busy from page load until its controls are bound and the first catalog is shown: assistive
      // technology waits, and so do tests (a click before this landed on a button with no handler yet).
      el('view-chat').setAttribute('aria-busy','false');
    }
  }

  function menuKeys(panel){
    panel.addEventListener('keydown',event=>{
      const items=[...panel.querySelectorAll('button:not([hidden]),input:not(:disabled),select,summary')],at=items.indexOf(document.activeElement);
      if(event.key==='Escape'){event.preventDefault();closePopover();}
      else if(panel.getAttribute('role')==='menu'&&event.key==='ArrowDown'){event.preventDefault();items[(at+1)%items.length]?.focus();}
      else if(panel.getAttribute('role')==='menu'&&event.key==='ArrowUp'){event.preventDefault();items[(at-1+items.length)%items.length]?.focus();}
      else if(event.key==='Tab'&&panel.getAttribute('role')==='menu')closePopover(false);
    });
  }

  function bind(){
    bound=true;
    el('chat-limit-open').onclick=async()=>{const previous=limit&&limit.previous;if(previous){limit=null;await openSession(previous);}};
    const pref=sidebarPreference();
    setSidebar(narrow()?false:pref!=='closed',false);
    if(global.matchMedia){
      const query=global.matchMedia('(max-width: 1100px)');
      const change=()=>setSidebar(query.matches?false:sidebarPreference()!=='closed',false);
      if(query.addEventListener)query.addEventListener('change',change);
    }
    el('chat-sidebar-toggle').onclick=()=>setSidebar(el('chat-shell').dataset.sidebar!=='open',!narrow());
    el('chat-sidebar-close').onclick=()=>{setSidebar(false,!narrow());el('chat-sidebar-toggle').focus();};
    el('chat-new').onclick=()=>newChat();
    el('chat-new-header').onclick=()=>newChat();
    el('chat-model-button').onclick=act(async()=>{
      if(popover?.panel===el('chat-model-menu'))return closePopover();
      await loadCatalog();renderModelMenu();
      const checked=el('chat-model-menu').querySelector('[aria-checked="true"]');
      openPopover(el('chat-model-menu'),el('chat-model-button'),checked);
    });
    el('chat-context-button').onclick=()=>{
      if(popover?.panel===el('chat-context-menu'))return closePopover();
      renderContextMenu();openPopover(el('chat-context-menu'),el('chat-context-button'),el('chat-context-menu').querySelector('input:checked')||undefined);
    };
    menuKeys(el('chat-model-menu'));menuKeys(el('chat-context-menu'));
    for(const id of ['chat-budget','chat-reserve'])el(id).oninput=updateBreakdown;
    el('chat-budget-apply').onclick=act(async()=>{
      const value=current()||defaultSelection();
      const next={...value,context:Number(el('chat-budget').value),reserve:Number(el('chat-reserve').value),gpu:el('chat-gpu').value};
      closePopover();await choose(next);
    });
    el('chat-gpu').onchange=()=>{if(!controller.session){selection={...current(),gpu:el('chat-gpu').value};storeSelection(selection);}};
    document.addEventListener('mousedown',event=>{if(popover&&!popover.panel.contains(event.target)&&!popover.anchor.contains(event.target))closePopover(false);});
    global.addEventListener('resize',()=>{if(popover)placePopover(popover.panel,popover.anchor);});
    el('chat-prepare-go').onclick=act(approvePlan);
    el('chat-prepare-cancel').onclick=()=>{pendingSend=false;hideCard();el('chat-draft').focus();};
    let searchTimer=null;
    el('chat-search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(act(async()=>{listQuery=el('chat-search').value.trim();await saved();}),200);};
    for(const [id,mode] of [['chat-show-active','active'],['chat-show-archived','archived']])el(id).onclick=act(async()=>{
      listMode=mode;el('chat-show-active').setAttribute('aria-pressed',String(mode==='active'));el('chat-show-archived').setAttribute('aria-pressed',String(mode==='archived'));await saved();
    });
    el('chat-saved-more').onclick=act(async()=>{await saved(true);});
    el('chat-list').addEventListener('click',act(async event=>{
      const openButton=event.target.closest('[data-chat-open]');
      if(openButton)return openSession(openButton.dataset.chatOpen);
      const more=event.target.closest('[data-chat-more]');
      if(more){const item=listItems.find(x=>x.id===more.dataset.chatMore);if(item)openMenu(more,item);}
    }));
    el('chat-actions').onclick=act(async()=>{const s=controller.session;if(s)openMenu(el('chat-actions'),s);});
    el('chat-action-menu').addEventListener('click',act(async event=>{
      const button=event.target.closest('[data-chat-action]');if(button&&menuTarget)await runAction(button.dataset.chatAction,menuTarget);
    }));
    el('chat-action-menu').addEventListener('keydown',event=>{
      const items=[...el('chat-action-menu').querySelectorAll('[data-chat-action]:not([hidden])')],at=items.indexOf(document.activeElement);
      if(event.key==='Escape'){event.preventDefault();closeMenu();}
      else if(event.key==='ArrowDown'){event.preventDefault();items[(at+1)%items.length].focus();}
      else if(event.key==='ArrowUp'){event.preventDefault();items[(at-1+items.length)%items.length].focus();}
      else if(event.key==='Tab')closeMenu(false);
    });
    document.addEventListener('click',event=>{if(!event.target.closest('#chat-action-menu,[data-chat-more],#chat-actions'))closeMenu(false);});
    el('chat-info-open').onclick=act(async()=>{el('chat-panel').showModal();await renderInfo();});
    el('chat-panel-close').onclick=()=>el('chat-panel').close();
    window.addEventListener('najdilab:languagechange',()=>{renderList();render();});
    el('chat-draft').addEventListener('input',autosize);
    // In a method="dialog" form, Enter would press the first button (Cancel/close).
    el('chat-rename-input').addEventListener('keydown',event=>{if(keyAction(event)==='send'){event.preventDefault();el('chat-rename').close('save');}});
    el('chat-delete-confirm').addEventListener('keydown',event=>{if(keyAction(event)==='send'){event.preventDefault();if(!el('chat-delete-go').disabled)el('chat-delete-go').click();}});
    let composing=false;
    el('chat-draft').addEventListener('compositionstart',()=>{composing=true;});
    el('chat-draft').addEventListener('compositionend',()=>{composing=false;});
    el('chat-draft').addEventListener('input',()=>{el('chat-send').disabled=!sendEnabled();});
    el('chat-draft').addEventListener('keydown',event=>{
      const action=composing?'compose':keyAction(event);
      // A held Enter never inserts a stray newline into a ready message, and never sends.
      if(action==='repeat'){event.preventDefault();return;}
      if(action!=='send')return;
      event.preventDefault();
      submit(null).catch(error=>{setNotice(errorParts(error));render();});
    });
    el('chat-form').onsubmit=event=>{event.preventDefault();submit(null).catch(error=>{setNotice(errorParts(error));render();});};
    el('chat-stop').onclick=act(async()=>{await controller.stop();if(live)live.status.textContent='Stopping… nothing from this reply will be saved.';});
    el('chat-collect').onchange=act(async()=>{
      const on=el('chat-collect').checked;
      if(controller.session)await controller.collect(on);else draftCollect=on;
      setNotice(on?'Collection is on for this conversation until you turn it off or NajdiLab restarts. Only future completed replies enter human review.':'Collection is off for this conversation.');
      render();
    });
    el('chat-messages').addEventListener('click',event=>{
      const button=event.target.closest('[data-copy],[data-code]');if(!button)return;
      const text=button.dataset.copy??button.dataset.code;
      const done=()=>{const before=button.textContent;button.textContent='Copied';setTimeout(()=>{button.textContent=before;},1500);};
      if(global.navigator.clipboard)global.navigator.clipboard.writeText(text).then(done,()=>{});
    });
  }
  global.NajdiChat={load,useModel};
  document.addEventListener('DOMContentLoaded',()=>{
    const form=el('context-warnings-form'),ids={info:'context-warn-info',warn:'context-warn-warn',critical:'context-warn-critical'};
    if(form){
      const saved=thresholds();for(const [key,id] of Object.entries(ids))el(id).value=saved[key];
      form.onsubmit=event=>{
        event.preventDefault();
        const value=Object.fromEntries(Object.entries(ids).map(([key,id])=>[key,Number(el(id).value)]));
        const status=el('context-warnings-status');
        if(!validThresholds(value)){status.textContent='Use whole numbers from 1 to 99 that increase from Information to Critical.';return;}
        try{global.localStorage.setItem('najdilab.contextWarnings',JSON.stringify(value));status.textContent='Context warnings saved.';}
        catch{status.textContent='This browser blocks local storage, so the default warnings (70, 85, 95) stay in use.';}
      };
    }
    const legacy=el('chat-legacy-providers');
    if(legacy){legacy.checked=legacyProviders();legacy.onchange=()=>{try{global.localStorage.setItem(LEGACY_PROVIDERS_KEY,legacy.checked?'1':'0');}catch{}};}
    // What the chosen version is ready for, before anything is exported.
    const READY_TEXT={VALID:'Valid',INVALID:'Invalid',STRUCTURE_CHECKED:'Structure checked',BLOCKED:'Blocked',NO_EVALUATION_DATA:'No evaluation data',
      LEAKAGE_DETECTED:'Leakage detected',INDEPENDENT_SAMPLES_AVAILABLE:'Independent samples',technical_smoke_test:'Technical smoke test',
      small_exploratory:'Small exploratory',measurable_evaluation:'Measurable evaluation'};
    async function showReadiness(){
      const version=el('unsloth-version').value,host=el('unsloth-readiness');host.replaceChildren();
      if(!version)return;
      try{
        const health=await api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/health`),r=health.readiness,s=health.statistics;
        const line=(label,value)=>{const p=document.createElement('p');p.append(label,' ');const b=document.createElement('strong');b.textContent=READY_TEXT[value]||value;p.append(b);return p;};
        host.append(line('Structural validity:',r.structural.status),line('Training compatibility:',r.training_compatibility.status),
          line('Evaluation readiness:',r.evaluation.status),line('Dataset stage:',s.stage));
        const facts=document.createElement('p');
        compose(facts,[{id:String(s.training_records)},' ','training records',' · ',{id:String(s.independent_source_conversations)},' ','independent source conversations']);
        host.append(facts);
        if(r.evaluation.status==='NO_EVALUATION_DATA'){const warn=document.createElement('p');warn.className='warning';warn.textContent='No independent evaluation samples: training on this version can run, but it cannot show a quality change.';host.append(warn);}
      }catch(error){host.textContent=error.message;}
    }
    el('unsloth-version').addEventListener('change',showReadiness);
    el('unsloth-create').onclick=async()=>{
      const button=el('unsloth-create'),host=el('unsloth-result');button.disabled=true;host.replaceChildren();
      try{
        const profile=document.querySelector('input[name="unsloth-profile"]:checked')?.value||'studio_chat';
        const data=await api('/api/v1/unsloth-exports',{method:'POST',body:JSON.stringify({version:el('unsloth-version').value.trim(),profile})});
        host.className='unsloth-result';
        const summary=document.createElement('p');
        compose(summary,[{id:String(data.record_count)},' ','training records',' · ',{id:String(data.independent_source_conversations)},' ','independent source conversations',' · ',data.target_trainer]);
        host.append(summary);
        const settings=document.createElement('p');
        compose(settings,['Trainer settings:',' ',{id:Object.entries(data.trainer_requirements).map(([k,v])=>`${k}=${v}`).join(', ')}]);
        host.append(settings);
        if(data.warnings.length){const list=document.createElement('ul');list.className='unsloth-result-list';for(const text of data.warnings)list.append(node('li',null,text));host.append(list);}
        const check=document.createElement('p');
        compose(check,['Token-level check: not run by NajdiLab. With your Unsloth Studio Python, run',' ',{id:`scripts/verify_unsloth_studio.py ${data.directory} --model <training model>`}]);
        host.append(check);
        for(const name of ['dataset.jsonl','provenance.jsonl','manifest.json']){
          const link=document.createElement('a');link.textContent=`Download ${name} `;link.href=`/api/v1/unsloth-exports/${data.id}/${name}`;link.download=name;host.append(link);
        }
      }catch(error){host.textContent=error.message;}finally{button.disabled=false;}
    };
  });
})(typeof window!=='undefined'?window:globalThis);
