/* Preserved legacy presentation. The official shell never imports this bundle. */
let fragmentsPromise=null;
let mounted=false;
async function fragments(){
  if(!fragmentsPromise){
    fragmentsPromise=fetch('/advanced-workspace.html',{cache:'no-store'}).then(async response=>{
      if(!response.ok)throw new Error('Unable to load the preserved workspace. Reload and try again.');
      return new DOMParser().parseFromString(await response.text(),'text/html');
    }).catch(error=>{fragmentsPromise=null;throw error;});
  }
  return fragmentsPromise;
}
function copy(document,id){
  const template=document.getElementById(id);
  if(!template)throw new Error('The preserved workspace template is incomplete.');
  return template.content.cloneNode(true);
}
export async function mountViews(){
  if(mounted)return;
  const source=await fragments();
  const style=document.createElement('link');
  style.rel='stylesheet';style.href='/advanced-workspace.css';
  document.head.append(style);
  document.getElementById('view-settings').before(copy(source,'legacy-panels'));
  bindLegacyEvents();
  window.NajdiChat.bindLegacyExports();
  document.querySelectorAll('#view-manual-data [data-add-new]').forEach(button=>button.onclick=()=>switchView('add-data'));
  mounted=true;
}

// Display preference only. Routes and backend checks remain available in either mode.
function setAdvancedMode(enabled,navigate=true){
  window.NajdiPrepare?.save();
  prefs.set('najdilab.advancedMode',enabled?'1':'0');
  document.documentElement.classList.toggle('advanced-mode',enabled);
  for(const id of ['advanced-mode','workspace-mode']){const input=document.getElementById(id);if(input)input.checked=enabled;}
  if(navigate)switchView('prepare');
}
function initAdvancedMode(){
  const enabled=prefs.get('najdilab.advancedMode')==='1';
  document.documentElement.classList.toggle('advanced-mode',enabled);
  for(const id of ['advanced-mode','workspace-mode']){const input=document.getElementById(id);if(input){input.checked=enabled;input.onchange=()=>setAdvancedMode(input.checked);}}
}

// Developer-only restoration. Call from an explicitly modified temporary shell.
export async function restoreWorkspace(){
  await mountViews();
  if(document.getElementById('advanced-workspace'))return;
  const source=await fragments();
  document.getElementById('view-prepare').prepend(copy(source,'legacy-launcher'));
  document.querySelector('.top-actions').prepend(copy(source,'legacy-topbar'));
  document.getElementById('view-settings').prepend(copy(source,'legacy-settings'));
  document.querySelector('.nav-item[data-view="prepare"]').before(copy(source,'legacy-navigation'));
  document.querySelectorAll('[data-advanced-view]').forEach(button=>button.onclick=()=>switchView(button.dataset.advancedView));
  window.setAdvancedMode=setAdvancedMode;
  window.initAdvancedMode=initAdvancedMode;
  window.NajdiLegacyWorkspace={restored:true};
  initAdvancedMode();
}
