/* Pure fictional boundary probes; never starts the original project. */
const {copyCandidate}=require('./candidate-copy.cjs'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'core-harness-'));
try{
 const source=path.join(temp,'fake'),out=path.join(temp,'out');fs.mkdirSync(source);fs.writeFileSync(path.join(source,'private-fixture.txt'),'fictional');
 assert.throws(()=>copyCandidate(source,out));assert(!fs.existsSync(out));
 const files={'app/server.py':'# fictional never executed','scripts/install.py':'raise RuntimeError("must never execute")','tests/browser.cjs':'// fictional'};
 const manifest={profile:'source-only-engineering-candidate',publication_approved:false,files:{}};
 for(const [p,data] of Object.entries(files)){const file=path.join(source,p);fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,data);manifest.files[p]=crypto.createHash('sha256').update(data).digest('hex');}
 fs.writeFileSync(path.join(source,'MANIFEST.json'),JSON.stringify(manifest));copyCandidate(source,out);assert(!fs.existsSync(path.join(out,'private-fixture.txt')));
 fs.writeFileSync(path.join(source,'app/server.py'),'tampered');assert.throws(()=>copyCandidate(source,path.join(temp,'blocked')));assert(!fs.existsSync(path.join(temp,'blocked')));
 manifest.files['../escape.py']='0'.repeat(64);fs.writeFileSync(path.join(source,'MANIFEST.json'),JSON.stringify(manifest));assert.throws(()=>copyCandidate(source,path.join(temp,'traversal')));
 console.log('PASS harness: non-candidate/tamper/traversal rejected before execution; only manifest files copied');
}finally{fs.rmSync(temp,{recursive:true,force:true});}
