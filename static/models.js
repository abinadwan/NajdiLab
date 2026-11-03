/* Model library: Hugging Face Direct discovery, Smart Model Advisor, downloads and the local library.
   Every network action is an explicit button press; nothing loads or downloads by itself. Text from
   Hugging Face is always inserted as text (never HTML); identifiers are isolated left-to-right. */
(function(global){
  'use strict';
  const el=id=>document.getElementById(id);
  const GB=1024**3,MB=1024**2;
  const VERDICT={COMPATIBLE:'ready',LIMITED:'warning',UNVERIFIED:'neutral',BLOCKED:'hold'};
  const STATUS={READY:'ready',DOWNLOADING:'info',PAUSED:'warning',UNVERIFIED:'neutral',ERROR:'blocked'};
  const STATUS_TEXT={READY:'Ready — verified',DOWNLOADING:'Downloading',PAUSED:'Paused',UNVERIFIED:'Unverified',ERROR:'Error'};
  const KIND_TEXT={measured:'measured',reported:'reported',estimate:'estimate',unknown:'unknown'};
  const ERROR_TEXT={
    STORAGE_RESERVE:'Paused before the drive\'s safety reserve was reached. Free space, then resume.',
    DISK_FULL:'The drive became full. Free space, then resume.',HUB_UNREACHABLE:'The connection was interrupted. Resume to continue from the verified part.',
    RATE_LIMITED:'Hugging Face is limiting requests. Resume in a minute.',HASH_MISMATCH:'The file did not match its published SHA-256 and was removed.',
    SIZE_MISMATCH:'The file size did not match the published size and was removed.',DIGEST_MISMATCH:'Hugging Face reported a different SHA-256 than reviewed.',
    REVISION_CHANGED:'The repository changed after review. Review it again.',MISSING:'The file is no longer in the managed folder.',
    INTERRUPTED:'NajdiLab stopped during the download. Resume to continue from the verified part.',PAUSED_BY_USER:'Paused.',
    NOT_A_TEXT_MODEL:'Verified, but this GGUF file is not a text model.',CONTEXT_UNKNOWN:'Verified, but the file does not state its context length.',
    ALREADY_PRESENT:'A file already existed at the destination; nothing was replaced.',WRITE_FAILED:'Writing to the drive failed.',
    DOWNLOAD_FAILED:'The download failed.',CANCELLED:'Cancelled.'};
  let current=null,adviceFor=null,timer=null,loaded=false,library=null;

  function node(tag,attrs={},...children){
    const n=document.createElement(tag);
    for(const [k,v] of Object.entries(attrs||{})){
      if(v==null||v===false)continue;
      if(k==='class')n.className=v;else if(k==='text')n.textContent=v;else if(k.startsWith('on'))n[k]=v;else n.setAttribute(k,v===true?'':v);
    }
    for(const c of children.flat(Infinity)){if(c==null||c===false)continue;n.append(c&&c.nodeType?c:typeof c==='object'?ident(c.id):String(c));}
    return n;
  }
  const ident=value=>node('bdi',{dir:'ltr',translate:'no'},String(value));
  const bytes=v=>Number.isFinite(v)?(v>=GB?`${(v/GB).toFixed(2)} GB`:v>=MB?`${(v/MB).toFixed(1)} MB`:`${v} B`):null;
  const count=v=>Number.isFinite(v)?new Intl.NumberFormat('en-US').format(v):null;
  const params=v=>!Number.isFinite(v)?null:v>=1e9?`${(v/1e9).toFixed(1)}B`:v>=1e6?`${(v/1e6).toFixed(0)}M`:String(v);
  function pill(kind,text){return node('span',{class:`status-pill model-pill ${kind}`},text);}
  function valueOrUnknown(v){return v==null||v===''?node('span',{class:'muted'},'Unknown'):ident(v);}

  async function api(path,body){
    const options=body===undefined?{}:{method:'POST',body:JSON.stringify(body)};
    return global.api(path,options);
  }
  function errorText(error){return [String(error&&error.message||'Something went wrong.'),error&&error.code?node('span',{class:'muted'},' ',ident(error.code)):null];}
  function say(id,...parts){const target=el(id);target.replaceChildren(...parts.flat().filter(Boolean));}

  // ------------------------------------------------------------- tabs
  function showTab(name){
    for(const tab of document.querySelectorAll('[data-models-tab]')){
      const on=tab.dataset.modelsTab===name;tab.classList.toggle('active',on);tab.setAttribute('aria-selected',String(on));tab.tabIndex=on?0:-1;
    }
    el('models-discover').hidden=name!=='discover';el('models-library').hidden=name!=='library';
    if(name==='library')refreshLibrary();
  }

  // ------------------------------------------------------------- discover
  async function search(event){
    event.preventDefault();
    const query=el('models-query').value.trim(),author=el('models-author').value.trim();
    if(!query&&!author){say('models-search-status','Enter a model name or a publisher.');return;}
    say('models-search-status','Searching Hugging Face…');el('models-results').replaceChildren();
    try{
      const data=await api('/api/v1/models/hub/search',{query,author});
      renderResults(data.items);
      say('models-search-status',data.items.length?[ident(data.items.length),' ','GGUF repositories found.']:'No GGUF repositories matched this search.');
    }catch(error){say('models-search-status',errorText(error));}
  }
  function renderResults(items){
    const list=node('ul',{class:'models-result-list',role:'list'});
    for(const item of items){
      const button=node('button',{type:'button',class:'models-result','data-repo':item.id,onclick:()=>openRepo(item.id)},
        node('span',{class:'models-result-name'},ident(item.name)),
        node('span',{class:'models-result-meta'},ident(item.author),' · ',item.license?ident(item.license):'License not stated',
          item.downloads!=null?[' · ',ident(count(item.downloads)),' ','downloads']:null));
      list.append(node('li',{},button));
    }
    el('models-results').replaceChildren(list);
  }
  async function openRepo(id){
    for(const b of document.querySelectorAll('.models-result'))b.setAttribute('aria-current',b.dataset.repo===id?'true':'false');
    const box=el('models-detail');box.replaceChildren(node('p',{class:'muted'},'Loading repository details…'));
    try{current=await api('/api/v1/models/hub/repo',{repo_id:id});adviceFor=null;renderDetail();}
    catch(error){box.replaceChildren(node('p',{class:'models-error',role:'alert'},errorText(error)));}
  }
  function renderDetail(){
    const d=current,box=el('models-detail');
    const access=d.access==='OPEN'?pill('ready','Open access'):pill('hold','Gated — needs approval on Hugging Face');
    const facts=node('dl',{class:'models-facts'},
      fact('Publisher',ident(d.author)),fact('License',d.license?ident(d.license):node('span',{class:'muted'},'Not stated — check the model card')),
      fact('Revision',node('bdi',{dir:'ltr',translate:'no',title:d.revision},d.revision.slice(0,12))),
      fact('Architecture',valueOrUnknown(d.reported.architecture),'reported'),
      fact('Parameters',valueOrUnknown(params(d.reported.parameters)),'reported'),
      fact('Context length',valueOrUnknown(count(d.reported.context_length)),'reported'),
      d.base_models.length?fact('Base model',ident(d.base_models[0])):null);
    const settings=node('div',{class:'models-check-settings',role:'group','aria-label':'Compatibility check settings'},
      node('label',{for:'models-context'},'Context size'),
      select('models-context',[['4096','4096'],['8192','8192'],['16384','16384'],['32768','32768']],'8192'),
      node('label',{for:'models-gpu'},'GPU use'),
      select('models-gpu',[['auto','Automatic'],['all','All layers on GPU'],['0','CPU only']],'auto'),
      node('label',{class:'inline-check'},node('input',{type:'checkbox',id:'models-hardware'}),' ','Read this computer\'s hardware for the check (stays on this computer)'));
    const rows=d.variants.map(v=>node('tr',{},
      node('td',{},v.quantization?ident(v.quantization):node('span',{class:'muted'},'—')),
      node('td',{class:'models-file'},ident(v.filename)),
      node('td',{class:'num'},v.size_bytes?ident(bytes(v.size_bytes)):node('span',{class:'muted'},'—')),
      node('td',{},v.supported?pill('ready','Supported'):pill('hold',unsupportedText(v.unsupported_reasons[0]))),
      node('td',{},v.supported&&d.access==='OPEN'?node('button',{type:'button',class:'button ghost',onclick:()=>advise(v)},'Check fit'):null)));
    const table=node('div',{class:'table-scroll',tabindex:'0',role:'region','aria-label':'GGUF files'},
      node('table',{class:'analytics-table models-variants'},node('thead',{},node('tr',{},
        ['Quantization','File','Size','Support',''].map((h,i)=>node('th',{class:i===2?'num':null,scope:'col'},h)))),node('tbody',{},rows)));
    box.replaceChildren(...[
      node('div',{class:'panel-heading'},node('div',{},node('h2',{id:'models-detail-title'},ident(d.id)),
        node('p',{class:'muted'},'Details from Hugging Face, pinned to one revision. Repository text is untrusted and shown as plain text.')),access),
      facts,
      d.variants.length?null:node('p',{class:'models-empty'},'This repository has no GGUF files.'),
      d.variants.length?settings:null,d.variants.length?table:null,
      node('div',{id:'models-advice',class:'models-advice','aria-live':'polite'}),
      node('p',{class:'muted models-source'},'GGUF only. Other formats are not supported yet. ',
        node('a',{href:`https://huggingface.co/${d.id}`,target:'_blank',rel:'noopener noreferrer'},'Open the model card on Hugging Face'))].filter(Boolean));
  }
  function fact(label,value,kind){return node('div',{},node('dt',{},label,kind?node('span',{class:'evidence-kind'},' · ',KIND_TEXT[kind]):null),node('dd',{},value));}
  function select(id,options,value){const s=node('select',{id});for(const [v,t] of options){const o=node('option',{value:v},t);if(v===value)o.selected=true;s.append(o);}return s;}
  function unsupportedText(code){return {SPLIT_UNSUPPORTED:'Split file — not supported',PROJECTOR_NOT_A_TEXT_MODEL:'Vision projector — not a text model',
    IN_SUBFOLDER:'In a subfolder — not supported',UNSAFE_FILE_NAME:'Unsafe file name',SIZE_UNKNOWN:'Size not published',DIGEST_UNKNOWN:'No SHA-256 published'}[code]||'Not supported';}

  async function advise(variant){
    const box=el('models-advice');box.replaceChildren(node('p',{class:'muted'},'Checking this file… reading its GGUF header with a small range request.'));
    try{
      const result=await api('/api/v1/models/advise',{repo_id:current.id,revision:current.revision,filename:variant.filename,
        context:Number(el('models-context').value),gpu_layers:el('models-gpu').value,hardware_approved:el('models-hardware').checked});
      adviceFor={variant,result};box.replaceChildren(adviceCard(result,{download:true}));box.querySelector('h3')?.focus();
    }catch(error){box.replaceChildren(node('p',{class:'models-error',role:'alert'},errorText(error)));}
  }
  function adviceCard(r,{download=false,load=null}={}){
    const verdict=r.load.classification;
    const reasons=node('ul',{class:'models-reasons'},r.load.reasons.map(x=>node('li',{},x.message)));
    const est=r.estimate;
    const estimate=est?node('dl',{class:'models-facts compact'},
      fact('Weights',ident(bytes(est.weights_bytes)),'reported'),
      fact('KV cache at this context',ident(bytes(est.kv_bytes)),'estimate'),
      fact('Runtime overhead',ident(bytes(est.overhead_bytes)),'estimate'),
      fact('Estimated memory needed',ident(bytes(est.required_bytes)),'estimate')):node('p',{class:'muted'},'No memory estimate: the model or hardware details are missing.');
    const host=r.host,gpu=(host.gpus||[])[0];
    const hardware=host.approved?node('dl',{class:'models-facts compact'},
      fact('GPU',gpu?[ident(gpu.name||'GPU'),' · ',ident(bytes(gpu.free_bytes)),' ','free of',' ',ident(bytes(gpu.total_bytes))]:'No GPU reported','measured'),
      fact('System memory',[ident(bytes(host.ram_available_bytes)),' ','free of',' ',ident(bytes(host.ram_total_bytes))],'measured'),
      fact('Processor and system',[ident(host.cpu_architecture||'?'),' · ',ident(host.os)]),
      fact('NajdiLab Native runtime',host.runtime.server_available?'llama-server configured':'llama-server not configured')):
      node('p',{class:'muted'},'Hardware was not read for this check.');
    const largest=r.load.largest_gpu_context?node('p',{},'Largest context that fits fully on the GPU (estimate): ',ident(count(r.load.largest_gpu_context))):null;
    const parts=[node('div',{class:'models-verdict'},node('h3',{tabindex:'-1'},'Smart Model Advisor'),pill(VERDICT[verdict],verdict)),
      node('p',{class:'models-performance'},r.performance.expectation),reasons,largest,
      node('div',{class:'models-advice-grid'},node('section',{'aria-label':'Memory estimate'},node('h4',{},'Memory estimate'),estimate),
        node('section',{'aria-label':'This computer'},node('h4',{},'This computer'),hardware)),
      node('p',{class:'muted'},r.note)];
    if(download){
      const s=r.download.storage;
      parts.push(node('section',{class:'models-download-check','aria-label':'Download check'},node('h4',{},'Download check'),
        r.download.decision==='ALLOWED'?pill('ready','Download allowed'):pill('hold','Download blocked'),
        node('ul',{class:'models-reasons'},r.download.reasons.map(x=>node('li',{},x.message))),
        s&&s.free_bytes!=null?storageTable(s):null,
        node('button',{type:'button',class:'button primary',disabled:r.download.decision!=='ALLOWED',onclick:()=>openDownload(r)},'Download…')));
    }
    if(load)parts.push(load);
    return node('article',{class:'models-advice-card'},...parts);
  }
  function storageTable(s){
    return node('dl',{class:'models-facts compact models-storage-facts'},
      fact('Destination drive',[ident(s.volume),s.system_volume?[' · ','system drive (larger reserve)']:null]),
      fact('Free space now',ident(bytes(s.free_bytes)),'measured'),
      fact('File size',ident(bytes(s.file_bytes)),'reported'),
      fact('Temporary space (.part file)',ident(bytes(s.temporary_bytes))),
      fact('Safety reserve',ident(bytes(s.reserve_bytes))),
      s.reserved_by_other_downloads_bytes?fact('Reserved by other downloads',ident(bytes(s.reserved_by_other_downloads_bytes))):null,
      fact('Total required',ident(bytes(s.required_bytes))),
      fact('Free after download',ident(bytes(s.free_after_bytes)),'estimate'));
  }

  // ------------------------------------------------------------- download dialog
  function openDownload(result){
    const f=result.file,dialog=el('models-download-dialog');
    say('models-download-summary',node('dl',{class:'models-facts compact'},
      fact('Repository',ident(f.repo_id)),fact('File',ident(f.filename)),fact('Revision',ident(f.revision.slice(0,12))),
      fact('Size',ident(bytes(f.size_bytes)),'reported'),fact('SHA-256',node('bdi',{dir:'ltr',translate:'no',class:'hash'},f.sha256))),
      storageTable(result.download.storage));
    say('models-download-license',f.license?['License: ',ident(f.license),'. ','Read the license on the model card before you use this model.']
      :'This model does not state a license. Check its model card before you use it.');
    el('models-license-ack').checked=false;el('models-download-start').disabled=true;say('models-download-error');
    dialog.showModal();el('models-license-ack').focus();
  }
  async function startDownload(){
    const f=adviceFor&&adviceFor.result.file;if(!f)return;
    el('models-download-start').disabled=true;
    try{
      await api('/api/v1/models/downloads',{approved:true,license_acknowledged:el('models-license-ack').checked,repo_id:f.repo_id,revision:f.revision,filename:f.filename});
      el('models-download-dialog').close();showTab('library');
    }catch(error){say('models-download-error',errorText(error));el('models-download-start').disabled=!el('models-license-ack').checked;}
  }

  // ------------------------------------------------------------- library
  async function refreshLibrary(){
    clearTimeout(timer);
    try{
      const [data,native]=await Promise.all([api('/api/v1/models/library'),api('/api/v1/native/status')]);
      library=data;renderLibrary(data,native);
      if(data.items.some(i=>i.active||i.status==='DOWNLOADING'))timer=setTimeout(refreshLibrary,1000);
    }catch(error){say('models-library-list',node('p',{class:'models-error',role:'alert'},errorText(error)));}
  }
  function renderLibrary(data,native){
    const s=data.storage;
    say('models-storage',node('h2',{},'Managed model folder'),
      node('p',{class:'muted'},'NajdiLab only lists, verifies and deletes files it downloaded into this folder. Ollama, LM Studio and other folders are never touched.'),
      node('dl',{class:'models-facts compact'},fact('Folder',ident(data.root)),fact('Drive',[ident(s.volume),s.system_volume?[' · ','system drive']:null]),
        fact('Free space now',ident(bytes(s.free_bytes)),'measured'),fact('Safety reserve',ident(bytes(s.reserve_bytes)))),
      node('p',{class:'muted'},native.state==='RUNNING'?['NajdiLab Native is running ',ident(native.model||''),'.']:'NajdiLab Native is not running a model.'));
    if(!data.items.length){say('models-library-list',node('div',{class:'empty-inline compact-empty'},node('p',{},'No models downloaded yet.'),
      node('button',{type:'button',class:'button ghost',onclick:()=>showTab('discover')},'Discover models')));return;}
    say('models-library-list',node('ul',{class:'models-library-items',role:'list'},data.items.map(item=>node('li',{},libraryItem(item,native)))));
  }
  function libraryItem(item,native){
    const running=native.state==='RUNNING'&&native.model===item.native_id;
    const progress=item.status==='DOWNLOADING'||item.status==='PAUSED'?node('div',{class:'models-progress'},
      node('progress',{max:String(item.size_bytes),value:String(item.downloaded_bytes||0),'aria-label':'Download progress'}),
      node('span',{},ident(bytes(item.downloaded_bytes||0)),' ','of',' ',ident(bytes(item.size_bytes)),
        item.speed_bytes_per_second?[' · ',ident(`${bytes(item.speed_bytes_per_second)}/s`)]:null,
        item.eta_seconds!=null?[' · ','about',' ',ident(Math.ceil(item.eta_seconds/60)),' ','min left']:null)):null;
    const actions=[];
    const act=(label,fn,cls='button ghost')=>actions.push(node('button',{type:'button',class:cls,onclick:fn},label));
    if(item.active)act('Pause',()=>control(item,'pause'));
    if(item.status==='PAUSED')act('Resume',()=>control(item,'resume',{approved:true}));
    if(item.active||item.status==='PAUSED'||item.status==='ERROR')act('Cancel and remove',()=>control(item,'cancel'));
    if(['READY','UNVERIFIED','ERROR'].includes(item.status)&&!item.active)act('Recheck integrity',()=>control(item,'recheck'));
    if(item.status==='READY')act('Check fit and load…',()=>openLoad(item),'button primary');
    if(!item.active&&!['DOWNLOADING'].includes(item.status))act('Delete…',()=>openDelete(item),'button delete-action');
    return node('article',{class:'models-library-item'},
      node('div',{class:'models-library-head'},node('h3',{},ident(item.filename)),pill(STATUS[item.status]||'neutral',STATUS_TEXT[item.status]||item.status),
        running?pill('info','Running in NajdiLab Native'):null),
      node('dl',{class:'models-facts compact'},fact('Repository',ident(item.repo_id)),fact('Revision',ident(item.revision.slice(0,12))),
        fact('Quantization',valueOrUnknown(item.quantization)),fact('Size',ident(bytes(item.size_bytes))),
        fact('SHA-256',item.verified_sha256?[node('bdi',{dir:'ltr',translate:'no',class:'hash',title:item.verified_sha256},item.verified_sha256.slice(0,16)+'…'),' ','verified']:'Not verified yet'),
        fact('Location',ident(item.path))),
      item.error_code?node('p',{class:'models-error-line'},ERROR_TEXT[item.error_code]||item.error_code):null,
      progress,node('div',{class:'models-actions'},actions),node('div',{class:'models-load','data-load':item.id}));
  }
  async function control(item,action,body={}){
    try{await api(`/api/v1/models/library/${item.id}/${action}`,body);}
    catch(error){global.toast?.(error.message,true);}
    refreshLibrary();
  }

  // ------------------------------------------------------------- load
  function openLoad(item){
    const box=document.querySelector(`[data-load="${item.id}"]`);
    const id=`load-${item.id.slice(0,8)}`;
    box.replaceChildren(node('div',{class:'models-check-settings',role:'group','aria-label':'Load settings'},
      node('label',{for:`${id}-ctx`},'Context size'),select(`${id}-ctx`,[['4096','4096'],['8192','8192'],['16384','16384'],['32768','32768']],'8192'),
      node('label',{for:`${id}-gpu`},'GPU use'),select(`${id}-gpu`,[['auto','Automatic'],['all','All layers on GPU'],['0','CPU only']],'auto'),
      node('label',{class:'inline-check'},node('input',{type:'checkbox',id:`${id}-hw`,checked:true}),' ','Read this computer\'s hardware for the check (stays on this computer)'),
      node('button',{type:'button',class:'button ghost',onclick:()=>checkLoad(item,id)},'Check fit')),node('div',{id:`${id}-result`,'aria-live':'polite'}));
    el(`${id}-ctx`).focus();
  }
  async function checkLoad(item,id){
    const out=el(`${id}-result`);out.replaceChildren(node('p',{class:'muted'},'Checking…'));
    const context=Number(el(`${id}-ctx`).value),gpu=el(`${id}-gpu`).value;
    try{
      const r=await api(`/api/v1/models/library/${item.id}/advise`,{context,gpu_layers:gpu,hardware_approved:el(`${id}-hw`).checked});
      const allowed=['COMPATIBLE','LIMITED'].includes(r.load.classification);
      const confirm=node('input',{type:'checkbox',id:`${id}-approve`,disabled:!allowed});
      const start=node('button',{type:'button',class:'button primary',disabled:true,onclick:()=>startNative(item,context,gpu,out)},'Load in NajdiLab Native');
      confirm.onchange=()=>{start.disabled=!confirm.checked;};
      out.replaceChildren(adviceCard(r,{load:node('section',{class:'models-load-confirm','aria-label':'Load approval'},
        allowed?null:node('p',{},'Loading is not offered: the advisor result is ',ident(r.load.classification),'.'),
        node('label',{class:'inline-check'},confirm,' ','Load this model now, with this context and GPU setting. Nothing loads without this approval.'),start)}));
    }catch(error){out.replaceChildren(node('p',{class:'models-error',role:'alert'},errorText(error)));}
  }
  async function startNative(item,context,gpu,out){
    out.querySelectorAll('button,input').forEach(b=>{b.disabled=true;});
    out.append(node('p',{class:'muted',role:'status'},'Starting NajdiLab Native… verifying the file and loading the model.'));
    try{
      await api('/api/v1/native/start',{approved:true,model:item.native_id,context_budget:context,gpu_layers:gpu});
      global.toast?.('NajdiLab Native is running this model. Start a new chat with NajdiLab Native to use it.');
    }catch(error){out.append(node('p',{class:'models-error',role:'alert'},errorText(error)));}
    refreshLibrary();
  }

  // ------------------------------------------------------------- delete
  let deleting=null;
  function openDelete(item){
    deleting=item;
    say('models-delete-name',ident(item.filename));el('models-delete-confirm').value='';el('models-delete-go').disabled=true;say('models-delete-error');
    el('models-delete-dialog').showModal();el('models-delete-confirm').focus();
  }
  async function confirmDelete(){
    try{
      await api(`/api/v1/models/library/${deleting.id}/delete`,{approved:true,confirm:el('models-delete-confirm').value});
      el('models-delete-dialog').close();refreshLibrary();
    }catch(error){say('models-delete-error',errorText(error));}
  }

  function bind(){
    el('models-search').onsubmit=search;
    for(const tab of document.querySelectorAll('[data-models-tab]')){
      tab.onclick=()=>showTab(tab.dataset.modelsTab);
      tab.onkeydown=event=>{if(['ArrowLeft','ArrowRight'].includes(event.key)){const next=tab.dataset.modelsTab==='discover'?'library':'discover';showTab(next);document.querySelector(`[data-models-tab="${next}"]`).focus();}};
    }
    el('models-license-ack').onchange=()=>{el('models-download-start').disabled=!el('models-license-ack').checked;};
    el('models-download-start').onclick=startDownload;
    el('models-delete-confirm').oninput=()=>{el('models-delete-go').disabled=el('models-delete-confirm').value!==deleting?.filename;};
    el('models-delete-go').onclick=confirmDelete;
  }
  global.NajdiModels={load(){if(!loaded){loaded=true;bind();}if(!el('models-library').hidden)refreshLibrary();}};
})(window);
