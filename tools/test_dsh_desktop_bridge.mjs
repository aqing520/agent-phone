import {apply} from './dsh-desktop-bridge/index.mjs';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import assert from 'node:assert/strict';
const directory=await fs.mkdtemp(path.join(os.tmpdir(),'ap-bridge-test-'));
const sid='11111111-1111-4111-8111-111111111111';
const archived=[];const attached=[];const disposers=[];
const workspace={id:'w',title:'fixture',path:directory,sessionIds:attached,attachSession:async id=>attached.push(id)};
const ctx={workspaceRegistry:{archivedSessionIds:archived,list:()=>[workspace],resolveByPath:async()=>workspace,
 archiveSession:async id=>archived.push(id),unarchiveSession:async id=>archived.splice(archived.indexOf(id),1)},
 sessionPersistence:{list:async()=>[{header:{id:sid,cwd:directory}}]},effect:factory=>disposers.push(factory())};
await apply(ctx,{directory});
const socket = path.join(directory, 'dsh-desktop.sock');
const call=request=>new Promise((resolve,reject)=>{
 const client=net.createConnection(socket);
 let data='';client.on('error',reject);client.on('connect',()=>client.write(JSON.stringify(request)+'\n'));
 client.on('data',chunk=>data+=chunk);client.on('end',()=>resolve(JSON.parse(data)));
});
try{
 assert.equal((await fs.stat(socket)).mode & 0o777, 0o600);
 assert.equal((await call({method:'status'})).ready,true);
 assert.deepEqual((await call({method:'archive',session:sid})).archived,[sid]);
 assert.deepEqual((await call({method:'restore',session:sid})).archived,[]);
 await call({method:'attach',session:sid});assert.deepEqual(attached,[sid]);
 assert.ok((await call({method:'delete',session:sid})).error);
 console.log('Desktop bridge: status/archive/restore/attach/deny passed');
}finally{
 for(const dispose of disposers) await dispose();
 await assert.rejects(fs.lstat(socket), {code:'ENOENT'});
 await fs.rmdir(directory);
}
