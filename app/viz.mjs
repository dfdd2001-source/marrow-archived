/* Marrow 探索可视化：全部 SVG 场景渲染器与求值机制。
 *
 * 职责边界：本模块只负责"渲染一个 explorable 配置"——不持有应用状态，
 * 不触碰路由/进度/账号；页面层（app.mjs）通过 renderExplorable(exp, idx) 进入。
 * 一节可含多个探索场景：用 idx 做元素 id 命名空间（p_0_a / outputs-box-0 …），
 * 避免参数 id 跨场景碰撞。
 */
import { esc } from './util.mjs';
import { check as exprAllowed } from './expr_guard.mjs';

// ---------- 求值 ----------
function evalExpr(expr, pv) {
  const names = Object.keys(pv);
  // expr 由提取流水线（LLM）生成，new Function 是"数据即代码"的执行面：
  // 只放行 参数名 + Math 成员 + 算术/比较/三元/数组字面量（expr_guard.mjs）。
  // 校验不过就显式抛错（输出显示 ?），绝不静默求值未知代码。
  if (!exprAllowed(expr, names)) throw new Error('表达式未通过白名单校验');
  const vals = names.map(n => pv[n]);
  return new Function(names.join(','), 'return (' + expr + ');').apply(null, vals);
}

function formatVal(v) {
  if (Array.isArray(v)) {
    if (Array.isArray(v[0])) return v.map(row => '[' + row.join(', ') + ']').join('&nbsp;&nbsp;');
    return '(' + v.join(', ') + ')';
  }
  return String(v);
}

// ---------- 场景入口 ----------
export function renderExplorable(exp, idx) {
  const box = document.getElementById('explorable-box-' + idx);
  const P = p => 'p_' + idx + '_' + p.id, O = p => 'out_' + idx + '_' + p.id;
  const update = () => updateExplorable(exp, idx);
  let html = exp.steps ? `<div class="steps-box">${exp.steps.map(esc).join('<br>')}</div>` : '';
  html += `<div class="viz-container" id="viz-container-${idx}"></div>`;
  html += `<div class="slider-grid">` + exp.parameters.map(p =>
    `<div class="slider-row"><label><span>${esc(p.id)}</span><span id="${O(p)}">${p.default}</span></label>
     <input type="range" id="${P(p)}" min="${p.range[0]}" max="${p.range[1]}" step="${p.step || 1}" value="${p.default}"></div>`).join('') + `</div>`;
  html += `<div class="outputs-box" id="outputs-box-${idx}"></div>`;
  box.innerHTML = html;
  exp.parameters.forEach(p =>
    document.getElementById(P(p)).addEventListener('input', update));
  update();
}

function updateExplorable(exp, idx) {
  const pv = {};
  exp.parameters.forEach(p => {
    const v = parseFloat(document.getElementById('p_' + idx + '_' + p.id).value);
    pv[p.id] = v;
    document.getElementById('out_' + idx + '_' + p.id).textContent = v;
  });
  const viz = document.getElementById('viz-container-' + idx);
  if (exp.viz === 'vectors_2d') renderVectors2D(viz, pv, idx, () => updateExplorable(exp, idx));
  else if (exp.viz === 'bars_match') renderBarsMatch(viz, pv, exp);
  else if (exp.viz === 'projection_2d') renderProjection2D(viz, pv, idx, () => updateExplorable(exp, idx));
  else if (exp.viz === 'gram_schmidt_2d') renderGramSchmidt2D(viz, pv, idx, () => updateExplorable(exp, idx));
  else if (exp.viz === 'mat2d') renderMat2D(viz, [[pv.a, pv.b], [pv.c, pv.d]],
    { badge: `det = ${Math.round((pv.a * pv.d - pv.b * pv.c) * 100) / 100}（单位面积被缩放 |det| 倍）` });
  else if (exp.viz === 'eig_mat2d') renderMat2D(viz, [[pv.a, pv.b], [pv.c, pv.d]],
    { circle: true, eig: true, badge: '绿色箭头是特征方向：M 在这些方向上只做缩放，不改变方向' });
  else if (exp.viz === 'spectral') {
    const M = [[pv.a, pv.b], [pv.b, pv.c]];
    const pos = pv.a > 0 && pv.a * pv.c - pv.b * pv.b > 0;
    renderMat2D(viz, M, { circle: true, eig: true, badge: 'M = Mᵀ 恒成立（对称矩阵）' + (pos ? '，且 ⟨Tv,v⟩ ≥ 0 —— 正算子' : '，且 ⟨Tv,v⟩ 可为负 —— 尚非正算子') });
  } else if (exp.viz === 'svd2d') {
    const r1 = pv.t1 * Math.PI / 180, r2 = pv.t2 * Math.PI / 180;
    const M = [
      [Math.cos(r1) * pv.s1 * Math.cos(r2) - Math.sin(r1) * pv.s2 * Math.sin(r2), Math.cos(r1) * pv.s1 * Math.sin(r2) - Math.sin(r1) * pv.s2 * Math.cos(r2)],
      [Math.sin(r1) * pv.s1 * Math.cos(r2) + Math.cos(r1) * pv.s2 * Math.sin(r2), Math.sin(r1) * pv.s1 * Math.sin(r2) + Math.cos(r1) * pv.s2 * Math.cos(r2)],
    ];
    renderMat2D(viz, M, { circle: true, svd: true, badge: `det = σ₁·σ₂ = ${Math.round(pv.s1 * pv.s2 * 100) / 100}（奇异值分解 M = U·Σ·Vᵀ）` });
  } else if (exp.viz === 'isometry') {
    const r = pv.th * Math.PI / 180;
    renderMat2D(viz, [[Math.cos(r), -Math.sin(r)], [Math.sin(r), Math.cos(r)]],
      { circle: true, badge: '两列范数均为 1、det = 1 —— 等距映射：只旋转，不拉伸' });
  } else if (exp.viz === 'chain') {
    const M = [[pv.a, pv.b], [pv.c, pv.d]], v = [pv.vx, pv.vy];
    renderChain(viz, M, v, 4);
    const Mv = matApply(M, v[0], v[1]), M2v = matApply(M, Mv[0], Mv[1]), M3v = matApply(M, M2v[0], M2v[1]);
    document.getElementById('outputs-box-' + idx).innerHTML =
      `<div class="out-row"><span>Mv</span><b>${formatVal(Mv)}</b></div>
       <div class="out-row"><span>M²v</span><b>${formatVal(M2v)}</b></div>
       <div class="out-row"><span>M³v</span><b>${formatVal(M3v)}</b></div>`;
    return;
  } else if (exp.viz === 'parallelogram') renderParallelogram(viz, pv, idx, () => updateExplorable(exp, idx));
  else if (exp.viz === 'outer') renderOuter(viz, pv);
  else if (exp.viz === 'bilinear') renderBilinear(viz, pv, idx, () => updateExplorable(exp, idx));
  else if (exp.viz === 'matrixcalc') renderMatrixCalc(viz, pv);
  else if (exp.viz === 'vecops') renderVecOps(viz, pv, idx, () => updateExplorable(exp, idx));
  else if (exp.viz === 'span_2d') renderSpan2D(viz, pv, idx, () => updateExplorable(exp, idx));
  else if (exp.viz === 'poly_2d') renderPoly2D(viz, pv);
  else if (exp.viz === 'det_area') renderMat2D(viz, [[pv.a, pv.b], [pv.c, pv.d]],
    { circle: true, badge: `det = ${Math.round((pv.a * pv.d - pv.b * pv.c) * 100) / 100}：单位圆的面积被缩放 |det| 倍——行列式就是体积（面积）缩放因子，det < 0 表示定向翻转` });
  let ohtml = '';
  for (const o of exp.outputs) {
    let v; try { v = evalExpr(o.expr, pv); } catch (e) { v = '?'; }
    ohtml += `<div class="out-row"><span>${esc(o.label)}</span><b>${formatVal(v)}</b></div>`;
  }
  document.getElementById('outputs-box-' + idx).innerHTML = ohtml;
}

// ---------- 2D 向量（可拖拽），用于内积/正交（6A） ----------
function renderVectors2D(container, pv, idx, update) {
  const S = 340, C = S / 2, K = 34, LIM = 4.5;
  if (!container.querySelector('svg')) {
    let grid = '';
    for (let i = -4; i <= 4; i++)
      grid += `<line x1="${C + i * K}" y1="10" x2="${C + i * K}" y2="${S - 10}" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>` +
              `<line x1="10" y1="${C + i * K}" x2="${S - 10}" y2="${C + i * K}" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>`;
    container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${grid}
      <g id="vz-u"><line class="vline" stroke="#6366f1" stroke-width="3" stroke-linecap="round"/>
        <polygon class="vhead" fill="#6366f1"/><text class="vlabel" fill="#6366f1" font-size="14" font-weight="700">u</text>
        <circle class="handle" r="9" fill="rgba(99,102,241,.25)" stroke="#6366f1" stroke-width="2" data-vec="u"/></g>
      <g id="vz-v"><line class="vline" stroke="#ec4899" stroke-width="3" stroke-linecap="round"/>
        <polygon class="vhead" fill="#ec4899"/><text class="vlabel" fill="#ec4899" font-size="14" font-weight="700">v</text>
        <circle class="handle" r="9" fill="rgba(236,72,153,.25)" stroke="#ec4899" stroke-width="2" data-vec="v"/></g>
      <rect id="dotBadge" x="12" y="12" rx="8" width="150" height="26" fill="var(--surface)" stroke="var(--border)"/>
      <text id="dotBadgeText" x="20" y="29" font-size="12.5" fill="var(--text)"></text>
    </svg><div class="viz-caption">直接拖动彩色圆点改变向量 u、v；当两向量垂直时会亮起"正交"提示</div>`;
    attachVecDrag(container, null, idx, update);
  }
  const svg = container.querySelector('svg');
  setArrow(svg.querySelector('#vz-u'), pv.ux, pv.uy, S, C, K);
  setArrow(svg.querySelector('#vz-v'), pv.vx, pv.vy, S, C, K);
  const dot = pv.ux * pv.vx + pv.uy * pv.vy;
  const nu = Math.hypot(pv.ux, pv.uy), nv = Math.hypot(pv.vx, pv.vy);
  const cosT = (nu > 1e-9 && nv > 1e-9) ? dot / (nu * nv) : null;
  const ortho = cosT !== null && Math.abs(cosT) < 0.03;
  const badge = svg.querySelector('#dotBadgeText');
  badge.textContent = `⟨u,v⟩ = ${Math.round(dot * 100) / 100}` + (cosT !== null ? `   cosθ = ${Math.round(cosT * 100) / 100}` : '');
  badge.setAttribute('fill', ortho ? '#047857' : 'var(--text)');
  svg.querySelector('#dotBadge').setAttribute('stroke', ortho ? '#10b981' : 'var(--border)');
  const ob = container.querySelector('.ortho-badge');
  if (ortho && !ob) {
    const div = document.createElement('div');
    div.className = 'ortho-badge'; div.textContent = '⟨u,v⟩ = 0 · 正交！';
    container.appendChild(div);
  } else if (!ortho && ob) ob.remove();
}

// ---------- 正交投影与最小化（6C） ----------
function renderProjection2D(container, pv, idx, update) {
  const S = 340, C = S / 2, K = 34, LIM = 4.5;
  if (!container.querySelector('svg')) {
    let grid = '';
    for (let i = -4; i <= 4; i++)
      grid += `<line x1="${C + i * K}" y1="10" x2="${C + i * K}" y2="${S - 10}" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>` +
              `<line x1="10" y1="${C + i * K}" x2="${S - 10}" y2="${C + i * K}" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>`;
    container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${grid}
      <g id="vz-span"><line class="vline" stroke="#10b981" stroke-width="3" stroke-linecap="round" opacity="0.5"/></g>
      <g id="vz-b"><line class="vline" stroke="#94a3b8" stroke-width="2.5" stroke-linecap="round"/>
        <polygon class="vhead" fill="#94a3b8"/><text class="vlabel" fill="#64748b" font-size="13" font-weight="700">b</text>
        <circle class="handle" r="9" fill="rgba(100,116,139,.2)" stroke="#64748b" stroke-width="2" data-vec="b"/></g>
      <g id="vz-proj"><line class="vline" stroke="#10b981" stroke-width="3.5" stroke-linecap="round"/>
        <polygon class="vhead" fill="#10b981"/><text class="vlabel" fill="#059669" font-size="13" font-weight="700">proj</text>
        <circle class="handle" r="9" fill="rgba(16,185,129,.2)" stroke="#10b981" stroke-width="2" data-vec="u"/></g>
      <line id="errLine" stroke="#dc2626" stroke-width="2" stroke-dasharray="5,4"/>
      <rect id="pBadge" x="12" y="12" rx="8" width="190" height="26" fill="var(--surface)" stroke="var(--border)"/>
      <text id="pBadgeText" x="20" y="29" font-size="12.5" fill="var(--text)"></text>
    </svg><div class="viz-caption">拖动灰点 b 与绿点 u（张成子空间 U）：红色虚线是 b 到 U 的误差向量，绿色是正交投影——它是 U 内离 b 最近的点</div>`;
    attachVecDrag(container, { u: ['ux', 'uy'], b: ['bx', 'by'] }, idx, update);
  }
  const svg = container.querySelector('svg');
  const uu = pv.ux * pv.ux + pv.uy * pv.uy;
  const t = uu ? (pv.bx * pv.ux + pv.by * pv.uy) / uu : 0;
  const px = t * pv.ux, py = t * pv.uy;
  const ex = pv.bx - px, ey = pv.by - py;
  const dist = Math.hypot(ex, ey);
  const X = x => C + x * K, Y = y => C - y * K;
  const un = Math.hypot(pv.ux, pv.uy) || 1;
  const spanLine = svg.querySelector('#vz-span line');
  spanLine.setAttribute('x1', X(-LIM / un * pv.ux)); spanLine.setAttribute('y1', Y(-LIM / un * pv.uy));
  spanLine.setAttribute('x2', X(LIM / un * pv.ux)); spanLine.setAttribute('y2', Y(LIM / un * pv.uy));
  setArrow(svg.querySelector('#vz-b'), pv.bx, pv.by, S, C, K);
  setArrow(svg.querySelector('#vz-proj'), px, py, S, C, K);
  const errLine = svg.querySelector('#errLine');
  errLine.setAttribute('x1', X(px)); errLine.setAttribute('y1', Y(py));
  errLine.setAttribute('x2', X(pv.bx)); errLine.setAttribute('y2', Y(pv.by));
  const badge = svg.querySelector('#pBadgeText');
  badge.textContent = `∥b − proj∥ = ${Math.round(dist * 100) / 100}` + (dist < 0.05 ? '   b 已在 U 内' : '');
  badge.setAttribute('fill', dist < 0.05 ? '#047857' : 'var(--text)');
  svg.querySelector('#pBadge').setAttribute('stroke', dist < 0.05 ? '#10b981' : 'var(--border)');
}

// ---------- 格拉姆-施密特（6B） ----------
function renderGramSchmidt2D(container, pv, idx, update) {
  const S = 340, C = S / 2, K = 34;
  if (!container.querySelector('svg')) {
    let grid = '';
    for (let i = -4; i <= 4; i++)
      grid += `<line x1="${C + i * K}" y1="10" x2="${C + i * K}" y2="${S - 10}" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>` +
              `<line x1="10" y1="${C + i * K}" x2="${S - 10}" y2="${C + i * K}" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>`;
    container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${grid}
      <circle cx="${C}" cy="${C}" r="${K}" fill="none" stroke="var(--border)" stroke-dasharray="3,4"/>
      <g id="vz-v1"><line class="vline" stroke="#6366f1" stroke-width="3" stroke-linecap="round"/>
        <polygon class="vhead" fill="#6366f1"/><text class="vlabel" fill="#6366f1" font-size="13" font-weight="700">v₁</text>
        <circle class="handle" r="9" fill="rgba(99,102,241,.2)" stroke="#6366f1" stroke-width="2" data-vec="v1"/></g>
      <g id="vz-v2"><line class="vline" stroke="#ec4899" stroke-width="3" stroke-linecap="round" opacity="0.55"/>
        <polygon class="vhead" fill="#ec4899" opacity="0.55"/><text class="vlabel" fill="#ec4899" font-size="13" font-weight="700">v₂</text>
        <circle class="handle" r="9" fill="rgba(236,72,153,.2)" stroke="#ec4899" stroke-width="2" data-vec="v2"/></g>
      <g id="vz-proj"><line class="vline" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,4"/></g>
      <g id="vz-w2"><line class="vline" stroke="#f59e0b" stroke-width="3" stroke-linecap="round"/>
        <polygon class="vhead" fill="#f59e0b"/></g>
      <g id="vz-e1"><line class="vline" stroke="#047857" stroke-width="4" stroke-linecap="round"/>
        <polygon class="vhead" fill="#047857"/><text class="vlabel" fill="#047857" font-size="13" font-weight="700">e₁</text></g>
      <g id="vz-e2"><line class="vline" stroke="#0d9488" stroke-width="4" stroke-linecap="round"/>
        <polygon class="vhead" fill="#0d9488"/><text class="vlabel" fill="#0d9488" font-size="13" font-weight="700">e₂</text></g>
      <rect id="gBadge" x="12" y="12" rx="8" width="170" height="26" fill="var(--surface)" stroke="var(--border)"/>
      <text id="gBadgeText" x="20" y="29" font-size="12.5" fill="var(--text)"></text>
    </svg><div class="viz-caption">拖动 v₁、v₂：灰色虚线是 v₂ 在 v₁ 上的投影，橙色 w₂ = v₂ − 投影 与 v₁ 垂直，绿色 e₁、e₂ 是归一化后的规范正交基（恒有 e₁·e₂ = 0）</div>`;
    attachVecDrag(container, { v1: ['v1x', 'v1y'], v2: ['v2x', 'v2y'] }, idx, update);
  }
  const svg = container.querySelector('svg');
  const n1 = Math.hypot(pv.v1x, pv.v1y), n2 = Math.hypot(pv.v2x, pv.v2y);
  const t = (pv.v1x * pv.v1x + pv.v1y * pv.v1y) ? (pv.v2x * pv.v1x + pv.v2y * pv.v1y) / (pv.v1x * pv.v1x + pv.v1y * pv.v1y) : 0;
  const wx = pv.v2x - t * pv.v1x, wy = pv.v2y - t * pv.v1y;
  const nw = Math.hypot(wx, wy);
  const X = x => C + x * K, Y = y => C - y * K;
  setArrow(svg.querySelector('#vz-v1'), pv.v1x, pv.v1y, S, C, K);
  setArrow(svg.querySelector('#vz-v2'), pv.v2x, pv.v2y, S, C, K);
  const projLine = svg.querySelector('#vz-proj line');
  projLine.setAttribute('x1', X(0)); projLine.setAttribute('y1', Y(0));
  projLine.setAttribute('x2', X(t * pv.v1x)); projLine.setAttribute('y2', Y(t * pv.v1y));
  const w2 = svg.querySelector('#vz-w2 line');
  w2.setAttribute('x1', X(t * pv.v1x)); w2.setAttribute('y1', Y(t * pv.v1y));
  w2.setAttribute('x2', X(pv.v2x)); w2.setAttribute('y2', Y(pv.v2y));
  if (n1 > 1e-6) setArrow(svg.querySelector('#vz-e1'), pv.v1x / n1, pv.v1y / n1, S, C, K);
  if (nw > 1e-6) setArrow(svg.querySelector('#vz-e2'), wx / nw, wy / nw, S, C, K);
  const badge = svg.querySelector('#gBadgeText');
  badge.textContent = nw > 1e-6 && n1 > 1e-6
    ? `e₁·e₂ = ${Math.round((pv.v1x / n1 * wx + pv.v1y / n1 * wy) / nw * 1000) / 1000}（恒为 0）`
    : '把 v₁、v₂ 拖开一些';
}

// ---------- 箭头与拖拽基础 ----------
function setArrow(g, x, y, S, C, K) {
  const X = C + x * K, Y = C - y * K, L = Math.hypot(X - C, Y - C) || 1;
  const ux = (X - C) / L, uy = (Y - C) / L, hs = 9;
  g.querySelector('.vline').setAttribute('x1', C); g.querySelector('.vline').setAttribute('y1', C);
  g.querySelector('.vline').setAttribute('x2', X); g.querySelector('.vline').setAttribute('y2', Y);
  const head = g.querySelector('.vhead');
  head.setAttribute('points', `${X},${Y} ${X - hs * ux + hs * .5 * -uy},${Y - hs * uy + hs * .5 * ux} ${X - hs * ux - hs * .5 * -uy},${Y - hs * uy - hs * .5 * ux}`);
  // 派生箭头（u+v、c·u、张成组合等）没有手柄和标签——按需设置
  const lbl = g.querySelector('.vlabel');
  if (lbl) { lbl.setAttribute('x', X + ux * 14); lbl.setAttribute('y', Y - uy * 14 + 4); }
  const h = g.querySelector('.handle');
  if (h) { h.setAttribute('cx', X); h.setAttribute('cy', Y); }
}
function attachVecDrag(container, idMap, idx, update) {
  const idsMap = idMap || { u: ['ux', 'uy'], v: ['vx', 'vy'] };
  const svg = container.querySelector('svg');
  const S = 340, C = S / 2, K = 34, LIM = 4.5;
  let active = null;
  svg.querySelectorAll('.handle').forEach(h =>
    h.addEventListener('pointerdown', e => { active = h.dataset.vec; svg.setPointerCapture(e.pointerId); e.preventDefault(); }));
  svg.addEventListener('pointermove', e => {
    if (!active) return;
    const rect = svg.getBoundingClientRect();
    const mx = ((e.clientX - rect.left) * (S / rect.width) - C) / K;
    const my = -((e.clientY - rect.top) * (S / rect.height) - C) / K;
    const cl = v => Math.max(-LIM, Math.min(LIM, Math.round(v * 2) / 2));
    const ids = idsMap[active];
    if (!ids) return;
    const ex = document.getElementById('p_' + idx + '_' + ids[0]), ey = document.getElementById('p_' + idx + '_' + ids[1]);
    if (ex && update) { ex.value = cl(mx); ey.value = cl(my); update(); }
  });
  const stop = () => { active = null; };
  svg.addEventListener('pointerup', stop);
  svg.addEventListener('pointercancel', stop);
}

// ---------- 分量条形对比（T(v) vs λv），用于特征向量（5A） ----------
function renderBarsMatch(container, pv, exp) {
  const vals = exp.outputs.map(o => { try { return evalExpr(o.expr, pv); } catch (e) { return []; } });
  const tv = Array.isArray(vals[0]) ? vals[0] : [];
  const lv = Array.isArray(vals[1]) ? vals[1] : [];
  const n = Math.min(tv.length, lv.length);
  if (!n) return;
  if (!container.querySelector('.bars')) {
    let rows = '';
    for (let i = 0; i < n; i++)
      rows += `<div class="bar-row"><div class="bar-comp">${'xyzw'[i] || i + 1}</div>
        <div class="bar-pair">
          <div class="bar-track"><div class="bar-fill tv" id="tv${i}"></div></div>
          <div class="bar-track"><div class="bar-fill lv" id="lv${i}"></div></div>
        </div></div>`;
    container.innerHTML = `<div class="bars">${rows}</div>
      <div class="bar-legend"><span><i style="background:#6366f1"></i>T(v) 第 k 个分量</span>
      <span><i style="background:#f472b6"></i>λv 第 k 个分量</span></div>
      <div id="matchBadge"></div>`;
  }
  const maxAbs = Math.max(1, ...tv.map(Math.abs), ...lv.map(Math.abs));
  for (let i = 0; i < n; i++) {
    const t = container.querySelector('#tv' + i), l = container.querySelector('#lv' + i);
    setBar(t, tv[i], maxAbs); setBar(l, lv[i], maxAbs);
  }
  const isMatch = tv.every((v, i) => Math.abs(v - lv[i]) < 1e-9);
  container.querySelector('#matchBadge').innerHTML = isMatch
    ? `<span class="match-badge match-yes">T(v) = λv ✓ —— 这就是一个特征向量！</span>`
    : `<span class="match-badge match-no">调整参数，让两组条形完全对齐</span>`;
}
function setBar(el, v, maxAbs) {
  const half = 50, w = Math.abs(v) / maxAbs * half;
  el.style.left = v >= 0 ? half + '%' : (half - w) + '%';
  el.style.width = Math.max(w, 0.5) + '%';
}

// ---------- 通用 2D 矩阵场景（网格变形/圆→椭圆/行列式/特征向量/SVD） ----------
function matGridStr() {
  let s = '';
  for (let i = -4; i <= 4; i++)
    s += `<line x1="${170 + i * 30}" y1="10" x2="${170 + i * 30}" y2="330" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>` +
         `<line x1="10" y1="${170 + i * 30}" x2="330" y2="${170 + i * 30}" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>`;
  return s;
}
function matApply(M, x, y) { return [M[0][0] * x + M[0][1] * y, M[1][0] * x + M[1][1] * y]; }
function eigen2(M) {
  const tr = M[0][0] + M[1][1], det = M[0][0] * M[1][1] - M[0][1] * M[1][0];
  const disc = tr * tr - 4 * det;
  if (disc < -1e-9) return null;
  const d = Math.sqrt(Math.max(disc, 0));
  const l1 = (tr + d) / 2, l2 = (tr - d) / 2;
  const dir = l => {
    const b = M[0][1], c = M[1][0];
    if (Math.abs(b) > 1e-6) return [b, l - M[0][0]];
    if (Math.abs(c) > 1e-6) return [l - M[1][1], c];
    return Math.abs(l - M[0][0]) < Math.abs(l - M[1][1]) ? [1, 0] : [0, 1];
  };
  return { l1, l2, v1: dir(l1), v2: dir(l2) };
}
function svd2(M) {
  const p = M[0][0] ** 2 + M[1][0] ** 2, q = M[0][0] * M[0][1] + M[1][0] * M[1][1], r = M[0][1] ** 2 + M[1][1] ** 2;
  const disc = Math.sqrt(Math.max((p - r) ** 2 + 4 * q * q, 0));
  return { s1: Math.sqrt((p + r + disc) / 2), s2: Math.sqrt(Math.max((p + r - disc) / 2, 0)) };
}
function arrowSVG(x1, y1, x2, y2, color, w) {
  const L = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / L, uy = (y2 - y1) / L, hs = 9;
  return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${w || 3}" stroke-linecap="round"/>
    <polygon points="${x2},${y2} ${x2 - hs * ux + hs * .5 * -uy},${y2 - hs * uy + hs * .5 * ux} ${x2 - hs * ux - hs * .5 * -uy},${y2 - hs * uy - hs * .5 * ux}" fill="${color}"/>`;
}
function renderMat2D(container, M, opts) {
  opts = opts || {};
  const S = 340, C = S / 2, K = 30, LIM = 4;
  const X = x => C + x * K, Y = y => C - y * K;
  const e1 = matApply(M, 1, 0), e2 = matApply(M, 0, 1);
  const det = M[0][0] * M[1][1] - M[0][1] * M[1][0];
  let body = '';
  if (opts.gridDeform !== false) {
    for (let i = -LIM; i <= LIM; i += 1) {
      let ptsA = [], ptsB = [];
      for (let t = -LIM; t <= LIM; t += 0.5) {
        const A = matApply(M, i, t), B = matApply(M, t, i);
        ptsA.push(`${X(A[0])},${Y(A[1])}`); ptsB.push(`${X(B[0])},${Y(B[1])}`);
      }
      body += `<polyline points="${ptsA.join(' ')}" fill="none" stroke="var(--border)" stroke-width="0.7"/>` +
              `<polyline points="${ptsB.join(' ')}" fill="none" stroke="var(--border)" stroke-width="0.7"/>`;
    }
  }
  body += `<polygon points="${X(0)},${Y(0)} ${X(e1[0])},${Y(e1[1])} ${X(e1[0] + e2[0])},${Y(e1[1] + e2[1])} ${X(e2[0])},${Y(e2[1])}" fill="rgba(79,70,229,.15)" stroke="rgba(79,70,229,.5)"/>`;
  if (opts.circle) {
    let pts = [];
    for (let t = 0; t < 48; t++) {
      const a = t / 48 * 2 * Math.PI, P = matApply(M, Math.cos(a), Math.sin(a));
      pts.push(`${X(P[0])},${Y(P[1])}`);
    }
    body += `<polygon points="${pts.join(' ')}" fill="rgba(236,72,153,.08)" stroke="#ec4899" stroke-width="1.5"/>` +
            `<circle cx="${C}" cy="${C}" r="${K}" fill="none" stroke="var(--text-3)" stroke-dasharray="3,4"/>`;
  }
  body += arrowSVG(X(0), Y(0), X(e1[0]), Y(e1[1]), '#6366f1');
  body += arrowSVG(X(0), Y(0), X(e2[0]), Y(e2[1]), '#ec4899');
  if (opts.eig) {
    const ev = eigen2(M);
    if (ev && Math.abs(det) > 1e-9) {
      const n1 = Math.hypot(ev.v1[0], ev.v1[1]) || 1, n2 = Math.hypot(ev.v2[0], ev.v2[1]) || 1;
      body += arrowSVG(X(0), Y(0), X(ev.v1[0] / n1 * 2.2), Y(ev.v1[1] / n1 * 2.2), '#047857', 2.5);
      body += arrowSVG(X(0), Y(0), X(ev.v2[0] / n2 * 2.2), Y(ev.v2[1] / n2 * 2.2), '#0d9488', 2.5);
      body += `<text x="${X(ev.v1[0] / n1 * 2.5)}" y="${Y(ev.v1[1] / n1 * 2.5)}" font-size="11" fill="#047857">λ=${Math.round(ev.l1 * 100) / 100}</text>`;
      body += `<text x="${X(ev.v2[0] / n2 * 2.5)}" y="${Y(ev.v2[1] / n2 * 2.5)}" font-size="11" fill="#0d9488">λ=${Math.round(ev.l2 * 100) / 100}</text>`;
    }
  }
  if (opts.svd) {
    const { s1, s2 } = svd2(M);
    body += `<text x="14" y="46" font-size="12" fill="#ec4899">奇异值 σ₁=${Math.round(s1 * 100) / 100}，σ₂=${Math.round(s2 * 100) / 100}</text>`;
  }
  const badge = opts.badge !== undefined ? opts.badge : `det = ${Math.round(det * 100) / 100}`;
  container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${body}</svg>
    <div class="match-badge ${opts.badgeClass || 'match-no'}">${esc(String(badge))}</div>`;
}

// ---------- 特征向量链（8A） ----------
function renderChain(container, M, v, L) {
  const S = 340, C = S / 2, K = 30;
  const X = x => C + x * K, Y = y => C - y * K;
  const colors = ['#94a3b8', '#6366f1', '#0ea5e9', '#f59e0b', '#10b981'];
  let body = matGridStr();
  let cur = v.slice();
  for (let k = 0; k <= L; k++) {
    const l = Math.hypot(cur[0], cur[1]);
    if (l > 1e-6)
      body += arrowSVG(X(0), Y(0), X(cur[0]), Y(cur[1]), colors[Math.min(k, colors.length - 1)], 3.5 - k * 0.4) +
        `<text x="${X(cur[0]) + 6}" y="${Y(cur[1]) - 6}" font-size="11.5" fill="${colors[Math.min(k, colors.length - 1)]}">${k === 0 ? 'v' : 'M' + (k === 1 ? '' : '^' + k) + 'v'}</text>`;
    cur = matApply(M, cur[0], cur[1]);
  }
  container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${body}</svg>`;
}

// ---------- 平行四边形带符号面积（9B） ----------
function renderParallelogram(container, pv, idx, update) {
  const S = 340, C = S / 2, K = 30;
  const X = x => C + x * K, Y = y => C - y * K;
  const det = pv.ux * pv.vy - pv.uy * pv.vx;
  container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${matGridStr()}
    <polygon points="${X(0)},${Y(0)} ${X(pv.ux)},${Y(pv.uy)} ${X(pv.ux + pv.vx)},${Y(pv.uy + pv.vy)} ${X(pv.vx)},${Y(pv.vy)}"
      fill="${det >= 0 ? 'rgba(16,185,129,.25)' : 'rgba(220,38,38,.25)'}" stroke="${det >= 0 ? '#10b981' : '#dc2626'}"/>
    ${arrowSVG(X(0), Y(0), X(pv.ux), Y(pv.uy), '#6366f1')}
    ${arrowSVG(X(0), Y(0), X(pv.vx), Y(pv.vy), '#ec4899')}
    <text x="${X(pv.ux / 2)}" y="${Y(pv.uy / 2) - 6}" font-size="12" fill="#6366f1">u</text>
    <text x="${X(pv.vx / 2)}" y="${Y(pv.vy / 2) - 6}" font-size="12" fill="#ec4899">v</text>
  </svg>
  <div class="match-badge ${det >= 0 ? 'match-yes' : 'match-no'}">交错型 (u,v) = ${Math.round(det * 100) / 100} ${det > 0 ? '（u 在 v 的逆时针侧）' : det < 0 ? '（u 在 v 的顺时针侧——交换两向量会变号！）' : '（共线，退化为 0）'}</div>
  <div class="viz-caption">拖动 u、v 的手柄：平行四边形面积是 |交错值|，交换 u、v 则变号——这就是"交错"的含义</div>`;
  attachVecDrag(container, { u: ['ux', 'uy'], v: ['vx', 'vy'] }, idx, update);
}

// ---------- 张量积外积热图（9D） ----------
function renderOuter(container, pv) {
  const cells = [[pv.ux * pv.vx, pv.ux * pv.vy], [pv.uy * pv.vx, pv.uy * pv.vy]];
  const maxAbs = Math.max(0.001, ...cells.flat().map(Math.abs));
  let grid = '';
  for (let i = 0; i < 2; i++)
    for (let j = 0; j < 2; j++) {
      const val = cells[i][j], inten = Math.abs(val) / maxAbs;
      const bg = val >= 0 ? `rgba(79,70,229,${0.15 + 0.6 * inten})` : `rgba(220,38,38,${0.15 + 0.6 * inten})`;
      grid += `<div style="background:${bg};border-radius:10px;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:14px 6px">
        <div style="font-size:11px;opacity:.85">u${i === 0 ? '₁' : '₂'}v${j === 0 ? '₁' : '₂'}</div>
        <div style="font-size:18px;font-weight:700;font-variant-numeric:tabular-nums">${Math.round(val * 100) / 100}</div></div>`;
    }
  container.innerHTML = `<div class="viz-caption">u ⊗ v 是一个 2×2 矩阵：第 i 行第 j 列 = uᵢ·vⱼ（蓝=正，红=负，深浅=大小）</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;max-width:320px;margin:8px auto">${grid}</div>`;
}

// ---------- 双线性型 uᵀBv（9A） ----------
function renderBilinear(container, pv, idx, update) {
  const S = 340, C = S / 2, K = 30;
  const B = [[pv.m11, pv.m12], [pv.m12, pv.m22]];
  const Bu = matApply(B, pv.ux, pv.uy);
  const val = pv.ux * Bu[0] + pv.uy * Bu[1];
  const X = x => C + x * K, Y = y => C - y * K;
  container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${matGridStr()}
    ${arrowSVG(X(0), Y(0), X(pv.ux), Y(pv.uy), '#6366f1')}
    ${arrowSVG(X(0), Y(0), X(pv.vx), Y(pv.vy), '#ec4899')}
    ${arrowSVG(X(0), Y(0), X(Bu[0]), Y(Bu[1]), '#f59e0b')}
    <text x="${X(Bu[0]) + 6}" y="${Y(Bu[1]) - 6}" font-size="12" fill="#f59e0b">B(u)</text>
    <text x="${X(pv.vx) + 6}" y="${Y(pv.vy) - 6}" font-size="12" fill="#ec4899">v</text>
  </svg>
  <div class="match-badge ${Math.abs(val) < 0.03 ? 'match-yes' : 'match-no'}">β(u,v) = uᵀBv = ${Math.round(val * 100) / 100}${Math.abs(val) < 0.03 ? ' —— 关于 B 正交！' : ''}</div>
  <div class="viz-caption">黄色 B(u) = B 作用于 u；β(u,v) = v 与 B(u) 的点积。B 对称时这就是一个双线性型</div>`;
  attachVecDrag(container, { u: ['ux', 'uy'], v: ['vx', 'vy'] }, idx, update);
}

// ---------- 矩阵计算器（凯莱-哈密顿，5B/8C） ----------
function renderMatrixCalc(container, pv) {
  const a = pv.a, b = pv.b, c = pv.c, d = pv.d;
  const A2 = [[a * a + b * c, a * b + b * d], [c * a + d * c, c * b + d * d]];
  const tr = a + d, det = a * d - b * c;
  const pA = [[A2[0][0] - tr * a + det, A2[0][1] - tr * b], [A2[1][0] - tr * c, A2[1][1] - tr * d + det]];
  const isZero = pA.flat().every(x => Math.abs(x) < 1e-9);
  const rnd = x => Math.round(x * 100) / 100;
  const mat = (M, label) => `<div><div style="font-size:11px;color:var(--text-2);margin-bottom:3px">${label}</div>
    <div style="font-family:ui-monospace,monospace;font-size:13px;line-height:1.5">${M.map(r => '[' + r.map(rnd).join(', ') + ']').join('<br>')}</div></div>`;
  container.innerHTML = `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
    ${mat([[a, b], [c, d]], 'A')}${mat(A2, 'A²')}
    ${mat([[tr, 0], [0, tr]], 'tr(A)·I = ' + rnd(tr) + '·I')}${mat([[det, 0], [0, det]], 'det(A)·I = ' + rnd(det) + '·I')}
  </div>
  <div class="match-badge ${isZero ? 'match-yes' : 'match-no'}" style="margin-top:12px">p(A) = A² − tr(A)·A + det(A)·I ${isZero ? '= 0 ✓ —— 凯莱-哈密顿定理' : ''}</div>`;
}

// ---------- 向量加法与标量乘法（1A/1B） ----------
function renderVecOps(container, pv, idx, update) {
  const S = 340, C = S / 2, K = 34;
  if (!container.querySelector('svg')) {
    container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${matGridStr()}
      <g id="vo-cu"><line class="vline" stroke="#f59e0b" stroke-width="3" stroke-linecap="round"/>
        <polygon class="vhead" fill="#f59e0b"/><text class="vlabel" fill="#d97706" font-size="13" font-weight="700">c·u</text></g>
      <g id="vo-sum"><line class="vline" stroke="#10b981" stroke-width="3.5" stroke-linecap="round"/>
        <polygon class="vhead" fill="#10b981"/><text class="vlabel" fill="#059669" font-size="13" font-weight="700">u+v</text></g>
      <g id="vo-u"><line class="vline" stroke="#6366f1" stroke-width="3" stroke-linecap="round"/>
        <polygon class="vhead" fill="#6366f1"/><text class="vlabel" fill="#6366f1" font-size="14" font-weight="700">u</text>
        <circle class="handle" r="9" fill="rgba(99,102,241,.25)" stroke="#6366f1" stroke-width="2" data-vec="u"/></g>
      <g id="vo-v"><line class="vline" stroke="#ec4899" stroke-width="3" stroke-linecap="round"/>
        <polygon class="vhead" fill="#ec4899"/><text class="vlabel" fill="#ec4899" font-size="14" font-weight="700">v</text>
        <circle class="handle" r="9" fill="rgba(236,72,153,.25)" stroke="#ec4899" stroke-width="2" data-vec="v"/></g>
      <rect id="voBadgeBg" x="12" y="12" rx="8" width="230" height="26" fill="var(--surface)" stroke="var(--border)"/>
      <text id="voBadge" x="20" y="29" font-size="12.5" fill="var(--text)"></text>
    </svg><div class="viz-caption">拖动 u、v：绿色箭头是 u + v（平行四边形法则）；橙色是 c·u——标量 c 只改变长度，c &lt; 0 时反向。加法与标量乘法的结果都仍是向量（封闭性）</div>`;
    attachVecDrag(container, { u: ['ux', 'uy'], v: ['vx', 'vy'] }, idx, update);
  }
  const svg = container.querySelector('svg');
  setArrow(svg.querySelector('#vo-u'), pv.ux, pv.uy, S, C, K);
  setArrow(svg.querySelector('#vo-v'), pv.vx, pv.vy, S, C, K);
  setArrow(svg.querySelector('#vo-sum'), pv.ux + pv.vx, pv.uy + pv.vy, S, C, K);
  setArrow(svg.querySelector('#vo-cu'), pv.c * pv.ux, pv.c * pv.uy, S, C, K);
  const rnd = x => Math.round(x * 100) / 100;
  svg.querySelector('#voBadge').textContent =
    `u+v = (${rnd(pv.ux + pv.vx)}, ${rnd(pv.uy + pv.vy)})   c·u = (${rnd(pv.c * pv.ux)}, ${rnd(pv.c * pv.uy)})`;
}

// ---------- 张成 / 线性无关 / 坐标（1C/2A/2B/2C） ----------
function renderSpan2D(container, pv, idx, update) {
  const S = 340, C = S / 2, K = 30, L = 4;
  if (!container.querySelector('svg')) {
    container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${matGridStr()}
      <polygon id="spanArea" points="" fill="rgba(16,185,129,.10)" stroke="rgba(16,185,129,.45)" stroke-width="1.2"/>
      <line id="spanLine" stroke="#10b981" stroke-width="4" stroke-linecap="round" opacity="0.55" visibility="hidden"/>
      <polyline id="coordPath" points="" fill="none" stroke="#94a3b8" stroke-width="2" stroke-dasharray="5,4"/>
      <g id="sp-a"><line class="vline" stroke="#6366f1" stroke-width="3" stroke-linecap="round"/>
        <polygon class="vhead" fill="#6366f1"/><text class="vlabel" fill="#6366f1" font-size="14" font-weight="700">a</text>
        <circle class="handle" r="9" fill="rgba(99,102,241,.25)" stroke="#6366f1" stroke-width="2" data-vec="a"/></g>
      <g id="sp-b"><line class="vline" stroke="#ec4899" stroke-width="3" stroke-linecap="round"/>
        <polygon class="vhead" fill="#ec4899"/><text class="vlabel" fill="#ec4899" font-size="14" font-weight="700">b</text>
        <circle class="handle" r="9" fill="rgba(236,72,153,.25)" stroke="#ec4899" stroke-width="2" data-vec="b"/></g>
      <g id="sp-v"><line class="vline" stroke="#94a3b8" stroke-width="2.5" stroke-linecap="round"/>
        <polygon class="vhead" fill="#94a3b8"/><text class="vlabel" fill="#64748b" font-size="14" font-weight="700">v</text>
        <circle class="handle" r="9" fill="rgba(100,116,139,.2)" stroke="#64748b" stroke-width="2" data-vec="v"/></g>
      <rect id="spBadgeBg" x="12" y="12" rx="8" width="240" height="26" fill="var(--surface)" stroke="var(--border)"/>
      <text id="spBadge" x="20" y="29" font-size="12" fill="var(--text)"></text>
    </svg><div class="viz-caption">拖动 a、b、v：绿色区域是张成 span{a,b}（共线时退化成一条直线）；灰色 v 能否写成 c₁a + c₂b？虚线路径就是分解，坐标即系数——这正是"基"的含义</div>`;
    attachVecDrag(container, { a: ['ax', 'ay'], b: ['bx', 'by'], v: ['vx', 'vy'] }, idx, update);
  }
  const svg = container.querySelector('svg');
  const X = x => C + x * K, Y = y => C - y * K;
  const det = pv.ax * pv.by - pv.ay * pv.bx;
  const indep = Math.abs(det) > 1e-9;
  const area = svg.querySelector('#spanArea'), line = svg.querySelector('#spanLine');
  if (indep) {
    const P = (s, t) => `${X(s * pv.ax + t * pv.bx)},${Y(s * pv.ay + t * pv.by)}`;
    area.setAttribute('points', `${P(-L, -L)} ${P(L, -L)} ${P(L, L)} ${P(-L, L)}`);
    area.setAttribute('visibility', 'visible'); line.setAttribute('visibility', 'hidden');
  } else {
    area.setAttribute('visibility', 'hidden');
    const n = Math.hypot(pv.ax, pv.ay) || 1;
    line.setAttribute('x1', X(-L / n * pv.ax)); line.setAttribute('y1', Y(-L / n * pv.ay));
    line.setAttribute('x2', X(L / n * pv.ax)); line.setAttribute('y2', Y(L / n * pv.ay));
    line.setAttribute('visibility', 'visible');
  }
  const path = svg.querySelector('#coordPath');
  let badge;
  if (indep) {
    const c1 = (pv.vx * pv.by - pv.vy * pv.bx) / det;
    const c2 = (pv.ax * pv.vy - pv.ay * pv.vx) / det;
    path.setAttribute('points', `${X(0)},${Y(0)} ${X(c1 * pv.ax)},${Y(c1 * pv.ay)} ${X(pv.vx)},${Y(pv.vy)}`);
    path.setAttribute('visibility', 'visible');
    badge = `det = ${Math.round(det * 100) / 100} ≠ 0：a、b 线性无关；v = ${Math.round(c1 * 100) / 100}·a + ${Math.round(c2 * 100) / 100}·b`;
  } else {
    const onLine = Math.abs(pv.vx * pv.ay - pv.vy * pv.ax) < 1e-6;
    path.setAttribute('visibility', 'hidden');
    badge = `det = 0：a、b 共线，张成只是一条直线${onLine ? '，v 在其中' : '，v 不在其中'}——不是 R² 的基`;
  }
  svg.querySelector('#spBadge').textContent = badge;
  setArrow(svg.querySelector('#sp-a'), pv.ax, pv.ay, S, C, K);
  setArrow(svg.querySelector('#sp-b'), pv.bx, pv.by, S, C, K);
  setArrow(svg.querySelector('#sp-v'), pv.vx, pv.vy, S, C, K);
}

// ---------- 多项式曲线与零点计数（4A） ----------
function renderPoly2D(container, pv) {
  const S = 340, C = S / 2;
  const p = x => pv.a0 + pv.a1 * x + pv.a2 * x * x + pv.a3 * x * x * x;
  const deg = pv.a3 !== 0 ? 3 : (pv.a2 !== 0 ? 2 : (pv.a1 !== 0 ? 1 : (pv.a0 !== 0 ? 0 : -1)));
  if (!container.querySelector('svg')) {
    let grid = '';
    for (let i = -3; i <= 3; i++)
      grid += `<line x1="${C + i * 45}" y1="10" x2="${C + i * 45}" y2="330" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>` +
              `<line x1="10" y1="${C + i * 45}" x2="330" y2="${C + i * 45}" stroke="var(--border)" stroke-width="${i === 0 ? 1.5 : 0.6}"/>`;
    container.innerHTML = `<svg viewBox="0 0 ${S} ${S}" class="vec-svg">${grid}
      <polyline id="polyCurve" points="" fill="none" stroke="#6366f1" stroke-width="2.5" stroke-linecap="round"/>
      <g id="polyRoots"></g>
      <rect id="plBadgeBg" x="12" y="12" rx="8" width="240" height="26" fill="var(--surface)" stroke="var(--border)"/>
      <text id="plBadge" x="20" y="29" font-size="12" fill="var(--text)"></text>
    </svg><div class="viz-caption">四个滑杆是多项式 p(x) = a₀ + a₁x + a₂x² + a₃x³ 的系数：蓝色圆点是实零点。数一数：实零点个数永远 ≤ 次数 n（算法"零点计数上限"）；代数基本定理说在 C 上恰有 n 个（计重数）</div>`;
  }
  const svg = container.querySelector('svg');
  const KX = 45, pts = [];
  let ymax = 1e-9;
  const samples = [];
  for (let i = -66; i <= 66; i++) { const x = i / 22; samples.push([x, p(x)]); ymax = Math.max(ymax, Math.abs(p(x))); }
  const KY = Math.min(140 / Math.max(ymax, 1), 90);
  for (const [x, y] of samples) {
    const cy = Math.max(8, Math.min(332, C - y * KY));
    pts.push(`${C + x * KX},${cy}`);
  }
  svg.querySelector('#polyCurve').setAttribute('points', pts.join(' '));
  let roots = '';
  for (let i = 1; i < samples.length; i++) {
    const [x0, y0] = samples[i - 1], [x1, y1] = samples[i];
    if (Math.abs(y0) < 1e-9) roots += `<circle cx="${C + x0 * KX}" cy="${C}" r="4.5" fill="#047857"/>`;
    else if (y0 * y1 < 0) {
      const xr = x0 + (x1 - x0) * (y0 / (y0 - y1));
      roots += `<circle cx="${C + xr * KX}" cy="${C}" r="4.5" fill="#047857"/>`;
    }
  }
  svg.querySelector('#polyRoots').innerHTML = roots;
  const k = svg.querySelector('#polyRoots').childElementCount;
  svg.querySelector('#plBadge').textContent = deg < 0
    ? '零多项式：次数没有定义，有无穷多零点'
    : `次数 n = ${deg}，实零点 ${k} 个（k ≤ n）`;
}
