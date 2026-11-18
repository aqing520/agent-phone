// Runs inside the desktop Host. Never opens a second storage-domain writer.
import net from 'node:net';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createServer } from 'node:http';
export const name = 'agent-phone-desktop-bridge';
export const inject = ['workspaceRegistry', 'sessionPersistence'];

async function readDashboard(path) {
  const port = Number(process.env.AGENT_PHONE_PORT || 5173);
  const response = await fetch(`http://127.0.0.1:${port}${path}`, {
    redirect: 'error', signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error(`Dashboard gateway returned HTTP ${response.status}`);
  return response.json();
}

export function createDashboardServer(read = readDashboard) {
  const dashboard = createServer(async (request, response) => {
    const port = request.socket.localPort;
    if (![`127.0.0.1:${port}`, `localhost:${port}`].includes(request.headers.host)) {
      response.writeHead(403).end();
      return;
    }
    if (request.method !== 'GET' || request.url !== '/api/dashboard') {
      response.writeHead(404).end();
      return;
    }
    try {
      const [usage, history] = await Promise.all([read('/api/usage'), read('/api/sessions')]);
      const { today, all } = usage.totals;
      const sessions = history.sessions.filter(row => row.source === 'dsh' && row.archived !== true)
        .map(({ id, source, title, project, projectKey, cwd, startedAt, endedAt }) =>
          ({ id, source, title, project, projectKey, cwd, startedAt, endedAt }));
      response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify({ usage: { daily: usage.daily, totals: { today, all } }, sessions }));
    } catch {
      response.writeHead(503, { 'Cache-Control': 'no-store' }).end();
    }
  });
  return dashboard;
}

function serveDashboard(ctx, port) {
  const dashboard = createDashboardServer();
  dashboard.on('error', error => ctx.logger(name).warn('Dashboard listener: %s', error.message));
  dashboard.listen(port, '127.0.0.1');
  ctx.effect(() => () => new Promise(resolve => dashboard.close(resolve)), 'agent-phone read-only dashboard');
}

export async function apply(ctx, config = {}) {
  const root = config.directory || path.join(os.homedir(), '.config/agent-phone/control');
  const socket = path.join(root, 'dsh-desktop.sock');
  await fs.mkdir(root, { recursive:true, mode:0o700 });
  // Refuse to steal a live bridge; only remove a verified stale socket.
  try {
    const stat = await fs.lstat(socket);
    if (!stat.isSocket()) throw new Error('desktop bridge path is not a socket');
    const live = await new Promise(resolve=>{
      const probe = net.createConnection(socket);
      probe.once('connect',()=>{probe.destroy();resolve(true);});
      probe.once('error',e=>resolve(e.code !== 'ECONNREFUSED' && e.code !== 'ENOENT'));
      probe.setTimeout(1000,()=>{probe.destroy();resolve(true);});
    });
    if(live) throw new Error('desktop bridge is already running');
    await fs.unlink(socket);
  } catch(e) { if(e.code !== 'ENOENT') throw e; }
  const registry = ctx.workspaceRegistry;
  const snapshot = () => ({ready:true, archived:[...registry.archivedSessionIds],
    workspaces:registry.list().map(w=>({id:w.id,title:w.title,path:w.path,sessionIds:[...w.sessionIds]}))});
  const server = net.createServer(client=>{
    client.setEncoding('utf8'); client.setTimeout(5000,()=>client.destroy());
    let buffer = '', done=false;
    client.on('data', async chunk=>{
      if(done)return;
      buffer+=chunk;
      if(Buffer.byteLength(buffer)>8192){done=true;client.destroy();return;}
      if(!buffer.includes('\n'))return;
      done=true;
      try {
        const request=JSON.parse(buffer.split('\n')[0]);
        if(request.method==='status'){client.end(JSON.stringify(snapshot())+'\n');return;}
        const sid=request.session;
        if(typeof sid!=='string'||! /^(?:session-)?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(sid))throw new Error('invalid session');
        if(request.method==='archive')await registry.archiveSession(sid);
        else if(request.method==='restore')await registry.unarchiveSession(sid);
        else if(request.method==='attach') {
          const snapshots=await ctx.sessionPersistence.list();
          const header=snapshots.find(x=>x.header.id===sid)?.header;
          if(!header||header.origin==='subagent'||header.parentSession||header.parentSessionId||header.delegationDepth)throw new Error('not a persisted main session');
          const workspace=await registry.resolveByPath(header.cwd);
          // Only attach to an existing workspace. Never create unexpected projects.
          if(workspace)await workspace.attachSession(sid);
        } else throw new Error('unsupported method');
        client.end(JSON.stringify(snapshot())+'\n');
      } catch(error) {client.end(JSON.stringify({ready:true,error:String(error.message||error)})+'\n');}
    });
    client.on('error',()=>{});
  });
  await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(socket,resolve);});
  await fs.chmod(socket,0o600);
  ctx.effect(() => () => new Promise(resolve => server.close(resolve)), 'agent-phone desktop bridge');
  serveDashboard(ctx, config.dashboardPort ?? 5174);
}
