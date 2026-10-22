(() => {
  const BOOT = window.__EXAMLENS__;
  const D = BOOT.data;
  document.documentElement.dataset.theme = BOOT.theme;

  // ---------- helpers ----------
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const nf = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const pc = (v, d = 0) => (v == null ? "–" : nf(v * 100, d) + "%");
  const diffColor = (v) => (v < 25 ? "#34c759" : v < 45 ? "#ff9500" : "#ff453a");
  const LEVEL = { High: "#ff453a", Medium: "#ff9f0a", Low: "#30d158" };
  const AV = ["#0a84ff", "#5e5ce6", "#bf5af2", "#ff9500", "#40c8e0", "#ff2d55", "#34c759"];
  const avColor = (s) => AV[[...String(s)].reduce((a, c) => a + c.charCodeAt(0), 0) % AV.length];
  const initials = (n) => String(n).split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  const avatar = (n) => `<span class="av" style="background:${avColor(n)}">${esc(initials(n))}</span>`;
  let uid = 0;
  let cardIndex = 0;
  const card = (cls, inner, style = "") => `<section class="card ${cls}" style="--i:${cardIndex++};${style}">${inner}</section>`;
  const head = (title, sub = "", right = "") => `<div class="ch"><div><div class="ct">${title}</div>${sub ? `<div class="cs">${sub}</div>` : ""}</div>${right}</div>`;

  const tip = Object.assign(document.createElement("div"), { className: "tip" });
  document.body.appendChild(tip);
  const showTip = (html, e) => {
    tip.innerHTML = html;
    tip.style.opacity = 1;
    const r = tip.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
    tip.style.transform = `translate(${x}px,${y}px)`;
  };
  const hideTip = () => (tip.style.opacity = 0);

  const onSize = (el, draw) => {
    el.__draw = draw;
    const run = () => { const w = Math.round(el.clientWidth); if (w) { el.__last = w; el.__draw(w, Math.round(el.clientHeight) || 240); } };
    if (!el.__ro) {
      el.__ro = new ResizeObserver(() => { if (Math.round(el.clientWidth) !== el.__last) run(); });
      el.__ro.observe(el);
    } else run();
  };
  const smooth = (pts) => {
    if (pts.length < 2) return "";
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
      d += ` C${p1[0] + (p2[0] - p0[0]) / 6},${p1[1] + (p2[1] - p0[1]) / 6} ${p2[0] - (p3[0] - p1[0]) / 6},${p2[1] - (p3[1] - p1[1]) / 6} ${p2[0]},${p2[1]}`;
    }
    return d;
  };
  const niceStep = (maxV, n = 4) => {
    const raw = maxV / n, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  };
  const trunc = (s, n) => (s.length > n ? s.slice(0, Math.max(1, n - 1)) + "…" : s);

  // ---------- chart primitives ----------
  function areaLine(el, { labels, series, yMax = 100, unit = "%" }) {
    onSize(el, (w, h) => {
      const m = { l: 36, r: 16, t: 14, b: 28 }, iw = w - m.l - m.r, ih = h - m.t - m.b, id = ++uid;
      const x = (i) => m.l + (labels.length > 1 ? (i / (labels.length - 1)) * iw : iw / 2);
      const y = (v) => m.t + ih - (v / yMax) * ih;
      let s = `<svg width="${w}" height="${h}"><defs>${series.map((q, k) => `<linearGradient id="g${id}${k}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${q.color}" stop-opacity=".32"/><stop offset="1" stop-color="${q.color}" stop-opacity="0"/></linearGradient>`).join("")}</defs>`;
      for (let g = 0; g <= 4; g++) {
        const v = (yMax / 4) * g;
        s += `<line class="gridl" x1="${m.l}" x2="${w - m.r}" y1="${y(v)}" y2="${y(v)}"/><text class="axl" x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end">${Math.round(v)}</text>`;
      }
      labels.forEach((l, i) => (s += `<text class="axl" x="${x(i)}" y="${h - 6}" text-anchor="middle">${esc(l)}</text>`));
      series.forEach((q, k) => {
        const pts = q.values.map((v, i) => (v == null ? null : [x(i), y(v)])).filter(Boolean);
        if (pts.length < 2) return;
        const d = smooth(pts);
        if (q.area !== false) s += `<path class="area" d="${d} L${pts[pts.length - 1][0]},${y(0)} L${pts[0][0]},${y(0)} Z" fill="url(#g${id}${k})"/>`;
        s += `<path class="line" pathLength="1" d="${d}" stroke="${q.color}" ${q.dash ? 'style="stroke-width:2.2"' : ""}/>`;
        pts.forEach((p, i) => (s += `<circle class="dot" style="--k:${i}" cx="${p[0]}" cy="${p[1]}" r="4" fill="${q.color}" stroke="var(--solid)" stroke-width="2"/>`));
      });
      s += `<line id="cx${id}" y1="${m.t}" y2="${m.t + ih}" stroke="var(--text2)" stroke-dasharray="3 4" opacity="0"/><rect id="hv${id}" x="${m.l}" y="${m.t}" width="${iw}" height="${ih}" fill="transparent"/></svg>`;
      el.innerHTML = s;
      const hv = $(`#hv${id}`, el), cx = $(`#cx${id}`, el);
      hv.addEventListener("mousemove", (e) => {
        const r = hv.getBoundingClientRect();
        const i = Math.max(0, Math.min(labels.length - 1, Math.round(((e.clientX - r.left) / r.width) * (labels.length - 1))));
        cx.setAttribute("x1", x(i)); cx.setAttribute("x2", x(i)); cx.setAttribute("opacity", 0.6);
        showTip(`<b>${esc(labels[i])}</b><br>${series.map((q) => `<i style="background:${q.color}"></i>${esc(q.name)}: <b>${q.values[i] == null ? "–" : nf(q.values[i], 1) + unit}</b>`).join("<br>")}`, e);
      });
      hv.addEventListener("mouseleave", () => { cx.setAttribute("opacity", 0); hideTip(); });
    });
  }

  function bars(el, { labels, values, colors, max, fmt = (v) => nf(v), ticks = 4, tipFn }) {
    onSize(el, (w, h) => {
      const m = { l: 36, r: 6, t: 22, b: 30 }, iw = w - m.l - m.r, ih = h - m.t - m.b;
      const maxV = Math.max(...values.filter((v) => v != null), 1);
      let step = max ? max / ticks : niceStep(maxV * 1.04, ticks);
      const top = max || Math.ceil((maxV * 1.04) / step) * step;
      const bw = iw / labels.length, bwid = Math.min(54, bw * 0.62);
      const y = (v) => m.t + ih - (v / top) * ih;
      let s = `<svg width="${w}" height="${h}">`;
      for (let v = 0; v <= top + 1e-9; v += step) {
        s += `<line class="gridl" x1="${m.l}" x2="${w - m.r}" y1="${y(v)}" y2="${y(v)}"/><text class="axl" x="${m.l - 7}" y="${y(v) + 4}" text-anchor="end">${nf(v, step < 1 ? 1 : 0)}</text>`;
      }
      labels.forEach((l, i) => {
        const cx = m.l + bw * i + bw / 2, v = values[i] ?? 0, c = Array.isArray(colors) ? colors[i] : colors;
        s += `<rect class="bar" data-i="${i}" style="--k:${i}" x="${cx - bwid / 2}" y="${y(v)}" width="${bwid}" height="${Math.max(0, m.t + ih - y(v))}" rx="${Math.min(9, bwid / 2.2)}" fill="${c}"/>`;
        s += `<text class="axl" x="${cx}" y="${y(v) - 6}" text-anchor="middle" style="fill:var(--text);font-weight:600">${fmt(v)}</text>`;
        s += `<text class="axl" x="${cx}" y="${h - 9}" text-anchor="middle">${esc(trunc(String(l), Math.floor(bw / 5.4)))}</text>`;
      });
      el.innerHTML = s + "</svg>";
      $$(".bar", el).forEach((b) => {
        const i = +b.dataset.i;
        b.addEventListener("mousemove", (e) => showTip(tipFn ? tipFn(i) : `<b>${esc(labels[i])}</b><br>${fmt(values[i])}`, e));
        b.addEventListener("mouseleave", hideTip);
      });
    });
  }

  function donut(el, { items, center }) {
    onSize(el, (w, h) => {
      const size = Math.min(w, h), R = size / 2 - 18, sw = Math.max(16, R * 0.27), C = 2 * Math.PI * R;
      const total = items.reduce((a, b) => a + b.value, 0) || 1;
      let off = 0, arcs = "";
      items.forEach((it, k) => {
        const len = (it.value / total) * C, gap = it.value ? 3 : 0;
        arcs += `<circle class="seg-arc" data-k="${k}" style="--k:${k};--circ:${C}" cx="${w / 2}" cy="${h / 2}" r="${R}" stroke="${it.color}" stroke-width="${sw}" stroke-linecap="butt" stroke-dasharray="${Math.max(0, len - gap)} ${C}" stroke-dashoffset="${-off}" transform="rotate(-90 ${w / 2} ${h / 2})"/>`;
        off += len;
      });
      el.innerHTML = `<svg width="${w}" height="${h}">${arcs}<text x="${w / 2}" y="${h / 2 - 2}" text-anchor="middle" style="font-size:${R * 0.4}px;font-weight:700;letter-spacing:-.04em;fill:var(--text)">${center[0]}</text><text x="${w / 2}" y="${h / 2 + R * 0.28}" text-anchor="middle" class="axl" style="font-size:12px">${center[1]}</text></svg>`;
      $$(".seg-arc", el).forEach((a) => {
        const it = items[+a.dataset.k];
        a.addEventListener("mousemove", (e) => { a.style.opacity = 1; showTip(`<i style="background:${it.color}"></i><b>${esc(it.label)}</b><br>${nf(it.value)} (${nf((it.value / total) * 100, 1)}%)`, e); });
        a.addEventListener("mouseleave", hideTip);
      });
    });
  }

  function scatter(el, { points }) {
    onSize(el, (w, h) => {
      const m = { l: 40, r: 18, t: 16, b: 34 }, iw = w - m.l - m.r, ih = h - m.t - m.b;
      const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
      const x0 = Math.floor((Math.min(...xs) - 2) / 5) * 5, x1 = Math.ceil((Math.max(...xs) + 2) / 5) * 5, y0 = Math.floor((Math.min(...ys) - 4) / 10) * 10, y1 = Math.min(100, Math.ceil((Math.max(...ys) + 4) / 10) * 10);
      const X = (v) => m.l + ((v - x0) / (x1 - x0)) * iw, Y = (v) => m.t + ih - ((v - y0) / (y1 - y0)) * ih;
      let s = `<svg width="${w}" height="${h}">`;
      for (let v = y0; v <= y1; v += 10) s += `<line class="gridl" x1="${m.l}" x2="${w - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axl" x="${m.l - 8}" y="${Y(v) + 4}" text-anchor="end">${v}</text>`;
      for (let v = x0; v <= x1; v += 5) s += `<text class="axl" x="${X(v)}" y="${h - 14}" text-anchor="middle">${v}</text>`;
      s += `<text class="axl" x="${m.l + iw / 2}" y="${h - 1}" text-anchor="middle">Mean mark</text>`;
      points.forEach((p, i) => {
        const r = 6 + Math.sqrt(p.r) * 0.55;
        s += `<circle class="dot pt" data-i="${i}" style="--k:${i}" cx="${X(p.x)}" cy="${Y(p.y)}" r="${r}" fill="${p.color}" fill-opacity=".78" stroke="var(--solid)" stroke-width="1.5"/>`;
        if (p.show) s += `<text class="axl" x="${X(p.x)}" y="${Y(p.y) - r - 5}" text-anchor="middle" style="fill:var(--text);font-weight:600">${esc(p.label)}</text>`;
      });
      el.innerHTML = s + "</svg>";
      $$(".pt", el).forEach((c) => {
        const p = points[+c.dataset.i];
        c.addEventListener("mousemove", (e) => showTip(`<b>${esc(p.label)}</b> · ${esc(p.name)}<br>Mean ${nf(p.x, 1)} · Pass ${nf(p.y, 0)}%<br>Difficulty ${nf(p.d, 0)}`, e));
        c.addEventListener("mouseleave", hideTip);
      });
    });
  }

  function funnelChart(el, f) {
    const steps = [["Attempted", f.attempted, "var(--blue)"], ["Passed first time", f.first, "#34c759"], ["Passed second time", f.second, "#40c8e0"], ["Passed later", f.later, "#5e5ce6"], ["Still outstanding", f.outstanding, "#ff453a"]];
    const max = Math.max(f.attempted, 1);
    el.innerHTML = `<div class="rows" style="gap:15px">${steps.map(([l, v, c]) => `<div><div class="ri"><div class="rt">${l}</div><div class="rv">${nf(v)}</div></div><div class="track" style="height:11px"><i style="width:${(v / max) * 100}%;background:${c}"></i></div></div>`).join("")}</div>`;
  }

  function sparkSvg(values, color) {
    const v = values.filter((x) => x != null);
    if (v.length < 2) return "";
    const lo = Math.min(...v), hi = Math.max(...v), sp = hi - lo || 1;
    const pts = v.map((q, i) => [(i / (v.length - 1)) * 100, 28 - ((q - lo) / sp) * 22]);
    const d = smooth(pts);
    return `<svg class="spark" viewBox="0 0 100 32" preserveAspectRatio="none"><path class="sa" d="${d} L100,32 L0,32 Z" fill="${color}"/><path class="sl" pathLength="1" d="${d}" stroke="${color}" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function ringsSvg(rings) {
    const R = (i) => 70 - i * 18;
    const svg = rings.map((r, i) => {
      const c = 2 * Math.PI * R(i), f = Math.max(0, Math.min(1, r.value ?? 0));
      return `<circle class="rtrack" cx="84" cy="84" r="${R(i)}" stroke="${r.color}" stroke-width="13"/><circle class="ring" cx="84" cy="84" r="${R(i)}" stroke="${r.color}" stroke-width="13" style="--c:${c};stroke-dasharray:${c};stroke-dashoffset:${c * (1 - f)}"/>`;
    }).join("");
    const lg = rings.map((r) => `<div class="lg"><i style="background:${r.color}"></i>${esc(r.label)}<b>${pc(r.value)}</b></div>`).join("");
    return `<div class="rings"><svg viewBox="0 0 168 168">${svg}</svg><div class="legend">${lg}</div></div>`;
  }

  // ---------- reusable cards ----------
  function kpi(k) {
    const delta = k.delta && k.delta.text ? `<span class="kd ${k.delta.kind}">${esc(k.delta.text)}</span>` : "";
    const foot = k.bar ? `<div class="stack">${k.bar.map(([v, c]) => `<i style="flex:${Math.max(v, 0.0001)};background:${c}"></i>`).join("")}</div>` : k.spark ? sparkSvg(k.spark, k.color) : "";
    const small = String(k.value).length > 12 ? " sm" : "";
    return card("kpi", `<div class="kl">${esc(k.label)}</div><div class="kr"><span class="kv${small}" data-v="${esc(k.value)}">${esc(k.value)}</span>${delta}</div><div class="kn">${esc(k.note || "")}</div><div class="kf">${foot}</div>`, `--ac:${k.color}`);
  }

  function barRows(items) {
    return `<div class="rows">${items.map((it) => `<div class="ri"><div class="rm"><div class="rt"><span class="tag">${esc(it.code)}</span>${esc(it.name)}</div><div class="track"><i style="width:${Math.max(2, it.pct)}%;background:${it.color}"></i></div></div><div class="rv">${esc(it.shown)}</div></div>`).join("")}</div>`;
  }
  function peopleRows(items) {
    return `<div class="rows">${items.map((p) => `<div class="ri">${avatar(p.name)}<div class="rm"><div class="rt">${esc(p.name)}</div><div class="rs">${esc(p.sub)}</div></div><span class="pill ${p.level}">${esc(p.score)}</span></div>`).join("")}</div>`;
  }

  // ---------- data table ----------
  function dataTable(el, { cols, rows, maxHeight, onRow, rowKey, selected, limit = 200 }) {
    let sortK = null, sortD = 1, shown = limit, sel = selected, data = rows;
    const cell = (c, r) => {
      const v = r[c.k];
      if (c.t === "bar") { const pct = v == null ? 0 : Math.max(0, Math.min(100, (v / c.max) * 100)); return `<td><div class="cb"><div class="track"><i style="width:${pct}%;background:${typeof c.color === "function" ? c.color(v) : c.color}"></i></div><span>${v == null ? "–" : c.f(v)}</span></div></td>`; }
      if (c.t === "num") return `<td class="r">${v == null ? "–" : c.f ? c.f(v) : nf(v)}</td>`;
      if (c.t === "code") return `<td><span class="tag">${esc(v)}</span></td>`;
      if (c.t === "pill") return `<td><span class="pill ${esc(v)}">${esc(v)}</span></td>`;
      if (c.t === "name") return `<td><div class="nm">${avatar(v)}<div>${esc(v)}<small>${esc(r.id)}</small></div></div></td>`;
      return `<td>${esc(c.f ? c.f(v) : v)}</td>`;
    };
    const render = () => {
      let list = data.slice();
      if (sortK) list.sort((a, b) => { const x = a[sortK], y = b[sortK]; if (x == null) return 1; if (y == null) return -1; return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * sortD; });
      const view = list.slice(0, shown);
      el.innerHTML = `<div class="tw" style="${maxHeight ? `max-height:${maxHeight}px` : ""}"><table class="tbl"><thead><tr>${cols.map((c) => `<th class="${c.t === "num" ? "r" : ""}" data-k="${c.k}">${esc(c.l)}<span class="ar">${sortK === c.k ? (sortD > 0 ? "↑" : "↓") : ""}</span></th>`).join("")}</tr></thead><tbody>${view.map((r, n) => `<tr style="--n:${Math.min(n, 14)}" class="${onRow ? "click" : ""} ${rowKey && r[rowKey] === sel ? "sel" : ""}" data-r="${rowKey ? esc(r[rowKey]) : n}">${cols.map((c) => cell(c, r)).join("")}</tr>`).join("")}</tbody></table>${list.length > shown ? `<div class="more"><button class="btn" data-more>Show ${Math.min(200, list.length - shown)} more · ${nf(list.length - shown)} left</button></div>` : ""}${list.length === 0 ? '<div class="empty">Nothing to show for these filters.</div>' : ""}</div>`;
      $$("th", el).forEach((th) => th.addEventListener("click", () => { const k = th.dataset.k; if (sortK === k) sortD *= -1; else { sortK = k; sortD = 1; } render(); }));
      const more = $("[data-more]", el); if (more) more.addEventListener("click", () => { shown += 200; render(); });
      if (onRow) $$("tbody tr", el).forEach((tr) => tr.addEventListener("click", () => { sel = tr.dataset.r; $$("tbody tr", el).forEach((x) => x.classList.toggle("sel", x === tr)); onRow(sel); }));
    };
    render();
    return { setRows(r) { data = r; shown = limit; render(); }, select(k) { sel = k; render(); } };
  }

  const downloadCsv = (name, head, rows) => {
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const blob = new Blob(["﻿" + [head, ...rows].map((r) => r.map(q).join(",")).join("\n")], { type: "text/csv" });
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
    a.click();
  };

  // ---------- profile ----------
  function profileHtml(p) {
    const lvl = p.level ? `<span class="pill ${p.level}">${p.level} · ${p.score}</span>` : "";
    return `<div class="pl"><div class="ph">${avatar(p.name)}<div class="rm"><h2>${esc(p.name)}</h2><div class="muted">${esc(p.id)} · ${esc(p.programme)} · ${esc(p.intake)}</div></div>${lvl}</div>
      <div class="mini"><div><small>Subjects passed</small><b>${p.passed} / ${p.subjects}</b></div><div><small>Attempt pass rate</small><b>${p.attempt_pass == null ? "–" : nf(p.attempt_pass, 0) + "%"}</b></div><div><small>Outstanding</small><b>${p.remaining.length}</b></div></div>
      ${p.reasons ? `<div class="reasons">${esc(p.reasons)}</div>` : ""}
      <div class="h3">Marks over time</div><div class="chart" data-timeline style="height:190px"></div>
      <div class="h3">What remains</div>
      ${p.remaining.length ? `<div class="rows" style="gap:9px">${p.remaining.map((r) => `<div class="ri"><div class="rm"><div class="rt"><span class="tag">${esc(r.code)}</span>${esc(r.name)}</div></div><div class="rs">${r.attempts} attempt${r.attempts > 1 ? "s" : ""} · best ${r.best == null ? "–" : nf(r.best)}</div></div>`).join("")}</div>` : '<div class="muted">Nothing outstanding. Every attempted subject has been passed.</div>'}
      </div><div class="pr"><div class="h3" style="margin-top:0">Exam history</div><div data-hist></div></div>`;
  }
  function mountProfile(root, p, passMark) {
    const sessions = [...new Set(p.history.map((h) => h[0]))];
    const pts = p.history.filter((h) => h[4] != null);
    const tl = $("[data-timeline]", root);
    onSize(tl, (w, h) => {
      const m = { l: 32, r: 12, t: 10, b: 24 }, iw = w - m.l - m.r, ih = h - m.t - m.b;
      const X = (i) => m.l + (sessions.length > 1 ? (i / (sessions.length - 1)) * iw : iw / 2), Y = (v) => m.t + ih - (v / 100) * ih;
      let s = `<svg width="${w}" height="${h}">`;
      [0, 25, 50, 75, 100].forEach((v) => (s += `<line class="gridl" x1="${m.l}" x2="${w - m.r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axl" x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end">${v}</text>`));
      if (passMark != null) s += `<line x1="${m.l}" x2="${w - m.r}" y1="${Y(passMark)}" y2="${Y(passMark)}" stroke="#ff453a" stroke-dasharray="4 4" opacity=".7"/>`;
      sessions.forEach((q, i) => (s += `<text class="axl" x="${X(i)}" y="${h - 6}" text-anchor="middle">${esc(q)}</text>`));
      const col = { Pass: "#34c759", Fail: "#ff453a", Absent: "#8e8e93" };
      pts.forEach((r, i) => (s += `<circle class="dot pt" data-i="${i}" style="--k:${i}" cx="${X(sessions.indexOf(r[0]))}" cy="${Y(r[4])}" r="6" fill="${col[r[6]] || "#0a84ff"}" stroke="var(--solid)" stroke-width="2"/>`));
      tl.innerHTML = s + "</svg>";
      $$(".pt", tl).forEach((c) => { const r = pts[+c.dataset.i]; c.addEventListener("mousemove", (e) => showTip(`<b>${esc(r[1])}</b> · ${esc(r[2])}<br>${esc(r[0])} · attempt ${r[3]}<br>Marks <b>${nf(r[4])}</b> (${r[5]}) · ${r[6]}`, e)); c.addEventListener("mouseleave", hideTip); });
    });
    const rows = p.history.map((h) => ({ session: h[0], code: h[1], subject: h[2], attempt: h[3], marks: h[4], grade: h[5], result: h[6] }));
    dataTable($("[data-hist]", root), { rows, maxHeight: 300, cols: [{ k: "session", l: "Session" }, { k: "code", l: "Code", t: "code" }, { k: "attempt", l: "Try", t: "num" }, { k: "marks", l: "Marks", t: "num" }, { k: "grade", l: "Grade" }, { k: "result", l: "Result", t: "pill" }] });
  }

  // ---------- pages ----------
  const pages = {
    overview() {
      const h = D.hero;
      let html = card("hero", `<div class="hero-text"><div class="kicker">${esc(h.kicker)}</div><h1>${esc(h.title)}</h1><p>${esc(h.copy)}</p><div class="chips">${h.chips.map((c) => `<span class="chip">${esc(c)}</span>`).join("")}</div></div>${ringsSvg(h.rings)}`);
      html += `<div class="row r-5">${D.kpis.map(kpi).join("")}</div>`;
      html += `<div class="row r-21">${card("", head("Pass rate by session", "Pass rate and first-attempt pass rate", `<div class="legend" style="flex-direction:row;gap:14px"><div class="lg"><i style="background:#0a84ff"></i>Pass</div><div class="lg"><i style="background:#ff9500"></i>First attempt</div></div>`) + '<div class="chart" id="trend" style="height:300px"></div>')}${card("insights", head("Key insights", "Generated from the current filters") + D.insights.map((i) => `<p>${esc(i)}</p>`).join(""))}</div>`;
      html += `<div class="row r-3">${card("", head("Grade distribution", "All graded results") + '<div class="chart" id="grades" style="height:240px"></div>')}${card("", head("Pass rate by programme") + '<div class="chart" id="progs" style="height:240px"></div>')}${card("", head("Pass rate by intake") + '<div class="chart" id="intakes" style="height:240px"></div>')}</div>`;
      html += `<div class="row r-3">${card("", head("Hardest subjects", "Difficulty index, 0-100") + barRows(D.hardest.map((r) => ({ code: r.code, name: r.name, pct: r.value, color: diffColor(r.value), shown: nf(r.value) }))))}${card("", head("Needs attention", "Highest risk scores right now") + peopleRows(D.attention))}${card("", head("Students by risk level") + '<div class="chart" id="risk" style="height:230px"></div>' + `<div class="legend" style="flex-direction:row;justify-content:center;gap:16px;margin-top:6px">${["High", "Medium", "Low"].map((k) => `<div class="lg"><i style="background:${LEVEL[k]}"></i>${k}<b>${D.risk[k]}</b></div>`).join("")}</div>`)}</div>`;
      return html;
    },
    overviewInit() {
      areaLine($("#trend"), { labels: D.trend.labels, series: [{ name: "Pass rate", color: "#0a84ff", values: D.trend.pass }, { name: "First attempt", color: "#ff9500", values: D.trend.first, area: false, dash: true }] });
      bars($("#grades"), { labels: D.grades.labels, values: D.grades.values, colors: ["#34c759", "#40c8e0", "#0a84ff", "#ff9500", "#ff453a"] });
      const palette = ["#0a84ff", "#5e5ce6", "#40c8e0", "#ff9500", "#bf5af2"];
      bars($("#progs"), { labels: D.programmes.labels, values: D.programmes.values, colors: palette, max: 100, fmt: (v) => nf(v, 0) + "%" });
      bars($("#intakes"), { labels: D.intakes.labels, values: D.intakes.values, colors: palette, max: 100, fmt: (v) => nf(v, 0) + "%" });
      donut($("#risk"), { items: ["High", "Medium", "Low"].map((k) => ({ label: k, value: D.risk[k], color: LEVEL[k] })), center: [nf(D.risk.High + D.risk.Medium + D.risk.Low), "students"] });
    },

    subjects() {
      return `<div class="toolbar"><div class="seg" id="tabs"><button class="on" data-t="board">Leaderboard</button><button data-t="detail">Subject detail</button></div></div><div id="view"></div>`;
    },
    subjectsInit() {
      const rows = D.rows, view = $("#view");
      const board = () => {
        cardIndex = 0;
        view.innerHTML = `<div class="row r-32">${card("", head("Subject leaderboard", "Hardest first · click a column to sort") + '<div id="tbl"></div>')}${card("", head("Mean mark vs pass rate", "Bubble size = candidates · colour = difficulty") + '<div class="chart" id="sc" style="height:520px"></div>')}</div>`;
        dataTable($("#tbl"), { rows, maxHeight: 560, cols: [
          { k: "code", l: "Code", t: "code" }, { k: "name", l: "Subject" },
          { k: "difficulty", l: "Difficulty", t: "bar", max: 100, f: (v) => nf(v), color: diffColor },
          { k: "pass", l: "Pass", t: "bar", max: 1, f: (v) => pc(v), color: "#34c759" },
          { k: "first", l: "1st try", t: "bar", max: 1, f: (v) => pc(v), color: "#ff9500" },
          { k: "repeat", l: "Repeat", t: "num", f: (v) => pc(v) }, { k: "mean", l: "Mean", t: "num", f: (v) => nf(v, 1) }, { k: "never", l: "Never", t: "num" }] });
        const order = [...rows].sort((a, b) => b.difficulty - a.difficulty), show = new Set([...order.slice(0, 3), ...order.slice(-2)].map((r) => r.code));
        scatter($("#sc"), { points: rows.map((r) => ({ x: r.mean, y: r.pass * 100, r: r.candidates, color: diffColor(r.difficulty), label: r.code, name: r.name, d: r.difficulty, show: show.has(r.code) })) });
      };
      const detail = (code) => {
        cardIndex = 0;
        const r = rows.find((x) => x.code === code), d = D.detail[code];
        const sel = `<select class="sel" id="subj">${rows.map((x) => `<option value="${x.code}" ${x.code === code ? "selected" : ""}>${esc(x.code)} · ${esc(x.name)}</option>`).join("")}</select>`;
        view.innerHTML = `<div class="toolbar" style="margin-bottom:14px">${sel}</div><div class="row r-5">${[
          { label: "Difficulty", value: nf(r.difficulty), color: "#ff453a", note: "0-100, higher is harder" },
          { label: "Pass rate", value: pc(r.pass), color: "#34c759", note: "all attempts" },
          { label: "First attempt", value: pc(r.first), color: "#ff9500", note: "attempt 1 only" },
          { label: "Mean mark", value: nf(r.mean, 1), color: "#0a84ff", note: "median " + nf(r.median, 1) },
          { label: "Never passed", value: nf(r.never), color: "#bf5af2", note: nf(r.candidates) + " candidates" }].map(kpi).join("")}</div>
          <div class="row r-3" style="margin-top:14px">${card("", head("Mark distribution", "Dashed line = pass mark") + '<div class="chart" id="h" style="height:260px"></div>')}${card("", head("Pass rate by session") + '<div class="chart" id="t" style="height:260px"></div>')}${card("", head("First attempt vs repeat") + '<div class="chart" id="fr" style="height:260px"></div>')}</div>`;
        $("#subj").addEventListener("change", (e) => detail(e.target.value));
        const labels = d.hist.map((_, i) => i * 5);
        bars($("#h"), { labels: labels.map((l) => (l % 20 === 0 ? l : "")), values: d.hist, colors: labels.map((l) => (l + 5 <= D.pass_mark ? "#ff453a" : "#0a84ff")), fmt: () => "", tipFn: (i) => `<b>${labels[i]}-${labels[i] + 4}</b><br>${d.hist[i]} attempts` });
        areaLine($("#t"), { labels: d.trend.labels, series: [{ name: "Pass rate", color: "#0a84ff", values: d.trend.pass }] });
        bars($("#fr"), { labels: ["First attempt", "Repeat attempts"], values: [d.first, d.repeat], colors: ["#0a84ff", "#34c759"], max: 100, fmt: (v) => (v == null ? "–" : nf(v, 0) + "%") });
      };
      $$("#tabs button").forEach((b) => b.addEventListener("click", () => { $$("#tabs button").forEach((x) => x.classList.toggle("on", x === b)); b.dataset.t === "board" ? board() : detail(rows[0].code); }));
      board();
    },

    repeats() {
      const k = D.kpis;
      const kp = [
        { label: "Repeat rate", value: pc(k.repeat_rate), color: "#ff9500", note: "pairs needing 2+ attempts" },
        { label: "Avg attempts to pass", value: k.avg_attempts == null ? "–" : nf(k.avg_attempts, 2), color: "#0a84ff", note: "eventual passes" },
        { label: "Passed first time", value: pc(k.first_time), color: "#34c759", note: "of eventual passes" },
        { label: "Never passed", value: nf(k.never), color: "#ff453a", note: "student-subject pairs" }];
      const opts = `<option value="all">All subjects</option>` + D.codes.map((c) => `<option value="${c.code}">${esc(c.code)} · ${esc(c.name)}</option>`).join("");
      return `<div class="row r-4">${kp.map(kpi).join("")}</div>
        <div class="row r-2">${card("", head("Attempts needed to pass", "Student-subject passes by attempt number", `<select class="sel" id="s1">${opts}</select>`) + '<div class="chart" id="dist" style="height:260px"></div>')}${card("", head("Journey to a pass", "Attempted to passed to outstanding", `<select class="sel" id="s2">${opts}</select>`) + '<div id="fun" style="padding:6px 2px"></div>')}</div>
        <div class="row r-2">${card("", head("Repeat rate by subject", "Click a column to sort") + '<div id="rank"></div>')}${card("", head("Never passed", "Students with no pass yet", '<button class="btn" id="csv">Download CSV</button>') + `<div class="toolbar" style="margin-bottom:10px"><select class="sel" id="s3">${opts}</select><input class="inp" id="q" placeholder="Search name or ID"><span class="muted" id="cnt"></span></div><div id="never"></div>`)}</div>`;
    },
    repeatsInit() {
      const draw = () => {
        const c = $("#s1").value, dist = D.dist[c] || {}, keys = Object.keys(dist).sort((a, b) => a - b);
        bars($("#dist"), { labels: keys.length ? keys : ["–"], values: keys.length ? keys.map((x) => dist[x]) : [0], colors: "#0a84ff", tipFn: (i) => `<b>${keys[i]} attempt${keys[i] > 1 ? "s" : ""}</b><br>${nf(dist[keys[i]])} passes` });
      };
      $("#s1").addEventListener("change", draw);
      draw();
      const fun = () => funnelChart($("#fun"), D.funnel[$("#s2").value]);
      $("#s2").addEventListener("change", fun); fun();
      dataTable($("#rank"), { rows: D.ranking, maxHeight: 420, cols: [{ k: "code", l: "Code", t: "code" }, { k: "name", l: "Subject" }, { k: "repeat", l: "Repeat rate", t: "bar", max: Math.max(...D.ranking.map((r) => r.repeat || 0), 0.01), f: (v) => pc(v), color: "#ff9500" }, { k: "avg", l: "Avg tries", t: "num", f: (v) => nf(v, 2) }, { k: "never", l: "Never", t: "num" }] });
      const nv = dataTable($("#never"), { rows: D.never, maxHeight: 360, cols: [{ k: "name", l: "Student", t: "name" }, { k: "code", l: "Code", t: "code" }, { k: "subject", l: "Subject" }, { k: "attempts", l: "Tries", t: "num" }] });
      const cur = () => { const c = $("#s3").value, q = $("#q").value.trim().toLowerCase(); return D.never.filter((r) => (c === "all" || r.code === c) && (!q || (r.name + " " + r.id).toLowerCase().includes(q))); };
      const apply = () => { const l = cur(); nv.setRows(l); $("#cnt").textContent = `${nf(l.length)} pairs`; };
      $("#s3").addEventListener("change", apply); $("#q").addEventListener("input", apply); apply();
      $("#csv").addEventListener("click", () => downloadCsv("never_passed.csv", ["Student ID", "Name", "Code", "Subject", "Attempts"], cur().map((r) => [r.id, r.name, r.code, r.subject, r.attempts])));
    },

    risk() {
      const c = D.counts;
      const kp = [{ label: "High risk", value: nf(c.High || 0), color: "#ff453a", note: "score 50+ by default" }, { label: "Medium risk", value: nf(c.Medium || 0), color: "#ff9500", note: "score 25-49" }, { label: "Low risk", value: nf(c.Low || 0), color: "#34c759", note: "score below 25" }];
      return `<div class="row r-risk">${kp.map(kpi).join("")}${card("", head("Students by risk level") + '<div class="chart" id="rd" style="height:150px"></div>')}</div>
        ${card("", `<div class="toolbar"><button class="fchip High on" data-l="High">High</button><button class="fchip Medium on" data-l="Medium">Medium</button><button class="fchip Low" data-l="Low">Low</button><input class="inp" id="q" placeholder="Search name, ID or reason"><span class="sp"></span><span class="muted" id="cnt"></span><button class="btn" id="csv">Download CSV</button></div>`)}
        <div class="row r-split">${card("", head("Students", "Select a row to open the profile") + '<div id="list"></div>')}${card("", '<div id="prof"></div>', "position:sticky;top:6px")}</div>`;
    },
    riskInit() {
      donut($("#rd"), { items: ["High", "Medium", "Low"].map((k) => ({ label: k, value: D.counts[k] || 0, color: LEVEL[k] })), center: [nf(D.rows.length), "students"] });
      const on = new Set(["High", "Medium"]);
      let current = null;
      let list = null;
      const show = (id, auto = false) => {
        const p = D.profiles[id]; if (!p) return;
        current = id;
        const root = $("#prof"); root.innerHTML = profileHtml(p); mountProfile(root, p, BOOT.pass_mark);
        if (auto && list) list.select(id);
      };
      list = dataTable($("#list"), { rows: D.rows, maxHeight: 640, rowKey: "id", onRow: (id) => show(id), selected: null, cols: [{ k: "name", l: "Student", t: "name" }, { k: "programme", l: "Programme", f: (v) => String(v).replace("Diploma in ", "") }, { k: "score", l: "Score", t: "num" }, { k: "level", l: "Risk", t: "pill" }, { k: "outstanding", l: "Open", t: "num" }] });
      const filtered = () => { const q = $("#q").value.trim().toLowerCase(); return D.rows.filter((r) => on.has(r.level) && (!q || (r.name + " " + r.id + " " + r.reasons).toLowerCase().includes(q))); };
      const apply = () => { const l = filtered(); list.setRows(l); $("#cnt").textContent = `${nf(l.length)} students`; if (l.length && (!current || !l.some((r) => r.id === current))) show(l[0].id, true); if (!l.length) $("#prof").innerHTML = '<div class="empty">No students match.</div>'; };
      $$(".fchip").forEach((b) => b.addEventListener("click", () => { const l = b.dataset.l; on.has(l) ? on.delete(l) : on.add(l); b.classList.toggle("on", on.has(l)); apply(); }));
      $("#q").addEventListener("input", apply);
      $("#csv").addEventListener("click", () => downloadCsv("at_risk_students.csv", ["Student ID", "Name", "Programme", "Intake", "Score", "Risk", "Outstanding", "Reasons"], filtered().map((r) => [r.id, r.name, r.programme, r.intake, r.score, r.level, r.outstanding, r.reasons])));
      apply();
    },

    student() {
      return card("", '<div id="prof"></div>');
    },
    studentInit() { const root = $("#prof"); root.classList.add("wide"); root.innerHTML = profileHtml(D.profile); mountProfile(root, D.profile, D.pass_mark); },

    health() {
      const k = D.kpis;
      const kp = [{ label: "Rows loaded", value: nf(k.loaded), color: "#0a84ff", note: "across all files" }, { label: "After cleaning", value: nf(k.final), color: "#34c759", note: "valid and de-duplicated" }, { label: "Students", value: nf(k.students), color: "#bf5af2", note: "unique IDs" }, { label: "Files", value: nf(k.files), color: "#ff9500", note: "merged into one dataset" }];
      const dot = (ok) => `<i style="width:10px;height:10px;border-radius:50%;flex:none;background:${ok === true ? "#34c759" : ok === false ? "#ff9500" : "#8e8e93"};box-shadow:0 0 0 4px ${ok === true ? "rgba(52,199,89,.18)" : ok === false ? "rgba(255,149,0,.2)" : "rgba(142,142,147,.18)"}"></i>`;
      const issues = [];
      if (D.name_conflicts.length) issues.push(card("", head(`Name conflicts (${D.name_conflicts.length})`, "Most frequent name kept") + '<div id="nc"></div>'));
      if (D.invalid.length) issues.push(card("", head(`Invalid marks (${D.invalid.length})`, "Excluded from metrics") + '<div id="im"></div>'));
      if (D.duplicates.length) issues.push(card("", head(`Duplicates removed (${D.duplicates.length})`, "Highest mark kept") + '<div id="dp"></div>'));
      return `<div class="row r-4">${kp.map(kpi).join("")}</div>
        <div class="row r-32">${card("", head("Quality checks") + `<div class="rows" style="gap:11px">${D.checks.map((c) => `<div class="ri">${dot(c.ok)}<div class="rm" style="font-size:13.5px">${c.text}</div></div>`).join("")}</div>`)}${card("", head("Rows per file") + '<div id="files"></div>')}</div>
        ${issues.length ? `<div class="row" style="grid-template-columns:repeat(${issues.length},minmax(0,1fr))">${issues.join("")}</div>` : ""}
        ${card("", head("Cleaned dataset", `First ${nf(D.preview.length)} of ${nf(D.total_rows)} rows · download the full set below`) + '<div id="prev"></div>')}`;
    },
    healthInit() {
      dataTable($("#files"), { rows: D.files, cols: [{ k: "file", l: "File" }, { k: "rows", l: "Rows", t: "num" }] });
      if ($("#nc")) dataTable($("#nc"), { rows: D.name_conflicts, maxHeight: 220, cols: [{ k: "id", l: "ID", t: "code" }, { k: "names", l: "Names" }, { k: "kept", l: "Kept" }] });
      if ($("#im")) dataTable($("#im"), { rows: D.invalid, maxHeight: 220, cols: [{ k: "student_id", l: "ID", t: "code" }, { k: "subject_code", l: "Subject" }, { k: "exam_session", l: "Session" }, { k: "source_file", l: "File" }] });
      if ($("#dp")) dataTable($("#dp"), { rows: D.duplicates, maxHeight: 220, cols: [{ k: "student_id", l: "ID", t: "code" }, { k: "subject_code", l: "Subject" }, { k: "exam_session", l: "Session" }] });
      const labels = { student_id: "ID", student_name: "Name", programme: "Programme", intake: "Intake", subject_code: "Subject", exam_session: "Session", attempt_no: "Try", marks: "Marks", grade: "Grade", result: "Result" };
      const rows = D.preview.map((r) => Object.fromEntries(D.columns.map((c, i) => [c, r[i]])));
      dataTable($("#prev"), { rows, maxHeight: 460, limit: 150, cols: D.columns.map((c) => ({ k: c, l: labels[c], t: c === "result" ? "pill" : c === "subject_code" ? "code" : c === "attempt_no" || c === "marks" ? "num" : undefined })) });
    },
  };

  // ---------- boot ----------
  const root = $("#app");
  root.className = "page";
  root.innerHTML = pages[BOOT.page]();
  const init = pages[BOOT.page + "Init"];
  if (init) init();

  // count-up for numeric KPI values
  const NUM = /^([^\d\-]*)(-?[\d,]*\.?\d+)([^\d]*)$/;
  $$(".kv[data-v]").forEach((el) => {
    const m = NUM.exec(el.dataset.v); if (!m) return;
    const [, pre, num, suf] = m, target = parseFloat(num.replace(/,/g, "")), dec = (num.split(".")[1] || "").length, t0 = performance.now();
    const step = (t) => { const p = Math.min(1, (t - t0) / 1100), e = 1 - Math.pow(1 - p, 4); el.textContent = pre + nf(target * e, dec) + suf; if (p < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });

  // 3D tilt
  $$(".card").forEach((c) => {
    c.addEventListener("mousemove", (e) => {
      if (e.target.closest(".tw, select, input, .chart")) { c.style.transform = ""; return; }
      const r = c.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      c.style.transform = `perspective(1000px) rotateX(${(-y * 4).toFixed(2)}deg) rotateY(${(x * 5).toFixed(2)}deg) translateY(-3px)`;
      c.style.setProperty("--mx", (x + 0.5) * 100 + "%"); c.style.setProperty("--my", (y + 0.5) * 100 + "%");
    });
    c.addEventListener("mouseleave", () => (c.style.transform = ""));
  });

  // auto-size the host iframe to the content
  const fit = () => { try { window.frameElement.style.height = Math.ceil(document.body.getBoundingClientRect().height) + 6 + "px"; } catch (e) {} };
  new ResizeObserver(fit).observe(document.body);
  fit();
})();
