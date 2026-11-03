/* Chat V2. Controls own only NajdiLab sessions; the server owns consent, admission
 * and what is saved. Streamed text is display-only until the server's final
 * `done` event returns the committed session. */
(function(global){
  'use strict';
  const PRESETS={light:{context_budget:4096,reply_reserve:1024},balanced:{context_budget:8192,reply_reserve:2048},long:{context_budget:16384,reply_reserve:3072}};
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
  /* Presets are offered only with evidence (ported from PR #21): a proven engine
     ceiling at least as large, and an estimate for exactly that context that fits
     free GPU memory. Estimates stay labelled unverified; Custom is always available. */
  const PRESET_LABELS={light:'Light',balanced:'Balanced',long:'Long'};
  function budgetPresets(snapshot){
    const r=snapshot?.recommendation||{},ceiling=r.budget_ceiling;
    return Object.entries(PRESETS).map(([id,p])=>{
      const estimate=r.candidates?.find(c=>c.context===p.context_budget);
      const reason=!Number.isInteger(ceiling)||ceiling<1?'Engine ceiling unknown':p.context_budget>ceiling?'Above engine ceiling'
        :!estimate||!Number.isFinite(estimate.estimated_required_bytes)||estimate.estimated_required_bytes<=0?'Memory estimate unavailable'
        :estimate.assessment!=='ESTIMATE_FITS_FREE_VRAM'?'Memory estimate does not fit':'Unverified memory estimate';
      return {id,label:PRESET_LABELS[id],context:p.context_budget,reply:p.reply_reserve,enabled:reason==='Unverified memory estimate',reason,estimatedBytes:estimate?.estimated_required_bytes};
    });
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

  function presetFor(context,reserve){
    return Object.entries(PRESETS).find(([,p])=>p.context_budget===context&&p.reply_reserve===reserve)?.[0]||'custom';
  }

  const gib=n=>typeof n==='number'?`${(n/1024**3).toFixed(1)} GiB`:null;
  /* Structured device/model evidence. Each value says whether it was measured,
     estimated or is unknown: an estimate must never read as a measurement. */
  function hardwareModel(data){
    const r=data.recommendation||{},m=data.model||{},seen=r.measured||null;
    const device=[
      {label:'RAM available',value:gib(data.ram_available_bytes),of:gib(data.ram_total_bytes),kind:data.ram_total_bytes==null?'unknown':'measured'},
      ...(data.gpus||[]).map(g=>({label:'GPU',name:g.name,value:gib(g.free_bytes),of:gib(g.total_bytes),kind:'measured'}))
    ];
    if(!(data.gpus||[]).length)device.push({label:'GPU',value:null,kind:'unknown'});
    const model=[
      {label:'Architecture',value:m.architecture||null,kind:m.architecture?'reported':'unknown'},
      {label:'Quantization',value:m.quantization||null,kind:m.quantization?'reported':'unknown'},
      {label:'Weights size',value:gib(m.weights_bytes),kind:m.weights_bytes?'reported':'unknown'},
      {label:'Maximum context',value:r.model_max_context??null,kind:r.model_max_context?'reported':'unknown'},
      {label:'Proven engine ceiling',value:Number.isInteger(r.budget_ceiling)&&r.budget_ceiling>0?r.budget_ceiling:null,kind:Number.isInteger(r.budget_ceiling)&&r.budget_ceiling>0?'reported':'unknown'},
      {label:'Loaded context now',value:r.runtime_context??null,kind:r.runtime_context?'measured':'unknown'}
    ];
    if(seen&&typeof seen.size_vram_bytes==='number')model.push({label:'Measured memory now',value:gib(seen.size_vram_bytes),kind:'measured'});
    const estimates=(r.candidates||[]).map(c=>({context:c.context,value:gib(c.estimated_required_bytes),kind:'estimate',
      assessment:{ABOVE_MODEL_MAX:'Above model maximum',ESTIMATE_FITS_FREE_VRAM:'May fit in free GPU memory',ESTIMATE_EXCEEDS_FREE_VRAM:'Likely exceeds free GPU memory'}[c.assessment]||'Unknown'}));
    return {device,model,estimates,status:r.status||'INSUFFICIENT_EVIDENCE',recommended:r.recommended_context||null,
      reason:r.reason||null,otherModels:m.other_loaded_models||[],systemPrompt:!!m.model_system_prompt,
      processes:typeof data.gpu_compute_processes==='number'?data.gpu_compute_processes:null};
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
    module.exports={ChatController,ChatError,keyAction,shouldSendOnEnter,canSend,validBudgets,budgetPresets,shouldClearDraft,groupSessions,budgetBreakdown,presetFor,hardwareModel,ndjsonSplitter,errorParts,PRESETS,PHASES,
      contextUsage,contextLevel,validThresholds,failureCategory,CONTEXT_THRESHOLDS};
    return;
  }

  // ======================================================================= DOM
  const el=id=>document.getElementById(id);
  const tr=text=>global.NajdiI18n?global.NajdiI18n.t(text):text;
  let runtimes=[],nativeState=null,bound=false,notice=[];
  let listMode='active',listQuery='',savedLoaded=0,menuTarget=null,live=null;
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

  // literal=true marks identifiers (model, provider, session) that the localizer must not translate.
  function option(select,value,label,literal=false){const item=new Option(label,value);if(literal)item.setAttribute('translate','no');select.add(item);}
  function compose(target,parts){target.replaceChildren(...parts.map(part=>{if(typeof part==='string')return document.createTextNode(part);const id=document.createElement('bdi');id.dir='ltr';id.setAttribute('translate','no');id.textContent=part.id;return id;}));}
  function node(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
  function literal(tag,text,cls){const e=node(tag,cls,text);e.dir='auto';e.setAttribute('translate','no');return e;}
  function setNotice(parts){notice=Array.isArray(parts)?parts:[parts];renderNotice();}
  function renderNotice(){
    const s=controller.session,busy=controller.pending||s?.busy;
    if(notice.length&&!(notice.length===1&&notice[0]===''))return compose(el('chat-notice'),notice);
    const ready=sessionRuntimeReady();
    const text=busy?'':
      s&&s.status==='OPEN'&&!ready?'This conversation is bound to its original model and runtime. Connect and select that exact model to continue; nothing was changed automatically.':
      s&&s.status==='CONTEXT_LIMIT'?'This conversation reached its context limit. Start a new chat to continue.':
      s&&s.status==='ARCHIVED'?'This conversation is archived. Restore it to continue.':'';
    el('chat-notice').textContent=text;
  }

  function sessionRuntime(s=controller.session){return s&&runtimes.find(p=>p.id===s.provider);}
  function sessionRuntimeReady(){const s=controller.session,p=sessionRuntime();return !!p&&p.selected_model===s?.model;}

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
  function timingDetails(t){
    const d=node('details','chatv2-timings');d.append(node('summary',null,'Performance details'));
    const rows=[['Runtime check',t.engine_check_ms],['Model identity and context check',t.admission_ms],
      ['First token',t.generation?.first_token_ms],['Thinking',t.generation?.thinking_ms],['Answer',t.generation?.answer_ms],
      ['Whole generation',t.generation_total_ms],['Final check and save',t.verify_commit_ms]];
    const list=node('dl','chatv2-dl');
    for(const [label,value] of rows){if(typeof value!=='number')continue;list.append(node('dt',null,label));const dd=node('dd');compose(dd,[{id:`${value} ms`}]);list.append(dd);}
    if(t.admission?.context_proof){list.append(node('dt',null,'Context proof'));list.append(node('dd',null,t.admission.context_proof==='reused'?'Reused (same engine version, model and context)':'Measured this turn'));}
    d.append(list);return d;
  }
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
  function render(){
    const s=controller.session,busy=controller.pending||!!s?.busy,open=s?.status==='OPEN';
    const ready=sessionRuntimeReady();
    controller.modelReady=ready;
    el('chat-send').disabled=!controller.canSend(el('chat-draft').value);
    el('chat-stop').disabled=!busy;
    el('chat-collect').disabled=!open||busy;el('chat-collect').checked=!!s?.collect;
    el('chat-actions').disabled=!s;
    el('chat-draft').setAttribute('aria-busy',busy?'true':'false');
    if(s){
      const title=s.display_title;
      if(title){el('chat-title').textContent=title;el('chat-title').setAttribute('translate','no');}
      else{el('chat-title').textContent='New chat';el('chat-title').removeAttribute('translate');}
      compose(el('chat-session-identity'),[{id:runtimeName(s.provider)},' · ',{id:s.model},' · ',
        statusLabel(s.status),' · ','Context ',{id:String(s.context_budget)},' · ','Reply ',{id:String(s.reply_reserve)}]);
    }else{
      el('chat-title').textContent='New chat';el('chat-title').removeAttribute('translate');
      el('chat-session-identity').textContent='No conversation selected.';
    }
    renderContext();
    renderLimit();
    if(!live)renderMessages();
    if(lingering.length&&!busy){el('chat-messages').append(...lingering);}
    renderNotice();
    renderListSelection();
  }
  function runtimeName(id){return {lmstudio:'LM Studio',ollama:'Ollama',native:'NajdiLab Native'}[id]||id;}
  /* Context indicator: one meter, one sentence, and a notice only when a threshold is first crossed. */
  let limit=null;
  const announced=new Map();
  function thresholds(){
    try{const t=JSON.parse(global.localStorage.getItem('najdilab.contextWarnings')||'null');return validThresholds(t)?t:CONTEXT_THRESHOLDS;}catch{return CONTEXT_THRESHOLDS;}
  }
  function renderContext(){
    const box=el('chat-context'),label=el('chat-usage'),meter=el('chat-context-meter'),alert=el('chat-context-alert');
    if(!box)return;
    const s=controller.session,u=contextUsage(s,live&&live.admitted);
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
  function statusLabel(status){return {OPEN:'Open',CONTEXT_LIMIT:'Context limit reached',ARCHIVED:'Archived'}[status]||status;}

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
        compose(meta,[{id:item.model}]);if(item.pinned_at)meta.prepend(node('span','chatv2-pin','Pinned'));
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
      const current=controller.session?.id===button.dataset.chatOpen;
      if(current)button.setAttribute('aria-current','true');else button.removeAttribute('aria-current');
    }
  }
  async function openSession(id){
    controller.session=await request(`/api/v1/chat/sessions/${id}`);
    controller.selectionRevision=sessionRuntime()?.selection_revision??null;
    lingering=[];notice=[];render();
    if(narrow())setSidebar(false,false);
    el('chat-draft').focus();
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
      const current=await revisionOf(id);
      if(action==='archive'&&!global.confirm(tr('Archive this conversation? It is hidden from the list and its collected pairs are excluded from future dataset selection. You can restore it later.')))return;
      const s=await controller.post(`/api/v1/chat/sessions/${id}/${action}`,{revision:current.revision});
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

  // ------------------------------------------------------------ setup dialog
  function providerSelect(){return runtimes.find(x=>x.id===el('chat-provider').value);}
  let presetEvidence=null;
  function evidenceKey(){const p=providerSelect();return JSON.stringify([p?.id,el('chat-model').value,p?.selection_revision]);}
  function currentEvidence(){return presetEvidence?.key===evidenceKey()?presetEvidence.data:undefined;}
  // Approval to load is tied to one model and one context: any change withdraws it.
  function withdrawApproval(){el('chat-load-approved').checked=false;}
  function renderPresets(){
    const evidence=currentEvidence();
    for(const p of budgetPresets(evidence)){
      const radio=document.querySelector(`input[name="chat-preset"][value="${p.id}"]`);if(!radio)continue;
      radio.disabled=!p.enabled;if(!p.enabled&&radio.checked)document.querySelector('input[name="chat-preset"][value="custom"]').checked=true;
      const reason=radio.parentElement.querySelector('.chatv2-preset-reason');if(reason)reason.textContent=p.reason;
    }
    const r=evidence?.recommendation;
    if(r)compose(el('chat-preset-evidence'),['Proven engine ceiling: ',{id:Number.isInteger(r.budget_ceiling)&&r.budget_ceiling>0?String(r.budget_ceiling):'Unknown'}]);
    else el('chat-preset-evidence').textContent='Presets unlock after checking this model. The engine ceiling and memory estimate are unknown until then; Custom is always available.';
  }
  function fillModels(){
    const p=providerSelect();el('chat-model').replaceChildren();
    for(const model of p?.models||[])option(el('chat-model'),model,model,true);
    if(p?.selected_model)el('chat-model').value=p.selected_model;
    el('chat-load-row').hidden=p?.id!=='ollama';withdrawApproval();
    renderPresets();updateBreakdown();
  }
  /* Read-only: never selects or loads a model, even if another model is highlighted. */
  async function checkPresets(){
    const p=providerSelect(),model=el('chat-model').value,key=evidenceKey();
    if(!p||!model)throw new ChatError('Connect and select a model first.','NOT_CONNECTED');
    const data=await request('/api/v1/chat/hardware',{method:'POST',body:JSON.stringify({approved:true,provider:p.id,model,selection_revision:p.selection_revision})});
    presetEvidence={key,data};renderPresets();
  }
  function readBudget(){return {context:Number(el('chat-budget').value),reserve:Number(el('chat-reserve').value)};}
  function applyPreset(name){
    const preset=PRESETS[name];if(!preset){el('chat-advanced').open=true;return updateBreakdown();}
    el('chat-budget').value=preset.context_budget;el('chat-reserve').value=preset.reply_reserve;updateBreakdown();
  }
  function updateBreakdown(){
    const {context,reserve}=readBudget(),b=budgetBreakdown(context,reserve,currentEvidence()?.recommendation?.model_max_context||null);
    b.valid=b.valid&&validBudgets(context,reserve);
    const box=el('chat-budget-breakdown');box.replaceChildren();
    const list=node('dl','chatv2-dl');
    const row=(label,value)=>{list.append(node('dt',null,label));const dd=node('dd');compose(dd,[{id:value==null?'—':String(value)}]);list.append(dd);};
    row('Total context',b.context);row('Message and history space',b.input);row('Reply and thinking space',b.reserve);
    box.append(list);for(const w of b.warnings)box.append(node('p','chatv2-warning',w));
    el('chat-create').disabled=!b.valid;
  }
  async function selectModel(p,model){
    if(p.id==='native'||p.selected_model===model)return p.selection_revision;
    const snap=await request(`/api/v1/integrations/${p.id}/select`,{method:'POST',body:JSON.stringify({approved:true,model})});
    Object.assign(p,snap.items.find(x=>x.id===p.id));
    return p.selection_revision;
  }
  function openSetup(){
    el('chat-setup-error').textContent='';
    const previous=el('chat-provider').value;el('chat-provider').replaceChildren();
    for(const p of runtimes)option(el('chat-provider'),p.id,p.name,true);
    if(runtimes.some(p=>p.id===previous))el('chat-provider').value=previous;
    fillModels();
    el('chat-provider-note').hidden=runtimes.length>0;
    renderPresets();
    const checked=document.querySelector('input[name="chat-preset"]:checked:not(:disabled)');applyPreset(checked?.value||'custom');
    el('chat-setup').showModal();
  }
  async function createSession(){
    const p=providerSelect(),model=el('chat-model').value,{context,reserve}=readBudget();
    if(!p||!model)throw new ChatError('Connect and select a model first.','NOT_CONNECTED');
    if(!validBudgets(context,reserve))throw new ChatError('Reply space must be between 1 and 8192 tokens and smaller than the total context.','INVALID_LIMIT');
    const revision=await selectModel(p,model);
    const session=await controller.post('/api/v1/chat/sessions',{provider:p.id,model,selection_revision:revision,
      context_budget:context,reply_reserve:reserve,load_approved:p.id==='ollama'&&el('chat-load-approved').checked});
    controller.session=session;controller.selectionRevision=revision;
    el('chat-load-approved').checked=false;lingering=[];notice=[];
    el('chat-setup').close();await saved();render();el('chat-draft').focus();
  }

  // ------------------------------------------------------------ settings drawer
  function renderDetails(){
    const box=el('chat-details'),s=controller.session;box.replaceChildren();
    if(!s){box.append(node('p','muted','No conversation selected.'));return;}
    const list=node('dl','chatv2-dl');
    const row=(label,value)=>{list.append(node('dt',null,label));const dd=node('dd');compose(dd,[{id:String(value??'—')}]);list.append(dd);};
    row('Runtime',runtimeName(s.provider));row('Model',s.model);row('Conversation ID',s.id);
    list.append(node('dt',null,'Status'));list.append(node('dd',null,statusLabel(s.status)));
    row('Total context',s.context_budget);row('Message and history space',s.context_budget-s.reply_reserve);row('Reply and thinking space',s.reply_reserve);
    const last=s.turns?.at(-1);
    if(last)row('Last turn tokens (prompt + reply)',`${last.input_tokens} + ${last.output_tokens}`);
    if(s.model_fingerprint)row('Model identity',s.model_fingerprint);
    box.append(list);
  }
  function evidence(kind){
    return {measured:'Measured',reported:'Reported by the runtime',estimate:'Estimate',unknown:'Unknown'}[kind]||'Unknown';
  }
  function renderHardware(data){
    const view=hardwareModel(data),box=el('chat-hardware-result');box.replaceChildren();
    const card=(title,rows,columns)=>{
      const section=node('section','chatv2-card');section.append(node('h3',null,title));
      const table=node('table','chatv2-table');const head=node('tr');for(const c of columns)head.append(node('th',null,c));
      const thead=node('thead');thead.append(head);const tbody=node('tbody');
      for(const r of rows){const tr=node('tr');for(const cell of r){const td=node('td');if(cell&&typeof cell==='object'&&'id' in cell)compose(td,[cell]);else td.textContent=cell??'Unknown';tr.append(td);}tbody.append(tr);}
      table.append(thead,tbody);section.append(table);box.append(section);
    };
    card('Device',view.device.map(d=>[d.label,d.name?{id:d.name}:'—',d.value?{id:d.of?`${d.value} / ${d.of}`:d.value}:'Unknown',evidence(d.kind)]),['Item','Name','Free / total','Evidence']);
    card('Model',view.model.map(m=>[m.label,m.value==null?'Unknown':{id:String(m.value)},evidence(m.kind)]),['Item','Value','Evidence']);
    if(view.estimates.length)card('Memory estimates by context',view.estimates.map(e=>[{id:String(e.context)},e.value?{id:e.value}:'Unknown',e.assessment]),['Context','Estimated need','Assessment']);
    const note=node('p','muted');
    if(view.recommended)compose(note,['Largest estimated fit: ',{id:String(view.recommended)},'. Unverified estimate, not a guaranteed safe limit. No allocation test was run.']);
    else note.textContent='No reliable recommendation. Estimates need the model size, layer sizes and free GPU memory.';
    box.append(note);
    if(view.systemPrompt)box.append(node('p','muted','This model defines its own system prompt. That is part of the model, not added by NajdiLab.'));
    if(view.otherModels.length){const p=node('p','muted');compose(p,['Also loaded in this runtime: ',{id:view.otherModels.join(', ')}]);box.append(p);}
    if(view.processes!=null){const p=node('p','muted');compose(p,['Other GPU compute processes now: ',{id:String(view.processes)}]);box.append(p);}
  }
  async function readHardware(nativeModel){
    const s=controller.session,body={approved:true};
    if(nativeModel)body.native_model=nativeModel;
    else if(s&&sessionRuntimeReady())Object.assign(body,{provider:s.provider,model:s.model,selection_revision:controller.selectionRevision});
    renderHardware(await controller.post('/api/v1/chat/hardware',body));
  }
  async function loadNative(){
    const [status,models]=await Promise.all([request('/api/v1/native/status'),request('/api/v1/native/models')]);
    nativeState=status;
    const box=el('chat-native-status');box.replaceChildren();
    const list=node('dl','chatv2-dl');
    const row=(label,value)=>{list.append(node('dt',null,label));const dd=node('dd');compose(dd,[{id:String(value??'—')}]);list.append(dd);};
    list.append(node('dt',null,'State'));list.append(node('dd',null,{STOPPED:'Stopped',STARTING:'Starting',RUNNING:'Running',STOPPING:'Stopping',FAILED:'Failed'}[status.state]||status.state));
    row('llama-server',status.server_available?status.server_path:'Not found');row('Models folder',status.models_dir);
    if(status.state==='RUNNING'){row('Model',status.model);row('Context',status.context);row('GPU layers',status.gpu_layers);
      row('Measured GPU memory',typeof status.measured_vram_bytes==='number'?`${(status.measured_vram_bytes/1024**3).toFixed(2)} GiB`:'Unknown');row('Build',status.build);}
    if(status.devices?.length)row('Devices seen by llama-server',status.devices.map(d=>d.name).join(', '));
    box.append(list);
    if(status.last_error){const p=node('p','chatv2-error');compose(p,[status.last_error.message,' ',{id:status.last_error.code}]);box.append(p);}
    if(!status.server_available)box.append(node('p','muted','Set NAJDILAB_NATIVE_SERVER to the path of an existing llama-server, then restart NajdiLab.'));
    const select=el('chat-native-model');select.replaceChildren();
    for(const m of models.items){
      const label=m.valid?`${m.id} · ${m.quantization||'?'} · ${m.model_max_context||'?'}`:`${m.id} · ${m.error}`;
      option(select,m.id,label,true);if(!m.valid)select.options[select.options.length-1].disabled=true;
    }
    if(!models.items.length)option(select,'','No GGUF files in the models folder');
    el('chat-native-start').disabled=status.state==='RUNNING'||!status.server_available||!models.items.some(m=>m.valid);
    el('chat-native-stop').disabled=status.state!=='RUNNING';
  }
  async function loadRuntimes(){
    const items=(await request('/api/v1/integrations')).items.filter(x=>x.kind==='model_runtime'&&x.connection==='CONNECTED');
    let native=null;
    try{native=await request('/api/v1/native/status');}catch{native=null;}
    nativeState=native;
    if(native&&native.state==='RUNNING')items.push({id:'native',name:'NajdiLab Native',models:[native.model],selected_model:native.model,selection_revision:native.revision});
    runtimes=items;
    if(controller.session)controller.selectionRevision=sessionRuntime()?.selection_revision??null;
  }
  async function load(){
    if(!bound)bind();
    // A refresh replaces stale notices, so a current binding warning is never hidden.
    notice=[];
    await loadRuntimes();
    if(controller.session)await controller.refresh();
    await saved();render();
  }

  function act(fn){return async event=>{try{await fn(event);}catch(error){setNotice(errorParts(error));render();}};}
  function autosize(){const t=el('chat-draft');t.style.height='auto';t.style.height=Math.min(t.scrollHeight,240)+'px';}

  async function submit(){
    const draft=el('chat-draft'),submitted=draft.value;
    if(!controller.canSend(submitted)||!sessionRuntimeReady())return;
    notice=[];lingering=[];
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
    await saved();render();
    if(result&&result.status==='COMPLETED')scrollDown(true);
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
    el('chat-new').onclick=act(async()=>{await loadRuntimes();openSetup();});
    el('chat-new-header').onclick=act(async()=>{await loadRuntimes();openSetup();});
    el('chat-provider').onchange=fillModels;
    el('chat-model').onchange=()=>{withdrawApproval();renderPresets();updateBreakdown();};
    el('chat-preset-check').onclick=async()=>{el('chat-setup-error').textContent='';try{await checkPresets();}catch(error){compose(el('chat-setup-error'),errorParts(error));}};
    for(const radio of document.querySelectorAll('input[name="chat-preset"]'))radio.onchange=()=>{withdrawApproval();applyPreset(radio.value);};
    for(const id of ['chat-budget','chat-reserve'])el(id).oninput=()=>{
      withdrawApproval();
      const {context,reserve}=readBudget(),candidate=presetFor(context,reserve),allowed=budgetPresets(currentEvidence()).find(p=>p.id===candidate)?.enabled;
      const name=allowed?candidate:'custom';
      const radio=document.querySelector(`input[name="chat-preset"][value="${name}"]`);if(radio)radio.checked=true;updateBreakdown();
    };
    el('chat-create').onclick=async()=>{try{await createSession();}catch(error){compose(el('chat-setup-error'),errorParts(error));}};
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
    el('chat-settings-open').onclick=act(async()=>{renderDetails();el('chat-panel').showModal();loadNative().catch(()=>{});});
    el('chat-panel-close').onclick=()=>el('chat-panel').close();
    el('chat-hardware').onclick=act(async()=>{await readHardware();});
    el('chat-native-estimate').onclick=act(async()=>{const m=el('chat-native-model').value;if(m)await readHardware(m);el('chat-hardware-section').open=true;});
    el('chat-native-start').onclick=act(async()=>{
      el('chat-native-start').disabled=true;
      try{
        await request('/api/v1/native/start',{method:'POST',body:JSON.stringify({approved:true,model:el('chat-native-model').value,
          context_budget:Number(el('chat-native-context').value),gpu_layers:el('chat-native-gpu').value})});
      }finally{await loadNative().catch(()=>{});await loadRuntimes();render();}
    });
    el('chat-native-stop').onclick=act(async()=>{
      try{await request('/api/v1/native/stop',{method:'POST',body:JSON.stringify({approved:true})});}
      finally{await loadNative().catch(()=>{});await loadRuntimes();render();}
    });
    window.addEventListener('najdilab:languagechange',()=>{renderList();render();});
    el('chat-draft').addEventListener('input',autosize);
    // In a method="dialog" form, Enter would press the first button (Cancel/close).
    el('chat-rename-input').addEventListener('keydown',event=>{if(keyAction(event)==='send'){event.preventDefault();el('chat-rename').close('save');}});
    el('chat-setup-form').addEventListener('keydown',event=>{
      if(keyAction(event)==='send'&&event.target.tagName==='INPUT'){event.preventDefault();if(!el('chat-create').disabled)el('chat-create').click();}
    });
    el('chat-delete-confirm').addEventListener('keydown',event=>{if(keyAction(event)==='send'){event.preventDefault();if(!el('chat-delete-go').disabled)el('chat-delete-go').click();}});
    let composing=false;
    el('chat-draft').addEventListener('compositionstart',()=>{composing=true;});
    el('chat-draft').addEventListener('compositionend',()=>{composing=false;});
    el('chat-draft').addEventListener('input',()=>{el('chat-send').disabled=!controller.canSend(el('chat-draft').value);});
    el('chat-draft').addEventListener('keydown',event=>{
      const action=composing?'compose':keyAction(event);
      // A held Enter never inserts a stray newline into a ready message, and never sends.
      if(action==='repeat'){event.preventDefault();return;}
      if(action!=='send')return;
      event.preventDefault();
      submit().catch(error=>{setNotice(errorParts(error));render();});
    });
    el('chat-form').onsubmit=event=>{event.preventDefault();submit().catch(error=>{setNotice(errorParts(error));render();});};
    el('chat-stop').onclick=act(async()=>{await controller.stop();if(live)live.status.textContent='Stopping… nothing from this reply will be saved.';});
    el('chat-collect').onchange=act(async()=>{
      await controller.collect(el('chat-collect').checked);
      setNotice(el('chat-collect').checked?'Collection is on for this conversation until you turn it off or NajdiLab restarts. Only future completed replies enter human review.':'Collection is off for this conversation.');
      render();
    });
    el('chat-messages').addEventListener('click',event=>{
      const button=event.target.closest('[data-copy],[data-code]');if(!button)return;
      const text=button.dataset.copy??button.dataset.code;
      const done=()=>{const before=button.textContent;button.textContent='Copied';setTimeout(()=>{button.textContent=before;},1500);};
      if(global.navigator.clipboard)global.navigator.clipboard.writeText(text).then(done,()=>{});
    });
  }
  global.NajdiChat={load};
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
