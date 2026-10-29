/* Marrow 前端：应用壳、路由、页面、学习数据与账号。
 *
 * 架构：ES modules（util / expr_guard / viz / app 四个文件），零构建、零依赖。
 * 交互一律走事件委托——[data-nav] 跳转、[data-action] 动作，文档级统一分发；
 * 不再有内联 onclick 与 window.* 全局函数。
 * 静态优先：API 不可达时自动回退到 cores-index.json + cores/<id>.json。
 */
import { esc } from './util.mjs';
import { renderExplorable } from './viz.mjs';

const API_BASE = '/api'; // 平台同源；不可达时自动回退静态模式
let STATIC_MODE = false;
let PLATFORM_MODE = false;
const coreCache = {};
const app = document.getElementById('app');
const PROGRESS_KEY = 'marrow.progress.v1';
const TOKEN_KEY = 'marrow.token.v1';
function authed() { return !!localStorage.getItem(TOKEN_KEY); }
function authHeaders() {
  const t = localStorage.getItem(TOKEN_KEY);
  return t ? { 'Authorization': 'Bearer ' + t } : {};
}

// ---------- 设置与界面多语言（外观/主题/字号/语言，内容语言跟随书籍） ----------
const SETTINGS_KEY = 'marrow.settings.v1';
let SETTINGS = { theme: 'auto', lang: 'zh', font: 'm', book: 'all' };
function loadSettings() {
  try { Object.assign(SETTINGS, JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {}); } catch (e) {}
}
function saveSettings() {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(SETTINGS));
  applySettings();
}
function applySettings() {
  document.documentElement.dataset.theme = SETTINGS.theme === 'auto' ? '' : SETTINGS.theme;
  document.body.classList.toggle('font-l', SETTINGS.font === 'l');
  const btn = document.getElementById('themeBtn');
  if (btn) btn.textContent = SETTINGS.theme === 'dark' ? '☀️' : '🌙';
}
const I18N = {
  zh: {
    catalog: '目录', import: '导入书籍', settings: '设置', search: '搜索术语/结论/习题…',
    glossary: '词典', results: '核心结论', explore: '动手探索', examples: '例题（用于验证）',
    exercises: '动手练习（原书未给答案）', related: '相关内容', kmap: '知识结构',
    showAnswer: '显示参考答案（机器验证）', hideAnswer: '收起参考答案', submit: '提交作答',
    answerPlaceholder: '写下你的答案或证明思路…',
    allBooks: '全部书籍', appearance: '外观', theme: '主题', light: '浅色', dark: '深色', auto: '跟随系统',
    language: '界面语言', font: '字号', normal: '标准', large: '大', data: '数据',
    clearProgress: '清除本地进度', exportProgress: '导出进度', mastered: '已掌握',
    tagline: '把任何一本教科书，变成可以动手玩的数学',
    taglineSub: '打开任意一节：拖动向量与滑块，实时看定义与定理在几何里发生。',
    sections: '节', back: '← 返回目录', importTitle: '导入新书籍',
    importHint: '探测用启发式识别章节标题，结果含少量误报，请人工勾选确认后再运行流水线。',
    detect: '探测章节结构', detectRunning: '探测中…（大 PDF 约需 10-30 秒）',
    runPipeline: '按勾选运行流水线（每节约 3-6 分钟）', corePrefix: 'core 前缀',
    imported: '已收录 {n} 本书。打开任意一节：拖动向量与滑块，实时看定义与定理在几何里发生。',
    importBtn: '＋ 导入新书籍（PDF）', langNote: '书籍内容语言跟随原书，此处切换的是界面语言。',
    pdfPathLabel: '书籍 PDF 路径（本机）：',
    foundNote: '共 {p} 页，发现 {n} 个小节候选（含目录/页眉误报，请勾选真实小节）',
    colKey: '编号', colTitle: '标题', colStart: '起始页', colEnd: '结束页',
    noSelection: '先勾选要导入的小节',
    startLog: '▶ {id}（{title}，页 {start}-{end}）启动…',
    jobDone: '已入库', jobFail: '失败，详见服务端日志',
    allDone: '—— 完成。回到首页即可看到新书内容。',
    errPrefix: '错误：', loadFail: '内容加载失败：找不到这个 core 文件。',
    needText: '先写下你的答案或证明思路再提交', submitting: '提交中…',
    correct: '✓ 与机器验证答案一致！',
    incorrect: '✗ 与机器验证答案不一致——展开参考答案对照推理步骤',
    recorded: '已记录（本节暂无机器验证答案，建议与教师/同学讨论核对）',
    needPlatform: '作答记录需要平台服务：./scripts/serve_platform.sh',
    progressCleared: '本地进度已清除', noResults: '无结果',
    account: '账号（多设备同步）', accountNote: '进度与作答已按账号保存在本机服务端，换浏览器登录同一账号即可同步。',
    login: '登录', register: '注册并登录', logout: '退出登录',
    emailPh: '邮箱', passPh: '密码（至少 6 位）', loginOk: '已登录，进度已同步',
    statsTitle: '学习档案', chapterProgress: '各节掌握进度',
    masteredOf: '{m} / {t} 道习题已掌握', recentAttempts: '最近作答', noAttempts: '还没有作答记录。',
    attemptOk: '✓ 一致', attemptBad: '✗ 不一致', attemptNeu: '记录',
    importProgress: '导入进度', importProgressBad: '文件格式不对：需要 Marrow 导出的 marrow-progress.json',
    importProgressOk: '已导入 {n} 条进度', importNeedsPlatform: '导入新书需要平台模式：先运行 ./scripts/serve_platform.sh 再刷新页面。',
    resetSection: '清零本节', resetConfirm: '清零本节的全部掌握记录？',
  },
  en: {
    catalog: 'Catalog', import: 'Import book', settings: 'Settings', search: 'Search terms / results / exercises…',
    glossary: 'Glossary', results: 'Key results', explore: 'Explore', examples: 'Worked examples',
    exercises: 'Exercises (no answers in book)', related: 'Related', kmap: 'Knowledge map',
    showAnswer: 'Show reference answer (machine-verified)', hideAnswer: 'Hide answer', submit: 'Submit',
    answerPlaceholder: 'Write your answer or proof idea…',
    allBooks: 'All books', appearance: 'Appearance', theme: 'Theme', light: 'Light', dark: 'Dark', auto: 'Auto',
    language: 'UI language', font: 'Font size', normal: 'Normal', large: 'Large', data: 'Data',
    clearProgress: 'Clear local progress', exportProgress: 'Export progress', mastered: 'mastered',
    tagline: 'Turn any textbook into math you can play with',
    taglineSub: 'Open any section: drag vectors and sliders, watch definitions and theorems happen in geometry.',
    sections: 'sections', back: '← Catalog', importTitle: 'Import a new book',
    importHint: 'Section detection is heuristic — review and confirm the checkboxes before running the pipeline.',
    detect: 'Detect chapter structure', detectRunning: 'Detecting… (large PDFs take 10-30s)',
    runPipeline: 'Run pipeline on selection (3-6 min per section)', corePrefix: 'core prefix',
    imported: '{n} book(s) imported. Open a section and drag vectors and sliders to see the math happen.',
    importBtn: '＋ Import a book (PDF)', langNote: 'Book content stays in its original language; this switches the UI.',
    pdfPathLabel: 'Book PDF path (local):',
    foundNote: '{p} pages, {n} section candidates found (TOC/headers included — check the real ones)',
    colKey: 'No.', colTitle: 'Title', colStart: 'Start', colEnd: 'End',
    noSelection: 'Select at least one section first',
    startLog: '▶ {id} ({title}, pages {start}-{end}) started…',
    jobDone: 'imported', jobFail: 'failed, see server log',
    allDone: '—— Done. Go back to the catalog to see the new book.',
    errPrefix: 'Error: ', loadFail: 'Failed to load: core file not found.',
    needText: 'Write your answer or proof idea first', submitting: 'Submitting…',
    correct: '✓ Matches the machine-verified answer!',
    incorrect: '✗ Differs from the reference answer — expand it and compare your reasoning',
    recorded: 'Recorded (no machine-verified answer yet — discuss with a teacher or classmate)',
    needPlatform: 'Attempt records need the platform: ./scripts/serve_platform.sh',
    progressCleared: 'Local progress cleared', noResults: 'No results',
    account: 'Account (multi-device sync)', accountNote: 'Progress and attempts are stored per-account on the local server. Sign in on any browser to sync.',
    login: 'Sign in', register: 'Register & sign in', logout: 'Sign out',
    emailPh: 'Email', passPh: 'Password (min 6 chars)', loginOk: 'Signed in, progress synced',
    statsTitle: 'Profile', chapterProgress: 'Progress by section',
    masteredOf: '{m} / {t} exercises mastered', recentAttempts: 'Recent attempts', noAttempts: 'No attempts yet.',
    attemptOk: '✓ match', attemptBad: '✗ mismatch', attemptNeu: 'logged',
    importProgress: 'Import progress', importProgressBad: 'Wrong file: expected marrow-progress.json exported from Marrow',
    importProgressOk: 'Imported {n} progress entries', importNeedsPlatform: 'Importing books needs platform mode: run ./scripts/serve_platform.sh and refresh.',
    resetSection: 'Reset section', resetConfirm: 'Clear all mastered records for this section?',
  },
};
function t(k) {
  const L = I18N[SETTINGS.lang] || I18N.zh;
  return L[k] !== undefined ? L[k] : (I18N.zh[k] !== undefined ? I18N.zh[k] : k);
}
function bookOf(it) {
  return ((it.source && it.source.book) || '未命名书籍').replace(/（[^）]*）/, '').trim() || '未命名书籍';
}
function toggleSidebar(open) {
  document.body.classList.toggle('sb-open', open === undefined ? !document.body.classList.contains('sb-open') : open);
}
function cycleTheme() {
  SETTINGS.theme = SETTINGS.theme === 'dark' ? 'auto' : (SETTINGS.theme === 'auto' ? 'light' : 'dark');
  saveSettings();
  if (location.hash === '#/settings') renderSettings();
}

// ---------- 数据加载（API 优先，静态回退，1.5s 超时兜底） ----------
async function loadCoreList() {
  if (!STATIC_MODE) {
    try {
      const res = await fetch(API_BASE + '/cores', { signal: AbortSignal.timeout(1500) });
      if (res.ok) { PLATFORM_MODE = true; return res.json(); }
    } catch (e) { /* 后端不可达，转静态模式 */ }
    STATIC_MODE = true;
  }
  return (await fetch('cores-index.json')).json();
}

async function loadCore(id) {
  if (coreCache[id]) return coreCache[id];
  let data = null;
  if (!STATIC_MODE) {
    try {
      const res = await fetch(API_BASE + '/cores/' + id, { signal: AbortSignal.timeout(1500) });
      if (res.ok) data = await res.json();
    } catch (e) { /* 后端不可达，转静态模式 */ }
    if (!data) STATIC_MODE = true;
  }
  if (!data) data = await (await fetch('cores/' + id + '.json')).json();
  coreCache[id] = data;
  return data;
}

// ---------- 学习进度 ----------
function getProgress() { try { return JSON.parse(localStorage.getItem(PROGRESS_KEY)) || {}; } catch (e) { return {}; } }
function setDone(key, done) {
  const p = getProgress();
  if (done) p[key] = 1; else delete p[key];
  localStorage.setItem(PROGRESS_KEY, JSON.stringify(p));
}
function chapterOf(item) {
  const m = (item.source && item.source.section || '').match(/第\s*(\d+)\s*章/);
  return m ? '第' + m[1] + '章' : '其他';
}
const CHAPTER_META = {
  '第1章': { name: '向量空间', color: '#3b82f6' },
  '第2章': { name: '有限维向量空间', color: '#14b8a6' },
  '第3章': { name: '线性映射与矩阵', color: '#6366f1' },
  '第4章': { name: '多项式', color: '#f97316' },
  '第5章': { name: '特征值与特征向量', color: '#0ea5e9' },
  '第6章': { name: '内积空间', color: '#10b981' },
  '第7章': { name: '内积空间上的算子', color: '#f59e0b' },
  '第8章': { name: '复向量空间上的算子', color: '#ef4444' },
  '第9章': { name: '多重线性代数与行列式', color: '#a855f7' },
};

// ---------- 首页：书籍 → 章节 地图 ----------
async function renderHome() {
  const items = await loadCoreList();
  const books = {};
  items.forEach(it => { const b = bookOf(it); (books[b] = books[b] || []).push(it); });
  const filter = SETTINGS.book !== 'all' && books[SETTINGS.book] ? SETTINGS.book : null;
  const shown = filter ? { [filter]: books[filter] } : books;
  let html = `<div class="hero"><h2>${t('tagline')}</h2>
    <p>${t('imported').replace('{n}', Object.keys(books).length)}</p>
    <button class="answer-btn" data-nav="#/import">${t('importBtn')}</button></div>`;
  for (const book of Object.keys(shown)) {
    html += `<div class="book-head"><h3>${esc(book)}</h3><span class="chapter-count">${shown[book].length} ${t('sections')}</span></div>`;
    const groups = {};
    shown[book].forEach(it => { const ch = chapterOf(it); (groups[ch] = groups[ch] || []).push(it); });
    for (const ch of Object.keys(groups)) {
      const meta = CHAPTER_META[ch] || { name: '', color: '#64748b' };
      html += `<div class="chapter-head"><span class="chapter-dot" style="background:${meta.color}"></span>
        <h3>${esc(ch)}${meta.name ? ' · ' + esc(meta.name) : ''}</h3><span class="chapter-count">${groups[ch].length} ${t('sections')}</span></div><div class="chapter-cards">`;
      for (const it of groups[ch]) {
        html += `<div class="core-card" data-nav="#/core/${esc(it.id)}">
          <h4>${esc(it.topic)}</h4><div class="meta">${esc(it.source.section)}</div></div>`;
      }
      html += `</div>`;
    }
  }
  app.innerHTML = html;
  wireA11y();
}

// ---------- 导入书籍（平台 API） ----------
let detected = null, importedPdfPath = '';
async function renderImport() {
  const staticHint = STATIC_MODE
    ? `<div class="card" style="margin-bottom:12px;border-color:var(--amber)"><b>${t('errPrefix')}</b>${t('importNeedsPlatform')}</div>`
    : '';
  app.innerHTML = `<div class="back-link" data-nav="#/">← ${t('catalog')}</div>
    <h2 class="core-title">${t('importTitle')}</h2>
    ${staticHint}
    <div class="card" style="margin-top:12px">
      <div class="practice-content">${t('pdfPathLabel')}</div>
      <input id="pdfPath" style="width:100%;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--text)" placeholder="/path/to/book.pdf">
      <button class="answer-btn" style="margin-top:10px" data-action="detect">${t('detect')}</button>
      <div id="detectHint" class="viz-caption" style="margin-top:8px">${t('importHint')}</div>
    </div>
    <div id="detectResult"></div>`;
  wireA11y();
}
async function detectSections() {
  if (STATIC_MODE) { alert(t('importNeedsPlatform')); return; }
  const path = document.getElementById('pdfPath').value.trim();
  const hint = document.getElementById('detectHint');
  hint.textContent = t('detectRunning');
  const res = await fetch('/api/import/detect', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pdf_path: path }) });
  const d = await res.json();
  if (d.error) { hint.textContent = t('errPrefix') + d.error; return; }
  hint.textContent = t('foundNote').replace('{p}', d.total_pages).replace('{n}', d.sections.length);
  const rows = d.sections.map((s, i) => `<tr>
    <td><input type="checkbox" class="sec-check" data-i="${i}"></td>
    <td>${esc(s.key)}</td><td>${esc(s.title)}</td>
    <td><input class="pg pg-start" data-i="${i}" value="${s.page}" size="4"></td>
    <td><input class="pg pg-end" data-i="${i}" value="${s.end_page || ''}" size="4"></td></tr>`).join('');
  document.getElementById('detectResult').innerHTML = `<div class="card" style="overflow:auto"><table class="sec-table">
    <thead><tr><th></th><th>${t('colKey')}</th><th>${t('colTitle')}</th><th>${t('colStart')}</th><th>${t('colEnd')}</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="card"><div class="practice-content">${t('corePrefix')}：<input id="bookPrefix" value="book" size="10"
      style="padding:6px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--text)"></div>
    <button class="answer-btn" data-action="onboard">${t('runPipeline')}</button>
    <div id="runLog" style="margin-top:10px;font-size:12.5px;white-space:pre-wrap;font-family:ui-monospace,monospace"></div></div>`;
  detected = d; importedPdfPath = path;
  wireA11y();
}
async function runOnboard() {
  const checks = Array.from(document.querySelectorAll('.sec-check:checked'));
  if (!checks.length) { alert(t('noSelection')); return; }
  const prefix = document.getElementById('bookPrefix').value.trim() || 'book';
  const log = document.getElementById('runLog');
  for (const ck of checks) {
    const i = ck.dataset.i;
    const s = detected.sections[i];
    const sid = (prefix + '-' + s.key).toLowerCase().replace(/[^a-z0-9-]/g, '');
    const start = document.querySelectorAll('.pg-start')[i].value;
    const end = document.querySelectorAll('.pg-end')[i].value;
    log.textContent += t('startLog').replace('{id}', sid).replace('{title}', s.title)
      .replace('{start}', start).replace('{end}', end) + '\n';
    const res = await fetch('/api/onboard', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pdf_path: importedPdfPath, section_id: sid, title: s.title, start: +start, end: +end, related: [] }) });
    const d = await res.json();
    if (d.error) { log.textContent += `  ✗ ${d.error}\n`; continue; }
    let last = '';
    while (true) {
      await new Promise(r => setTimeout(r, 4000));
      const j = await (await fetch('/api/jobs/' + d.job_id)).json();
      if (j.status !== last) { log.textContent += `  [${j.status}]\n`; last = j.status; }
      if (j.status !== 'running') break;
    }
    log.textContent += `  ✓ ${sid} ${j.status === 'done' ? t('jobDone') : t('jobFail')}\n`;
  }
  log.textContent += t('allDone');
  _shellBuilt = false;  // 新书入库后侧边栏书籍列表需要重建
}

// ---------- 详情页 ----------
async function renderCoreDetail(id) {
  let core;
  try {
    core = await loadCore(id);
  } catch (e) {
    app.innerHTML = `<div class="back-link" data-nav="#/">${t('back')}</div>
      <h2 class="core-title">${esc(id)}</h2>
      <div class="card">${t('loadFail')}</div>`;
    wireA11y();
    return;
  }
  let html = `<div class="back-link" data-nav="#/">${t('back')}</div>
    <h2 class="core-title">${esc(core.topic)}</h2>
    <div class="core-meta">${esc(core.source.book)} · ${esc(core.source.section)}</div>`;

  if (core.structure && core.structure.nodes && core.structure.nodes.length)
    html += `<div class="section-title">${t('kmap')}</div><div class="structure-wrap" id="structure-box"></div>`;

  if (core.dictionary && core.dictionary.length) {
    html += `<div class="section-title">${t('glossary')}</div><div class="dict-grid">`;
    for (const d of core.dictionary)
      html += `<div class="card"><div class="card-top"><b>${esc(d.term)}</b><span class="src-ref">${esc(d.source_ref)}</span></div>${esc(d.definition)}</div>`;
    html += `</div>`;
  }
  if (core.algorithms && core.algorithms.length) {
    html += `<div class="section-title">${t('results')}</div>`;
    for (const a of core.algorithms)
      html += `<div class="card"><div class="card-top"><b>${esc(a.name)}</b><span class="src-ref">${esc(a.source_ref)}${a.executable ? ' · ✓ 可执行' : ''}</span></div>${esc(a.statement)}</div>`;
  }
  // 多个探索场景全部渲染
  if (core.explorable && core.explorable.length) {
    html += `<div class="section-title">${t('explore')}</div>`;
    core.explorable.forEach((exp, i) => {
      html += `<div class="explorable-box" id="explorable-box-${i}"></div>`;
    });
  }

  if (core.cases && core.cases.length) {
    html += `<div class="section-title">${t('examples')}</div>`;
    for (const c of core.cases)
      html += `<div class="card"><div class="card-top"><span class="badge badge-val">${esc(c.source_ref)}</span>${c.is_verbatim ? '<span class="badge badge-verbatim">原书数值</span>' : ''}</div>${esc(c.content)}</div>`;
  }

  const prCases = core.cases_practice || [];
  if (prCases.length) {
    const prog = getProgress();
    const done = prCases.filter(c => prog[id + ':' + c.id]).length;
    const pct = Math.round(100 * done / prCases.length);
    html += `<div class="section-title">${t('exercises')}</div>
      <div class="practice-progress"><div class="practice-progress-bar" style="width:${pct}%"></div></div>
      <div class="practice-count">${done} / ${prCases.length} ${t('mastered')}</div>`;
    for (const c of prCases) {
      const key = id + ':' + c.id;
      const isDone = !!prog[key];
      html += `<div class="card practice-card ${isDone ? 'done' : ''}" data-key="${esc(key)}">
        <label class="practice-check"><input type="checkbox" ${isDone ? 'checked' : ''}>
        <span class="badge badge-practice">${esc(c.source_ref)}</span>
        ${c.answer_verified ? '<span class="badge badge-ai">有机器验证答案</span>' : ''}</label>
        <div class="practice-content">${esc(c.content)}</div>
        <textarea class="attempt-input" id="ans_${esc(c.id)}" rows="2" placeholder="${t('answerPlaceholder')}"></textarea>
        <button class="answer-btn" data-action="attempt" data-core="${esc(id)}" data-case="${esc(c.id)}">${t('submit')}</button>
        <div class="attempt-feedback" id="fb_${esc(c.id)}"></div>
        ${c.candidate_answer && c.answer_verified
          ? `<button class="answer-btn" data-action="toggle-answer">${t('showAnswer')}</button>
             <div class="answer-body" hidden>✓ ${esc(c.candidate_answer)}</div>` : ''}
      </div>`;
    }
  }

  if (core.related_cores && core.related_cores.length) {
    html += `<div class="section-title">${t('related')}</div>`;
    for (const r of core.related_cores)
      html += `<span class="related-link" data-nav="#/core/${esc(r.core_id)}">${esc(r.via)}</span>`;
  }
  app.innerHTML = html;
  if (core.structure && core.structure.nodes && core.structure.nodes.length)
    renderStructure(core.structure, 'structure-box');
  (core.explorable || []).forEach((exp, i) => renderExplorable(exp, i));
  refreshPracticeBar();
  wireA11y();
}

// ---------- 知识结构图（structure 字段可视化，对应产品文档步骤4） ----------
function renderStructure(st, containerId) {
  const box = document.getElementById(containerId);
  const nodes = st.nodes, edges = st.edges || [];
  const adj = {};
  edges.forEach(e => { (adj[e.from] = adj[e.from] || []).push(e.to); });
  const depth = {};
  if (nodes.length) { depth[nodes[0]] = 0; }
  const q = nodes.length ? [nodes[0]] : [];
  while (q.length) {
    const n = q.shift();
    (adj[n] || []).forEach(m => { if (!(m in depth)) { depth[m] = (depth[n] || 0) + 1; q.push(m); } });
  }
  nodes.forEach(n => { if (!(n in depth)) depth[n] = 0; });
  const cols = {};
  nodes.forEach(n => { (cols[depth[n]] = cols[depth[n]] || []).push(n); });
  const colKeys = Object.keys(cols).map(Number).sort((a, b) => a - b);
  const CW = 138, RH = 50;
  const W = Math.max(340, colKeys.length * CW + 20);
  const H = Math.max(...colKeys.map(c => cols[c].length)) * RH + 16;
  const pos = {};
  colKeys.forEach(cc => cols[cc].forEach((n, i) => pos[n] = [12 + cc * CW, 10 + i * RH]));
  let svg = edges.map(e => {
    if (!(e.from in pos) || !(e.to in pos)) return '';
    const x1 = pos[e.from][0] + 112, y1 = pos[e.from][1] + 15, x2 = pos[e.to][0] + 4, y2 = pos[e.to][1] + 15;
    return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--text-3)" stroke-width="1.2" marker-end="url(#arr)"><title>${esc(e.relation)}</title></line>`;
  }).join('');
  nodes.forEach(n => {
    const [x, y] = pos[n];
    svg += `<rect x="${x}" y="${y}" width="112" height="30" rx="8" fill="var(--primary-soft)" stroke="var(--primary)"/><text x="${x + 56}" y="${y + 19}" text-anchor="middle" font-size="11" fill="var(--text)">${esc(n.length > 11 ? n.slice(0, 10) + '…' : n)}</text>`;
  });
  const list = edges.map(e => `<div class="edge-row"><b>${esc(e.from)}</b> → <b>${esc(e.to)}</b>：${esc(e.relation)}</div>`).join('');
  box.innerHTML = `<div style="overflow:auto"><svg width="${W}" height="${H}" style="min-width:${W}px">
    <defs><marker id="arr" markerWidth="9" markerHeight="8" refX="8" refY="3.5" orient="auto"><path d="M0,0 L8,3.5 L0,7" fill="none" stroke="var(--text-3)" stroke-width="1.2"/></marker></defs>
    ${svg}</svg></div>${list ? `<div class="edge-list">${list}</div>` : ''}`;
}

// ---------- 习题作答提交（case_attempts，对应产品文档步骤6） ----------
async function submitAttempt(coreId, caseId, btn) {
  const ta = document.getElementById('ans_' + caseId);
  const fb = document.getElementById('fb_' + caseId);
  const text = (ta && ta.value || '').trim();
  if (!text) { fb.textContent = t('needText'); return; }
  btn.disabled = true; fb.textContent = t('submitting');
  try {
    const res = await fetch('/api/attempt', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ core_id: coreId, case_id: caseId, text }) });
    const d = await res.json();
    if (d.error) { fb.textContent = t('errPrefix') + d.error; }
    else if (d.is_correct === true) fb.innerHTML = `<b style="color:#047857">${t('correct')}</b>`;
    else if (d.is_correct === false) fb.innerHTML = `<b style="color:#dc2626">${t('incorrect')}</b>`;
    else fb.textContent = t('recorded');
  } catch (e) {
    fb.textContent = t('needPlatform');
  }
  btn.disabled = false;
}

// ---------- 全局搜索（术语/结论/例题/习题） ----------
let _searchTimer = null, _searchGen = 0, _searchIdx = -1;
function doSearch(q) {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(() => _doSearch(q.trim()), 250);
}
function hideSearchPanel() {
  const panel = document.getElementById('searchResults');
  if (panel) panel.hidden = true;
  _searchIdx = -1;
}
async function _doSearch(q) {
  const panel = document.getElementById('searchResults');
  if (!panel) return;
  if (!q) { panel.hidden = true; return; }
  const gen = ++_searchGen;  // 输入竞态防护：慢查询返回时若已有更新查询，丢弃过期结果
  const items = await loadCoreList();
  const qq = q.toLowerCase();
  const out = [];
  for (const it of items) {
    const c = await loadCore(it.id);
    (c.dictionary || []).forEach(d => { if ((d.term + d.definition).toLowerCase().includes(qq)) out.push({ core: it.id, topic: it.topic, kind: '术语', ref: d.source_ref, text: d.term + '：' + d.definition }); });
    (c.algorithms || []).forEach(a => { if ((a.name + a.statement).toLowerCase().includes(qq)) out.push({ core: it.id, topic: it.topic, kind: '结论', ref: a.source_ref, text: a.name }); });
    (c.cases || []).forEach(x => { if ((x.content || '').toLowerCase().includes(qq)) out.push({ core: it.id, topic: it.topic, kind: '例题', ref: x.source_ref, text: (x.content || '').slice(0, 70) }); });
    (c.cases_practice || []).forEach(x => { if ((x.content || '').toLowerCase().includes(qq)) out.push({ core: it.id, topic: it.topic, kind: '习题', ref: x.source_ref, text: (x.content || '').slice(0, 70) }); });
  }
  if (gen !== _searchGen) return;
  panel.innerHTML = out.length
    ? out.slice(0, 12).map(r => `<div class="search-hit" data-nav="#/core/${esc(r.core)}">
        <span class="badge badge-val">${esc(r.kind)}</span> ${esc(r.text)}<br><span class="src-ref">${esc(r.topic)} · ${esc(r.ref)}</span></div>`).join('')
    : `<div class="search-hit">${t('noResults')}</div>`;
  _searchIdx = -1;
  panel.hidden = false;
  wireA11y();
}
function togglePractice(key, checked) {
  setDone(key, checked);
  const el = document.querySelector(`.practice-card[data-key="${key}"]`);
  if (el) el.classList.toggle('done', checked);
  refreshPracticeBar();
  if (PLATFORM_MODE) fetch('/api/progress', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ key, done: checked }) }).catch(() => {});
}
function toggleAnswer(btn) {
  const body = btn.nextElementSibling;
  body.hidden = !body.hidden;
  btn.textContent = body.hidden ? t('showAnswer') : t('hideAnswer');
}
function refreshPracticeBar() {
  const cards = document.querySelectorAll('.practice-card');
  if (!cards.length) return;
  let done = 0;
  cards.forEach(c => { if (c.classList.contains('done')) done++; });
  const bar = document.querySelector('.practice-progress-bar');
  const cnt = document.querySelector('.practice-count');
  if (bar) bar.style.width = Math.round(100 * done / cards.length) + '%';
  if (cnt) {
    const coreId = (cards[0].dataset.key || '').split(':')[0];
    const btn = done
      ? `<button class="answer-btn" style="margin-left:10px;padding:2px 10px;font-size:12px" data-action="reset-section" data-core="${esc(coreId)}">${t('resetSection')}</button>`
      : '';
    cnt.innerHTML = `${done} / ${cards.length} ${t('mastered')}${btn}`;
  }
}

// ---------- 可访问性：交互元素补齐键盘可达性 ----------
function wireA11y() {
  document.querySelectorAll('[data-nav],[data-action]').forEach(el => {
    if (/^(BUTTON|INPUT|A|LABEL|TEXTAREA|SELECT)$/.test(el.tagName)) return;
    el.setAttribute('role', 'button');
    if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '0');
  });
}

// ---------- 事件委托：data-nav 跳转 + data-action 动作，全应用零内联 onclick ----------
const ACTIONS = {
  'sidebar': () => toggleSidebar(),
  'sidebar-close': () => toggleSidebar(false),
  'theme': () => cycleTheme(),
  'pick-book': el => pickBook(el.dataset.bookIndex),
  'detect': () => detectSections(),
  'onboard': () => runOnboard(),
  'attempt': el => submitAttempt(el.dataset.core, el.dataset.case, el),
  'toggle-answer': el => toggleAnswer(el),
  'set-theme': el => setSetting('theme', el.dataset.value),
  'set-font': el => setSetting('font', el.dataset.value),
  'set-lang': el => setSetting('lang', el.dataset.value),
  'export-progress': () => exportProgress(),
  'clear-progress': () => clearProgress(),
  'reset-section': el => resetSection(el.dataset.core),
  'login': () => authAction('login'),
  'register': () => authAction('register'),
  'logout': () => doLogout(),
};
document.addEventListener('click', e => {
  const el = e.target.closest('[data-nav],[data-action]');
  if (!el) return;
  if (el.dataset.nav) {
    hideSearchPanel();
    location.hash = el.dataset.nav;
    return;
  }
  const fn = ACTIONS[el.dataset.action];
  if (fn) fn(el);
});
// 习题"已掌握"勾选：change 委托，key 取自卡片 data-key
document.addEventListener('change', e => {
  const cb = e.target;
  if (cb instanceof HTMLInputElement && cb.id === 'importFile') {
    importProgress(cb);
    cb.value = '';
    return;
  }
  if (cb instanceof HTMLInputElement && cb.type === 'checkbox' && cb.classList.contains('sec-check')) return;
  if (cb instanceof HTMLInputElement && cb.type === 'checkbox') {
    const card = cb.closest('.practice-card');
    if (card && card.dataset.key) togglePractice(card.dataset.key, cb.checked);
  }
});
// 键盘：Enter/Space 触发带 data-* 的"按钮"
document.addEventListener('keydown', e => {
  // 搜索面板键盘导航：↑↓ 选择、Enter 跳转、Esc 关闭（焦点已在命中项上时走通用分支）
  const panel = document.getElementById('searchResults');
  if (panel && !panel.hidden && !panel.contains(document.activeElement)) {
    const hits = Array.from(panel.querySelectorAll('.search-hit[data-nav]'));
    if (hits.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        _searchIdx = e.key === 'ArrowDown' ? Math.min(_searchIdx + 1, hits.length - 1)
                                           : Math.max(_searchIdx - 1, 0);
        hits.forEach((h, i) => h.classList.toggle('active', i === _searchIdx));
        hits[_searchIdx].scrollIntoView({ block: 'nearest' });
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        hits[Math.max(_searchIdx, 0)].click();
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        hideSearchPanel();
        return;
      }
    }
  }
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const el = e.target;
  if (el && (el.hasAttribute('data-nav') || el.hasAttribute('data-action'))) {
    e.preventDefault();
    el.click();
  }
});

// ---------- 应用壳：侧边栏 + 顶栏 ----------
// 壳只构建一次（语言切换/新书入库时强制重建），路由切换只更新激活态——
// 避免每次导航重建顶栏导致搜索框丢焦点、丢已输入文本。
let _shellBuilt = false;
let bookNames = [];
async function renderShell(force) {
  loadSettings();
  applySettings();
  const route = (location.hash || '#/');
  if (_shellBuilt && !force) { updateShellActive(route); return; }
  let items = [];
  try { items = await loadCoreList(); } catch (e) {}
  const books = {};
  items.forEach(it => { const b = bookOf(it); (books[b] = books[b] || []).push(it); });
  bookNames = Object.keys(books);
  const cur = SETTINGS.book;
  const sb = document.getElementById('sidebar');
  sb.innerHTML = `
    <div class="sb-logo" data-nav="#/">Marrow</div>
    <div class="sb-label">${t('allBooks')}</div>
    <div class="sb-book ${cur === 'all' ? 'active' : ''}" data-action="pick-book" data-book-index="all"><span>${t('allBooks')}</span><span class="cnt">${items.length}</span></div>
    ${bookNames.map((b, i) => `<div class="sb-book ${cur === b ? 'active' : ''}" data-action="pick-book" data-book-index="${i}"><span>${esc(b.length > 22 ? b.slice(0, 21) + '…' : b)}</span><span class="cnt">${books[b].length}</span></div>`).join('')}
    <div class="sb-sep"></div>
    <div class="sb-item ${route === '#/' ? 'active' : ''}" data-route="#/" data-nav="#/">📖 ${t('catalog')}</div>
    <div class="sb-item ${route === '#/stats' ? 'active' : ''}" data-route="#/stats" data-nav="#/stats">📊 ${t('statsTitle')}</div>
    <div class="sb-item ${route === '#/import' ? 'active' : ''}" data-route="#/import" data-nav="#/import">📥 ${t('import')}</div>
    <div class="sb-item ${route === '#/settings' ? 'active' : ''}" data-route="#/settings" data-nav="#/settings">⚙️ ${t('settings')}</div>
    <div class="sb-foot">Marrow v2 · ${items.length} cores</div>`;
  const tb = document.getElementById('topbar');
  tb.innerHTML = `
    <button class="hamburger" data-action="sidebar">☰</button>
    <div style="position:relative;flex:1;max-width:340px">
      <input id="searchBox" placeholder="${t('search')}" style="width:100%">
      <div id="searchResults" hidden style="position:absolute;left:0;top:40px;width:340px;max-height:420px;overflow:auto;
        background:var(--surface);border:1px solid var(--border);border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,.18);z-index:30;padding:6px"></div>
    </div>
    <button id="themeBtn" class="icon-btn" data-action="theme" title="${t('theme')}">🌙</button>`;
  document.getElementById('searchBox').addEventListener('input', e => doSearch(e.target.value));
  _shellBuilt = true;
  wireA11y();
}
function updateShellActive(route) {
  document.querySelectorAll('#sidebar .sb-item[data-route]').forEach(el =>
    el.classList.toggle('active', el.dataset.route === route));
  const btn = document.getElementById('themeBtn');
  if (btn) btn.textContent = SETTINGS.theme === 'dark' ? '☀️' : '🌙';
}
function pickBook(index) {
  SETTINGS.book = index === 'all' ? 'all' : bookNames[+index];
  saveSettings();
  toggleSidebar(false);
  document.querySelectorAll('#sidebar .sb-book').forEach(el =>
    el.classList.toggle('active', el.dataset.bookIndex === String(index)));
  if (location.hash === '#/' || location.hash === '') renderHome(); else location.hash = '#/';
}

// ---------- 学习档案：跨节进度 + 最近作答（/api/stats） ----------
async function renderStats() {
  let data = null;
  try {
    const res = await fetch('/api/stats', { headers: authHeaders(), signal: AbortSignal.timeout(1500) });
    if (res.ok) data = await res.json();
  } catch (e) { /* 静态模式 */ }
  if (!data) {
    app.innerHTML = `<div class="back-link" data-nav="#/">${t('back')}</div>
      <h2 class="core-title">${t('statsTitle')}</h2>
      <div class="card">${t('needPlatform')}</div>`;
    wireA11y();
    return;
  }
  const pct = data.totals.exercises ? Math.round(100 * data.totals.mastered / data.totals.exercises) : 0;
  const groups = {};
  data.sections.forEach(sec => {
    const m = (sec.topic || '').match(/第\s*(\d+)\s*章/);
    const ch = m ? '第' + m[1] + '章' : '其他';
    (groups[ch] = groups[ch] || []).push(sec);
  });
  let secHtml = '';
  for (const ch of Object.keys(groups)) {
    const meta = CHAPTER_META[ch] || { name: '', color: '#64748b' };
    secHtml += `<div class="chapter-head" style="margin-top:10px"><span class="chapter-dot" style="background:${meta.color}"></span>
      <h3>${esc(ch)}${meta.name ? ' · ' + esc(meta.name) : ''}</h3></div>`;
    for (const sec of groups[ch]) {
      const w = sec.total ? Math.round(100 * sec.mastered / sec.total) : 0;
      secHtml += `<div class="out-row" data-nav="#/core/${esc(sec.id)}" style="cursor:pointer">
        <span>${esc(sec.topic)}</span>
        <b>${sec.mastered} / ${sec.total}<span class="practice-progress" style="width:90px;margin-left:10px;display:inline-block;vertical-align:middle">
          <span class="practice-progress-bar" style="width:${w}%;display:block"></span></span></b></div>`;
    }
  }
  let attHtml = data.recent_attempts.length
    ? data.recent_attempts.map(a => {
        const badge = a.is_correct === true ? t('attemptOk') : a.is_correct === false ? t('attemptBad') : t('attemptNeu');
        const when = a.ts ? new Date(a.ts * 1000).toLocaleString() : '';
        return `<div class="out-row" data-nav="#/core/${esc(a.core_id)}" style="cursor:pointer;align-items:flex-start">
          <span style="min-width:0"><b style="font-size:12px">${esc(a.core_id)} · ${esc(a.case_id)}</b>
          <span class="src-ref" style="margin-left:8px">${esc(when)}</span><br>
          <span style="font-size:12.5px;color:var(--text-2)">${esc((a.text || '').slice(0, 60))}</span></span>
          <b style="color:${a.is_correct === true ? '#047857' : a.is_correct === false ? '#dc2626' : 'var(--text-3)'}">${badge}</b></div>`;
      }).join('')
    : `<div class="viz-caption">${t('noAttempts')}</div>`;
  app.innerHTML = `<div class="back-link" data-nav="#/">${t('back')}</div>
    <h2 class="core-title">${t('statsTitle')}</h2>
    <div class="card" style="margin-top:12px">
      <div class="practice-progress"><div class="practice-progress-bar" style="width:${pct}%"></div></div>
      <div class="practice-count">${t('masteredOf').replace('{m}', data.totals.mastered).replace('{t}', data.totals.exercises)}</div>
    </div>
    <div class="section-title">${t('chapterProgress')}</div>
    <div class="card">${secHtml}</div>
    <div class="section-title">${t('recentAttempts')}</div>
    <div class="card">${attHtml}</div>`;
  wireA11y();
}

// ---------- 设置页 ----------
function renderSettings() {
  const opts = (keys, labels, cur, action) => keys.map(k =>
    `<button class="opt-btn ${cur === k ? 'opt-active' : ''}" data-action="${action}" data-value="${k}">${labels[k]}</button>`).join('');
  const accountCard = authed()
    ? `<div class="card" style="margin-top:14px"><div class="card-top"><b>${t('account')}</b>
        <span class="src-ref">${esc(localStorage.getItem('marrow.email.v1') || '')}</span></div>
      <div class="viz-caption">${t('accountNote')}</div>
      <div class="setting-row"><button class="answer-btn" data-action="logout">${t('logout')}</button></div></div>`
    : `<div class="card" style="margin-top:14px"><div class="card-top"><b>${t('account')}</b></div>
      <div class="setting-row"><input id="authEmail" placeholder="${t('emailPh')}" style="flex:1;min-width:0;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--text)">
        <input id="authPass" type="password" placeholder="${t('passPh')}" style="flex:1;min-width:0;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--surface);color:var(--text)"></div>
      <div class="setting-row"><button class="answer-btn" data-action="login">${t('login')}</button>
        <button class="answer-btn" data-action="register">${t('register')}</button></div>
      <div class="attempt-feedback" id="authMsg"></div></div>`;
  app.innerHTML = `<div class="back-link" data-nav="#/">${t('back')}</div>
    <h2 class="core-title">${t('settings')}</h2>
    ${accountCard}
    <div class="card"><div class="card-top"><b>${t('appearance')}</b></div>
      <div class="setting-row"><span>${t('theme')}</span><div class="opt-group">
        ${opts(['light', 'dark', 'auto'], { light: t('light'), dark: t('dark'), auto: t('auto') }, SETTINGS.theme, 'set-theme')}</div></div>
      <div class="setting-row"><span>${t('font')}</span><div class="opt-group">
        ${opts(['m', 'l'], { m: t('normal'), l: t('large') }, SETTINGS.font, 'set-font')}</div></div>
    </div>
    <div class="card"><div class="card-top"><b>${t('language')}</b></div>
      <div class="setting-row"><span>${t('language')}</span><div class="opt-group">
        ${opts(['zh', 'en'], { zh: '中文', en: 'English' }, SETTINGS.lang, 'set-lang')}</div></div>
      <div class="viz-caption">${t('langNote')}</div>
    </div>
    <div class="card"><div class="card-top"><b>${t('data')}</b></div>
      <div class="setting-row">
        <button class="answer-btn" data-action="export-progress">${t('exportProgress')}</button>
        <label class="answer-btn" style="cursor:pointer">${t('importProgress')}
          <input type="file" id="importFile" accept=".json,application/json" style="display:none"></label>
        <button class="answer-btn" style="background:var(--amber-soft);color:var(--amber)" data-action="clear-progress">${t('clearProgress')}</button>
      </div>
    </div>`;
  wireA11y();
}
function setSetting(kind, value) {
  SETTINGS[kind] = value;
  saveSettings();
  if (kind === 'lang') renderShell(true);
  renderSettings();
}
async function authAction(kind) {
  const email = (document.getElementById('authEmail') || {}).value || '';
  const pass = (document.getElementById('authPass') || {}).value || '';
  const msg = document.getElementById('authMsg');
  if (!email.trim() || !pass) { msg.textContent = t('emailPh') + ' / ' + t('passPh'); return; }
  msg.textContent = '…';
  try {
    const res = await fetch('/api/auth/' + kind, { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim(), password: pass }) });
    const d = await res.json();
    if (d.error) { msg.textContent = t('errPrefix') + d.error; return; }
    localStorage.setItem(TOKEN_KEY, d.token);
    localStorage.setItem('marrow.email.v1', email.trim());
    // 本地 → 服务端，再服务端 → 本地（双向合并）
    const local = Object.keys(getProgress());
    if (local.length) await fetch('/api/progress/bulk', { method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys: local }) }).catch(() => {});
    try {
      const server = await (await fetch('/api/progress', { headers: authHeaders() })).json();
      const prog = getProgress(); let changed = false;
      for (const k of Object.keys(server)) if (!(k in prog)) { prog[k] = 1; changed = true; }
      if (changed) localStorage.setItem(PROGRESS_KEY, JSON.stringify(prog));
    } catch (e) {}
    msg.textContent = t('loginOk');
    renderSettings();
  } catch (e) {
    msg.textContent = t('needPlatform');
  }
}
async function doLogout() {
  await fetch('/api/auth/logout', { method: 'POST', headers: authHeaders() }).catch(() => {});
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem('marrow.email.v1');
  renderSettings();
}
function importProgress(input) {
  const file = input.files && input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    let imported;
    try { imported = JSON.parse(reader.result); } catch (e) { alert(t('importProgressBad')); return; }
    const keys = Object.keys(imported.progress || {});
    if (!keys.length) { alert(t('importProgressBad')); return; }
    let n = 0;
    for (const k of keys) {
      if (!getProgress()[k]) { setDone(k, true); n++; }
      if (PLATFORM_MODE) fetch('/api/progress', { method: 'POST',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: k, done: true }) }).catch(() => {});
    }
    alert(t('importProgressOk').replace('{n}', n));
    router();
  };
  reader.readAsText(file);
}
async function resetSection(coreId) {
  if (!confirm(t('resetConfirm'))) return;
  const prefix = coreId + ':';
  for (const card of document.querySelectorAll('.practice-card[data-key]')) {
    const key = card.dataset.key;
    if (!key.startsWith(prefix)) continue;
    setDone(key, false);
    if (PLATFORM_MODE) fetch('/api/progress', { method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, done: false }) }).catch(() => {});
  }
  router();
}
function clearProgress() {
  localStorage.removeItem(PROGRESS_KEY);
  if (PLATFORM_MODE) fetch('/api/progress/clear', { method: 'POST', headers: authHeaders() }).catch(() => {});
  alert(t('progressCleared'));
  if (location.hash === '#/settings') renderSettings();
}
function exportProgress() {
  const data = { progress: getProgress(), settings: SETTINGS, exportedAt: new Date().toISOString() };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'marrow-progress.json';
  a.click();
}

// ---------- 路由 ----------
function router() {
  renderShell();
  if (location.hash === '#/import') { renderImport(); return; }
  if (location.hash === '#/settings') { renderSettings(); return; }
  if (location.hash === '#/stats') { renderStats(); return; }
  const m = (location.hash || '#/').match(/^#\/core\/(.+)$/);
  if (m) renderCoreDetail(decodeURIComponent(m[1])); else renderHome();
}
window.addEventListener('hashchange', router);
window.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  router();
  if ('serviceWorker' in navigator)
    navigator.serviceWorker.register('sw.js').catch(() => {});
  // 平台模式探测 + 进度服务端同步（user_progress，产品文档步骤）
  (async () => {
    try {
      const h = await (await fetch('/api/health', { signal: AbortSignal.timeout(1200) })).json();
      if (!h.platform) return;
      PLATFORM_MODE = true;
      const server = await (await fetch('/api/progress', { headers: authHeaders() })).json();
      const local = getProgress();
      let changed = false;
      for (const k of Object.keys(server)) if (!(k in local)) { local[k] = 1; changed = true; }
      if (changed) {
        localStorage.setItem(PROGRESS_KEY, JSON.stringify(local));
        if ((location.hash || '#/') === '#/') router();
      }
    } catch (e) { /* 静态模式 */ }
  })();
});
