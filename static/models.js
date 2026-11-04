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
  const RUNTIME={READY:'ready',RUNNING:'info',STARTING:'info',STOPPING:'info',INSTALLING:'info',STOPPED:'neutral',
    NOT_INSTALLED:'neutral',UNVERIFIED:'warning',BLOCKED:'hold',ERROR:'blocked'};
  const RUNTIME_TEXT={READY:'Ready — verified',RUNNING:'Running a model',STARTING:'Starting',STOPPING:'Stopping',INSTALLING:'Installing',
    STOPPED:'Stopped',NOT_INSTALLED:'Not installed',UNVERIFIED:'Unverified',BLOCKED:'Blocked',ERROR:'Error'};
  const PHASE_TEXT={PREPARING:'Preparing',DOWNLOADING:'Downloading',CHECKING_OFFLINE_COPY:'Checking the offline copy',
    EXTRACTING:'Unpacking',VERIFYING:'Verifying on this computer'};
  const TABS=['recommended','trending','discover','library','runtime'];
  const PROVENANCE={OFFICIAL:['ready','Verified official publisher'],COMMUNITY:['info','Community conversion'],
    MODIFIED:['warning','Fine-tuned / modified'],UNVERIFIED:['neutral','Unverified source']};
  const LICENSE_TEXT={OPEN:'Open license',TERMS:'Custom terms: read them before use',NON_COMMERCIAL:'Non-commercial use only',UNKNOWN:'No license stated'};
  const PLACEMENT_TEXT={GPU:'Fully on the GPU',PARTIAL_OFFLOAD:'Split between GPU and system memory',CPU:'CPU only',NONE:'Does not fit',UNKNOWN:'Unknown'};
  const FILTERS={
    sort:['Ranking',[['trending','Trending score'],['downloads','Downloads'],['likes','Likes'],['updated','Recently updated']],'trending'],
    size:['Size (total parameters)',[['all','Up to 12B'],['small','Up to 3B'],['medium','Above 3B through 7B'],['large','Above 7B through 12B']],'all'],
    source:['Source',[['official','Verified official publishers'],['community','Official and community conversions'],['all','All sources, including modified and unverified']],'official'],
    purpose:['Purpose',[['chat','Instruct / chat'],['any','Any purpose']],'chat'],
    context:['Context size',[['4096','4096'],['8192','8192'],['16384','16384'],['32768','32768']],'8192'],
    gpu:['GPU use',[['auto','Automatic'],['all','All layers on GPU'],['0','CPU only']],'auto']};
  let trending=null;
  let current=null,adviceFor=null,timer=null,loaded=false,library=null,runtime=null,runtimeTimer=null,pending=null;

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
    for(const tab of TABS)el(`models-${tab}`).hidden=name!==tab;
    if(name==='library')refreshLibrary();
    if(name==='runtime')refreshRuntime();
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
    if(r.load.reasons.some(x=>x.code==='NATIVE_SERVER_MISSING'))
      parts.push(node('button',{type:'button',class:'button ghost',onclick:()=>showTab('runtime')},'Set up the llama.cpp runtime'));
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

  // ------------------------------------------------------------- trending and recommended
  function buildFilters(){
    for(const box of document.querySelectorAll('[data-filters]')){
      const prefix=box.dataset.filters==='trending'?'trend':'rec';
      const keys=prefix==='trend'?['sort','size','source','purpose']:['size','source','purpose','context','gpu'];
      box.replaceChildren(...keys.map(key=>{const [label,options,value]=FILTERS[key];const id=`${prefix}-${key}`;
        return node('div',{class:'field'},node('label',{for:id},label),select(id,options,value));}));
    }
  }
  const value=id=>el(id).value;
  function leftOut(counts){
    const parts=[['over_12b','above 12B parameters'],['unknown_size','with an unknown parameter count'],['outside_size_filter','outside the size filter'],
      ['not_chat','not instruct / chat'],['other_sources','from other sources'],['no_single_file_gguf','without a single-file GGUF'],
      ['merged_duplicates','duplicate conversions merged']].filter(([k])=>counts[k]);
    return parts.length?node('div',{},node('p',{class:'muted'},'Left out of',' ',ident(count(counts.fetched)),' ','models read from Hugging Face:'),
      node('ul',{class:'models-left-out'},parts.map(([k,text])=>node('li',{},ident(count(counts[k])),' ',text)))):null;
  }
  function fetchedLine(r){
    return node('p',{class:r.cache==='stale'?'models-error-line':'muted'},'Rankings fetched from Hugging Face at',' ',ident(r.fetched_at||'—'),
      r.cache==='cached'?[' · ','cached copy, less than 10 minutes old']:null,
      r.cache==='stale'?[' · ','Hugging Face could not be reached; this is the last ranking fetched.']:null);
  }
  function parameterFact(check){
    if(check.status!=='CONFIRMED')return [pill('hold','UNVERIFIED'),' ',check.reasons.length?check.reasons[0].message:''];
    return [ident(`${check.billions}B`),' ','total',check.mixture_of_experts?[' · ','mixture of experts, all experts counted']:null];
  }
  function discoveryCard(item,mode){
    const [kind,label]=PROVENANCE[item.provenance.class];
    const check=item.parameter_check;
    const facts=[fact('Publisher',ident(item.author)),
      fact('Model family',[item.family.architecture?ident(item.family.architecture):'Unknown',item.family.base_model?[' · ',ident(item.family.base_model)]:null],'reported'),
      fact('Total parameters',parameterFact(check),check.status==='CONFIRMED'?'reported':'unknown'),
      fact('Quantizations',node('span',{class:'models-chips'},item.quantizations.slice(0,10).map(q=>node('span',{class:'models-chip',translate:'no'},q)))),
      fact('License',[item.license?ident(item.license):null,item.license?' · ':null,LICENSE_TEXT[item.license_class]])];
    if(mode==='trending')facts.push(fact('Hugging Face ranking',[ident(`#${item.rank}`),item.trending_score!=null?[' · ','trending score',' ',ident(count(item.trending_score))]:null,
      ' · ',ident(count(item.downloads)),' ','downloads',' · ',ident(count(item.likes)),' ','likes'],'reported'),fact('Last updated',ident(item.last_modified||'—'),'reported'));
    if(item.also_converted_by&&item.also_converted_by.length)facts.push(fact('Also converted by',item.also_converted_by.map((a,i)=>[i?', ':null,ident(a)])));
    let fit=null;
    if(mode==='recommended'){
      const a=item.advice,c=item.chosen;
      fit=node('section',{class:'models-download-check','aria-label':'Fit on this computer'},
        node('div',{class:'models-verdict-line'},node('h4',{},'Compatibility (estimate)'),pill(VERDICT[a.load.classification],a.load.classification),
          node('span',{class:'muted'},'Where it would run:',' ',PLACEMENT_TEXT[a.performance.placement]||a.performance.placement)),
        node('p',{class:'models-performance'},'Expected performance:',' ',a.performance.expectation),
        node('dl',{class:'models-facts compact'},fact('Suggested file',[ident(c.filename),' · ',ident(bytes(c.size_bytes))],'reported'),
          a.estimate?fact('Estimated memory needed',ident(bytes(a.estimate.required_bytes)),'estimate'):null,
          a.load.recommended_context?fact('Largest context that fits (estimate)',ident(count(a.load.recommended_context))):null,
          fact('Download check',a.download.decision==='ALLOWED'?pill('ready','Download allowed'):pill('hold','Download blocked'))),
        a.load.reasons.length?node('ul',{class:'models-reasons'},a.load.reasons.slice(0,3).map(x=>node('li',{},x.message))):null);
    }
    return node('li',{},node('article',{class:'models-discovery-item'},
      node('div',{class:'models-library-head'},node('h3',{},ident(item.id)),pill(kind,label),check.status!=='CONFIRMED'?pill('hold','UNVERIFIED size'):null,
        item.access&&item.access!=='OPEN'?pill('hold','Needs approval on Hugging Face'):null),
      node('dl',{class:'models-facts compact'},facts),
      node('ul',{class:'models-reasons'},item.provenance.evidence.map(e=>node('li',{},e))),fit,
      node('div',{class:'models-actions'},node('button',{type:'button',class:'button ghost',onclick:()=>{showTab('discover');openRepo(item.id);}},'View files and download…'))));
  }
  async function loadTrending(more=false,refresh=false){
    const body={sort:value('trend-sort'),size:value('trend-size'),source:value('trend-source'),purpose:value('trend-purpose'),
      include_unknown_size:el('trend-unknown').checked,refresh};
    if(more&&trending){body.cursor=trending.next_cursor;body.offset=trending.next_offset;}
    say('models-trending-status','Reading the ranking from Hugging Face…');el('models-trending-more').hidden=true;
    try{
      const r=await api('/api/v1/models/hub/trending',body);
      const shown=more?new Set([...el('models-trending-list').querySelectorAll('h3')].map(h=>h.textContent)):new Set();
      const items=r.items.filter(i=>!shown.has(i.id));
      if(!more)el('models-trending-list').replaceChildren();
      el('models-trending-list').append(...items.map(i=>discoveryCard(i,'trending')));
      trending=r;
      say('models-trending-summary',fetchedLine(r),leftOut(r.counts));
      say('models-trending-status',el('models-trending-list').children.length?null:'No model matches these filters on the pages read. Load more, or widen the filters.');
      el('models-trending-more').hidden=!r.next_cursor;el('models-trending-refresh').hidden=false;
    }catch(error){say('models-trending-status',node('span',{class:'models-error',role:'alert'},errorText(error),error.hint?[' ',error.hint]:null));}
  }
  async function loadRecommended(refresh=false){
    if(!el('rec-hardware').checked){say('models-recommend-status','Allow reading this computer\'s hardware first: recommendations depend on it.');return;}
    say('models-recommend-status','Checking up to 10 models against this computer… this reads their file lists and GGUF headers from Hugging Face.');
    el('models-recommend-list').replaceChildren();say('models-recommend-summary');
    try{
      const r=await api('/api/v1/models/hub/recommended',{size:value('rec-size'),source:value('rec-source'),purpose:value('rec-purpose'),
        context:Number(value('rec-context')),gpu_layers:value('rec-gpu'),hardware_approved:true,refresh});
      const gpu=(r.host.gpus||[])[0];
      say('models-recommend-summary',node('dl',{class:'models-facts compact'},
          fact('GPU',gpu?[ident(gpu.name||'GPU'),' · ',ident(bytes(gpu.free_bytes)),' ','free of',' ',ident(bytes(gpu.total_bytes))]:'No GPU reported','measured'),
          fact('System memory free',ident(bytes(r.host.ram_available_bytes)),'measured'),
          fact('NajdiLab Native runtime',r.host.runtime.server_available?'llama-server configured':'llama-server not configured')),
        node('p',{class:'muted'},r.method),node('p',{class:'muted'},r.note),fetchedLine({...r,cache:'fresh'}),leftOut(r.counts));
      el('models-recommend-list').replaceChildren(...r.items.map(i=>discoveryCard(i,'recommended')));
      say('models-recommend-status',r.items.length?null:'No model matched these filters among the models checked. Widen the source or size filter.');
      el('models-recommend-refresh').hidden=false;
    }catch(error){say('models-recommend-status',node('span',{class:'models-error',role:'alert'},errorText(error),error.hint?[' ',error.hint]:null));}
  }

  // ------------------------------------------------------------- managed llama.cpp runtime
  async function refreshRuntime(){
    clearTimeout(runtimeTimer);
    try{
      runtime=await api('/api/v1/runtime');renderRuntime(runtime);
      if(runtime.job||['STARTING','STOPPING'].includes(runtime.state))runtimeTimer=setTimeout(refreshRuntime,1000);
    }catch(error){say('runtime-status',node('p',{class:'models-error',role:'alert'},errorText(error)));}
  }
  function verification(v){
    if(!v)return null;
    const p=v.probe||{};
    return node('dl',{class:'models-facts compact'},
      fact('Program identity',[ident(`build ${v.version.build}`),' · ',ident(`commit ${v.version.commit}`)],'measured'),
      fact('Devices this build sees',v.devices.length?v.devices.map((d,i)=>[i?', ':null,ident(`${d.id}: ${d.name}`)]):'CPU only','measured'),
      fact('Test computation',[ident(p.device_name||p.device),p.layers_on_gpu?[' · ',ident(p.layers_on_gpu),' ','layers on the GPU']:null,
        ' · ',ident(`${p.tokens} tokens`),' · ',ident(`${p.seconds} s`)],'measured'),
      fact('Verified at',ident(v.verified_at)));
  }
  function installFacts(a){
    return node('dl',{class:'models-facts compact'},
      fact('Package',[a.label,' · ',ident(a.package)]),fact('llama.cpp build',[ident(a.build),' · ',ident(a.commit.slice(0,12))]),
      fact('Installed at',ident(a.installed_at)),fact('Files',[ident(count(a.files)),' · ',ident(bytes(a.size_bytes))]),
      fact('Folder',ident(a.path)),fact('License notices',ident(a.notices)));
  }
  function renderRuntime(r){
    const busy=Boolean(r.job)||['RUNNING','STARTING','STOPPING'].includes(r.native_state);
    const actions=[];
    const act=(label,fn,cls='button ghost',disabled=false)=>actions.push(node('button',{type:'button',class:cls,onclick:fn,disabled},label));
    if(r.job)act('Cancel installation',()=>runtimeAction('cancel',{}));
    if(!r.host&&r.platform.supported)act('Check this computer',()=>runtimeAction('detect',{approved:true}),'button primary',Boolean(r.job));
    if(r.active){
      act('Verify files',()=>runtimeAction('verify',{}),'button ghost',Boolean(r.job));
      if(['READY','STOPPED'].includes(r.state))act('Start a model…',()=>showTab('library'),'button primary');
      if(r.native_state==='RUNNING')act('Stop the model…',()=>openRuntimeDialog('stop'));
      if(r.previous)act('Roll back…',()=>openRuntimeDialog('rollback'),'button ghost',busy);
      act('Uninstall…',()=>openRuntimeDialog('uninstall'),'button delete-action',busy);
    }
    const job=r.job?node('div',{class:'models-progress',role:'status'},
      node('progress',{max:String(r.job.download_total_bytes),value:String(r.job.downloaded_bytes),'aria-label':'Installation progress'}),
      node('span',{},PHASE_TEXT[r.job.phase]||r.job.phase,r.job.asset?[' · ',ident(r.job.asset)]:null,' · ',
        ident(bytes(r.job.downloaded_bytes)),' ','of',' ',ident(bytes(r.job.download_total_bytes)))):null;
    const done=r.last_result;
    const result=done?node('p',{class:done.ok?'muted':'models-error-line'},
      done.action==='VERIFY'?(done.ok?'Every file matches its recorded SHA-256.':['Files changed since installation:',' ',ident(done.problems.join(', '))])
      :done.action==='UNINSTALL'?'The managed runtime was removed. Archives you placed in the archives folder were kept.'
      :done.action==='ROLLBACK'?'Switched back to the previous runtime.':'The runtime was installed and verified.'):null;
    say('runtime-status',node('div',{class:'models-library-head'},node('h2',{},'Managed llama.cpp runtime'),pill(RUNTIME[r.state]||'neutral',RUNTIME_TEXT[r.state]||r.state)),
      node('p',{class:'muted'},'NajdiLab can install the official llama.cpp build it was tested with, check that it really runs on this computer\'s GPU, and run it only on 127.0.0.1. Nothing is downloaded, installed, started or removed without your approval.'),
      r.mode==='EXTERNAL'?node('p',{class:'chatv2-warning'},'Your own llama-server (NAJDILAB_NATIVE_SERVER) is in use. The managed runtime is not used while that is set.'):null,
      !r.platform.supported?node('p',{class:'models-error-line'},'This system is not supported by the managed runtime. You can still set NAJDILAB_NATIVE_SERVER to your own llama-server.',' ',ident(`${r.platform.system} ${r.platform.machine}`)):null,
      node('dl',{class:'models-facts compact'},fact('Pinned build',[ident(r.build.tag),' · ',ident(r.build.commit.slice(0,12)),' · ',ident(r.build.published)]),
        fact('Source',ident(r.build.source)),fact('Network','The model server listens on 127.0.0.1 only.')),
      r.active?[node('h3',{},'Active installation'),installFacts(r.active),verification(r.active.verification)]:null,
      r.previous?node('p',{class:'muted'},'Previous installation kept for rollback:',' ',ident(r.previous.package),' · ',ident(r.previous.installed_at)):null,
      r.state==='UNVERIFIED'?node('p',{class:'models-error-line'},'Files changed since they were verified, so models will not start. Repair the runtime below.',' ',ident(r.problems.join(', '))):null,
      r.native_error&&r.state==='ERROR'?node('p',{class:'models-error-line'},r.native_error.message):null,
      r.last_error?node('p',{class:'models-error-line',role:'alert'},r.last_error.message,' ',node('span',{class:'muted'},ident(r.last_error.code))):null,
      result,job,node('div',{class:'models-actions'},actions));
    renderPackages(r,busy);
  }
  function renderPackages(r,busy){
    if(!r.candidates){say('runtime-packages',r.platform.supported?node('p',{class:'muted'},'Check this computer to see which build fits. NajdiLab reads the operating system, the GPU model, its compute capability and the driver\'s CUDA version with nvidia-smi. Nothing leaves this computer.'):null);return;}
    if(!r.candidates.length){say('runtime-packages',node('p',{class:'models-error-line'},'No package is available for this system.'));return;}
    say('runtime-packages',node('ul',{class:'models-library-items',role:'list'},r.candidates.map(c=>{
      const mine=r.active&&r.active.package===c.id;
      const label=mine?(r.update_available?'Update…':'Repair…'):'Install…';
      const state=c.recommended?pill('ready','Recommended'):c.eligible?pill('neutral','Compatible'):pill('hold','Not compatible');
      return node('li',{},node('article',{class:'models-library-item'},
        node('div',{class:'models-library-head'},node('h3',{},c.label),state,mine?pill('info','Installed'):null),
        node('dl',{class:'models-facts compact'},fact('Package',ident(c.id)),fact('Download',c.download_bytes?ident(bytes(c.download_bytes)):'Offline copy present'),
          fact('Tested on real hardware by the maintainers',c.tested_on_real_hardware?'Yes':'Not yet')),
        c.reasons.length?node('ul',{class:'models-reasons'},c.reasons.map(x=>node('li',{},x.message))):null,
        c.eligible?node('div',{class:'models-actions'},node('button',{type:'button',class:c.recommended?'button primary':'button ghost',
          disabled:busy||c.preflight.decision!=='ALLOWED',onclick:()=>openRuntimeDialog('install',c)},label)):null,
        c.eligible&&c.preflight.decision!=='ALLOWED'?node('p',{class:'models-error-line'},c.preflight.reasons.map(x=>x.message)):null));
    })));
  }
  function openRuntimeDialog(action,candidate){
    pending={action,candidate};
    const mine=candidate&&runtime.active&&runtime.active.package===candidate.id;
    const titles={install:mine?(runtime.update_available?'Update the runtime':'Repair the runtime'):'Install the llama.cpp runtime',
      rollback:'Roll back the runtime',uninstall:'Uninstall the managed runtime',stop:'Stop the running model'};
    const go={install:'Download and install',rollback:'Roll back',uninstall:'Uninstall',stop:'Stop'};
    say('runtime-dialog-title',titles[action]);say('runtime-dialog-go',go[action]);say('runtime-dialog-error');
    el('runtime-dialog-go').className=action==='uninstall'?'button delete-action':'button primary';
    el('runtime-dialog-license').hidden=action!=='install';el('runtime-dialog-typed').hidden=action!=='uninstall';
    el('runtime-license-ack').checked=false;el('runtime-dialog-confirm').value='';
    el('runtime-dialog-go').disabled=action==='install'||action==='uninstall';
    if(action==='install'){
      const p=candidate.preflight,cuda=candidate.assets.some(a=>a.name.startsWith('cudart-'));
      say('runtime-dialog-body',node('dl',{class:'models-facts compact'},fact('Package',[candidate.label,' · ',ident(candidate.id)]),
          fact('llama.cpp build',[ident(runtime.build.tag),' · ',ident(runtime.build.commit)]),fact('Source',ident(runtime.build.source))),
        node('ul',{class:'models-reasons'},candidate.assets.map(a=>node('li',{},ident(a.name),' · ',ident(bytes(a.size)),a.offline_copy?[' · ','offline copy']:null,' · ','SHA-256',' ',
          node('bdi',{dir:'ltr',translate:'no',class:'hash'},a.sha256)))),
        node('dl',{class:'models-facts compact models-storage-facts'},fact('Destination',ident(p.destination)),
          fact('Free space now',ident(bytes(p.free_bytes)),'measured'),fact('To download',ident(bytes(p.download_bytes))),
          fact('Unpacked size (upper bound)',ident(bytes(p.unpacked_bytes)),'estimate'),fact('Safety reserve',ident(bytes(p.reserve_bytes))),
          fact('Total required',ident(bytes(p.required_bytes)))),
        node('p',{class:'muted'},'Steps: download over HTTPS from GitHub, compare every file with its pinned SHA-256, unpack into a new folder, confirm the program\'s build and commit, run a tiny generated test model on the device, then switch to it. If any step fails, nothing changes and the current runtime stays active. No model is loaded.'));
      say('runtime-dialog-licenses',node('li',{},'llama.cpp and nlohmann/json: MIT License'),node('li',{},'LLVM OpenMP: Apache License 2.0 with LLVM exceptions'),
        cuda?node('li',{},'NVIDIA CUDA runtime libraries: NVIDIA CUDA Toolkit End User License Agreement'):null);
    }else if(action==='rollback'){
      say('runtime-dialog-body',node('p',{},'Switch back to the previous installation. Its files are checked first.'),
        node('dl',{class:'models-facts compact'},fact('Current',ident(runtime.active.package)),
          fact('Previous',[ident(runtime.previous.package),' · ',ident(runtime.previous.installed_at)])));
    }else if(action==='uninstall'){
      say('runtime-dialog-body',node('p',{class:'chatv2-warning'},'This permanently removes the managed llama.cpp installations from NajdiLab\'s runtime folder. Your models, Ollama, LM Studio and any llama-server of your own are not touched. Archives you placed in the archives folder are kept.'));
    }else{
      say('runtime-dialog-body',node('p',{},'Stop the model running in NajdiLab Native. Only the server process NajdiLab started is stopped.'),
        node('dl',{class:'models-facts compact'},fact('Model',ident(runtime.running_model||''))));
    }
    el('runtime-dialog').showModal();
  }
  async function confirmRuntime(){
    const {action,candidate}=pending||{};
    el('runtime-dialog-go').disabled=true;
    try{
      if(action==='install')await api('/api/v1/runtime/install',{approved:true,package:candidate.id,license_acknowledged:el('runtime-license-ack').checked});
      else if(action==='rollback')await api('/api/v1/runtime/rollback',{approved:true});
      else if(action==='uninstall')await api('/api/v1/runtime/uninstall',{approved:true,confirm:el('runtime-dialog-confirm').value});
      else await api('/api/v1/native/stop',{approved:true});
      el('runtime-dialog').close();refreshRuntime();
    }catch(error){say('runtime-dialog-error',errorText(error));el('runtime-dialog-go').disabled=false;}
  }
  async function runtimeAction(action,body){
    try{runtime=await api(`/api/v1/runtime/${action}`,body);renderRuntime(runtime);}
    catch(error){global.toast?.(error.message,true);}
    if(action!=='detect')refreshRuntime();
  }

  function bind(){
    el('models-search').onsubmit=search;
    buildFilters();
    el('models-trending-form').onsubmit=event=>{event.preventDefault();loadTrending();};
    el('models-trending-more').onclick=()=>loadTrending(true);
    el('models-trending-refresh').onclick=()=>loadTrending(false,true);
    el('models-recommend-form').onsubmit=event=>{event.preventDefault();loadRecommended();};
    el('models-recommend-refresh').onclick=()=>loadRecommended(true);
    for(const tab of document.querySelectorAll('[data-models-tab]')){
      tab.onclick=()=>showTab(tab.dataset.modelsTab);
      tab.onkeydown=event=>{
        if(!['ArrowLeft','ArrowRight'].includes(event.key))return;
        const rtl=document.documentElement.dir==='rtl',step=(event.key==='ArrowRight')!==rtl?1:-1;
        const next=TABS[(TABS.indexOf(tab.dataset.modelsTab)+step+TABS.length)%TABS.length];
        showTab(next);document.querySelector(`[data-models-tab="${next}"]`).focus();
      };
    }
    el('models-license-ack').onchange=()=>{el('models-download-start').disabled=!el('models-license-ack').checked;};
    el('models-download-start').onclick=startDownload;
    el('models-delete-confirm').oninput=()=>{el('models-delete-go').disabled=el('models-delete-confirm').value!==deleting?.filename;};
    el('models-delete-go').onclick=confirmDelete;
    el('runtime-license-ack').onchange=()=>{el('runtime-dialog-go').disabled=!el('runtime-license-ack').checked;};
    el('runtime-dialog-confirm').oninput=()=>{el('runtime-dialog-go').disabled=el('runtime-dialog-confirm').value!=='UNINSTALL';};
    el('runtime-dialog-go').onclick=confirmRuntime;
  }
  global.NajdiModels={load(){if(!loaded){loaded=true;bind();}if(!el('models-library').hidden)refreshLibrary();if(!el('models-runtime').hidden)refreshRuntime();}};
})(window);
