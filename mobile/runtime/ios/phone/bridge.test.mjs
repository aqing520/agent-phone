import assert from 'node:assert/strict';
import { randomBytes, randomUUID } from 'node:crypto';
import test from 'node:test';
import { createPhoneBridge } from './bridge.mjs';
async function fixture(t, timeoutMs = 2000) {
  const token = randomBytes(32).toString('hex'), runId = randomUUID();
  const bridge = await createPhoneBridge({ token, runId, timeoutMs, systemAction: (name, args) => ({ kind: `system-${name}`, text: args.set }) });
  t.after(() => bridge.close());
  const post = async (route, body = {}, headers = {}) => {
    const response = await fetch(bridge.endpoint.baseUrl + route, {
      method: 'POST', headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json', ...headers },
      body: JSON.stringify({ runId, ...body }),
    });
    return { status: response.status, body: await response.json() };
  };
  const controller = new AbortController();
  const execution = { signal: controller.signal, callId: 'call-1', agent: { session: { id: 'session-1' } } };
  return { bridge, post, controller, execution };
}
test('no successful completion before live begin; begin only once; final result settles tool', async t => {
  const { bridge, post, execution } = await fixture(t);
  const waiting = bridge.call('system:clipboard', { set: '中文' }, execution);
  const { request } = (await post('/claim')).body;
  assert.equal(request.action.text, '中文');
  assert.equal((await post('/result', { id: request.id, text: 'fake', isError: false })).status, 409);
  assert.equal((await post('/begin', { id: request.id })).status, 200);
  assert.equal((await post('/begin', { id: request.id })).status, 409);
  assert.equal((await post('/result', { id: request.id, text: 'written', isError: false })).status, 200);
  assert.equal((await waiting).content[0].text, 'written');
  assert.equal((await post('/begin', { id: request.id })).status, 410);
});
test('cancel while native prompt waits retires exact request, including a later real tap', async t => {
  const { bridge, post, controller, execution } = await fixture(t);
  const waiting = bridge.call('system:open', { url: 'https://example.com' }, execution);
  const { request } = (await post('/claim')).body;
  controller.abort();
  assert.match((await waiting).content[0].text, /CANCELLED/);
  assert.equal((await post('/begin', { id: request.id })).status, 410);
  const next = bridge.call('system:open', { url: 'https://example.org' }, { ...execution, signal: new AbortController().signal });
  const fresh = (await post('/claim')).body.request;
  assert.notEqual(fresh.id, request.id);
  assert.equal((await post('/begin', { id: request.id })).status, 410);
  await post('/result', { id: fresh.id, text: '用户拒绝', isError: true });
  assert.equal((await next).isError, true);
});
test('notification has no approve endpoint and no action is begun by claiming', async t => {
  const { bridge, post, execution } = await fixture(t);
  const waiting = bridge.call('system:notify', { title: 'notice', text: 'body' }, execution);
  const { request } = (await post('/claim')).body;
  assert.equal((await post('/approve', { id: request.id })).status, 404);
  assert.equal((await post('/status', { id: request.id })).body.state, 'claimed');
  await post('/result', { id: request.id, text: '用户拒绝', isError: true });
  await waiting;
});
test('wrong token, browser Origin and prior run identifiers are rejected', async t => {
  const { post } = await fixture(t);
  assert.equal((await post('/claim', {}, { authorization: 'Bearer wrong' })).status, 403);
  assert.equal((await post('/claim', {}, { origin: 'http://example.com' })).status, 403);
  assert.equal((await post('/claim', { runId: 'previous' })).status, 410);
});
test('only one native request is leased at a time and declining releases the next', async t => {
  const { bridge, post, execution } = await fixture(t);
  const a = bridge.call('system:clipboard', { get: true }, execution);
  const b = bridge.call('system:clipboard', { set: 'next' }, { ...execution, callId: 'call-2' });
  const first = (await post('/claim')).body.request;
  assert.equal((await post('/claim')).body.request, null);
  await post('/result', { id: first.id, text: 'no', isError: true }); await a;
  const second = (await post('/claim')).body.request;
  assert.equal(second.owner.callId, 'call-2');
  await post('/result', { id: second.id, text: 'no', isError: true }); await b;
});
test('timeout after begin reports unknown; no automatic replay', async t => {
  const { bridge, post, execution } = await fixture(t, 100);
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const waiting = bridge.call('system:clipboard', { set: 'one' }, execution);
  const { request } = (await post('/claim')).body;
  assert.equal((await post('/begin', { id: request.id })).status, 200);
  t.mock.timers.tick(100);
  assert.match((await waiting).content[0].text, /结果未知/);
  assert.equal((await post('/claim')).body.request, null);
});
test('owner must follow rc.4 Agent.session.id; exact payload is snapshotted and close retires it', async t => {
  const { bridge, post, execution } = await fixture(t);
  const rejected = await bridge.call('system:clipboard', { set: 'x' }, { ...execution, agent: { sessionId: 'obsolete-shape' } });
  assert.equal(rejected.isError, true);
  assert.equal((await post('/claim')).body.request, null);
  const args = { set: 'approved text' };
  const waiting = bridge.call('system:clipboard', args, execution);
  args.set = 'changed after dispatch';
  const { request } = (await post('/claim')).body;
  assert.equal(request.action.text, 'approved text');
  assert.equal(request.owner.sessionId, execution.agent.session.id);
  await bridge.close();
  assert.match((await waiting).content[0].text, /RETIRED/);
});
