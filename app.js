/* =========================================================
   工作台 · 多智能体控制台（前端原型 / mock 数据）
   ========================================================= */

/* ---------- 品牌图标 ---------- */
const LOGO = {
  antigravity: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <defs><linearGradient id="agGrad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#5B7CFA"/><stop offset="1" stop-color="#2B3C9E"/>
      </linearGradient></defs>
      <path d="M12 3.4 21 20.2h-3.6L12 9.6 6.6 20.2H3z" fill="url(#agGrad)"/>
      <path d="M12 13.4l3.4 6.8H8.6z" fill="#8FA5FF" opacity=".85"/>
    </svg>`,
  workbuddy: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="2.5" y="2.5" width="19" height="19" rx="6" fill="#2FBF71"/>
      <path d="M12 6.6c.5 3 2.2 4.7 5.2 5.2-3 .5-4.7 2.2-5.2 5.2-.5-3-2.2-4.7-5.2-5.2 3-.5 4.7-2.2 5.2-5.2z" fill="#fff"/>
    </svg>`,
  claude: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <g stroke="#D97757" stroke-width="1.9" stroke-linecap="round">
        <path d="M12 3.6v16.8M5 7.2l14 9.6M19 7.2 5 16.8M12 3.6v3M12 17.4v3"/>
      </g>
      <circle cx="12" cy="12" r="2.1" fill="#D97757"/>
    </svg>`,
  chatgpt: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <g fill="none" stroke="#3C3C46" stroke-width="1.7" stroke-linejoin="round">
        <path d="M12 3.6 19 7.8v8.4L12 20.4 5 16.2V7.8z"/>
        <path d="M12 8.2 15.9 10.5v4.6L12 17.4 8.1 15.1v-4.6z"/>
      </g>
    </svg>`,
  glm: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="2.5" y="2.5" width="19" height="19" rx="6" fill="#3B62F6"/>
      <path d="M8 7.8h8L8 16.2h8" fill="none" stroke="#fff" stroke-width="1.9"
            stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,
  codex: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="2.5" y="2.5" width="19" height="19" rx="6" fill="#1F1F23"/>
      <path d="M9.4 7.8 6.5 12l2.9 4.2M14.6 7.8 17.5 12l-2.9 4.2"
            fill="none" stroke="#fff" stroke-width="1.8"
            stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`,
  deepseek: `<svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3.2 9.6c2.6-2.4 5-2.2 6.6-.4 1.2 1.3 1.8 2.9 3.4 3.5 1.7.6 3.6-.2 4.4-1.8.4-.8.5-1.7.3-2.5-.9.9-2 .8-2.6.2-.6-.6-.3-1.6.5-2 .9-.5 2.2-.3 3 .5 1.4 1.4 1.6 3.9.4 5.6-1.5 2.1-4.3 2.8-6.5 1.6-1.5-.8-2.2-2.3-3.3-3.4-1-1-2.3-1.3-3.6-.7-.5.2-.9.6-1.2 1l-1.4-1.6z" fill="#4D6BFE"/>
      <path d="M8.4 15.6c.9 1.1 2.3 1.7 3.7 1.9l-.5 1.7c-1.9-.3-3.6-1.2-4.8-2.6z" fill="#4D6BFE" opacity=".7"/>
      <circle cx="16.9" cy="9.9" r=".8" fill="#fff"/>
    </svg>`,
};

const ICON = {
  chat: `<svg class="ic" viewBox="0 0 24 24"><path d="M20 12.5c0 4-3.4 6.6-8 6.6-1 0-2-.1-2.9-.4L5 20.4l1-3.2c-1.3-1.2-2-2.9-2-4.7 0-4 3.4-6.6 8-6.6s8 2.6 8 6.6z"/></svg>`,
};

/* ---------- 智能体列表 ---------- */
// kind: client = 本机客户端（有自己的会话日志）；model = 经客户端路由、没有独立日志的模型
// source: 对应网关的数据源，决定从哪里读会话
// optional: 默认不显示的客户端，可在设置里打开
// note: 卡片上的一句话说明（只在未接入时展示）
const agents = [
  { id:'workbuddy',   name:'WorkBuddy',   kind:'client', source:'workbuddy', state:'待命', token:'—', rounds:'—', zero:true },
  { id:'codex',       name:'Codex',       kind:'client', source:'codex',     state:'待命', token:'—', rounds:'—', zero:true },
  { id:'deepseek',    name:'DeepSeek',    kind:'client', source:'dsh',       state:'待命', token:'—', rounds:'—', zero:true },
  { id:'antigravity', name:'Antigravity', kind:'client', source:null, optional:true, state:'未接入', token:'—', rounds:'—', zero:true,
    note:'没找到它的日志目录，用过后会自动出现' },
  { id:'claude',      name:'Claude',      kind:'client', source:null, optional:true, state:'未接入', token:'—', rounds:'—', zero:true,
    note:'桌面版不落本地用量日志' },
  { id:'chatgpt',     name:'ChatGPT',     kind:'client', source:null, optional:true, state:'未接入', token:'—', rounds:'—', zero:true,
    note:'纯聊天，本地没有用量日志' },
];

/* ---------- 展示偏好（localStorage） ---------- */
const HIDE_KEY = 'wg.hiddenAgents';
const hidden = (()=>{
  try{
    const raw = localStorage.getItem(HIDE_KEY);
    if(raw) return new Set(JSON.parse(raw));
  }catch(e){ /* 读不到就用默认 */ }
  // 首次打开：只展示真正在本机跑过的客户端
  return new Set(agents.filter(a=>a.optional).map(a=>a.id));
})();

function saveHidden(){
  try{ localStorage.setItem(HIDE_KEY, JSON.stringify([...hidden])); }catch(e){}
}
function isShown(a){ return !hidden.has(a.id); }
function visibleAgents(){
  return agents.map((a,i)=>({ a, i })).filter(x=> isShown(x.a));
}

const sessions = {
  // 只作为真实会话的容器；没有网关时不编造任何内容
  workbuddy: { title: 'WorkBuddy', messages: [] },
  codex:     { title: 'Codex', messages: [] },
  dsh:       { title: 'DeepSeek Harness', messages: [] },
};

/* ---------- 工具 ---------- */
const $ = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];

function seeded(seed){
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}

function toast(msg){
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('is-on');
  clearTimeout(toast._t);
  toast._t = setTimeout(()=> t.classList.remove('is-on'), 1600);
}

/* ---------- 极简 Markdown ---------- */
function esc(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function inline(s){
  return esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s（(])(["“])([^"”]{2,})(["”])/g, '$1<strong>$3</strong>');
}
function md(src){
  const lines = src.split('\n');
  let out = '', para = [], list = null, code = null, codeBuf = [];

  const flushPara = () => { if(para.length){ out += `<p>${inline(para.join(' '))}</p>`; para = []; } };
  const flushList = () => { if(list){ out += `<ul>${list.join('')}</ul>`; list = null; } };

  for(let li = 0; li < lines.length; li++){
    const raw = lines[li];
    const line = raw.replace(/\s+$/,'');

    if(code !== null){
      if(/^```/.test(line)){ out += `<pre><code>${esc(codeBuf.join('\n'))}</code></pre>`; code = null; codeBuf = []; }
      else codeBuf.push(line);
      continue;
    }
    if(/^```/.test(line)){ flushPara(); flushList(); code = ''; continue; }

    if(!line.trim()){ flushPara(); flushList(); continue; }

    // 表格：当前行是 | a | b |，下一行是 |---|---|
    if(/^\s*\|.*\|\s*$/.test(line) && li + 1 < lines.length
       && /^\s*\|[\s:|-]+\|\s*$/.test(lines[li + 1])){
      flushPara(); flushList();
      const cells = l => l.trim().replace(/^\||\|$/g, '').split('|').map(c=> c.trim());
      const head = cells(line);
      li++;  // 跳过分隔行
      const rows = [];
      while(li + 1 < lines.length && /^\s*\|.*\|\s*$/.test(lines[li + 1])){
        li++;
        rows.push(cells(lines[li]));
      }
      out += `<div class="md-table"><table><thead><tr>`
        + head.map(c=>`<th>${inline(c)}</th>`).join('')
        + `</tr></thead><tbody>`
        + rows.map(r=>`<tr>${r.map(c=>`<td>${inline(c)}</td>`).join('')}</tr>`).join('')
        + `</tbody></table></div>`;
      continue;
    }

    if(/^#{1,6}\s/.test(line)){
      flushPara(); flushList();
      out += `<h4>${inline(line.replace(/^#{1,6}\s/,''))}</h4>`;
      continue;
    }
    if(/^\s*[-*]\s+/.test(line)){
      flushPara();
      list = list || [];
      list.push(`<li>${inline(line.replace(/^\s*[-*]\s+/,''))}</li>`);
      continue;
    }
    if(/^\s*\d+\.\s+/.test(line)){
      flushPara();
      list = list || [];
      list.push(`<li>${inline(line.replace(/^\s*\d+\.\s+/,''))}</li>`);
      continue;
    }
    flushList();
    para.push(line.trim());
  }
  flushPara(); flushList();
  if(codeBuf.length) out += `<pre><code>${esc(codeBuf.join('\n'))}</code></pre>`;
  return out;
}

/* ---------- 热力图（真实 / mock 共用） ---------- */
function pad2(n){ return n<10 ? '0'+n : ''+n; }
function dateKey(d){ return d.getFullYear()+'-'+pad2(d.getMonth()+1)+'-'+pad2(d.getDate()); }

function buildHeatmap(daily){
  // daily: {'YYYY-MM-DD': tokens}；不传则退回 mock 分布
  const WEEKS = 21, DAYS = 7;
  const wrap = $('#heatmap');
  wrap.innerHTML = '';
  const today = new Date();
  const total = WEEKS * DAYS;

  let max = 0;
  if(daily) for(const k in daily) max = Math.max(max, daily[k]);

  const rnd = seeded(20261103);
  for(let i=0; i<total; i++){
    const d = new Date(today);
    d.setDate(today.getDate() - (total - 1 - i));
    const key = dateKey(d);
    let level = 0, label = '无记录';
    if(daily){
      const v = daily[key] || 0;
      if(v > 0 && max > 0){
        const r = v / max;
        level = r > 0.66 ? 4 : r > 0.33 ? 3 : r > 0.12 ? 2 : 1;
      }
      label = v ? fmtTok(v) : '无消耗';
    } else {
      // mock：越靠右越活跃
      const recency = Math.pow((i/(total-1)), 2.1);
      const p = rnd() * (0.22 + recency * 1.25);
      level = p > 1.02 ? 4 : p > 0.82 ? 3 : p > 0.62 ? 2 : p > 0.42 ? 1 : 0;
      label = level ? ((level ** 1.7) * (2 + rnd()*9) * 10).toFixed(1) + 'M' : '无消耗';
    }

    const cell = document.createElement('div');
    cell.className = 'hm-cell' + (level ? ' l'+level : '') + (level === 4 ? ' is-hot' : '');
    cell.dataset.tip = `${key.slice(5)} · ${label}`;
    cell.addEventListener('click', ()=> toast(cell.dataset.tip));
    wrap.appendChild(cell);
  }
}

/* ---------- 真实用量接入 ---------- */
const state = {
  realSessions: [],      // /api/sessions（三个来源合并）
  realSessionId: null,   // 当前展示的真实会话
  realSessionSource: null, // workbuddy / codex / dsh
  latestTitle: null,
  pollTimer: null,       // 当前会话的自动刷新定时器
  rendered: null,        // { id, count } 已渲染到的位置
};

function fmtTok(n){
  if(n >= 1e9) return (n/1e9).toFixed(2)+'G';
  if(n >= 1e6) return (n/1e6).toFixed(2)+'M';
  if(n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return String(n|0);
}

function setStat(key, val){
  const el = $(`[data-stat="${key}"]`);
  if(el) el.textContent = val;
}

async function fetchUsage(){
  try{
    const r = await fetch('/api/usage', { cache: 'no-store' });
    if(!r.ok) throw new Error(r.status);
    return await r.json();
  }catch(e){
    return null;
  }
}

function applyUsage(u){
  if(!u) return false;

  setStat('today', fmtTok(u.totals.today));
  setStat('total', fmtTok(u.totals.all));
  setStat('cache', u.totals.cacheHit.toFixed(1)+'%');
  setStat('rounds', String(u.totals.rounds));

  buildHeatmap(u.daily);

  const map = u.agents || { workbuddy: u.agent };

  // 路由模型（如 GLM）没有独立客户端，统一并到 WorkBuddy 名下，不单独占卡片
  const wb = map.workbuddy;
  const routed = Object.keys(map)
    .filter(k=> k !== 'workbuddy' && (map[k].via || k === 'glm'))
    .map(k=>({ name: map[k].name || (k === 'glm' ? 'GLM' : k.toUpperCase()), tokens: map[k].tokens || 0 }));
  if(wb) wb.routes = routed;

  agents.forEach(a=>{
    const info = map[a.id];
    if(info && (info.tokens || info.rounds)){
      a.token = fmtTok(info.tokens);
      a.rounds = info.rounds;
      a.zero = !info.tokens;
      a.via = info.via || null;
      a.models = info.models || [];
      a.routes = info.routes || null;
      a.state = info.via ? '运行中' : (info.running ? '运行中' : '待命');
    }else{
      a.token = '—';
      a.rounds = '—';
      a.zero = true;
      a.via = null;
      a.models = [];
      a.routes = null;
      a.state = a.kind === 'model' ? '未发现' : '未接入';
    }
  });
  // WorkBuddy 会话标题：只看最新一条；正在看历史会话时保持不动
  if(u.agent && u.agent.lastTitle){
    state.latestTitle = u.agent.lastTitle;
    const viewingLatest = !state.realSessionId
      || (state.realSessions[0] && state.realSessionId === state.realSessions[0].id);
    if(viewingLatest){
      sessions.workbuddy.title = u.agent.lastTitle;
      if(agents[current] && agents[current].id === 'workbuddy'
         && $('#viewChat').classList.contains('is-active')){
        $('#sessionTitle').textContent = sessions.workbuddy.title;
      }
    }
  }
  renderAgents();
  // 正停在模型卡片页时，用量到达后补渲染（模型卡片没有独立会话）
  const cur = agents[current];
  if(cur && cur.id !== 'workbuddy' && $('#viewChat').classList.contains('is-active')){
    renderSession();
  }
  return true;
}

let usageReady = false;
async function syncUsage(silent){
  const u = await fetchUsage();
  if(u){
    const first = !usageReady;
    usageReady = true;
    applyUsage(u);
    if(!silent && !first) toast('已同步本机用量');
    if(first && !silent) toast('已接入 WorkBuddy 真实用量');
  } else if(!silent){
    toast('网关未连接，当前为演示数据');
  }
  return !!u;
}

/* ---------- 真实会话：列表 + 正文 ---------- */
function relTime(ms){
  if(!ms) return '';
  const diff = Date.now() - ms;
  if(diff < 60e3) return '刚刚';
  if(diff < 3600e3) return Math.floor(diff/60e3)+' 分钟前';
  if(diff < 86400e3) return Math.floor(diff/3600e3)+' 小时前';
  if(diff < 7*86400e3) return Math.floor(diff/86400e3)+' 天前';
  const d = new Date(ms);
  return (d.getMonth()+1)+'/'+d.getDate();
}

async function loadSessions(){
  try{
    const r = await fetch('/api/sessions', { cache:'no-store' });
    if(!r.ok) return false;
    const d = await r.json();
    state.realSessions = d.sessions || [];
    return true;
  }catch(e){
    return false;
  }
}

const SRC_LABEL = { workbuddy: 'WorkBuddy', codex: 'Codex', dsh: 'DeepSeek' };

function renderSessionList(){
  const list = $('#sessList');
  if(!state.realSessions.length){
    $('#sessMeta').textContent = '';
    list.innerHTML = `<div class="sess__empty">未连接到本机网关<br>暂无真实会话记录</div>`;
    return;
  }
  $('#sessMeta').textContent = state.realSessions.length + ' 条';
  // 当前智能体自己的会话排前面，其余来源跟在后面
  const src = (agents[current] || {}).source;
  const rows = src
    ? [...state.realSessions].sort((a, b)=> (b.source === src) - (a.source === src))
    : state.realSessions;
  list.innerHTML = rows.map(s=>`
    <button class="sess ${s.id === state.realSessionId ? 'is-active' : ''}"
            data-sid="${s.id}" data-src="${s.source || 'workbuddy'}">
      <div class="sess__title">${esc(s.title)}</div>
      <div class="sess__meta">
        <span class="sess__src sess__src--${s.source || 'workbuddy'}">${SRC_LABEL[s.source] || s.source || '—'}</span>
        <span class="sess__proj">${esc(s.project || '-')}</span>
        <span>${s.rounds} 轮</span>
        <span>${fmtTok(s.tokens)} tok</span>
        <span>${relTime(s.endedAt || s.startedAt)}</span>
      </div>
    </button>
  `).join('');

  $$('.sess', list).forEach(el=>{
    el.addEventListener('click', ()=>{
      $('#sessMask').classList.remove('is-open');
      loadRealSession(el.dataset.sid, el.dataset.src);
    });
  });
}

async function openSessSheet(){
  renderSessionList();
  $('#sessMask').classList.add('is-open');
  // 每次打开顺手刷新一次列表
  if(await loadSessions()){ renderSessionList(); renderProjects(); }
}

async function loadRealSession(id, source){
  if(!$('#viewChat').classList.contains('is-active')){
    $('#viewHome').classList.remove('is-active');
    $('#viewChat').classList.add('is-active');
  }
  const src = source || (state.realSessions.find(s=> s.id === id) || {}).source || 'workbuddy';
  state.realSessionId = id;
  state.realSessionSource = src;

  const idx = agents.findIndex(a=> a.source === src);
  if(idx >= 0 && idx !== current){ current = idx; renderChips(); }

  const box = $('#messages');
  $('#sessionTitle').textContent = '载入中…';
  box.classList.remove('is-empty');
  box.innerHTML = `<div class="sess-loading">正在读取本机会话记录…</div>`;

  try{
    const url = `/api/messages?session=${encodeURIComponent(id)}&source=${encodeURIComponent(src)}`;
    const r = await fetch(url, { cache:'no-store' });
    if(!r.ok) throw new Error('HTTP ' + r.status);
    const d = await r.json();
    const sess = d.session || state.realSessions.find(s=> s.id === id) || {};
    const slot = sessions[src] || (sessions[src] = { title:'', messages: [] });

    slot.title = d.title || sess.title || '未命名会话';
    slot.messages = (d.messages || []).map(m=>({
      role: m.role === 'user' ? 'me' : 'agent',
      text: m.text,
    }));

    if(!slot.messages.length){
      box.classList.add('is-empty');
      $('#sessionTitle').textContent = slot.title;
      box.innerHTML = `<div class="empty-state">
        <div class="empty-state__title">这段会话没有正文</div>
        日志里只有工具调用与用量记录，没有可展示的对话内容。
      </div>`;
      // 空态也挂上刷新：正文一出现自动补进来
      state.rendered = { id, count: 0 };
      startSessionPoll();
      return;
    }
    renderSession();
    startSessionPoll();
  }catch(e){
    box.innerHTML = `<div class="empty-state">
      <div class="empty-state__title">读取失败</div>${esc(String(e.message || e))}
    </div>`;
  }
}

/* ---------- 渲染：最近项目（按 project 聚合真实会话） ---------- */
const PROJ_MAX = 8;

function projectList(){
  const map = new Map();
  for(const s of state.realSessions){
    const key = (s.project || '').trim() || '未命名';
    let p = map.get(key);
    if(!p){
      p = { name:key, sessions:0, tokens:0, rounds:0, sources:new Set(), last:0, latest:null };
      map.set(key, p);
    }
    p.sessions++;
    p.tokens += s.tokens || 0;
    p.rounds += s.rounds || 0;
    if(s.source) p.sources.add(s.source);
    const t = s.endedAt || s.startedAt || 0;
    if(t >= p.last){ p.last = t; p.latest = s; }
  }
  return [...map.values()].sort((a,b)=> b.last - a.last).slice(0, PROJ_MAX);
}

function renderProjects(){
  const row = $('#projRow');
  if(!row) return;

  if(!state.realSessions.length){
    row.innerHTML = `<div class="proj-empty">还没有可读的会话记录<br>网关连上后，这里按项目归最近的活动</div>`;
    return;
  }

  row.innerHTML = projectList().map(p=>{
    const srcs = [...p.sources];
    const main = p.latest || {};
    return `
    <button class="proj" data-sid="${main.id || ''}" data-src="${main.source || ''}">
      <div class="proj__top">
        <span class="proj__logo">
          <svg viewBox="0 0 24 24"><path d="M3.5 7.3c0-1.1.9-2 2-2h3.2l2 2.4h7.8c1.1 0 2 .9 2 2v8c0 1.1-.9 2-2 2h-13c-1.1 0-2-.9-2-2z"/><path d="M3.5 11h17"/></svg>
        </span>
        <span class="proj__name" title="${esc(p.name)}">${esc(p.name)}</span>
      </div>
      <div class="proj__srcs">
        ${srcs.map(s=>`<span class="proj__src proj__src--${s}">${SRC_LABEL[s] || s}</span>`).join('')}
      </div>
      <div class="proj__stats">
        <span class="proj__tok">${p.tokens ? fmtTok(p.tokens) : '—'}</span>
        <span class="proj__unit">tok · ${p.rounds} 轮</span>
      </div>
      <div class="proj__foot">
        <span>${p.sessions} 个会话</span>
        <span class="proj__time">${relTime(p.last)}</span>
      </div>
    </button>`;
  }).join('');

  $$('.proj', row).forEach(el=>{
    el.addEventListener('click', ()=>{
      if(!el.dataset.sid) return;
      loadRealSession(el.dataset.sid, el.dataset.src);
    });
  });
}

/* ---------- 渲染：智能体看板 ---------- */
function renderAgents(){
  const grid = $('#agentGrid');
  const list = visibleAgents();

  grid.innerHTML = list.map(({a,i})=>`
    <button class="agent" data-agent="${i}">
      <div class="agent__top">
        <span class="agent__logo">${LOGO[a.id]}</span>
        <span class="agent__meta">
          <span class="agent__name">${a.name}</span>
          <span class="agent__state">
            <span class="dot ${a.state==='运行中' && !a.via ? 'dot--live':''}"></span>${a.via ? '经 ' + a.via : a.state}
          </span>
        </span>
        <span class="agent__msg">${ICON.chat}</span>
      </div>
      <div class="agent__stats">
        <span class="agent__stat">
          <span class="agent__label">消耗</span>
          <span class="agent__value ${a.zero?'agent__value--zero':''}">${a.token}</span>
        </span>
        <span class="agent__stat agent__stat--right">
          <span class="agent__label">轮次</span>
          <span class="agent__value ${a.rounds?'':'agent__value--zero'}">${a.rounds}</span>
        </span>
      </div>
      ${a.routes && a.routes.length
        ? `<div class="agent__route">含 ${a.routes.map(r=> `${r.name} ${fmtTok(r.tokens)}`).join(' · ')}</div>`
        : ''}
      ${(!a.source && a.note)
        ? `<div class="agent__note">${a.note}</div>`
        : ''}
    </button>
  `).join('');

  $$('.agent', grid).forEach(el=>{
    el.addEventListener('click', ()=> openChat(+el.dataset.agent));
  });

  $('#runningCount').textContent = list.filter(x=> x.a.state==='运行中' && !x.a.via).length;
  $('#totalCount').textContent = list.length;

  // 当前选中的智能体被隐藏了，退回第一个可见的
  if(!list.length) return false;
  if(!isShown(agents[current])){
    current = list[0].i;
    renderChips();
  }
  return true;
}

/* ---------- 设置：看板展示哪些客户端 ---------- */
const PICK_DESC = {
  workbuddy:   '本机客户端 · 含 GLM 等路由模型',
  codex:       '本机客户端 · 读 JSONL 会话',
  deepseek:    'DeepSeek Harness · 读事件流',
  antigravity: '本机客户端 · 未找到日志目录',
  claude:      '桌面版 · 不落本地用量',
  chatgpt:     '纯聊天 · 只有网页账单',
};

function renderPicker(){
  const box = $('#agentPicker');
  if(!box) return;

  box.innerHTML = agents.map(a=>`
    <button class="pick ${isShown(a) ? 'is-on' : ''}" data-pick="${a.id}">
      <span class="pick__logo">${LOGO[a.id]}</span>
      <span class="pick__text">
        <span class="pick__name">${a.name}</span>
        <span class="pick__desc">${PICK_DESC[a.id] || ''}</span>
      </span>
      <span class="switch ${isShown(a) ? 'is-on' : ''}"></span>
    </button>
  `).join('');

  $$('.pick', box).forEach(el=>{
    el.addEventListener('click', ()=>{
      const id = el.dataset.pick;
      const hiding = !hidden.has(id);
      const watching = agents[current] && agents[current].id === id
        && $('#viewChat').classList.contains('is-active');

      if(hiding){
        if(hidden.size >= agents.length - 1){ toast('至少留一个在看板上'); return; }
        hidden.add(id);
      }else{
        hidden.delete(id);
      }
      saveHidden();
      renderPicker();
      renderAgents();
      renderChips();
      // 正在看的那个被关掉了，回工作台，别停在它上面
      if(hiding && watching) goHome();
      const nm = (agents.find(a=>a.id===id) || {}).name || id;
      toast(hiding ? `${nm} 已从看板移除` : `${nm} 已加回看板`);
    });
  });
}

/* ---------- 会话 ---------- */
let current = 0;
let lastMsgRole = null;   // 渲染游标：连续同角色消息合并头像用

function renderChips(){
  $('#chipScroll').innerHTML = visibleAgents().map(({a,i})=>`
    <button class="chip chip--agent ${i===current?'is-active':''}" data-chip="${i}" aria-label="${a.name}">
      ${LOGO[a.id]}
    </button>
  `).join('');
  $$('.chip--agent').forEach(el=>{
    el.addEventListener('click', ()=> switchAgent(+el.dataset.chip));
    el.addEventListener('dblclick', ()=> toast(agents[+el.dataset.chip].name));
  });
}

function renderSession(){
  const a = agents[current];
  const box = $('#messages');
  box.innerHTML = '';
  box.classList.remove('is-empty');

  // 模型卡：讲清归属；没有数据源的客户端：如实说没日志
  if(!a.source){
    stopSessionPoll();
    state.rendered = null;
    box.classList.add('is-empty');

    if(a.kind === 'model' && (a.via || a.token !== '—')){
      $('#sessionTitle').textContent = a.name + ' · 模型';
      box.innerHTML = `<div class="empty-state">
        <div class="empty-state__title">${a.name} 经 ${a.via || 'WorkBuddy'} 调用</div>
        ${a.models && a.models.length ? esc(a.models.join('、')) + '<br>' : ''}
        共 ${a.rounds} 次调用 · ${a.token} tokens<br>
        模型本身没有独立会话记录，对话都在 ${a.via || 'WorkBuddy'} 的会话里。
      </div>`;
      return;
    }

    $('#sessionTitle').textContent = a.name + ' · 未接入';
    box.innerHTML = `<div class="empty-state">
      <div class="empty-state__title">${a.name} 未接入</div>
      ${a.note ? esc(a.note) + '<br>' : ''}
      本机没有可读的调用记录。<br>
      有本地日志的客户端，装上并聊过一次后这里会自动出现真实数据。
    </div>`;
    return;
  }

  const s = sessions[a.source] || { title: a.name, messages: [] };
  if(!s.messages.length){
    box.classList.add('is-empty');
    $('#sessionTitle').textContent = state.realSessions.length ? (s.title || a.name) : '未连接网关';
    box.innerHTML = `<div class="empty-state">
      <div class="empty-state__title">${state.realSessions.length ? '没有可展示的正文' : '未连接本机网关'}</div>
      ${state.realSessions.length
        ? '这段会话只有工具调用与用量记录，没有对话正文。'
        : '启动 server.py 后即可读取本机真实用量与会话记录。'}
    </div>`;
    // 空态也挂上刷新：一旦日志里出现了正文会自动补进来
    state.rendered = state.realSessionId ? { id: state.realSessionId, count: 0 } : null;
    return;
  }

  $('#sessionTitle').textContent = s.title;
  lastMsgRole = null;
  s.messages.forEach(m=>{
    const showWho = !(m.role !== 'me' && lastMsgRole === 'agent');
    addMsg(m.role, m.text, a, false, showWho);
    lastMsgRole = m.role === 'me' ? 'me' : 'agent';
  });
  box.scrollTop = box.scrollHeight;
  state.rendered = { id: state.realSessionId, count: s.messages.length };
  // 让激活的 chip 滚到可视区
  const chip = $(`.chip--agent[data-chip="${current}"]`);
  if(chip) chip.scrollIntoView({ inline:'center', block:'nearest', behavior:'smooth' });
}

const MSG_LIMIT = 1400;   // 单条超过这个字数先折叠

function addMsg(role, text, agent, isNew=true, showWho=true){
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + (role === 'me' ? 'msg--me' : 'msg--agent')
    + (isNew ? '' : ' msg--static') + (showWho ? '' : ' msg--cont');

  const long = text && text.length > MSG_LIMIT;

  if(role === 'me'){
    wrap.innerHTML = `<div class="bubble">${esc(long ? text.slice(0, MSG_LIMIT) + '…' : text)}</div>`;
  } else {
    wrap.innerHTML = `
      ${showWho ? `<div class="who">
        <span class="agent__logo">${LOGO[agent.id]}</span>${agent.name}
      </div>` : ''}
      <div class="body">${text ? md(long ? text.slice(0, MSG_LIMIT) : text) : ''}</div>
    `;
  }

  if(long){
    const btn = document.createElement('button');
    btn.className = 'expand-btn';
    btn.textContent = `展开全文（${text.length} 字）`;
    btn.addEventListener('click', ()=>{
      if(role === 'me'){
        wrap.querySelector('.bubble').textContent = text;
      }else{
        wrap.querySelector('.body').innerHTML = md(text);
      }
      btn.remove();
    });
    (role === 'me' ? wrap : wrap.querySelector('.body')).appendChild(btn);
  }

  $('#messages').appendChild(wrap);
  if(isNew) scrollBottom();
  return wrap;
}

function scrollBottom(smooth=false){
  const box = $('#messages');
  box.scrollTo({ top: box.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
}

/* ---------- 当前会话自动刷新：轮询 + 增量追加 ---------- */
const SESSION_POLL_MS = 4000;

function startSessionPoll(){
  stopSessionPoll();
  state.pollTimer = setInterval(pollSession, SESSION_POLL_MS);
}
function stopSessionPoll(){
  if(state.pollTimer){ clearInterval(state.pollTimer); state.pollTimer = null; }
}

function nearBottom(box){
  return box.scrollHeight - box.scrollTop - box.clientHeight < 160;
}

function appendMessages(list, agent){
  const box = $('#messages');
  list.forEach(m=>{
    const showWho = !(m.role !== 'me' && lastMsgRole === 'agent');
    addMsg(m.role, m.text, agent, false, showWho);
    lastMsgRole = m.role === 'me' ? 'me' : 'agent';
  });
  if(nearBottom(box)) scrollBottom(true);
}

// 最后一条还在生成、内容原地变长：只替换末节点，不整屏重画
function replaceLastMessage(m, agent){
  const box = $('#messages');
  const nodes = box.querySelectorAll('.msg');
  if(nodes.length) nodes[nodes.length-1].remove();
  const prev = state.rendered && state.rendered.count >= 2
    ? (sessions[state.realSessionSource] || {}).messages[state.rendered.count - 2]
    : null;
  lastMsgRole = prev ? (prev.role === 'me' ? 'me' : 'agent') : null;
  const showWho = !(m.role !== 'me' && lastMsgRole === 'agent');
  addMsg(m.role, m.text, agent, false, showWho);
  if(nearBottom(box)) scrollBottom(true);
}

async function pollSession(){
  if(document.hidden) return;
  if(!$('#viewChat').classList.contains('is-active') || !state.realSessionId) return;
  const id = state.realSessionId, src = state.realSessionSource;
  if(!state.rendered || state.rendered.id !== id) return;

  try{
    const url = `/api/messages?session=${encodeURIComponent(id)}&source=${encodeURIComponent(src)}`;
    const r = await fetch(url, { cache:'no-store' });
    if(!r.ok) return;
    const d = await r.json();
    if(state.realSessionId !== id) return;   // 期间切走了

    const msgs = (d.messages || []).map(m=>({
      role: m.role === 'user' ? 'me' : 'agent',
      text: m.text,
    }));
    const slot = sessions[src];
    if(!slot) return;

    const agent = agents.find(a=> a.source === src) || agents[current];
    const rendered = state.rendered;

    if(msgs.length === rendered.count){
      // 数量没变，但最后一条内容变了 = 还在流式生成
      const oldLast = slot.messages[rendered.count - 1];
      const newLast = msgs[msgs.length - 1];
      if(oldLast && newLast && oldLast.text !== newLast.text
         && !$('#messages').classList.contains('is-empty')){
        slot.messages = msgs;
        replaceLastMessage(newLast, agent);
      }
      return;
    }

    if(msgs.length > rendered.count){
      // 前缀没变：只追加新增部分，避免整屏闪烁
      let same = true;
      for(let i = 0; i < rendered.count; i++){
        const o = slot.messages[i], n = msgs[i];
        if(!o || o.text !== n.text || o.role !== n.role){ same = false; break; }
      }
      if(same){
        slot.messages = msgs;
        if(rendered.count === 0 && !slot.messages.length){ return; }
        if($('#messages').classList.contains('is-empty')){
          // 之前是“没有正文”的空态，现在有了，整体画一遍
          renderSession();
          return;
        }
        appendMessages(msgs.slice(rendered.count), agent);
        rendered.count = msgs.length;
        return;
      }
    }

    // 结构变了（重试/编辑/截断）：整体重画
    slot.messages = msgs;
    renderSession();
  }catch(e){ /* 网关暂时不可达，下轮再试 */ }
}

// 打开某个智能体：优先载入它自己最近的一条真实会话
async function openAgentConversation(a){
  if(!a.source) return false;
  if(!state.realSessions.length) await loadSessions();
  const list = state.realSessions.filter(s=> s.source === a.source);
  if(!list.length) return false;
  const keep = state.realSessionId && state.realSessionSource === a.source
    && list.some(s=> s.id === state.realSessionId);
  loadRealSession(keep ? state.realSessionId : list[0].id, a.source);
  return true;
}

async function openChat(index){
  current = index;
  renderChips();
  $('#viewHome').classList.remove('is-active');
  $('#viewChat').classList.add('is-active');

  const a = agents[index];
  if(await openAgentConversation(a)) return;
  renderSession();
}

function goHome(){
  stopSessionPoll();
  $('#viewChat').classList.remove('is-active');
  $('#viewHome').classList.add('is-active');
}

function switchAgent(i){
  if(i === current) return;
  current = i;
  renderChips();

  const a = agents[i];
  openAgentConversation(a).then(ok=>{ if(!ok) renderSession(); });
  toast(`已切换到 ${a.name}`);
}

/* ---------- 发送 ---------- */
function send(){
  const input = $('#input');
  const text = input.value.trim();
  if(!text) return;

  const a = agents[current];
  if(a.id !== 'workbuddy'){
    toast(`${a.name} 未接入，无法发送`);
    return;
  }
  toast('发送通道尚未接入网关，消息未送达');
}

function updateSendState(){
  const ready = $('#input').value.trim().length > 0;
  $('#btnSend').classList.toggle('is-ready', ready);
}

/* ---------- 统计刷新 ---------- */
function refreshStats(){
  const btn = $('#btnRefresh');
  btn.classList.add('is-spinning');
  setTimeout(()=> btn.classList.remove('is-spinning'), 600);

  const values = {
    today: '395.33M', total: '28.47G', cache: '85.1%', rounds: '8732',
  };
  // 无网关时做本地假刷新动画
  if(!usageReady){
    values.today = (380 + Math.random()*30).toFixed(2)+'M';
    values.total = (28.2 + Math.random()*0.5).toFixed(2)+'G';
    values.cache = (83 + Math.random()*4).toFixed(1)+'%';
    values.rounds = String(8700 + Math.floor(Math.random()*80));
    Object.entries(values).forEach(([k,v])=>{
      const el = $(`[data-stat="${k}"]`);
      el.style.transition = 'opacity .18s';
      el.style.opacity = '0';
      setTimeout(()=>{ el.textContent = v; el.style.opacity = '1'; }, 180);
    });
    toast('已刷新（演示数据）');
  }
  syncUsage(true);
}

/* ---------- 事件绑定 ---------- */
function bind(){
  $('#btnBack').addEventListener('click', goHome);
  $('#btnHome').addEventListener('click', goHome);
  $('#btnRefresh').addEventListener('click', refreshStats);

  $('#btnSettings').addEventListener('click', ()=> $('#sheetMask').classList.add('is-open'));
  $('#sheetDone').addEventListener('click', ()=> $('#sheetMask').classList.remove('is-open'));
  $('#sheetMask').addEventListener('click', e=>{
    if(e.target.id === 'sheetMask') $('#sheetMask').classList.remove('is-open');
  });
  $$('[data-toggle]').forEach(sw=> sw.addEventListener('click', ()=> sw.classList.toggle('is-on')));

  const host = location.host || 'localhost:5173';
  const lanDesc = $('#lanDesc');
  if(lanDesc) lanDesc.textContent = `直连 ${host}，不经云端`;

  $('#lanPill').addEventListener('click', ()=>{
    const on = $('#lanPill').querySelector('.dot--live');
    toast(on ? '已连接 ' + host : '未连接，点击设置');
  });

  $('#sessionBar').addEventListener('click', openSessSheet);
  $('#btnAllSessions').addEventListener('click', openSessSheet);
  $('#sessMask').addEventListener('click', e=>{
    if(e.target.id === 'sessMask') $('#sessMask').classList.remove('is-open');
  });
  $('#proPill').addEventListener('click', ()=> toast('当前套餐：Pro'));

  $('#input').addEventListener('input', updateSendState);
  $('#input').addEventListener('keydown', e=>{
    if(e.key === 'Enter'){ e.preventDefault(); send(); }
  });
  $('#btnSend').addEventListener('click', send);

// 浏览器返回键
  window.addEventListener('popstate', ()=>{
    if($('#viewChat').classList.contains('is-active')) goHome();
  });

  // 从后台切回时立即刷新一次，不等下一轮
  document.addEventListener('visibilitychange', ()=>{
    if(!document.hidden && $('#viewChat').classList.contains('is-active')) pollSession();
  });
}

/* ---------- 启动 ---------- */
buildHeatmap();
renderAgents();
renderChips();
renderPicker();
renderProjects();
bind();

// 接入真实用量与会话列表，之后每 30 秒轮询
syncUsage(false);
loadSessions().then(ok=>{ if(ok) renderProjects(); });
setInterval(()=> syncUsage(true), 30000);

// 支持深链：#chat / #chat=2 直接进入会话页，#sessions 直接展开会话历史
if(location.hash.startsWith('#chat')){
  const m = location.hash.match(/=(\d+)/);
  openChat(m ? Math.min(+m[1], agents.length-1) : 0);
}
if(location.hash === '#sessions'){
  setTimeout(()=> openSessSheet(), 60);
}
if(location.hash === '#settings'){
  setTimeout(()=> $('#sheetMask').classList.add('is-open'), 60);
}
