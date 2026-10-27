'use strict';
let token;
const flags = ['training_eligible','contains_personal_data','contains_sensitive_data','evaluation_only','exclude_from_training','needs_fact_check'];
async function api(path,body){
  const response=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-NajdiLab-CSRF':token}:{},body:body?JSON.stringify(body):undefined});
  const data=await response.json();if(!response.ok)throw Error(data.message||data.code||'Local operation unavailable');return data;
}
function status(message){document.querySelector('#status').textContent=message;}
async function refresh(){
  const data=await api('/api/v1/review-queue');const host=document.querySelector('#queue');host.replaceChildren();
  for(const row of data.items){
    const card=document.createElement('article'),original=document.createElement('p'),editor=document.createElement('textarea'),button=document.createElement('button');
    original.dir='auto';original.textContent='Original: '+row.original_response;
    editor.dir='auto';editor.setAttribute('aria-label','Corrected response');editor.value=row.corrected_response||'';
    const fields=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent='Saved flags — change only after review';fields.append(legend);
    const changed={};
    for(const flag of flags){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=Boolean(row[flag]);input.onchange=()=>{changed[flag]=input.checked;status('Unsaved changes.');};label.append(input,' '+flag.replaceAll('_',' '));fields.append(label);}
    button.textContent='Save correction';editor.oninput=()=>status('Unsaved correction.');
    button.onclick=async()=>{try{await api(`/api/v1/reviews/${row.id}/correct`,{expected_updated_at:row.updated_at,review_status:'FULL_CORRECTION',corrected_response:editor.value,...changed});status('Correction saved; original and unrelated flags preserved.');await refresh();}catch(e){status(e.message+' Reload and review saved state before retrying.');}};
    card.append(original,editor,fields,button);host.append(card);
  }
  if(!data.items.length)host.textContent='No pending reviews. Use the explicit synthetic setup command in README for a fresh disposable candidate.';
  document.querySelector('#versions').textContent=JSON.stringify(await api('/api/v1/dataset-versions'),null,2);
}
document.querySelector('#refresh').onclick=()=>{if(confirm('Reload saved data? Unsaved edits will be discarded.'))refresh().catch(e=>status(e.message));};
document.querySelector('#prepare').onclick=async()=>{if(!confirm('Prepare a local version including demo records? No model training occurs.'))return;try{await api('/api/v1/exports',{include_demo:true});status('Version prepared.');await refresh();}catch(e){status(e.message);}};
(async()=>{try{token=(await api('/api/v1/session')).csrf_token;await refresh();status('Local source-only core ready.');}catch(e){status(e.message);}})();
