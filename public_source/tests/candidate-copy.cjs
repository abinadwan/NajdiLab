/* Integrity-selected copy for acceptance; no directory discovery or app execution. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
function copyCandidate(source,destination){
 source=path.resolve(source);destination=path.resolve(destination);
 const linked=p=>{const s=fs.lstatSync(p);return s.isSymbolicLink();};
 if(linked(source))throw Error('Linked source root');
 const mp=path.join(source,'MANIFEST.json');if(linked(mp)||fs.statSync(mp).size>256*1024)throw Error('Invalid source manifest');
 const raw=fs.readFileSync(mp),m=JSON.parse(raw),files=m.files;
 if(m.profile!=='source-only-engineering-candidate'||m.publication_approved!==false||!files||typeof files!=='object'||Array.isArray(files)||Object.keys(files).length>512||!['app/server.py','scripts/install.py','tests/browser.cjs'].every(p=>Object.hasOwn(files,p)))throw Error('Build and verify an exact candidate before acceptance');
 const checked=new Map();let total=0;
 for(const [name,hash] of Object.entries(files)){
  if(!/^[A-Za-z0-9_./-]+$/.test(name)||path.posix.normalize(name)!==name||name.startsWith('/')||name.split('/').some(p=>p.startsWith('.')&&!['.env.example','.gitignore'].includes(name)||['data','exports','backups','training','datasets','checkpoints'].includes(p))||/^(app\/phase|app\/training_control|app\/runtime_control|app\/platform_state)/.test(name)||!/^([a-f0-9]{64})$/.test(hash))throw Error('Invalid candidate path/hash');
  const file=path.join(source,...name.split('/'));let cursor=file;while(true){if(linked(cursor))throw Error('Linked candidate source');const parent=path.dirname(cursor);if(parent===cursor)break;cursor=parent;}
  const stat=fs.statSync(file);total+=stat.size;if(!stat.isFile()||stat.size>16*1024*1024||total>64*1024*1024)throw Error('Candidate bounds exceeded');
  const data=fs.readFileSync(file);if(crypto.createHash('sha256').update(data).digest('hex')!==hash)throw Error('Candidate source hash mismatch');checked.set(name,data);
 }
 fs.mkdirSync(destination);checked.set('MANIFEST.json',raw);
 for(const [name,data] of checked){const file=path.join(destination,...name.split('/'));fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,data,{flag:'wx'});}
 return m;
}
module.exports={copyCandidate};
