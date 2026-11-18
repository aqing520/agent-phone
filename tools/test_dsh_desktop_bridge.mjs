import {apply, createDashboardServer} from './dsh-desktop-bridge/index.mjs';
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
await apply(ctx,{directory, dashboardPort:0});
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

const dashboard = createDashboardServer(async route => route === '/api/usage'
  ? { daily: {}, totals: { today: 7, all: 10 } }
  : { sessions: [{ id: sid, source: 'dsh' }, { source: 'codex' }] });
await new Promise(resolve => dashboard.listen(0, '127.0.0.1', resolve));
try {
  const url = `http://127.0.0.1:${dashboard.address().port}/api/dashboard`;
  const response = await fetch(url);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    usage: { daily: {}, totals: { today: 7, all: 10 } }, sessions: [{ id: sid, source: 'dsh' }],
  });
  const { get } = await import('node:http');
  const denied = await new Promise((resolve, reject) => {
    get(url, { headers: { host: 'unrelated.invalid' } }, res => {
      res.resume();
      resolve(res.statusCode);
    }).on('error', reject);
  });
  assert.equal(denied, 403);
} finally {
  await new Promise(resolve => dashboard.close(resolve));
}

const { createServer } = await import('node:http');
const gateway = createServer((req, res) => {
  const usage = { daily: {}, totals: { today: 3, all: 5 } };
  res.end(JSON.stringify(req.url === '/api/usage' ? usage : { sessions: [] }));
});
await new Promise(resolve => gateway.listen(0, '127.0.0.1', resolve));
const previousPort = process.env.AGENT_PHONE_PORT;
process.env.AGENT_PHONE_PORT = String(gateway.address().port);
const configuredDashboard = createDashboardServer();
try {
  await new Promise(resolve => configuredDashboard.listen(0, '127.0.0.1', resolve));
  const result = await fetch(`http://127.0.0.1:${configuredDashboard.address().port}/api/dashboard`);
  assert.equal(result.status, 200);
  assert.deepEqual((await result.json()).usage.totals, { today: 3, all: 5 });
} finally {
  if (previousPort === undefined) delete process.env.AGENT_PHONE_PORT;
  else process.env.AGENT_PHONE_PORT = previousPort;
  await Promise.all([gateway, configuredDashboard].map(server => new Promise(resolve => server.close(resolve))));
}
