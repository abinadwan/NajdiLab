const state = { view: 'dashboard', pages: {}, queue: [], queueIndex: 0, reviewStatus: null, reviewActionPending: false, reviewDraftBaseline: null, channels: new Set(), tags: [], reviewedSelected: new Set(), manualItems: [], manualSelected: new Set(), manualCurrent: null, datasetVersions: [], phase38:null, phase38Index:0, phase38Dirty:false, phase38Saving:false, phase38Decision:null };

const titles = {
  chat: ['Chat Workspace', 'Raw local model conversations, saved here. Collection for review is a separate choice.'],
  models: ['Model library', 'Discover, check and download GGUF models for NajdiLab Native, safely and only with your approval.'],
  dashboard: ['Dashboard', 'Dataset status and local workflows in one place.'],
  'review-queue': ['Review queue', 'Review responses one at a time while preserving the original text.'],
  conversations: ['Conversations', 'Explore full context and open any earlier response for review.'],
  reviewed: ['Reviewed', 'Search and filter previous decisions and corrections.'],
  'add-data': ['Add dataset records', 'Add conversations, texts, or preference pairs with a clear source.'],
  'manual-data': ['Manual data', 'Browse, edit, and archive SFT, direct texts, and DPO pairs with a complete version history.'],
  dataset: ['Dataset records', 'Eligible records only, excluding evaluation and blocked data.'],
  'dataset-health': ['Dataset health', 'Quality, concentration, and leakage metrics from trusted backend services.'],
  balancer: ['Dataset balancer', 'Analyze dataset distributions and inspect imbalance and bias warnings.'],
  'dataset-versions': ['Dataset versions', 'Manifest, provenance, hashes, and frozen status for each version.'],
  'eval-sets': ['Evaluation sets', 'Locked Holdout isolated with automatic detection of leakage.'],
  'phase38-review': ['Remediation review', 'Human review of new records in draft gold-v009-remediation-draft.'],
  'phase39-review': ['Verify edits', 'Review edited records after applying reviewer requests.'],
  exports: ['Export center', 'Versions of Gold are numbered, separated by type, and protected against leakage.'],
  analytics: ['Analytics', 'A quick overview of quality, models, channels, and errors.'],
  settings: ['Settings', 'Local security status and boundaries of NajdiLab v1.']
};
const statusArabic = {MULTI_TURN:'Multi-turn conversation',UNSPECIFIED:'Unspecified',PREFERENCE_PAIR:'Preference pair',MANUAL_ADDITION:'Manual addition',PENDING:'Pending review',APPROVED:'Approved',FULL_CORRECTION:'Full correction',DIALECT_CORRECTION:'Dialect correction',CONTENT_CORRECTION:'Content correction',IGNORED:'Ignored',DELETED:'Deleted'};
const tagArabic = {forgot_previous_constraint:'Forgot previous constraint',ignored_user_instruction:'Ignored user instruction',wrong_context:'Wrong context',repeated_rejected_option:'Repeated rejected option',contradiction:'Contradiction',instruction_following:'Instruction following',constraint_failure:'Constraint failure',context_failure:'Context failure',tool_behavior:'Tool behavior',repetition:'Repetition',verbosity:'Verbosity',formatting:'Formatting',safety:'Safety',hallucination:'Hallucination',dialect_issue:'Dialect issue',grammar_issue:'Grammar issue',unnatural_arabic:'Unnatural Arabic',too_verbose:'Too verbose',too_short:'Too short',format_failure:'Format failure',factual_error:'Factual error',other:'Other'};
const $ = (selector) => document.querySelector(selector);
const $$ = (selector,root=document) => [...root.querySelectorAll(selector)];
const esc = (value='') => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
// UX-05: a preview never hides content; long text keeps a native disclosure with the complete text.
const fullText = (value='', max=220) => {
  const text=String(value ?? '');
  if(text.length<=max)return `<p dir="auto">${esc(text)}</p>`;
  return `<p dir="auto">${esc(compact(text,max))}</p><details class="full-text"><summary>Show full text</summary><p dir="auto">${esc(text)}</p></details>`;
};
const compact = (value='', max=130) => String(value ?? '').length > max ? `${String(value).slice(0,max)}…` : String(value ?? '');
// UX-21: <time> keeps the machine value, so a language switch re-formats it without reloading data.
const fmtDate = (value) => value ? `<time datetime="${esc(value)}">${esc(window.NajdiI18n?window.NajdiI18n.date(value):value)}</time>` : '—';
// Browser storage can be blocked (private mode, site policy); it must never stop the interface.
const prefs = {get(key){try{return localStorage.getItem(key);}catch{return null;}}, set(key,value){try{localStorage.setItem(key,value);}catch{}}};
const tr = (text) => window.NajdiI18n ? window.NajdiI18n.t(text) : text;
const uiStatus = (value) => window.NajdiI18n?.status(value) || String(value || 'Unknown');

let sessionTokenPromise = null;
async function sessionToken() {
  if (!sessionTokenPromise) {
    sessionTokenPromise = fetch('/api/v1/session', {cache:'no-store', headers:{'Accept':'application/json'}})
      .then(async response => {
        if (!response.ok) throw new Error('Unable to initialize browser session. Reload and try again.');
        const session = await response.json();
        if (typeof session.csrf_token !== 'string' || !session.csrf_token) throw new Error('Invalid browser session response');
        return session.csrf_token;
      }).catch(error => { sessionTokenPromise = null; throw error; });
  }
  return sessionTokenPromise;
}

async function api(path, options={}, retried=false) {
  const method = (options.method || 'GET').toUpperCase();
  const readOnly = method === 'GET' || method === 'HEAD' || method === 'OPTIONS';
  const headers = {'Content-Type':'application/json', ...(options.headers || {})};
  if (!readOnly) headers['X-NajdiLab-CSRF'] = await sessionToken();
  const response = await fetch(path, {...options, method, headers});
  let payload;
  try { payload = await response.json(); } catch { payload = {error:'Invalid server response'}; }
  if (!readOnly && !retried && response.status === 403 && payload.code === 'CSRF_TOKEN_INVALID') {
    sessionTokenPromise = null;
    return api(path, options, true);
  }
  if (!response.ok) throw Object.assign(new Error(payload.message || payload.error || `HTTP ${response.status}`), {code: payload.code, hint: payload.hint});
  return payload;
}

function toast(message, error=false) {
  // UX-19: successful notifications may expire, but actionable errors must
  // remain visible until the user dismisses them or an updated status replaces.
  const el=$('#toast');clearTimeout(toast.timer);el.textContent='';
  const text=document.createElement('span');text.className='toast-message';
  const source=String(message),shown=tr(source);
  // UX-21: a server message missing from the catalog is labelled and isolated, not mixed into Arabic.
  if(window.NajdiI18n&&window.NajdiI18n.language!=='en'&&shown===source&&/[A-Za-z]{3}/.test(source)){
    const raw=document.createElement('bdi');raw.dir='ltr';raw.textContent=source;
    text.append(document.createTextNode(tr('Server message:')+' '),raw);
  }else text.textContent=source;
  el.append(text);
  el.className=error?'toast show error':'toast show';
  el.setAttribute('role',error?'alert':'status');
  el.setAttribute('aria-live',error?'assertive':'polite');
  if(error){
    // The glyph is hidden from assistive technology so the alert reads only the message.
    const close=document.createElement('button');
    close.type='button';close.className='toast-dismiss';close.setAttribute('aria-label','Dismiss error');
    const glyph=document.createElement('span');glyph.setAttribute('aria-hidden','true');glyph.textContent='×';
    close.append(glyph);close.onclick=()=>{el.className='toast';el.textContent='';};
    el.append(close);return;
  }
  toast.timer=setTimeout(()=>{el.className='toast';},2800);
}

const viewPaths={chat:'/chat',models:'/models',dashboard:'/',conversations:'/conversations','review-queue':'/review','reviewed':'/gold','add-data':'/data/add','manual-data':'/data/manual',dataset:'/datasets/gold','dataset-health':'/datasets/health',balancer:'/datasets/balancer','dataset-versions':'/datasets/versions','eval-sets':'/datasets/eval','phase38-review':'/evaluation/remediation-review','phase39-review':'/evaluation/remediation-review-edits',exports:'/exports',analytics:'/analytics',settings:'/settings'};
const pathViews=Object.fromEntries(Object.entries(viewPaths).map(([view,path])=>[path,view]));
function selectedVersion(){return new URLSearchParams(location.search).get('version')||state.selectedDataset||'';}
function updateLocation(view,version='',replace=false){const path=viewPaths[view]||'/';const query=version?`?version=${encodeURIComponent(version)}`:'';(replace?history.replaceState:history.pushState).call(history,{view,version},'',path+query);}
// UX-07: snapshot the editable review, not its immutable original. This guard
// catches tags/flags/notes/corrections without persisting draft text to storage.
function reviewDraftSnapshot(){
  if(!state.queue.length)return null;
  return JSON.stringify({
    id:state.queue[state.queueIndex]?.id,
    status:state.reviewStatus,
    editorOpen:!$('#edit-review-panel').classList.contains('hidden'),
    payload:reviewPayload(),
    corrected:$('#corrected-response').value,
    ignoredReason:$('#ignored-reason').value
  });
}
function hasUnsavedReviewDraft(){
  return state.view==='review-queue' && !state.reviewActionPending &&
    state.reviewDraftBaseline!==null && reviewDraftSnapshot()!==state.reviewDraftBaseline;
}
function confirmDiscardReviewDraft(){
  return !hasUnsavedReviewDraft() || confirm(tr('You have unsaved review changes. Leave and discard this draft?'));
}
function switchView(view,options={}) {
  if(!titles[view])view='dashboard';
  if(view!==state.view&&!confirmDiscardReviewDraft()){
    if(options.fromHistory)updateLocation(state.view,state.selectedDataset||'',true);
    return;
  }
  if(state.view==='phase38-review'&&view!==state.view&&state.phase38Dirty&&!confirm(tr('You have unsaved remediation changes. Leave this page and discard them?')))return;
  // An accepted navigation discards this in-memory review snapshot; otherwise
  // returning to the queue would wrongly compare the old DOM before reloading.
  if(view!==state.view&&state.view==='review-queue')state.reviewDraftBaseline=null;
  state.view = view;
  $$('.nav-item').forEach(b=>{const current=b.dataset.view===view;b.classList.toggle('active',current);if(current)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  $$('.view').forEach(v=>v.classList.toggle('active', v.id===`view-${view}`));
  $('#page-title').textContent = titles[view][0]; $('#page-subtitle').textContent = titles[view][1];
  // Breadcrumb: the workflow group, then the screen. Separate text nodes so each part is translated.
  // English source names (the DOM may already show a translation, which must not become source text).
  const navGroups={'nav-group-overview':'Overview','nav-group-chat':'Chat','nav-group-review':'Review','nav-group-data':'Data entry','nav-group-datasets':'Datasets','nav-group-export':'Export','nav-group-system':'Administration'};
  const group=navGroups[document.querySelector(`.nav-item[data-view="${view}"]`)?.closest('.nav-section')?.getAttribute('aria-labelledby')]||'';
  $('#page-breadcrumb').replaceChildren(...[group,titles[view][0]].filter(Boolean).flatMap((part,i)=>{const s=document.createElement('span');s.textContent=part;if(!i)return [s];const sep=document.createElement('span');sep.className='crumb-sep';sep.setAttribute('aria-hidden','true');sep.textContent='/';s.setAttribute('aria-current','page');return [sep,s];}));
  if(view==='dataset-health')$('#page-subtitle').textContent='Check the quality, balance, and integrity of a dataset version';
  setMobileNav(false);
  if(!options.fromHistory)updateLocation(view,options.version||selectedVersion(),options.replace);
  loadView(view).catch(error=>toast(error.message,true));
}

async function loadView(view) {
  if (view==='chat') return window.NajdiChat?.load();
  if (view==='models') return window.NajdiModels?.load();
  if (view==='dashboard') return loadDashboard();
  if (view==='review-queue') return loadQueue();
  if (view==='conversations') return loadConversations();
  if (view==='reviewed') return loadReviewed();
  if (view==='manual-data') return loadManualData();
  if (view==='dataset') return loadDataset();
  if (view==='dataset-health') return loadHealth();
  if (view==='balancer') return loadBalancer();
  if (view==='dataset-versions') return loadDatasetVersions();


  if (view==='eval-sets') return loadEvalSets();
  if (view==='phase38-review') return loadPhase38Review();
  if (view==='phase39-review') return loadPhase39Verification();
  if (view==='exports') return loadExports();
  if (view==='analytics') return loadAnalytics();
  if (view==='settings') return loadSettingsView();
}

async function loadSettingsView(){
  // UX-26: /health verifies only the application response, not SQLite integrity.
  const indicator=$('#sqlite-status');
  indicator.textContent='Checking service…';indicator.className='status-neutral';
  try{
    const health=await api('/api/v1/health');
    indicator.textContent=health?.ok===true&&health.service==='NajdiLab'
      ? 'Application responding · database not verified'
      : 'Unable to verify service';
  }catch(error){indicator.textContent='Health check unavailable';}
  return window.NajdiIntegrations?.load();
}

// UX-18: the server owns the verification queue; never assume exactly seven rows.
async function loadPhase39Verification(){
  const host=$('#phase39-status'),list=$('#phase39-records');
  host.className='phase38-status';host.textContent='Loading verification status…';list.replaceChildren();
  try{
    const data=await api('/api/v1/phase39/post-edit-verification');
    if(!data||!Array.isArray(data.records)||!data.summary)throw Error('Invalid verification response');
    state.phase39=data;
    state.phase39Index=Math.min(Math.max(0,state.phase39Index||0),Math.max(0,data.records.length-1));
    state.phase39Dirty=false;renderPhase39Verification();
  }catch(error){
    state.phase39=null;host.textContent='Unable to load verification status: '+error.message;host.className='phase38-status error-state';
  }
}
function phase39Navigate(delta){
  if(state.phase39Dirty&&!confirm(tr('You have unsaved verification changes. Discard them?')))return;
  state.phase39Index=Math.max(0,Math.min(state.phase39.records.length-1,state.phase39Index+delta));
  state.phase39Dirty=false;renderPhase39Verification();
}
function renderPhase39Verification(){
  const data=state.phase39,host=$('#phase39-status'),list=$('#phase39-records');
  if(!data||!Array.isArray(data.records))return;
  const total=data.records.length;
  if($('#nav-phase39'))$('#nav-phase39').textContent=String(data.summary.verified||0)+'/'+total;
  if(total===0){
    host.className='phase38-status';host.textContent='No post-edit verification records available.';
    list.replaceChildren();return;
  }
  const record=data.records[state.phase39Index];
  state.phase39Decision=record.decision||null;
  host.className='phase38-status';
  host.textContent='Progress: '+(data.summary.verified||0)+'/'+total+' · Record '+(state.phase39Index+1)+' of '+total;
  // No audit verdict must ever be represented as a successful PASS.
  const fallback=x=>esc(x==null||x===''?'UNVERIFIED':x);
  list.innerHTML='<article class="phase38-message"><b class="technical-id">'+esc(record.record_id)+'</b><p dir="auto">'+
    esc(record.record_type)+' · '+fallback(record.validation_status)+' · contamination: '+fallback(record.contamination_status)+
    ' · loss-mask: '+fallback(record.loss_mask_status)+'</p><h4>Original response</h4><p dir="auto">'+esc(record.original_assistant_messages)+
    '</p><h4>Reviewer note</h4><p dir="auto">'+esc(record.reviewer_note)+
    '</p><h4>Requested correction</h4><p dir="auto">'+esc(record.requested_correction)+
    '</p><h4>Applied version</h4><p dir="auto">'+esc(record.final_assistant_messages)+
    '</p>'+(record.record_type==='native_tool_use'?'<p>Tool calls, authoritative results, and record metadata are read-only.</p>':'')+
    '</article><label class="wide-label">Verification note<textarea dir="auto" id="phase39-reviewer-note" rows="3">'+esc(record.post_edit_note||'')+
    '</textarea></label><div class="phase38-decisions" role="group" aria-label="Verification decision">'+
    '<button type="button" class="button ghost" data-phase39-decision="اعتماد التعديل">Approve edit</button>'+
    '<button type="button" class="button ghost" data-phase39-decision="يحتاج تعديل إضافي">Needs further editing</button>'+
    '<button type="button" class="button ghost" data-phase39-decision="رفض">Reject</button></div>'+
    '<p id="phase39-save-state" role="status" aria-live="polite"></p><div class="save-row">'+
    '<button type="button" class="button ghost" data-phase39-nav="prev" '+(state.phase39Index===0?'disabled':'')+'>Previous</button>'+
    '<button type="button" class="button primary" id="phase39-save" '+(state.phase39Decision?'':'disabled')+'>Save</button>'+
    '<button type="button" class="button ghost" data-phase39-nav="next" '+(state.phase39Index===total-1?'disabled':'')+'>Next</button></div>';
  $$('[data-phase39-decision]').forEach(button=>{
    const selected=button.dataset.phase39Decision===state.phase39Decision;
    button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));
  });
  bindPhase39Verification();
}
function bindPhase39Verification(){
  const root=$('#view-phase39-review');
  root.oninput=event=>{if(event.target.id==='phase39-reviewer-note')state.phase39Dirty=true;};
  root.onclick=async event=>{
    const nav=event.target.closest('[data-phase39-nav]'),decision=event.target.closest('[data-phase39-decision]');
    if(nav){phase39Navigate(nav.dataset.phase39Nav==='prev'?-1:1);return;}
    if(decision){
      state.phase39Decision=decision.dataset.phase39Decision;state.phase39Dirty=true;
      $$('[data-phase39-decision]').forEach(button=>{
        const selected=button===decision;
        button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));
      });$('#phase39-save').disabled=false;return;
    }
    if(!event.target.closest('#phase39-save'))return;
    if(!state.phase39Decision){$('#phase39-save-state').textContent='Choose a verification decision first.';return;}
    const record=state.phase39.records[state.phase39Index],button=$('#phase39-save'),note=$('#phase39-reviewer-note').value;
    button.disabled=true;$('#phase39-save-state').textContent='Saving…';
    try{
      const result=await api('/api/v1/phase39/post-edit-verification/'+encodeURIComponent(record.record_id),{
        method:'POST',body:JSON.stringify({decision:state.phase39Decision,reviewer_note:note})
      });
      if(!result||!result.verification||!Array.isArray(result.verification.records))throw Error('Invalid save acknowledgement');
      state.phase39=result.verification;
      state.phase39Index=Math.min(state.phase39Index,Math.max(0,state.phase39.records.length-1));
      state.phase39Dirty=false;renderPhase39Verification();toast('Verification saved.');
    }catch(error){
      button.disabled=false;button.textContent='Retry save';$('#phase39-save-state').textContent='Unable to save: '+error.message;
    }
  };
}

async function ensureDatasetVersions(force=false){
  // UX-13: actively refresh after a new visit. A separately created/frozen
  // version may not have been created through this browser's mutation handlers.
  if(force||!state.datasetVersions.length){const data=await api('/api/v1/dataset-versions');if(!Array.isArray(data.items))throw new Error('Invalid dataset version response');state.datasetVersions=data.items;}
  const preferred=state.datasetVersions.some(x=>x.version==='gold-v008-split-clean')?'gold-v008-split-clean':state.datasetVersions.some(x=>x.version==='gold-v007-balanced')?'gold-v007-balanced':state.datasetVersions[0]?.version;
  const requested=selectedVersion();state.selectedDataset=state.datasetVersions.some(x=>x.version===requested)?requested:preferred||'';
  ['#health-version','#balance-version','#eval-version'].forEach(selector=>{const select=$(selector);if(!select)return;select.innerHTML=state.datasetVersions.map(x=>`<option value="${esc(x.version)}" ${x.readable===false?'disabled':''}>${esc(x.version)}${x.readable===false?' — Unreadable':''}</option>`).join('');select.value=state.selectedDataset;});
  return preferred;
}

function pct(value){return value==null?'—':`${(Number(value)*100).toFixed(2)}%`;}
function healthCard(title,status,value,description,detail){return `<button class="health-card" data-health-detail="${esc(detail)}"><span class="health-card-status ${esc(String(status).toLowerCase())}">${esc(status)}</span><h3>${esc(title)}</h3><strong>${esc(value)}</strong><p dir="auto">${esc(description)}</p><small>View details</small></button>`;}
function showHealthError(message){$('#health-results').classList.add('hidden');$('#health-state').className='panel health-state error-state';$('#health-state').innerHTML=`<strong>Unable to check dataset health</strong><p dir="auto">${esc(message)}. No changes were made to the dataset and you can safely retry.</p><button id="health-retry" class="button primary">Retry</button>`;$('#health-retry').onclick=()=>loadHealth(true);}
async function loadHealth(force=false){
  $('#health-state').className='panel health-state';$('#health-state').textContent='Loading versions...';$('#health-results').classList.add('hidden');
  try{await ensureDatasetVersions();}catch(error){showHealthError(`Unable to load dataset versions: ${error.message}`);return;}
  const select=$('#health-version'),button=$('#refresh-health');if(!state.datasetVersions.length){select.innerHTML='';button.disabled=true;$('#health-state').textContent='No dataset versions are available to check.';return;}
  const version=select.value||state.selectedDataset;select.value=version;button.disabled=false;state.selectedDataset=version;updateLocation('dataset-health',version,true);
  button.disabled=true;button.textContent=force?'Checking again...':`Checking ${version}...`;$('#health-state').textContent=`Checking ${version}...`;
  try{const data=await api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/health`);state.health=data;$('#health-state').classList.add('hidden');$('#health-results').classList.remove('hidden');$('#health-dataset').textContent=data.version;$('#health-timestamp').textContent=data.checked_at;$('#health-last-result').textContent=force?'New health result':'Last Health Result';
    const tr=data.training_readiness,ei=data.evaluation_integrity;$('#health-summary').innerHTML=healthCard('Dataset Readiness',tr.status,tr.status,tr.training_errors?'Dataset validation errors were found.':'Schema, targets, and loss masks are valid.','training')+healthCard('Evaluation Integrity',ei.status,ei.status,`${ei.conversation_overlap_count} conversation overlaps`,'evaluation')+healthCard('Dataset Records','INFO',data.training_count,`${data.counts['sft.jsonl']||0} SFT and ${data.counts['multi_turn.jsonl']||0} Multi-turn`,'records')+healthCard('Warnings',data.warnings.length?'WARNING':'CLEAN',data.warnings.length,'Reviewable warnings that do not modify the source.','warnings');
    const r=data.highest_record_share?.[1]||{},c=data.highest_context_word_share?.[1]||{},t=data.highest_target_word_share?.[1]||{};$('#health-checks').innerHTML=healthCard('Conversation Balance',r.record_share>.15?'WARNING':'CLEAN',pct(r.record_share),'Largest record share for a single conversation.','balance')+healthCard('Duplicates',data.exact_duplicate_extra?'FAILED':'CLEAN',data.exact_duplicate_extra,'Extra identical dataset targets.','duplicates')+healthCard('Language / Phrase Dominance','INFO',pct(data.longest_10_target_word_share),'Share of the ten longest targets.','phrases')+healthCard('Loss Masks',data.loss_mask_validation?.failures?.length?'FAILED':'CLEAN',`${data.loss_mask_validation?.passed??0}/${data.loss_mask_validation?.total??0}`,'Validate final target selection.','masks')+healthCard('Leakage',ei.status,ei.conversation_overlap_count,'Conversation overlap between evaluation and eligible records.','evaluation');
    $('#health-warning-count').textContent=data.warnings.length;$('#health-warnings').innerHTML=data.warnings.length?data.warnings.map(x=>`<button class="health-warning ${esc(x.level)}" data-health-detail="${esc(x.code)}"><strong>${x.level==='error'?'Error':'Warning'}</strong><span>${esc(x.message)}</span></button>`).join(''):'<div class="success-state">No warnings.</div>';
  }catch(error){showHealthError(error.message);}finally{button.disabled=false;button.textContent=force?'Check again':'Check again';}}

function showHealthDetail(kind){const d=state.health;if(!d)return;const r=d.highest_record_share?.[1]||{},c=d.highest_context_word_share?.[1]||{},t=d.highest_target_word_share?.[1]||{};const key=d.highest_record_share?.[0]||'—';const details={training:[['Status',d.training_readiness.status],['Invalid target indices',d.training_readiness.invalid_target_indices],['Invalid loss masks',d.training_readiness.invalid_loss_masks]],evaluation:[['Status',d.evaluation_integrity.status],['Conversation overlap',d.evaluation_integrity.conversation_overlap_count],['Exact target overlap',d.evaluation_integrity.exact_target_overlap_count],...d.evaluation_integrity.by_file.map(x=>[x.name,`${x.status} · ${x.conversation_overlap_count} overlap`])],balance:[['Conversation',key],['Records',r.total_records??'—'],['Record share',pct(r.record_share)],['Target-word share',pct(t.target_word_share)],['Context-word share',pct(c.context_word_share)]],conversation_concentration:[['Conversation',key],['Records',r.total_records??'—'],['Record share',pct(r.record_share)]],context_concentration:[['Conversation',d.highest_context_word_share?.[0]||'—'],['Context-word share',pct(c.context_word_share)]],phrases:[['Longest-10 target share',pct(d.longest_10_target_word_share)],...Object.entries(d.phrase_counts||{})],duplicates:[['Exact duplicate extra',d.exact_duplicate_extra]],masks:[['Passed',d.loss_mask_validation?.passed??0],['Total',d.loss_mask_validation?.total??0]],warnings:d.warnings.map(x=>[x.code,x.message]),records:[['SFT',d.counts['sft.jsonl']||0],['Multi-turn',d.counts['multi_turn.jsonl']||0],['Total',d.training_count]],eval_leakage:[['Conversation overlap',d.evaluation_integrity.conversation_overlap_count],['Exact target overlap',d.evaluation_integrity.exact_target_overlap_count]]};const rows=details[kind]||details.warnings;$('#health-detail-panel').classList.remove('hidden');$('#health-detail-panel').innerHTML=`<div class="panel-heading"><h2>Check details</h2><button class="button ghost" data-close-health-detail>Close</button></div><dl class="metric-list">${rows.map(([k,v])=>`<div><dt>${esc(k)}</dt><dd class="technical-value">${esc(v)}</dd></div>`).join('')}</dl>`;$('#health-detail-panel').scrollIntoView({behavior:'smooth',block:'nearest'});}

function balanceBars(title,items,labels={}){const max=Math.max(1,...items.map(x=>x.count));return `<section class="panel phase-panel balance-panel"><h2>${esc(title)}</h2><div class="balance-bars">${items.length?items.map(x=>`<div class="balance-bar"><header><span>${labels[x.name]?esc(labels[x.name]):`<bdi>${esc(x.name)}</bdi>`}</span><strong>${x.count} · ${pct(x.share)}</strong></header><div><i data-share="${x.count/max*100}"></i></div></div>`).join(''):'<div class="empty-inline">No data available.</div>'}</div></section>`;}
function balanceMetricPanel(title,items){return `<section class="panel phase-panel balance-panel"><h2>${esc(title)}</h2><dl class="metric-list">${items.map(([key,value])=>`<div><dt>${esc(key)}</dt><dd class="technical-value">${esc(value)}</dd></div>`).join('')}</dl></section>`;}
function showBalanceError(message){$('#balance-results').classList.add('hidden');$('#balance-state').className='panel health-state error-state';$('#balance-state').innerHTML=`<strong>Unavailable</strong><p dir="auto">${esc(message)}. The version remains visible and no files were changed.</p><button id="balance-retry" class="button primary">Retry</button>`;$('#balance-retry').onclick=()=>loadBalancer(true);}
async function loadBalancer(force=false){
  $('#balance-state').className='panel health-state';$('#balance-state').textContent='Loading dataset versions Dataset...';$('#balance-results').classList.add('hidden');
  try{await ensureDatasetVersions();}catch(error){showBalanceError(error.message);return;}
  const select=$('#balance-version'),button=$('#run-balance');if(!state.datasetVersions.length){select.innerHTML='';button.disabled=true;$('#balance-state').textContent='No dataset versions.';return;}
  const version=select.value||state.selectedDataset;select.value=version;state.selectedDataset=version;updateLocation('balancer',version,true);button.disabled=true;button.textContent='Analyzing...';
  try{const data=await api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/balance`);state.balance=data;$('#balance-state').classList.add('hidden');$('#balance-results').classList.remove('hidden');$('#balance-dataset').textContent=data.version;$('#balance-dataset-state').textContent=data.state;$('#balance-timestamp').textContent=data.analyzed_at;
    const counts=data.record_types.counts;const cards=[['Total Records',data.summary.total_records,'INFO'],['SFT',counts.sft||0,'INFO'],['Multi-turn',counts.multi_turn||0,'INFO'],['Preference',counts.preference||0,'INFO'],['Balance Status',data.balance_status,data.balance_status],['Warnings',data.warnings.length,data.warnings.length?'WARNING':'CLEAN']];$('#balance-overview').innerHTML=cards.map(([label,value,status])=>`<article class="health-card static-card"><span class="health-card-status ${esc(String(status).toLowerCase())}">${esc(status)}</span><h3>${esc(label)}</h3><strong>${esc(value)}</strong></article>`).join('');
    const typeLabels={sft:'SFT',multi_turn:'Multi-turn',preference:'Preference / DPO',direct_language:'Direct Language',evaluation:'Evaluation',unknown:'Unknown'},turnLabels={'1':'1 turn','2-3':'2–3 turns','4-6':'4–6 turns','7-10':'7–10 turns','11+':'11+ turns'},lengthLabels={very_short:'Very short',short:'Short',medium:'Medium',long:'Long',very_long:'Very long'};
    $('#balance-panels').innerHTML=balanceBars('Record type distribution',data.record_types.distribution.items,typeLabels)+balanceBars('Conversation turns',data.conversation_structure.distribution.items,turnLabels)+balanceBars('Assistant text length',Object.entries(data.length_distribution.assistant.buckets).map(([name,value])=>({name,...value})),lengthLabels)+balanceBars('Source distribution',data.sources.items)+balanceBars('Review type distribution',data.review_types.items,statusArabic)+balanceBars('Error tags',data.error_tags.items,tagArabic)+balanceBars('Language Signal',data.language_signals.items,{arabic_dominant:'Arabic-dominant',english_dominant:'English-dominant',mixed:'Mixed',empty_invalid:'Empty / invalid'})+balanceMetricPanel('Conversation structure',[['Single-turn',data.conversation_structure.single_turn],['Multi-turn',data.conversation_structure.multi_turn],['Mean turns',data.conversation_structure.mean_turns],['Median turns',data.conversation_structure.median_turns],['Minimum',data.conversation_structure.min_turns],['Maximum',data.conversation_structure.max_turns]])+balanceMetricPanel('Length statistics',[['User min / mean / median / max',`${data.length_distribution.user.min} / ${data.length_distribution.user.mean} / ${data.length_distribution.user.median} / ${data.length_distribution.user.max}`],['User p90 / p95',`${data.length_distribution.user.p90} / ${data.length_distribution.user.p95}`],['Assistant min / mean / median / max',`${data.length_distribution.assistant.min} / ${data.length_distribution.assistant.mean} / ${data.length_distribution.assistant.median} / ${data.length_distribution.assistant.max}`],['Assistant p90 / p95',`${data.length_distribution.assistant.p90} / ${data.length_distribution.assistant.p95}`],['Total p90 / p95',`${data.length_distribution.conversation_total.p90} / ${data.length_distribution.conversation_total.p95}`],['Unit','characters']])+balanceMetricPanel('Duplicate & integrity signals',[['Exact records',data.duplicates.exact_records],['Exact user inputs',data.duplicates.exact_user_inputs],['Exact assistant targets',data.duplicates.exact_assistant_targets],['Conversation ID extra',data.duplicates.conversation_id_extra],['Eval conversation overlap',data.duplicates.evaluation_conversation_overlap],['Eval target overlap',data.duplicates.evaluation_target_overlap]]);applyShares('#balance-panels');
    $('#balance-warning-count').textContent=data.warnings.length;$('#balance-warnings').innerHTML=data.warnings.length?data.warnings.map(x=>`<article class="balance-notice ${esc(x.severity)}"><header><span>${esc(x.severity)}</span><code>${esc(x.code)}</code></header><h3>${esc(x.title)}</h3><p>${esc(x.description)}</p><small><code>${esc(x.dimension)}</code> · observed: ${esc(x.observed)}${x.recommended_min!=null?` · recommended ≥ ${esc(x.recommended_min)}`:''}${x.recommended_max!=null?` · recommended ≤ ${esc(x.recommended_max)}`:''}</small></article>`).join(''):'<div class="success-state">No balance rules triggered a warning.</div>';
    $('#balance-recommendations').innerHTML=data.recommendations.map(x=>`<article class="balance-notice recommendation"><header><span>${esc(x.priority)}</span><code>${esc(x.category)}</code></header><h3>${esc(x.reason)}</h3><p>${esc(x.suggested_action)}</p><small>Evidence: <code>${esc(JSON.stringify(x.evidence))}</code></small></article>`).join('');
  }catch(error){showBalanceError(error.message);}finally{button.disabled=false;button.textContent=force?'Analyze again':'Analyze balance';}
}

async function loadDatasetVersions(){await ensureDatasetVersions(true);$('#version-list').innerHTML=state.datasetVersions.length?state.datasetVersions.map(x=>`<button data-version-name="${esc(x.version)}"><strong><bdi dir="ltr">${esc(x.version)}</bdi></strong><span>${esc(x.state)}</span><small>${x.created_at?fmtDate(x.created_at):'Unverified date'}</small></button>`).join(''):'<div class="empty-inline">No versions.</div>';const preferred=state.datasetVersions.find(x=>x.version===state.selectedDataset&&x.readable!==false)?.version||state.datasetVersions.find(x=>x.version==='gold-v007-balanced'&&x.readable!==false)?.version||state.datasetVersions.find(x=>x.readable!==false)?.version;
  if(preferred)await showVersionDetail(preferred);else $('#version-detail').innerHTML='<div class="empty-inline">No readable dataset versions are available.</div>';}
async function showVersionDetail(version){state.selectedDataset=version;updateLocation('dataset-versions',version,true);const data=await api(`/api/v1/dataset-versions/${encodeURIComponent(version)}`);$$('[data-version-name]').forEach(x=>x.classList.toggle('active',x.dataset.versionName===version));const counts=data.manifest.files||{},source=typeof data.provenance==='string'?data.provenance:data.provenance?.source_version,provenance=source?`<bdi dir="ltr">${esc(source)}</bdi>`:'Derived version';const canFreeze=data.health.training_readiness.status==='READY'&&data.health.evaluation_integrity.status==='CLEAN';const derived=data.state==='Draft'?`<section class="derived-workflow"><div class="safety-banner">The frozen source version will remain unchanged.</div><div class="workflow-actions"><button class="button ghost" data-overlap-analysis="${esc(version)}">Check Overlaps</button><button class="button primary" data-overlap-plan="${esc(version)}">Create Dry Run</button><button class="button ghost" data-freeze-version="${esc(version)}" ${canFreeze?'':'disabled'}>Freeze version later</button></div><div id="overlap-workflow-result" class="overlap-result"></div></section>`:`<section class="derive-box"><div class="safety-banner">The frozen source version will remain unchanged.</div><label>Derived version name<input id="derived-version-name" dir="ltr" value="${version==='gold-v007-balanced'?'gold-v008-split-clean':esc(version+'-derived')}"></label><button class="button primary" data-derive-version="${esc(version)}">Create derived version</button></section>`;$('#version-detail').innerHTML=`<div class="version-hero"><div><span class="eyebrow">${provenance}</span><h2 dir="ltr">${esc(data.version)}</h2></div><div><button class="button ghost" data-health-version="${esc(version)}">Check dataset health</button> <span class="frozen-badge ${data.state==='Draft'?'draft':''}">${esc(data.state)}</span></div></div><div class="version-summary"><span>Dataset Readiness <b>${esc(data.health.training_readiness.status)}</b></span><span>Dataset records <b>${data.health.training_count}</b></span><span>Eval Integrity <b>${esc(data.health.evaluation_integrity.status)}</b></span><span>Leakage <b>${data.eval.conversation_overlap_count}</b></span></div>${derived}<h3>Counts</h3><div class="count-grid">${Object.entries(counts).map(([k,v])=>`<span><code>${esc(k)}</code><b>${v}</b></span>`).join('')}</div><h3>Files & SHA-256</h3><div class="hash-list">${data.files.map(f=>`<div><strong><bdi dir="ltr">${esc(f.name)}</bdi></strong><span>${f.count==null?'—':f.count} records · ${f.bytes} bytes</span><code>${esc(f.sha256)}</code></div>`).join('')}</div><details><summary>Manifest JSON</summary><pre>${esc(JSON.stringify(data.manifest,null,2))}</pre></details>`;}

function overlapTable(data){const items=data.items||[];return `<div class="overlap-summary">${items.length} overlapping conversations</div>${items.length?`<div class="overlap-table">${items.map(x=>`<article><code>${esc(x.conversation_id)}</code><div><span>Dataset records: <b>${x.train_records}</b></span><span>Evaluation: <b>${x.eval_records}</b></span><span>Turns: <b>${x.turn_count}</b></span><span>Destination: <b>${esc(x.proposed_destination)}</b></span></div><small>${esc(x.source_files.join(', '))}</small><p dir="auto">${esc(x.reason)}</p></article>`).join('')}</div>`:'<div class="success-state">No conversations are shared between eligible records and evaluation.</div>'}`;}
async function deriveVersion(source){const input=$('#derived-version-name'),target=input?.value.trim();if(!target)return toast('Enter the derived version name.',true);const button=$(`[data-derive-version="${source}"]`);button.disabled=true;button.textContent='Creating...';try{await api(`/api/v1/dataset-versions/${encodeURIComponent(source)}/derive`,{method:'POST',body:JSON.stringify({target_version:target})});state.datasetVersions=[];await loadDatasetVersions();await showVersionDetail(target);toast('Derived version created as Draft.');}catch(e){toast(e.message,true);}finally{if(button){button.disabled=false;button.textContent='Create derived version';}}}
async function analyzeOverlaps(version){const box=$('#overlap-workflow-result');box.innerHTML='<div class="health-state">Analyzing conversations...</div>';try{const data=await api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/conversation-overlaps`);box.innerHTML=overlapTable(data);}catch(e){box.innerHTML=`<div class="error-state">${esc(e.message)}</div>`;}}
async function dryRunOverlaps(version){const box=$('#overlap-workflow-result');box.innerHTML='<div class="health-state">Preparing Dry Run...</div>';try{const result=await api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/overlap-plan`,{method:'POST',body:'{}'});state.overlapPlan=result.plan;box.innerHTML=`<div class="success-state">Dry Run only; files are unchanged. Records to move: ${result.plan.summary.records_to_move} records.</div>${overlapTable(result.plan)}<button class="button primary apply-plan" data-apply-plan="${esc(version)}">Apply plan to Draft</button>`;}catch(e){box.innerHTML=`<div class="error-state">${esc(e.message)}</div>`;}}
async function applyOverlapPlan(version){if(!state.overlapPlan)return toast('Create a fresh Dry Run first.',true);const button=$('[data-apply-plan]');button.disabled=true;button.textContent='Applying safely...';try{await api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/apply-overlap-plan`,{method:'POST',body:JSON.stringify({plan_token:state.overlapPlan.plan_token,dataset_fingerprint:state.overlapPlan.dataset_fingerprint})});state.datasetVersions=[];state.overlapPlan=null;await loadDatasetVersions();await showVersionDetail(version);toast('Plan applied; manifest and SHA-256 hashes recalculated.');}catch(e){toast(e.message,true);button.disabled=false;button.textContent='Apply plan to Draft';}}
async function freezeVersion(version){try{await api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/freeze`,{method:'POST',body:'{}'});state.datasetVersions=[];await loadDatasetVersions();await showVersionDetail(version);toast('Version frozen after verifying health and fingerprints.');}catch(e){toast(e.message,true);}}

async function loadEvalSets(){
  await ensureDatasetVersions();
  const version=$('#eval-version').value,identity=$('#eval-version-identity');
  if(!version){identity.textContent='No dataset version selected.';return;}
  identity.textContent=`Checking evaluation integrity for ${version}…`;
  let data;
  try{data=await api(`/api/v1/dataset-versions/${encodeURIComponent(version)}/eval-sets`);}
  catch(error){identity.textContent=`Unable to check ${version}: ${error.message}`;throw error;}
  // UX-27: a slow response from version A must never overwrite version B's UI.
  if($('#eval-version').value!==version)return;
  identity.textContent=`Evaluation results for ${version} · ${data.leakage_free?'No leakage detected':'Leakage detected'}`;
$('#eval-status-card').innerHTML=`<div class="eval-lock"><span class="eval-lock-icon" aria-hidden="true"><svg class="icon" focusable="false"><use href="#i-lock"/></svg></span><div><span class="eyebrow">Locked Holdout</span><h2>${data.leakage_free?'Isolated from eligible records':'Detected Leakage'}</h2><p>${data.train_count} eligible records versus ${data.eval_count} evaluation records.</p></div><span class="health-pill ${data.leakage_free?'healthy':'critical'}">${data.leakage_free?'PASS':'FAIL'}</span></div>`;$('#eval-files').innerHTML=data.eval_files.map(x=>`<div class="stat-card"><span><bdi dir="ltr">${esc(x.name)}</bdi></span><strong>${x.count}</strong></div>`).join('');$('#leakage-detail').innerHTML=`<div class="panel-heading"><h2>Leakage Detection</h2><span class="locked-chip">Locked</span></div><dl class="metric-list"><div><dt>Conversation overlap</dt><dd>${data.conversation_overlap_count}</dd></div><div><dt>Exact target overlap</dt><dd>${data.exact_target_overlap_count}</dd></div></dl>${data.leakage_free?'<div class="success-state">No leakage detected between eligible records and evaluation files.</div>':`<pre>${esc(JSON.stringify({conversation_overlap:data.conversation_overlap,exact_target_overlap:data.exact_target_overlap},null,2))}</pre>`}`;}

async function loadDashboard(){
  const [analyticsData,exportsData,datasetData]=await Promise.all([api('/api/v1/analytics'),api('/api/v1/exports'),api('/api/v1/dataset-records')]);
  const s=analyticsData.summary;
  const eligible=(datasetData.reviews?.length||0)+(datasetData.manual_sft?.length||0)+(datasetData.direct_language?.length||0)+(datasetData.preference_pairs?.length||0);
  const stats=[['Conversations',s.total_conversations],['Pending review',s.pending_reviews],['Eligible for build',eligible],['Gold versions',exportsData.items.length]];
  // The pipeline strip: each stage opens the screen where its number is worked on.
  const stageView={'Conversations':'conversations','Pending review':'review-queue','Eligible for build':'dataset','Gold versions':'dataset-versions'};
  $('#dashboard-stats').innerHTML=stats.map(([label,value])=>`<button type="button" class="stat-card" data-go="${stageView[label]}"><span>${label}</span><strong>${value??0}</strong></button>`).join('');
  $('#dashboard-exports').innerHTML=exportsData.items.length?exportsData.items.slice(0,4).map(item=>`<div class="export-row"><strong><bdi dir="ltr">${esc(item.version)}</bdi></strong><span>${fmtDate(item.created_at)}</span><span>${item.record_count} records</span></div>`).join(''):'<div class="empty-inline compact-empty"><p>No Gold versions yet.</p><button type="button" class="button ghost" data-go="exports">Open Export center</button></div>';
  // UX-11: the dashboard is a snapshot, never a replacement for export gate tests.
  $('#dashboard-readiness').innerHTML=[
    `<li>${Number(s.pending_reviews)||0} pending human reviews reported by the API.</li>`,
    `<li>${eligible} records returned by the eligible-dataset API; build readiness has not been checked here.</li>`,
    '<li>Export readiness is checked independently in Export center before creating a version.</li>'
  ].join('');
}

async function loadConfig() {
  const config = await api('/api/v1/config'); state.tags = config.error_tags;
  // Product version from the server's single source (app/version.py); never hard-coded here.
  for(const id of ['app-version','settings-version']){const node=document.getElementById(id);if(node)node.textContent=config.app_version_display||'';}
  $('#error-tags').innerHTML = state.tags.map(tag=>`<button type="button" data-tag="${esc(tag)}">${esc(tagArabic[tag]||tag)}</button>`).join('');
  $('#filter-tag').innerHTML += state.tags.map(tag=>`<option value="${esc(tag)}">${esc(tagArabic[tag]||tag)}</option>`).join('');
  $('#error-tags').addEventListener('click', event=>{const button=event.target.closest('button');if(button)button.classList.toggle('selected');});
}

async function loadQueue() {
  if(!confirmDiscardReviewDraft())return;
  const data = await api('/api/v1/review-queue?include_demo=1');
  state.queue = data.items; state.queueIndex = Math.min(state.queueIndex, Math.max(0,state.queue.length-1));
  $('#nav-pending').textContent = state.queue.length;
  $('#queue-empty').classList.toggle('hidden', state.queue.length>0); $('#review-workspace').classList.toggle('hidden', !state.queue.length);
  if (state.queue.length) renderReview();
  else state.reviewDraftBaseline=null;
}

function renderCollectionWarning(item) {
  const incomplete=item.context_complete===false,warning=$('#review-context-warning');
  warning.textContent=incomplete?(item.context_warning||'This collected segment has incomplete context. Human review is available; training and evaluation are blocked.'):'';
  warning.classList.toggle('hidden',!incomplete);
  for(const id of ['training-eligible','evaluation-only']){
    const input=$(`#${id}`);input.disabled=incomplete;if(incomplete)input.checked=false;
  }
}

function renderReview() {
  const item = state.queue[state.queueIndex]; state.reviewStatus = null; state.reviewActionPending = false;
  $('#review-conversation-title').textContent = item.conversation_title || item.external_conversation_id;
  $('#review-demo').classList.toggle('hidden', !item.demo);
  $('#review-meta').innerHTML = [item.model_name||'Unspecified model',item.provider||'Unspecified provider',item.channel,fmtDate(item.message_created_at)].map(x=>`<span><bdi>${esc(x)}</bdi></span>`).join('');
  $('#context-messages').innerHTML = item.context.map(message=>`<article class="message ${esc(message.role)} ${message.id===item.message_id?'active-message':''}"><span class="role">${message.role==='user'?'User':message.role==='assistant'?'Assistant':esc(message.role)}</span><p dir="auto">${esc(message.content)}</p>${message.id===item.message_id?'<span class="message-status">Response under review</span>':''}</article>`).join('');
  $('#original-response').textContent = item.original_response; $('#corrected-response').value = item.corrected_response||item.original_response; $('#review-notes').value=item.review_notes||''; $('#ignored-reason').value=''; $('#reviewer-identity').value=item.reviewer||'human';
  $$('.status-grid button').forEach(button=>button.classList.remove('selected')); $('#edit-review-panel').classList.add('hidden'); $('#correction-editor').classList.add('hidden'); $('#correction-save-row').classList.add('hidden'); $('#save-review').disabled=true;
  $$('#error-tags button').forEach(button=>button.classList.toggle('selected',(item.tags||[]).includes(button.dataset.tag)));
  for(const [id,key] of Object.entries({'training-eligible':'training_eligible','evaluation-only':'evaluation_only','exclude-training':'exclude_from_training','needs-fact-check':'needs_fact_check','contains-personal':'contains_personal_data','contains-sensitive':'contains_sensitive_data'}))$(`#${id}`).checked=!!item[key];
  renderCollectionWarning(item);
  $$('.review-actions button').forEach(button=>button.disabled=false); $('#confirm-review-delete').disabled=false;
  $('#queue-position').textContent = `${state.queueIndex+1} of ${state.queue.length}`; $('#queue-progress').style.width = `${((state.queueIndex+1)/state.queue.length)*100}%`;
  state.reviewDraftBaseline=reviewDraftSnapshot();
}

function selectReviewStatus(status) {
  if (state.reviewActionPending) return;
  state.reviewStatus = status;
  $$('.status-grid button').forEach(button=>button.classList.toggle('selected',button.dataset.status===status));
  $('#correction-editor').classList.remove('hidden');
  $('#corrected-response').focus(); $('#corrected-response').select();
  $('#save-review').disabled=false;
}

function reviewPayload() {
  return {review_notes:$('#review-notes').value,reviewer:$('#reviewer-identity').value,expected_updated_at:state.queue[state.queueIndex]?.updated_at,training_eligible:$('#training-eligible').checked,evaluation_only:$('#evaluation-only').checked,exclude_from_training:$('#exclude-training').checked,needs_fact_check:$('#needs-fact-check').checked,contains_personal_data:$('#contains-personal').checked,contains_sensitive_data:$('#contains-sensitive').checked,tags:$$('#error-tags button.selected').map(b=>b.dataset.tag)};
}

function setReviewBusy(busy) {
  state.reviewActionPending=busy;
  $$('.review-actions button').forEach(button=>button.disabled=busy);
  $('#save-review').disabled=busy||!state.reviewStatus;
  $('#confirm-review-delete').disabled=busy;
}

function finishReviewAction(reviewId,message) {
  const index=state.queue.findIndex(item=>Number(item.id)===Number(reviewId));
  if(index>=0)state.queue.splice(index,1);
  if(state.queueIndex>=state.queue.length)state.queueIndex=Math.max(0,state.queue.length-1);
  $('#nav-pending').textContent=state.queue.length;toast(message);
  if(state.queue.length)renderReview();else{state.reviewDraftBaseline=null;$('#queue-empty').classList.remove('hidden');$('#review-workspace').classList.add('hidden');}
}

async function runReviewAction(action,payload,message) {
  if(state.reviewActionPending||!state.queue.length)return;
  const item=state.queue[state.queueIndex];setReviewBusy(true);
  try{await api(`/api/v1/reviews/${item.id}/${action}`,{method:'POST',body:JSON.stringify(payload)});finishReviewAction(item.id,message);}
  catch(error){toast(error.message||'Unable to perform action. Try again.',true);setReviewBusy(false);}
}

async function approveReview(){return runReviewAction('approve',reviewPayload(),'Sample approved. Moved to the next sample.');}
async function excludeReview(){const reason=$('#ignored-reason').value.trim();if(!reason){toast('Enter an exclusion reason first.',true);return;}return runReviewAction('exclude',{...reviewPayload(),reason},'Sample excluded; original data and reviewer metadata preserved.');}

function openEditReview() {
  if(state.reviewActionPending)return;
  state.reviewStatus=null;$('#edit-review-panel').classList.remove('hidden');$('#correction-save-row').classList.remove('hidden');$('#correction-editor').classList.add('hidden');$('#save-review').disabled=true;
  $$('.status-grid button').forEach(button=>button.classList.remove('selected'));
}

function cancelEditReview() {
  state.reviewStatus=null;$('#edit-review-panel').classList.add('hidden');$('#correction-save-row').classList.add('hidden');$('#correction-editor').classList.add('hidden');
}

async function saveReview() {
  if (!state.reviewStatus||state.reviewActionPending) return;
  const payload={...reviewPayload(),review_status:state.reviewStatus,corrected_response:$('#corrected-response').value};
  const button=$('#save-review');button.textContent='Saving…';
  try{await runReviewAction('correct',payload,'Correction saved. Moved to the next sample.');}
  finally{button.textContent='Save edit and continue';}
}

function openDeleteReview(){if(!state.reviewActionPending&&state.queue.length)$('#review-delete-dialog').showModal();}
async function confirmDeleteReview(){
  if(state.reviewActionPending)return;
  const currentId=state.queue[state.queueIndex]?.id;
  await runReviewAction('delete',{},'Sample moved to deleted items.');
  if(!state.queue.some(item=>Number(item.id)===Number(currentId)))$('#review-delete-dialog').close();
}

// UX-20: lists are paged by the server; the pager states exactly which records are shown
// and how many exist, so nothing is silently cut off.
function listPage(key){return state.pages[key]||(state.pages[key]={offset:0,limit:100});}
function pageQuery(key){const page=listPage(key);return `limit=${page.limit}&offset=${page.offset}`;}
function pageSummary(page){
  if(!page.total)return 'No records';
  return `Showing ${page.offset+1}–${page.offset+page.returned} of ${page.total}`;
}
// Returns true when the requested page is past the end (e.g. after deletions) and was corrected.
function correctedPage(key,page){
  if(page.returned||!page.total||!page.offset)return false;
  listPage(key).offset=Math.floor((page.total-1)/page.limit)*page.limit;return true;
}
function renderPager(key,page,reload){
  const el=$(`#${key}-pager`);if(!el)return;
  el.innerHTML=`<span class="pager-summary" role="status">${esc(pageSummary(page))}</span><button type="button" class="button ghost" data-page="prev" ${page.offset>0?'':'disabled'}>Previous page</button><button type="button" class="button ghost" data-page="next" ${page.has_more?'':'disabled'}>Next page</button>`;
  el.querySelector('[data-page="prev"]').onclick=()=>{listPage(key).offset=Math.max(0,page.offset-page.limit);reload().catch(error=>toast(error.message,true));};
  el.querySelector('[data-page="next"]').onclick=()=>{listPage(key).offset=page.offset+page.limit;reload().catch(error=>toast(error.message,true));};
}

async function loadConversations(options={}) {
  if(options.fresh)listPage('conversations').offset=0;
  const search=encodeURIComponent($('#conversation-search').value||'');const channel=encodeURIComponent($('#conversation-channel').value||'');
  const data=await api(`/api/v1/conversations?search=${search}&channel=${channel}&${pageQuery('conversations')}`);
  if(correctedPage('conversations',data.page))return loadConversations();
  data.items.forEach(item=>state.channels.add(item.channel));populateChannelFilters();
  $('#conversation-list').innerHTML=data.items.length?data.items.map(item=>`<button class="conversation-item" data-id="${item.id}"><small>${item.message_count} messages</small><strong dir="auto">${esc(item.title||item.external_conversation_id)}</strong><span>${item.model_name?`<bdi>${esc(item.model_name)}</bdi>`:'Unspecified'} · <bdi>${esc(item.channel)}</bdi> · ${item.pending_count||0} Pending</span></button>`).join(''):'<div class="empty-inline">No results.</div>';
  renderPager('conversations',data.page,loadConversations);
}

function populateChannelFilters(){['#conversation-channel','#filter-channel'].forEach(selector=>{const select=$(selector),current=select.value,first=select.options[0].outerHTML;select.innerHTML=first+[...state.channels].sort().map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');select.value=current;});}

async function showConversation(id) {
  const data=await api(`/api/v1/conversations/${id}`);$$('.conversation-item').forEach(b=>b.classList.toggle('active',Number(b.dataset.id)===Number(id)));
  $('#conversation-detail').innerHTML=`<header class="conversation-header"><h2 dir="auto">${esc(data.conversation.title)}</h2><p dir="ltr">${esc(data.conversation.external_conversation_id)}</p><div class="meta-row"><span><bdi>${esc(data.conversation.model_name||'Unspecified')}</bdi></span><span><bdi>${esc(data.conversation.provider||'Unspecified')}</bdi></span><span><bdi>${esc(data.conversation.channel)}</bdi></span>${data.conversation.demo?'<span class="badge demo">Demo</span>':''}</div></header><div class="chat-stream">${data.messages.map(message=>`<article class="message ${esc(message.role)}"><span class="role">${message.role==='user'?'User':message.role==='assistant'?'Assistant':esc(message.role)} ${message.review_status?`· <span class="status-badge status-${esc(message.review_status)}">${esc(statusArabic[message.review_status])}</span>`:''}</span><p dir="auto">${esc(message.content)}</p>${message.corrected_response?`<div class="answer corrected"><strong>Correction:</strong><p dir="auto">${esc(message.corrected_response)}</p></div>`:''}</article>`).join('')}</div>`;
}

async function loadReviewed(options={}){
  if(options.fresh)listPage('reviewed').offset=0;
  const params=new URLSearchParams({search:$('#reviewed-search').value,status:'',review_status:$('#filter-status').value,channel:$('#filter-channel').value,tag:$('#filter-tag').value,training_eligible:$('#filter-eligible').value,date_from:$('#filter-date-from').value,date_to:$('#filter-date-to').value});
  const data=await api(`/api/v1/reviewed?${params}&${pageQuery('reviewed')}`);
  if(correctedPage('reviewed',data.page))return loadReviewed();
  state.reviewedItems=data.items;data.items.forEach(i=>state.channels.add(i.channel));populateChannelFilters();
  state.reviewedSelected.clear();updateReviewedBulk();
  $('#reviewed-list').innerHTML=data.items.length?data.items.map(item=>`<article class="reviewed-card"><header><label class="inline-check"><input class="reviewed-row-check" type="checkbox" data-review-id="${item.id}"> Select</label><h3 dir="auto">${esc(item.conversation_title)}</h3><span class="status-badge status-${esc(item.review_status)}">${esc(statusArabic[item.review_status])}</span></header><div class="answer"><strong>Original:</strong>${fullText(item.original_response,220)}</div>${item.corrected_response?`<div class="answer corrected"><strong>Saved correction:</strong>${fullText(item.corrected_response,220)}</div>`:''}<div class="tag-picker">${item.tags.map(tag=>`<span class="status-badge status-FULL_CORRECTION">${esc(tagArabic[tag]||tag)}</span>`).join('')}</div><footer><span>${esc(item.reviewer||'—')} · ${fmtDate(item.updated_at)} · ${esc(item.model_name||'—')} · ${esc(item.channel)}</span><span>${item.training_eligible?'Eligible':'Ineligible'}${item.evaluation_only?' · Evaluation':''}</span></footer>${['IGNORED','DELETED'].includes(item.review_status)?`<button class="button ghost" data-restore-review="${item.id}">Restore for review</button>`:`<button class="button ignore-action" data-exclude-review="${item.id}">Exclude</button>`}</article>`).join(''):'<div class="empty-state"><h2>No results</h2><p>Change filters or start reviewing responses.</p></div>';
  renderPager('reviewed',data.page,loadReviewed);
}

function updateReviewedBulk(){const count=state.reviewedSelected.size;$('#bulk-review-count').textContent=count?`${count} reviews selected`:'No reviews selected';$('#bulk-exclude-reviews').disabled=!count;$('#bulk-restore-reviews').disabled=!count;}
async function bulkReviewed(action,ids=[...state.reviewedSelected]){const reason=$('#bulk-review-reason').value.trim();if(!reason){toast('An exclusion or restoration reason is required.',true);return;}const expected_updated_at_by_id=Object.fromEntries(ids.map(id=>[id,state.reviewedItems?.find(item=>Number(item.id)===Number(id))?.updated_at]));const result=await api('/api/v1/reviews/bulk',{method:'POST',body:JSON.stringify({action,review_ids:ids,reason,reviewer:'human',expected_updated_at_by_id})});toast(`Atomic operation completed on ${result.count} reviews.`);await loadReviewed();await loadQueue();}

function addSftTurn(role='user',content=''){
  const row=document.createElement('div');row.className='turn-row';row.innerHTML=`<select class="turn-role" aria-label="Turn role"><option value="user" ${role==='user'?'selected':''}>User</option><option value="assistant" ${role==='assistant'?'selected':''}>Assistant</option><option value="system" ${role==='system'?'selected':''}>System</option></select><textarea dir="auto" aria-label="Turn content" class="turn-content" placeholder="Enter turn content…">${esc(content)}</textarea><button type="button" aria-label="Delete turn">×</button>`;row.querySelector('button').addEventListener('click',()=>row.remove());$('#sft-turns').append(row);
}

function formPayload(form){const raw=Object.fromEntries(new FormData(form));$$('input[type=checkbox]',form).forEach(input=>raw[input.name]=input.checked);return raw;}
async function submitDataForm(form,endpoint,extra={}){const button=form.querySelector('button[type=submit]');button.disabled=true;try{await api(endpoint,{method:'POST',body:JSON.stringify({...formPayload(form),...extra})});toast('Record saved with source information.');form.reset();}catch(error){toast(error.message,true);}finally{button.disabled=false;}}

const originLabels={real_conversation:'Real conversation',manual:'Manual',human_corrected:'Human corrected',synthetic_reviewed:'Reviewed synthetic',ai_arena:'AI Arena',imported:'Imported'};
const manualTypeLabels={sft:'Conversation / SFT',direct:'Direct language text',dpo:'Preference pair / DPO'};
const languageLabels={najdi_riyadh:'Najdi / Riyadh',saudi_neutral:'Saudi neutral',msa:'MSA',technical_arabic:'Technical Arabic',formal_arabic:'Formal Arabic'};

function manualParams(){
  return new URLSearchParams({
    search:$('#manual-search').value,type:$('#manual-type').value,status:$('#manual-status').value,
    language_layer:$('#manual-language').value,source:$('#manual-source').value,origin:$('#manual-origin').value,
    domain:$('#manual-domain').value,date_from:$('#manual-date-from').value,date_to:$('#manual-date-to').value,
    sort:$('#manual-sort').value,show_archived:$('#manual-show-archived').checked?'1':'0'
  });
}

async function loadManualData(options={}){
  if(options.fresh)listPage('manual').offset=0;
  const data=await api(`/api/v1/manual-data?${manualParams()}&${pageQuery('manual')}`);
  if(correctedPage('manual',data.page))return loadManualData();
  state.manualItems=data.items;state.manualSelected.clear();updateManualBulk();
  const labels=[['total','Total items'],['sft','SFT'],['direct','Direct language text'],['dpo','DPO'],['eligible','Dataset eligible'],['ineligible','Ineligible'],['archived','Archived'],['excluded','Excluded from dataset selection'],['ignored','Ignored'],['deleted','Deleted']];
  $('#manual-stats').innerHTML=labels.map(([key,label])=>`<div class="stat-card"><span>${label}</span><strong>${data.summary[key]||0}</strong></div>`).join('');
  for(const key of ['source','origin','domain'])$(`#manual-${key}-options`).innerHTML=(data.facets[key]||[]).map(x=>`<option value="${esc(x)}"></option>`).join('');
  $('#manual-list').innerHTML=data.items.length?data.items.map(item=>`<tr class="${item.archived?'is-archived':''}">
    <td><input class="manual-row-check" type="checkbox" data-key="${item.item_type}:${item.id}" aria-label="Select record ${item.id}"></td>
    <td><code>${esc(item.item_type)}:${item.id}</code>${item.parent_item_id?`<small>Copy of #${item.parent_item_id}</small>`:''}</td>
    <td><strong>${esc(manualTypeLabels[item.item_type])}</strong><p dir="auto">${esc(compact(item.preview,150))}</p></td>
    <td><span>${esc(languageLabels[item.language_layer]||item.language_layer||'—')}</span><small>${esc(item.domain||'—')}</small></td>
    <td><span><bdi>${esc(item.source||'—')}</bdi></span><small>${esc(originLabels[item.origin]||item.origin||'—')}</small></td>
    <td><span>${fmtDate(item.created_at)}</span><small>${fmtDate(item.updated_at)}</small></td>
    <td><div class="status-stack"><span class="status-pill ${item.training_eligible_effective?'ok':'neutral'}">${item.training_eligible_effective?'Eligible':'Ineligible'}</span>${item.archived?'<span class="status-pill archived">Archived</span>':''}${item.exclude_from_training?'<span class="status-pill danger">Excluded</span>':''}${item.exported_before?`<span class="status-pill exported">Previously exported</span>`:''}</div></td>
    <td><bdi>v${item.version_number}</bdi></td>
    <td><div class="row-actions"><button data-action="view" data-type="${item.item_type}" data-id="${item.id}">View</button><button data-action="edit" data-type="${item.item_type}" data-id="${item.id}">Edit</button><button data-action="clone" data-type="${item.item_type}" data-id="${item.id}">Duplicate as new</button><button data-action="archive" data-type="${item.item_type}" data-id="${item.id}">${item.archived?'Unarchive':'Archive'}</button><button data-action="exclude" data-type="${item.item_type}" data-id="${item.id}">${item.exclude_from_training?'Remove exclusion':'Exclude from dataset selection'}</button><button data-action="ignore" data-type="${item.item_type}" data-id="${item.id}">Ignore</button><button class="danger" data-action="delete" data-type="${item.item_type}" data-id="${item.id}">Delete</button></div></td>
  </tr>`).join(''):'<tr><td colspan="9"><div class="empty-inline">No items match the current filters.</div></td></tr>';
  $('#manual-select-all').checked=false;
  renderPager('manual',data.page,loadManualData);
}

function updateManualBulk(){
  $('#manual-selected-count').textContent=state.manualSelected.size;
  $('#manual-bulk').classList.toggle('hidden',!state.manualSelected.size);
}

function manualContent(item){
  if(item.item_type==='sft')return `<div class="chat-stream manual-chat">${(item.messages||[]).map(turn=>`<article class="message ${esc(turn.role)}"><span class="role">${turn.role==='user'?'User':turn.role==='assistant'?'Assistant':'System'}</span><p dir="auto">${esc(turn.content)}</p></article>`).join('')}</div>`;
  if(item.item_type==='direct')return `<div class="full-text" dir="auto">${esc(item.text)}</div>`;
  const context=(item.prompt_context||[]).map(turn=>turn.content||'').join('\n');return `<div class="dpo-detail"><section><b>Prompt / Context</b><p dir="auto">${esc(context)}</p></section><section class="rejected"><b>Rejected response</b><p dir="auto">${esc(item.rejected_response)}</p></section><section class="preferred"><b>Preferred response</b><p dir="auto">${esc(item.preferred_response)}</p></section></div>`;
}

function manualStatusHtml(item){
  return `<span class="status-pill ${item.training_eligible_effective?'ok':'neutral'}">${item.training_eligible_effective?'Dataset eligible':'Not eligible for the dataset'}</span>${item.archived?'<span class="status-pill archived">Archived</span>':''}${item.exclude_from_training?'<span class="status-pill danger">Excluded from dataset selection</span>':''}${item.evaluation_only?'<span class="status-pill neutral">Evaluation only</span>':''}<span class="status-pill exported">Exported before: ${item.exported_before?'Yes':'No'}</span>`;
}

function renderManualDetails(item){
  const exported=item.exported_versions?.length?`<div class="export-history"><strong>Previous Gold versions</strong>${item.exported_versions.map(v=>`<code>${esc(v)}</code>`).join('')}</div>`:'<div class="export-history muted">Not included in a previous Gold version.</div>';
  $('#manual-tab-details').innerHTML=`
    <div class="detail-actions"><button class="button primary" data-detail-action="edit">Edit</button><button class="button ghost" data-detail-action="eligibility">${item.training_eligible?'Make ineligible':'Make dataset eligible'}</button><button class="button ghost" data-detail-action="clone">Duplicate as new</button><button class="button ghost" data-detail-action="archive">${item.archived?'Unarchive':'Archive'}</button><button class="button ghost" data-detail-action="exclude">${item.exclude_from_training?'Remove exclusion':'Exclude from dataset selection'}</button><button class="button ghost" data-detail-action="ignore">Ignore</button><button class="button danger-button" data-detail-action="delete">Delete</button></div>
    ${manualContent(item)}
    <dl class="detail-grid"><div><dt>Language layer</dt><dd><bdi>${esc(languageLabels[item.language_layer]||item.language_layer||'—')}</bdi></dd></div><div><dt>Domain</dt><dd><bdi>${esc(item.domain||'—')}</bdi></dd></div><div><dt>Source</dt><dd><bdi>${esc(item.source||'—')}</bdi></dd></div><div><dt>Source type</dt><dd><bdi>${esc(item.source_type||'—')}</bdi></dd></div><div><dt>Origin</dt><dd><bdi>${esc(item.origin||'—')}</bdi></dd></div><div><dt>Created</dt><dd>${fmtDate(item.created_at)}</dd></div><div><dt>Last modified</dt><dd>${fmtDate(item.updated_at)}</dd></div><div><dt>Current version</dt><dd>v${item.version_number}</dd></div><div><dt>Parent item</dt><dd>${item.parent_item_id?`#${item.parent_item_id}`:'—'}</dd></div><div class="wide"><dt>Notes</dt><dd><bdi>${esc(item.notes||'—')}</bdi></dd></div></dl>${exported}`;
}

function option(value,label,current){return `<option value="${value}" ${value===current?'selected':''}>${label}</option>`;}
function commonManualFields(item){
  return `<div class="form-grid"><label>Language layer<select name="language_layer">${Object.entries(languageLabels).map(([v,l])=>option(v,l,item.language_layer)).join('')}</select></label><label>Domain<input name="domain" value="${esc(item.domain||'')}"></label><label>Source<input name="source" value="${esc(item.source||'')}"></label><label>Source type<select name="source_type">${[['human_written','Human written'],['human_corrected','Human corrected'],['synthetic_reviewed','Reviewed synthetic'],['external_licensed','Licensed external']].map(([v,l])=>option(v,l,item.source_type)).join('')}</select></label><label>Origin<select name="origin">${[['manual','Manual'],['human_corrected','Human corrected'],['synthetic_reviewed','Reviewed synthetic'],['ai_arena','AI Arena'],['imported','Imported'],['real_conversation','Real conversation']].map(([v,l])=>option(v,l,item.origin)).join('')}</select></label></div><label class="wide-label">Notes<textarea dir="auto" name="notes" rows="2">${esc(item.notes||'')}</textarea></label><div class="check-grid"><label><input name="training_eligible" type="checkbox" ${item.training_eligible?'checked':''}> Dataset eligible</label><label><input name="evaluation_only" type="checkbox" ${item.evaluation_only?'checked':''}> Evaluation only</label><label><input name="exclude_from_training" type="checkbox" ${item.exclude_from_training?'checked':''}> Excluded from dataset selection</label><label><input name="archived" type="checkbox" ${item.archived?'checked':''}> Archived</label></div><label class="wide-label">Change note<textarea dir="auto" name="change_notes" rows="2" placeholder="What changed?"></textarea></label>`;
}

function renderManualEdit(item){
  let specific='';
  if(item.item_type==='sft')specific=`<div id="manual-edit-turns" class="turn-builder">${(item.messages||[]).map(turn=>manualTurnRow(turn.role,turn.content)).join('')}</div><button type="button" id="manual-add-turn" class="button ghost">＋ Add turn</button>`;
  else if(item.item_type==='direct')specific=`<label class="wide-label">Text<textarea dir="auto" name="text" rows="10" required>${esc(item.text)}</textarea></label>`;
  else specific=`<label class="wide-label">Prompt / Context<textarea dir="auto" name="prompt_context" rows="4" required>${esc((item.prompt_context||[]).map(x=>x.content||'').join('\n'))}</textarea></label><div class="preference-grid"><label>Rejected response<textarea dir="auto" name="rejected_response" rows="7" required>${esc(item.rejected_response)}</textarea></label><label>Preferred response<textarea dir="auto" name="preferred_response" rows="7" required>${esc(item.preferred_response)}</textarea></label></div>`;
  $('#manual-tab-details').innerHTML=`<form id="manual-edit-form" class="manual-edit-form">${specific}${commonManualFields(item)}<p id="manual-save-state" class="save-state" role="status" aria-live="polite"></p><div class="save-row"><button type="button" class="button ghost" data-detail-action="cancel-edit">Cancel</button><button type="submit" class="button primary">Save</button></div></form>`;
  if(item.item_type==='sft')$('#manual-add-turn').addEventListener('click',()=>$('#manual-edit-turns').insertAdjacentHTML('beforeend',manualTurnRow('user','')));
  $('#manual-edit-form').addEventListener('click',e=>{if(e.target.matches('.remove-manual-turn'))e.target.closest('.turn-row').remove();});
  $('#manual-edit-form').addEventListener('submit',saveManualEdit);
}

function manualTurnRow(role,content){return `<div class="turn-row"><select class="turn-role" aria-label="Turn role">${option('user','User',role)}${option('assistant','Assistant',role)}${option('system','System',role)}</select><textarea dir="auto" aria-label="Turn content" class="turn-content">${esc(content)}</textarea><button class="remove-manual-turn" type="button" aria-label="Delete turn">×</button></div>`;}

async function showManualItem(type,id,edit=false){
  const item=await api(`/api/v1/manual-data/${type}/${id}`);state.manualCurrent=item;
  $('#manual-dialog-kind').textContent=manualTypeLabels[type];$('#manual-dialog-title').innerHTML=`<bdi dir="ltr">${esc(type)}:${id} · v${item.version_number}</bdi>`;$('#manual-dialog-status').innerHTML=manualStatusHtml(item);
  renderManualDetails(item);$('#manual-tab-versions').innerHTML='<div class="empty-inline">Open this tab to load version history.</div>';
  $$('.dialog-tabs button').forEach(b=>b.classList.toggle('active',b.dataset.manualTab==='details'));$$('.manual-tab').forEach(x=>x.classList.toggle('active',x.id==='manual-tab-details'));
  if(edit)renderManualEdit(item);if(!$('#manual-dialog').open)$('#manual-dialog').showModal();
}

async function saveManualEdit(event){
  event.preventDefault();
  const item=state.manualCurrent,form=event.currentTarget,payload=formPayload(form);
  const button=form.querySelector('button[type=submit]'),feedback=form.querySelector('#manual-save-state');
  if(button.disabled)return;
  if(item.item_type==='sft')payload.messages=Array.from(document.querySelectorAll('#manual-edit-turns .turn-row')).map(row=>({role:row.querySelector('.turn-role').value,content:row.querySelector('.turn-content').value}));
  button.disabled=true;button.textContent='Saving…';feedback.textContent='Saving a new version…';feedback.className='save-state';
  try{
    const result=await api(`/api/v1/manual-data/${item.item_type}/${item.id}`,{method:'PATCH',body:JSON.stringify(payload)});
    state.manualCurrent=result.item;
    renderManualDetails(result.item);
    $('#manual-dialog-title').innerHTML=`<bdi dir="ltr">${esc(item.item_type)}:${item.id} · v${result.item.version_number}</bdi>`;
    $('#manual-dialog-status').innerHTML=manualStatusHtml(result.item);
    toast('New version saved in change history.');
    try{await loadManualData();}catch(error){toast('Saved successfully, but the list could not refresh: '+error.message,true);}
  }catch(error){
    // UX-16: leave the form/draft intact and a persistent error beside Retry.
    feedback.textContent='Unable to save: '+error.message;
    feedback.className='save-state error';
    button.textContent='Retry save';
  }finally{if(button.isConnected)button.disabled=false;}
}

async function loadManualVersions(){
  const item=state.manualCurrent,data=await api(`/api/v1/manual-data/${item.item_type}/${item.id}/versions`);
  $('#manual-tab-versions').innerHTML=data.items.length?data.items.map(v=>`<article class="version-row"><div><strong>v${v.version_number}</strong><span>${fmtDate(v.created_at)} · ${v.changed_by==='human'?'human':'system'}</span></div><p dir="auto">${esc(v.change_notes||'—')}</p><small>Changed fields: ${esc(v.changed_fields.length?v.changed_fields.join(', '):'Base version')}</small><button class="button ghost" data-version="${v.version_number}">View version</button></article>`).join(''):'<div class="empty-inline">No version history.</div>';
  $('#manual-tab-versions').onclick=e=>{const button=e.target.closest('[data-version]');if(!button)return;const version=data.items.find(v=>v.version_number===Number(button.dataset.version));$('#manual-tab-versions').innerHTML=`<button id="back-to-versions" class="button ghost">← Version history</button><div class="readonly-banner">Read-only version · v${version.version_number}</div><pre class="snapshot-view">${esc(JSON.stringify(version.snapshot,null,2))}</pre>`;$('#back-to-versions').onclick=loadManualVersions;};
}

async function manualAction(action,type,id){
  const item=state.manualItems.find(x=>x.item_type===type&&Number(x.id)===Number(id))||state.manualCurrent;
  if(action==='view'||action==='edit')return showManualItem(type,id,action==='edit');
  if(action==='clone'){await api(`/api/v1/manual-data/${type}/${id}/clone`,{method:'POST',body:'{}'});toast('Created an independent item with parent_item_id.');return loadManualData();}
  if(action==='archive'){await api(`/api/v1/manual-data/${type}/${id}/archive`,{method:'POST',body:JSON.stringify({archived:!item.archived})});toast(item.archived?'Unarchived.':'Archived.');}
  if(action==='exclude'){await api(`/api/v1/manual-data/${type}/${id}/exclude`,{method:'POST',body:JSON.stringify({excluded:!item.exclude_from_training})});toast(item.exclude_from_training?'Exclusion removed.':'Excluded from dataset selection.');}
  if(action==='eligibility'){await api(`/api/v1/manual-data/${type}/${id}`,{method:'PATCH',body:JSON.stringify({training_eligible:!item.training_eligible,change_notes:'Change dataset eligibility'})});toast('Dataset eligibility updated.');}
  if(action==='ignore'){
    await api(`/api/v1/manual-data/${type}/${id}/ignore`,{method:'POST',body:'{}'});toast('Record ignored and preserved in the archive.');$('#manual-dialog').close();
  }
  if(action==='delete'){
    if(item.exported_before&&!confirm(tr(`This record was previously included in a Dataset Version previous version (${item.exported_versions.join(', ')}). Older versions will remain unchanged. Continue?`)))return;
    if(!confirm(tr('Delete this record? It will be excluded from dataset selection, preserved in the archive, and can be restored later.')))return;
    await api(`/api/v1/manual-data/${type}/${id}`,{method:'DELETE',body:JSON.stringify({confirm_exported:item.exported_before})});toast('Record moved to deleted items; versions of Gold remain unchanged.');$('#manual-dialog').close();
  }
  await loadManualData();if($('#manual-dialog').open&&action!=='delete')await showManualItem(type,id);
}

async function applyManualBulk(){
  const action=$('#manual-bulk-action').value;if(!action)return toast('Choose a bulk action.',true);
  const items=[...state.manualSelected].map(key=>{const [type,id]=key.split(':');return {type,id:Number(id)};});
  await api('/api/v1/manual-data/bulk',{method:'POST',body:JSON.stringify({action,items,change_notes:'Bulk edit from administration panel'})});toast(`Updated ${items.length} records.`);await loadManualData();
}

async function loadDataset(){
  const include=$('#dataset-demo').checked?'1':'0';const data=await api(`/api/v1/dataset-records?include_demo=${include}`);const labels={total:'Total',total_approved:'Approved as is',full_corrections:'Full correction',dialect_corrections:'Dialect correction',content_corrections:'Content correction',manual_additions:'Manual additions',multi_turn_conversations:'Multi-turn',direct_language_texts:'Direct texts',preference_pairs:'Preference pairs'};
  $('#dataset-stats').innerHTML=Object.entries(labels).map(([key,label])=>`<div class="stat-card"><span>${label}</span><strong>${data.stats[key]||0}</strong></div>`).join('');
  const items=[...data.reviews.map(i=>({...i,type:'Review',preview:i.messages.at(-1)?.content})),...data.manual_sft.map(i=>({...i,type:'Manual SFT',preview:i.messages?.at(-1)?.content})),...data.direct_language.map(i=>({...i,type:'Direct text',preview:i.text})),...data.preference_pairs.map(i=>({...i,type:'Preference',preview:i.preferred_response}))];
  $('#dataset-list').innerHTML=items.length?items.map(item=>`<div class="dataset-item"><span class="status-badge status-APPROVED">${esc(item.type)}</span><div>${fullText(item.preview,180)}<small>${esc(originLabels[item.origin]||item.origin||'—')} · ${item.language_layer?esc(languageLabels[item.language_layer]||item.language_layer):`<bdi>${esc(item.model_name||'—')}</bdi>`} · <bdi>${esc(item.domain||'—')}</bdi></small></div><code>${esc(item.id)}</code></div>`).join(''):'<div class="empty-inline">No eligible records. Human approval is required first.</div>';
}

async function previewDedup(){
  const include=$('#export-demo').checked?'1':'0';
  const [report,readiness]=await Promise.all([
    api(`/api/v1/exports/dedup-report?include_demo=${include}`),
    api(`/api/v1/exports/readiness?include_demo=${include}`)
  ]);
  const blockers=readiness.blocking_findings||[];
  // UX-06: the persistent gate must show every blocker; a toast or top-three
  // sample would hide the reason a dataset cannot be exported.
  const gate=readiness.ok
    ? '<p><strong>Export gate: ready.</strong></p>'
    : `<section class="export-blockers" role="alert"><strong>Export gate: blocked — ${blockers.length} finding(s).</strong><ol>${blockers.map(item=>`<li><bdi>${esc(item.sample_id||'General')}</bdi>: ${esc(item.reason)}</li>`).join('')}</ol></section>`;
  $('#dedup-result').innerHTML=`Checked <strong>${report.record_count}</strong> records: <strong>${report.exact_duplicate_groups.length}</strong> exact duplicate groups and <strong>${report.near_duplicates.length}</strong> near duplicates. No records are deleted automatically.${gate}`;
  toast(readiness.ok?'Duplicate and readiness checks completed.':'Check completed: export blockers were found.',!readiness.ok);
  return readiness;
}
async function createExport(){const button=$('#create-export');button.disabled=true;button.textContent='Creating version…';try{const readiness=await previewDedup();if(!readiness.ok)throw new Error('Export is blocked until the displayed review findings are resolved.');const result=await api('/api/v1/exports',{method:'POST',body:JSON.stringify({include_demo:$('#export-demo').checked,filters:{source:'dashboard'}})});toast(`Created ${result.export.version} successfully.`);await loadExports();}catch(error){toast(error.message,true);}finally{button.disabled=false;button.textContent='Create new version';}}
async function loadFrozenHandoffVersions(){
  // UX-12: only a real Frozen, readable version can be selected for Unsloth.
  // Never accept arbitrary version names typed into the UI.
  const select=$('#unsloth-version'),button=$('#unsloth-create'),previous=select.value;
  button.disabled=true;select.disabled=true;
  select.replaceChildren(new Option('Loading frozen versions…',''));
  try{
    const data=await api('/api/v1/dataset-versions');
    if(!Array.isArray(data.items))throw Error('Invalid dataset catalog');
    const versions=data.items.filter(x=>x.readable===true&&x.state==='Frozen');
    select.replaceChildren(new Option(versions.length?'Choose a frozen dataset version':'No frozen versions available',''));
    for(const v of versions)select.add(new Option(v.version,v.version));
    if(versions.some(v=>v.version===previous))select.value=previous;
    select.disabled=!versions.length;
    button.disabled=!select.value;
    select.onchange=()=>{button.disabled=!select.value;};
  }catch(error){
    select.replaceChildren(new Option('Unable to load frozen versions',''));
    $('#unsloth-result').textContent='Unable to load dataset versions: '+error.message;
  }
}
async function loadExports(){
  const data=await api('/api/v1/exports');
  $('#exports-list').innerHTML=data.items.length?data.items.map(item=>{let manifest={};try{manifest=JSON.parse(item.manifest_json);}catch{}return`<div class="export-row"><strong>${esc(item.version)}</strong><div><span>${fmtDate(item.created_at)} · ${item.record_count} records</span><br><code>${esc(item.export_path)}</code></div><span>${Object.keys(manifest.sha256||{}).length} checksums</span></div>`;}).join(''):'<div class="empty-inline">No versions created yet.</div>';
  await loadFrozenHandoffVersions();
}

async function loadAnalytics(){const data=await api('/api/v1/analytics');const s=data.summary;const stats=[['Total conversations',s.total_conversations],['Total responses',s.total_responses],['Pending review',s.pending_reviews],['Approval rate',`${s.approved_pct}%`],['Dialect correction',`${s.dialect_corrections_pct}%`],['Content correction',`${s.content_corrections_pct}%`],['Full correction',`${s.full_corrections_pct}%`],['Ignored',s.ignored],['Deleted',s.deleted],['Dataset eligible',s.training_eligible_count]];$('#analytics-stats').innerHTML=stats.map(([label,value])=>`<div class="stat-card"><span>${label}</span><strong>${value??0}</strong></div>`).join('');$('#model-analytics').innerHTML=`<table class="analytics-table"><thead><tr><th>Model</th><th>Responses</th><th>Approve</th><th>Dialect error</th><th>Content error</th></tr></thead><tbody>${data.by_model.map(x=>`<tr><td>${esc(x.name)}</td><td>${x.total}</td><td>${x.approval_rate??0}%</td><td>${x.dialect_error_rate??0}%</td><td>${x.content_error_rate??0}%</td></tr>`).join('')}</tbody></table>`;renderBars('#channel-analytics',data.by_channel);renderBars('#tag-analytics',data.top_tags.map(x=>({...x,name:tagArabic[x.name]||x.name})));}
function renderBars(selector,items){const max=Math.max(1,...items.map(x=>x.count));$(selector).innerHTML=items.length?items.map(x=>`<div class="bar-item"><header><span>${esc(x.name||'Unspecified')}</span><strong>${x.count}</strong></header><div class="bar-track"><i data-share="${x.count/max*100}"></i></div></div>`).join(''):'<div class="empty-inline">No data yet.</div>';
  applyShares(selector);}
// The CSP forbids style attributes, so bar widths are set through the DOM after rendering.
function applyShares(selector){$$(`${selector} [data-share]`).forEach(bar=>{bar.style.width=`${Number(bar.dataset.share)||0}%`;});}

function bindEvents(){
  window.addEventListener('beforeunload',e=>{if(hasUnsavedReviewDraft()){e.preventDefault();e.returnValue='';}});
  $('#main-nav').addEventListener('click',e=>{const button=e.target.closest('[data-view]');if(button)switchView(button.dataset.view);});$('#mobile-menu').addEventListener('click',()=>setMobileNav(!$('.sidebar').classList.contains('open')));document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('.sidebar').classList.contains('open')){setMobileNav(false);$('#mobile-menu').focus();}});document.addEventListener('click',e=>{if($('.sidebar').classList.contains('open')&&!e.target.closest('.sidebar,#mobile-menu'))setMobileNav(false);});$('#refresh-view').addEventListener('click',()=>loadView(state.view).then(()=>toast('Data refreshed.')).catch(e=>toast(e.message,true)));
  document.addEventListener('click',e=>{const button=e.target.closest('[data-go]');if(button)switchView(button.dataset.go);});
  $('#collapse-sidebar').addEventListener('click',()=>{const collapsed=$('.shell').classList.toggle('sidebar-collapsed');prefs.set('najdilab.sidebar',collapsed?'collapsed':'expanded');$('#collapse-sidebar').setAttribute('aria-expanded',String(!collapsed));});
  $('.status-grid').addEventListener('click',e=>{const b=e.target.closest('[data-status]');if(b)selectReviewStatus(b.dataset.status);});$('#approve-review').addEventListener('click',approveReview);$('#edit-review').addEventListener('click',openEditReview);$('#exclude-review').addEventListener('click',excludeReview);$('#delete-review').addEventListener('click',openDeleteReview);$('#save-review').addEventListener('click',saveReview);$('#cancel-edit-review').addEventListener('click',cancelEditReview);$('#cancel-review-delete').addEventListener('click',()=>$('#review-delete-dialog').close());$('#confirm-review-delete').addEventListener('click',confirmDeleteReview);
  const restrictionControls=['#evaluation-only','#exclude-training','#needs-fact-check','#contains-personal','#contains-sensitive'];
  restrictionControls.forEach(selector=>$(selector).addEventListener('change',e=>{if(e.target.checked)$('#training-eligible').checked=false;}));
  $('#training-eligible').addEventListener('change',e=>{if(e.target.checked&&restrictionControls.some(selector=>$(selector).checked)){e.target.checked=false;toast('Resolve dataset restrictions explicitly before marking this record eligible.',true);}});
  $('#conversation-list').addEventListener('click',e=>{const b=e.target.closest('[data-id]');if(b)showConversation(b.dataset.id).catch(x=>toast(x.message,true));});$('#search-conversations').addEventListener('click',()=>loadConversations({fresh:true}).catch(e=>toast(e.message,true)));$('#conversation-search').addEventListener('keydown',e=>{if(e.key==='Enter')loadConversations({fresh:true}).catch(x=>toast(x.message,true));});$('#apply-reviewed-filters').addEventListener('click',()=>loadReviewed({fresh:true}).catch(e=>toast(e.message,true)));$('#reviewed-list').addEventListener('change',e=>{if(!e.target.matches('.reviewed-row-check'))return;const id=Number(e.target.dataset.reviewId);e.target.checked?state.reviewedSelected.add(id):state.reviewedSelected.delete(id);updateReviewedBulk();});$('#reviewed-list').addEventListener('click',e=>{const restore=e.target.closest('[data-restore-review]'),exclude=e.target.closest('[data-exclude-review]');if(restore)bulkReviewed('restore',[Number(restore.dataset.restoreReview)]).catch(x=>toast(x.message,true));if(exclude)bulkReviewed('exclude',[Number(exclude.dataset.excludeReview)]).catch(x=>toast(x.message,true));});$('#bulk-exclude-reviews').addEventListener('click',()=>bulkReviewed('exclude').catch(e=>toast(e.message,true)));$('#bulk-restore-reviews').addEventListener('click',()=>bulkReviewed('restore').catch(e=>toast(e.message,true)));
  document.querySelectorAll('#view-add-data .subtabs [data-add-tab]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('#view-add-data .subtabs [data-add-tab]').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-selected',String(b===button));});document.querySelectorAll('#view-add-data .data-form').forEach(form=>form.classList.toggle('active',form.id===`form-${button.dataset.addTab}`));}));$('#add-sft-turn').addEventListener('click',()=>addSftTurn($('#sft-turns .turn-row:last-child .turn-role')?.value==='user'?'assistant':'user'));
  $('#form-sft').addEventListener('submit',async e=>{
    e.preventDefault();
    const rows=Array.from(document.querySelectorAll('#sft-turns .turn-row'));
    // UX-15: deleted/all-empty turns cannot produce a valid conversation.
    if(!rows.length){toast('Add at least a user turn and an assistant turn before saving.',true);return;}
    const messages=rows.map(row=>({role:row.querySelector('.turn-role').value,content:row.querySelector('.turn-content').value}));
    if(messages.some(m=>!m.content.trim())){toast('Every conversation turn needs text before saving.',true);return;}
    await submitDataForm(e.target,'/api/v1/manual-data/sft',{messages});
  });$('#form-direct').addEventListener('submit',e=>{e.preventDefault();submitDataForm(e.target,'/api/v1/manual-data/direct');});$('#form-preference').addEventListener('submit',e=>{e.preventDefault();submitDataForm(e.target,'/api/v1/manual-data/preference');});
  $('#apply-manual-filters').addEventListener('click',()=>loadManualData({fresh:true}).catch(e=>toast(e.message,true)));$('#manual-search').addEventListener('keydown',e=>{if(e.key==='Enter')loadManualData({fresh:true}).catch(x=>toast(x.message,true));});
  $('#reset-manual-filters').addEventListener('click',()=>{$$('#view-manual-data input').forEach(input=>{if(input.type==='checkbox')input.checked=false;else input.value='';});$$('#view-manual-data select').forEach(select=>select.selectedIndex=0);loadManualData({fresh:true}).catch(e=>toast(e.message,true));});
  $('#manual-list').addEventListener('click',e=>{const button=e.target.closest('[data-action]');if(button)manualAction(button.dataset.action,button.dataset.type,Number(button.dataset.id)).catch(x=>toast(x.message,true));});
  $('#manual-list').addEventListener('change',e=>{if(!e.target.matches('.manual-row-check'))return;e.target.checked?state.manualSelected.add(e.target.dataset.key):state.manualSelected.delete(e.target.dataset.key);updateManualBulk();});
  $('#manual-select-all').addEventListener('change',e=>{$$('.manual-row-check').forEach(box=>{box.checked=e.target.checked;e.target.checked?state.manualSelected.add(box.dataset.key):state.manualSelected.delete(box.dataset.key);});updateManualBulk();});
  $('#apply-manual-bulk').addEventListener('click',()=>applyManualBulk().catch(e=>toast(e.message,true)));
  $('#close-manual-dialog').addEventListener('click',()=>$('#manual-dialog').close());$('#manual-dialog').addEventListener('click',e=>{if(e.target===$('#manual-dialog'))$('#manual-dialog').close();});
  $('.dialog-tabs').addEventListener('click',e=>{const button=e.target.closest('[data-manual-tab]');if(!button)return;$$('.dialog-tabs button').forEach(b=>b.classList.toggle('active',b===button));$$('.manual-tab').forEach(tab=>tab.classList.toggle('active',tab.id===`manual-tab-${button.dataset.manualTab}`));if(button.dataset.manualTab==='versions')loadManualVersions().catch(x=>toast(x.message,true));});
  $('#manual-tab-details').addEventListener('click',e=>{const button=e.target.closest('[data-detail-action]');if(!button)return;const item=state.manualCurrent,action=button.dataset.detailAction;if(action==='cancel-edit')return renderManualDetails(item);if(action==='edit')return renderManualEdit(item);manualAction(action,item.item_type,item.id).catch(x=>toast(x.message,true));});
  $('#dataset-demo').addEventListener('change',()=>loadDataset().catch(e=>toast(e.message,true)));$('#preview-dedup').addEventListener('click',()=>previewDedup().catch(e=>toast(e.message,true)));$('#create-export').addEventListener('click',createExport);
  $('#health-version').addEventListener('change',e=>{state.selectedDataset=e.target.value;updateLocation('dataset-health',state.selectedDataset,true);loadHealth(false);});$('#refresh-health').addEventListener('click',()=>loadHealth(true));$('#health-summary').addEventListener('click',e=>{const b=e.target.closest('[data-health-detail]');if(b)showHealthDetail(b.dataset.healthDetail);});$('#health-checks').addEventListener('click',e=>{const b=e.target.closest('[data-health-detail]');if(b)showHealthDetail(b.dataset.healthDetail);});$('#health-warnings').addEventListener('click',e=>{const b=e.target.closest('[data-health-detail]');if(b)showHealthDetail(b.dataset.healthDetail);});$('#health-detail-panel').addEventListener('click',e=>{if(e.target.closest('[data-close-health-detail]'))$('#health-detail-panel').classList.add('hidden');});$('#health-version-details').addEventListener('click',()=>switchView('dataset-versions',{version:state.selectedDataset}));
  $('#balance-version').addEventListener('change',e=>{state.selectedDataset=e.target.value;updateLocation('balancer',state.selectedDataset,true);loadBalancer();});$('#run-balance').addEventListener('click',()=>loadBalancer(true));$('#refresh-eval').addEventListener('click',()=>loadEvalSets().catch(e=>toast(e.message,true)));$('#version-list').addEventListener('click',e=>{const button=e.target.closest('[data-version-name]');if(button)showVersionDetail(button.dataset.versionName).catch(x=>toast(x.message,true));});$('#version-detail').addEventListener('click',e=>{const health=e.target.closest('[data-health-version]'),derive=e.target.closest('[data-derive-version]'),analysis=e.target.closest('[data-overlap-analysis]'),plan=e.target.closest('[data-overlap-plan]'),apply=e.target.closest('[data-apply-plan]'),freeze=e.target.closest('[data-freeze-version]');if(health){state.selectedDataset=health.dataset.healthVersion;switchView('dataset-health',{version:state.selectedDataset});}else if(derive)deriveVersion(derive.dataset.deriveVersion);else if(analysis)analyzeOverlaps(analysis.dataset.overlapAnalysis);else if(plan)dryRunOverlaps(plan.dataset.overlapPlan);else if(apply)applyOverlapPlan(apply.dataset.applyPlan);else if(freeze)freezeVersion(freeze.dataset.freezeVersion);});
  // UX-22: shortcuts never act behind an open dialog; single-key shortcuts (WCAG 2.1.4) are opt-in
  // because "4" approves immediately and a stray key press must not decide a review.
  const shortcutsEnabled=()=>prefs.get('najdilab.reviewShortcuts')==='on';
  const syncShortcutHint=()=>{$('#review-shortcuts').checked=shortcutsEnabled();$('#review-shortcut-hint').textContent=shortcutsEnabled()?'Ctrl + Enter saves · 1–3 correction type · 4 approve':'Ctrl + Enter to save the edit';};
  syncShortcutHint();
  $('#review-shortcuts').addEventListener('change',e=>{prefs.set('najdilab.reviewShortcuts',e.target.checked?'on':'off');syncShortcutHint();});
  document.addEventListener('keydown',e=>{
    if(state.view!=='review-queue'||!state.queue.length||document.querySelector('dialog[open]'))return;
    if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();if(!$('#save-review').disabled)saveReview();return;}
    if(!shortcutsEnabled()||e.ctrlKey||e.altKey||e.metaKey||e.repeat)return;
    if(e.target.closest('input,textarea,select,button,a,summary,[contenteditable],[role="button"]'))return;
    const status={1:'FULL_CORRECTION',2:'DIALECT_CORRECTION',3:'CONTENT_CORRECTION'}[e.key];
    if(status){e.preventDefault();openEditReview();selectReviewStatus(status);}
    if(e.key==='4'){e.preventDefault();approveReview();}
  });
}

// Phone navigation sheet: the button reports its state, Escape and an outside click close it.
function setMobileNav(open){$('.sidebar').classList.toggle('open',open);$('#mobile-menu').setAttribute('aria-expanded',String(open));document.body.classList.toggle('nav-open',open);}
async function init(){try{$('#copyright-year').textContent=new Date().getFullYear();$('#local-address').textContent=location.host;if(prefs.get('najdilab.sidebar')==='collapsed'){$('.shell').classList.add('sidebar-collapsed');$('#collapse-sidebar').setAttribute('aria-expanded','false');}await loadConfig();bindEvents();addSftTurn('user');addSftTurn('assistant');const initial=pathViews[location.pathname]||'dashboard';if(initial!=='review-queue')await loadQueue();switchView(initial,{fromHistory:true,replace:true,version:selectedVersion()});window.addEventListener('popstate',()=>switchView(pathViews[location.pathname]||'dashboard',{fromHistory:true,version:selectedVersion()}));}catch(error){toast(`Unable to start interface: ${error.message}`,true);}}
const phase38Criteria={factual_correctness:'Factual correctness',instruction_following:'Instruction following',dialect_quality:'Dialect quality',natural_arabic:'Natural Arabic',concision:'Concision',context_continuity:'Context continuity',tool_correctness:'Tool correctness',hallucination_risk:'Hallucination risk',repetition_risk:'Repetition risk',contamination_concern:'Evaluation contamination concern'};
const phase38Coverage={instruction_following:'Instruction following',verbosity_focus:'Verbosity control',constraint_following:'Constraint following',tool_behavior:'Tool behavior',capability_understanding:'Capability understanding',fabricated_tool_prevention:'Prevent fabricated tool execution',hallucination_prevention:'Prevent hallucinations',context_understanding:'Context handling',conversational_continuity:'Conversation continuity',najdi_saudi_dialect:'Saudi/Najdi dialect',natural_arabic:'Natural Arabic',repetition_prevention:'Prevent repetition',factual_accuracy:'Factual accuracy'};
const phase38Types={sft:'Short conversation (SFT)',multi_turn:'Multi-turn conversation',native_tool_use:'Native tool use'};
const phase38Roles={system:'System',user:'User',assistant:'Assistant',tool:'Tool result'};

function phase38Validate(data){
  if(!data||!Array.isArray(data.records))throw new Error('Review response does not contain valid records');
  const counts=data.records.reduce((a,r)=>(a[r.record_type]=(a[r.record_type]||0)+1,a),{});
  if(data.records.length!==36||counts.sft!==12||counts.multi_turn!==16||counts.native_tool_use!==8)throw new Error('Unexpected record distribution: 12 short conversations, 16 multi-turn conversations, 8 Tools');
  if(data.records.some(r=>r.record?.provenance?.kind!=='new_remediation'))throw new Error('A non-new record was found in the queue for Phase 3.8');
  if(data.records.some(r=>/holdout|eval/i.test(r.record_id||'')))throw new Error('Leakage protection blocked a record that appears to belong to the reserved holdout');
}
function phase38Messages(messages){return (messages||[]).map((m,i)=>{const calls=(m.tool_calls||[]).map(c=>`<div class="phase38-tool-call"><b>Tool call</b><div class="technical-id">${esc(c.function?.name||'—')}</div><pre dir="ltr">${esc(c.function?.arguments||'')}</pre></div>`).join('');const result=m.role==='tool'?`<div class="phase38-tool-result"><b>Authoritative read-only result</b><pre dir="auto">${esc(typeof m.content==='string'?m.content:JSON.stringify(m.content,null,2))}</pre></div>`:'';return `<article class="phase38-message ${esc(m.role)}"><span class="role">${phase38Roles[m.role]||esc(m.role)} · ${i+1}</span>${m.role==='tool'?'':`<p dir="auto">${esc(m.content||'')}</p>`}${calls}${result}</article>`;}).join('');}
function phase38EditFields(record){
  if(state.phase38Decision!=='EDIT')return '';
  const assistants=(record.record?.messages||[]).map((m,i)=>({m,i})).filter(x=>x.m.role==='assistant'&&x.m.content!==undefined);
  const editable=record.record_type==='native_tool_use'?assistants.slice(-1):assistants;
  const proposed=record.review?.proposed_assistant_edits||{};
  return `<div class="phase38-edit-fields"><h3>Proposed edit</h3>${record.record_type==='native_tool_use'?'<p class="readonly-tool-note">Tool calls and results are read-only; only the final assistant response can be edited.</p>':''}${editable.map(({m,i})=>`<label class="wide-label">Assistant response number ${i+1}<textarea dir="auto" data-phase38-edit-index="${i}" rows="5">${esc(proposed[i]??m.content??'')}</textarea></label>`).join('')}</div>`;
}
function renderPhase38(){
  const data=state.phase38,s=data.summary,r=data.records[state.phase38Index];
  if($('#nav-phase38'))$('#nav-phase38').textContent=`${s.reviewed}/${s.total}`;
  $('#phase38-status').classList.add('hidden');$('#phase38-workspace').classList.remove('hidden');
  const coverage=(r.record?.coverage||[]).map(x=>`<span title="${esc(x)}">${esc(phase38Coverage[x]||x)}</span>`).join('');
  $('#phase38-record').innerHTML=`<div class="phase38-record-head"><div><span class="eyebrow">${esc(phase38Types[r.record_type]||r.record_type)}</span><h2 class="technical-id">${esc(r.record_id)}</h2><p>Record ${state.phase38Index+1} of ${data.records.length}</p></div><span class="gate-badge ${r.decision?'pass':'unavailable'}">${r.decision==='APPROVE'?'Approved':r.decision==='EDIT'?'Needs editing':r.decision==='REJECT'?'Rejected':'Awaiting decision'}</span></div><div class="coverage-chips">${coverage}</div><div class="phase38-messages">${phase38Messages(r.record?.messages)}</div><details class="phase38-technical"><summary>Technical details</summary><pre>${esc(JSON.stringify({record_type:r.record_type,conversation_id:r.record?.conversation_id,target_message_index:r.record?.target_message_index,message_loss_mask:r.record?.message_loss_mask,train_on_last_assistant_only:r.record?.train_on_last_assistant_only,tool_contract:r.tool_view?{capability_registry:r.tool_view.capability_registry,visible_tools:r.tool_view.visible_tools,loss_mask_preview:r.tool_view.loss_mask_preview}:null},null,2))}</pre></details>`;
  $('#phase38-summary').innerHTML=`<span>Reviewed<b>${s.reviewed}/${s.total}</b></span><span>Approved<b>${s.approved}</b></span><span>Edit<b>${s.edited}</b></span><span>Rejected<b>${s.rejected}</b></span><span>Remaining<b>${s.remaining}</b></span><span>Type<b>${esc(r.record_type)}</b></span>`;
  $('#phase38-criteria').innerHTML=Object.entries(phase38Criteria).map(([key,label])=>`<label>${label}<select data-phase38-field="${key}"><option value="">Unspecified</option><option value="PASS">Passed</option><option value="FAIL">Needs attention</option><option value="NA">Not applicable</option></select></label>`).join('');
  $$('[data-phase38-field]').forEach(x=>x.value=r.review?.[x.dataset.phase38Field]??'');$('#phase38-notes').value=r.review?.notes||'';
  state.phase38Decision=r.decision;$$('[data-phase38-decision]').forEach(x=>x.classList.toggle('selected',x.dataset.phase38Decision===state.phase38Decision));
  $('#phase38-edit-fields').innerHTML=phase38EditFields(r);$('#phase38-save').disabled=!state.phase38Decision;$('#phase38-save').textContent='Save decision';$('#phase38-save-state').className='save-state';$('#phase38-save-state').textContent=state.phase38Dirty?'There are unsaved changes.':'';
}
function showPhase38Error(message){$('#phase38-workspace').classList.add('hidden');const host=$('#phase38-status');host.className='panel phase38-status error-state';host.innerHTML=`<strong>Unable to load review for Phase 3.8</strong><p dir="auto">${esc(message)}</p><button id="phase38-retry" class="button primary">Retry</button>`;$('#phase38-retry').onclick=loadPhase38Review;}
async function loadPhase38Review(){
  const host=$('#phase38-status');host.className='panel phase38-status';host.textContent='Loading 36 new records…';host.classList.remove('hidden');$('#phase38-workspace').classList.add('hidden');
  try{const data=await api('/api/v1/phase38/v009/human-review');phase38Validate(data);state.phase38=data;state.phase38Dirty=false;state.phase38Index=Math.min(state.phase38Index,35);renderPhase38();if(!state.phase38Bound)bindPhase38();}
  catch(error){showPhase38Error(error.message);}
}
function phase38Navigate(delta){if(state.phase38Dirty&&!confirm(tr('You have unsaved changes. Continue and discard them?')))return;state.phase38Index=Math.max(0,Math.min(35,state.phase38Index+delta));state.phase38Dirty=false;renderPhase38();}
function bindPhase38(){
  state.phase38Bound=true;const view=$('#view-phase38-review');
  view.addEventListener('input',e=>{if(e.target.matches('textarea,[data-phase38-field]')){state.phase38Dirty=true;$('#phase38-save-state').textContent='There are unsaved changes.';}});
  view.addEventListener('change',e=>{if(e.target.matches('[data-phase38-field]'))state.phase38Dirty=true;});
  view.addEventListener('click',async e=>{const decision=e.target.closest('[data-phase38-decision]'),nav=e.target.closest('[data-phase38-nav]');if(nav){phase38Navigate(nav.dataset.phase38Nav==='prev'?-1:1);return;}if(decision){state.phase38Decision=decision.dataset.phase38Decision;state.phase38Dirty=true;$$('[data-phase38-decision]').forEach(x=>x.classList.toggle('selected',x===decision));$('#phase38-edit-fields').innerHTML=phase38EditFields(state.phase38.records[state.phase38Index]);$('#phase38-save').disabled=false;$('#phase38-save-state').textContent='There are unsaved changes.';return;}if(!e.target.closest('#phase38-save'))return;
    const button=$('#phase38-save'),r=state.phase38.records[state.phase38Index],review={notes:$('#phase38-notes').value};$$('[data-phase38-field]').forEach(x=>review[x.dataset.phase38Field]=x.value||null);if(state.phase38Decision==='EDIT')review.proposed_assistant_edits=Object.fromEntries($$('[data-phase38-edit-index]').map(x=>[x.dataset.phase38EditIndex,x.value]));button.disabled=true;button.textContent='Saving…';state.phase38Saving=true;
    try{const out=await api(`/api/v1/phase38/v009/human-review/${encodeURIComponent(r.record_id)}`,{method:'POST',body:JSON.stringify({decision:state.phase38Decision,review})});phase38Validate(out.review);state.phase38=out.review;state.phase38Dirty=false;state.phase38Saving=false;renderPhase38();$('#phase38-save-state').className='save-state success';$('#phase38-save-state').textContent='Decision saved.';toast('Record review saved.');}
    catch(error){state.phase38Saving=false;button.disabled=false;button.textContent='Retry save';$('#phase38-save-state').className='save-state error';$('#phase38-save-state').textContent=`Unable to save: ${error.message}`;}
  });
  window.addEventListener('beforeunload',e=>{if(state.phase38Dirty){e.preventDefault();e.returnValue='';}});
}

document.addEventListener('DOMContentLoaded',init);
