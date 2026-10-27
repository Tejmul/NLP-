"use strict";

const $ = (id) => document.getElementById(id);
const ORDER = ["payments", "cards", "loans", "account", "fraud"];
const SAMPLES = [
  "I didn't make this payment",
  "My card was skimmed at the ATM",
  "EMI on a 5 lakh home loan?",
  "My transfer hasn't arrived",
  "My father passed away, close his account",
  "Card 4539 1488 0343 6467 is blocked",
];
const KEY_STORE = "routing-desk-api-key";
const THEME_STORE = "routing-desk-theme";
const PII_NAMES = { CARD: "card number", ACCOUNT: "account number", IBAN: "IBAN", SORT_CODE: "sort code", EMAIL: "email", PHONE: "phone" };
const RULE_NAMES = { fraud_escalation: "Fraud escalation", low_confidence: "Manual review", vulnerable_customer: "Vulnerable customer",
  formal_complaint: "Formal complaint", account_takeover: "Account takeover" };
const EVENT_TEXT = {
  created: (d) => `Routed to <b>${esc(d.department)}</b> at ${pct(d.confidence)} confidence`,
  rerouted: (d) => `Re-routed from ${esc(catLabel(d.from.category))} to <b>${esc(catLabel(d.to.category))}</b>`,
  status: (d) => `Status changed to <b>${esc(d.to.replace("_", " "))}</b>`,
  assigned: (d) => (d.assignee ? `Assigned to <b>${esc(d.assignee)}</b>` : "Unassigned"),
  note: (d) => `Note: “${esc(d.note)}”`,
};

const GATE_NAMES = { macro_f1: "Macro F1", fraud_recall: "Fraud recall", intent_accuracy: "Topic accuracy",
  macro_f1_vs_production: "No regression vs. live model" };

let CATS = {};
let TAXO = {};

/* ---------- Helpers ---------- */
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 0) => (x == null ? "–" : `${(x * 100).toFixed(d)}%`);
const pctSoft = (x) => (x < 0.005 ? "<1%" : pct(x));
const catLabel = (c) => CATS[c]?.label || c;
const fmtNum = (n) => (n == null ? "–" : n.toLocaleString());
const store = {
  get: (k) => { try { return localStorage.getItem(k) || ""; } catch { return ""; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
};

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const key = store.get(KEY_STORE);
  if (key) headers["X-API-Key"] = key;
  const res = await fetch(path, { ...options, headers });
  const body = await res.json().catch(() => ({}));
  if (res.status === 401) $("keybar").hidden = false;
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail;
    throw new Error((typeof detail === "string" && detail) || `The server returned ${res.status}.`);
  }
  return body;
}
const send = (path, method, data, signal) =>
  api(path, { method, signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

function showError(el, err) {
  el.textContent = err ? (err.message || String(err)) : "";
  el.hidden = !err;
}
function relTime(iso) {
  const mins = Math.round((Date.now() - new Date(iso)) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}
function span(m) {
  m = Math.abs(m);
  return m < 60 ? `${m}m` : m < 2880 ? `${Math.round(m / 60)}h` : `${Math.round(m / 1440)}d`;
}
function dueText(t) {
  if (t.status === "resolved") return t.sla_breached ? "Closed late" : "Closed on time";
  const mins = Math.round((new Date(t.due_at) - Date.now()) / 60000);
  return mins < 0 ? `Overdue ${span(mins)}` : `Due in ${span(mins)}`;
}
const clock = (iso) => new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const prioBadge = (p) => `<span class="badge p-${p}">${p[0].toUpperCase() + p.slice(1)}</span>`;

let toastTimer;
function toast(html, action) {
  const el = $("toast");
  el.innerHTML = html + (action ? ` <button type="button">${esc(action.label)}</button>` : "");
  el.hidden = false;
  if (action) el.querySelector("button").onclick = () => { el.hidden = true; action.run(); };
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 6000);
}

/* ---------- Theme ---------- */
function applyTheme(t) {
  if (t) document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  $("theme-btn").title = `Theme: ${t || "system"}`;
}
applyTheme(store.get(THEME_STORE));
$("theme-btn").addEventListener("click", () => {
  const next = { "": "dark", dark: "light", light: "" }[store.get(THEME_STORE)] ?? "";
  store.set(THEME_STORE, next);
  applyTheme(next);
});

$("key-form").addEventListener("submit", (e) => {
  e.preventDefault();
  store.set(KEY_STORE, $("api-key").value.trim());
  location.reload();
});

/* ---------- Navigation ---------- */
const tabs = [...document.querySelectorAll('[role="tab"]')];
const onShow = {
  "tab-route": () => requestAnimationFrame(layoutNet),
  "tab-inbox": () => loadQueue(true),
  "tab-analytics": () => loadAnalytics(),
  "tab-model": () => loadModel(),
};
function selectTab(tab) {
  tabs.forEach((t) => {
    const on = t === tab;
    t.setAttribute("aria-selected", on);
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute("aria-controls")).hidden = !on;
  });
  window.scrollTo({ top: 0 });
  $("toast").hidden = true;
  onShow[tab.id]?.();
}
tabs.forEach((t, i) => {
  t.addEventListener("click", () => selectTab(t));
  t.addEventListener("keydown", (e) => {
    const dir = ["ArrowDown", "ArrowRight"].includes(e.key) ? 1 : ["ArrowUp", "ArrowLeft"].includes(e.key) ? -1 : 0;
    if (!dir) return;
    e.preventDefault();
    const next = tabs[(i + dir + tabs.length) % tabs.length];
    next.focus();
    selectTab(next);
  });
});
function segmented(el, onChange) {
  el.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    el.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", x === b));
    onChange(b.dataset.v);
  });
}

/* ---------- Neural routing view (hero) ---------- */
// Signals start at the message's words, pass through two hidden layers and land on a team.
// Each signal's destination is sampled from the model's real probabilities; words that moved
// the decision more fire more often.
const NET_COLORS = { payments: "#21a690", cards: "#6f8bf5", loans: "#d19a3e", account: "#ad78d6", fraud: "#f0566c", review: "#8a94a6" };
const SIGNALS = ["#7dd3fc", "#a5b4fc", "#c4b5fd"]; // sky, indigo, violet: one cool family for the network
const NEURON = "#a5b4fc";
const H1 = 7, H2 = 6;
const net = { ctx: null, w: 0, h: 0, tokens: [], h1: [], h2: [], anchors: {}, glow: {}, particles: [], spawn: 0, last: 0, dirty: true };
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let current = null;

const rgba = (hex, a) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
};

function buildNet() {
  $("outs").innerHTML = ORDER.map((c) => `
    <li class="out c-${c}" data-cat="${c}">
      <span class="out-name">${esc(CATS[c].label)}<span class="out-tag" hidden></span></span>
      <span class="out-pct"></span>
      <span class="out-team">${esc(CATS[c].department)}</span>
      <span class="out-bar"><span></span></span>
    </li>`).join("");
  net.ctx = $("net").getContext("2d");
  net.h1 = Array.from({ length: H1 }, () => ({ act: 0 }));
  net.h2 = Array.from({ length: H2 }, () => ({ act: 0 }));
  ORDER.forEach((c) => { net.glow[c] = 0; });
  setTokens(null);
  layoutNet();
  requestAnimationFrame(tick);
}

function layoutNet() {
  const viz = $("viz");
  if (!viz || !viz.clientWidth || !net.ctx) return;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  net.w = viz.clientWidth;
  net.h = viz.clientHeight;
  const cv = $("net");
  cv.width = Math.round(net.w * dpr);
  cv.height = Math.round(net.h * dpr);
  net.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const outs = $("outs");
  let outX = net.w;
  outs.querySelectorAll(".out").forEach((li) => {
    const x = outs.offsetLeft + li.offsetLeft - 1;
    net.anchors[li.dataset.cat] = { x, y: outs.offsetTop + li.offsetTop + li.offsetHeight / 2 };
    outX = Math.min(outX, x);
  });
  const narrow = net.w < 520;
  net.labelW = narrow ? 70 : 104;
  net.inX = net.labelW + 14;
  const top = 14, bottom = net.h - (narrow ? 14 : 30);
  const col = (n, x) => Array.from({ length: n }, (_, i) => ({ x, y: top + ((bottom - top) * (i + 0.5)) / n }));
  col(H1, net.inX + (outX - net.inX) * 0.36).forEach((p, i) => Object.assign(net.h1[i], p));
  col(H2, net.inX + (outX - net.inX) * 0.7).forEach((p, i) => Object.assign(net.h2[i], p));
  positionTokens(top, bottom);
  $("leg-in").style.left = `${net.inX - 40}px`;
  $("leg-hid").style.left = `${(net.h1[0].x + net.h2[0].x) / 2}px`;
  net.particles = [];
  net.dirty = true;
}

function positionTokens(top = 14, bottom = net.h - 30) {
  const n = net.tokens.length;
  const gap = Math.min(34, (bottom - top) / Math.max(n, 1));
  const start = (top + bottom) / 2 - (gap * (n - 1)) / 2;
  net.tokens.forEach((t, i) => { t.x = net.inX; t.y = start + gap * i; });
}

// The phrase a fraud rule fired on, e.g. "skimmed" (null when no rule overrode the model).
function ruleKeyword(d) {
  const r = d.rules_applied.find((x) => x.rule === "fraud_escalation");
  const m = r && r.detail.match(/“([^”]+)”/);
  return m ? m[1] : null;
}

// Keywords to highlight: the rule's trigger phrase when a rule decided, otherwise the model's evidence.
function evidence(d) {
  const kw = ruleKeyword(d);
  if (!kw) return d.keywords;
  const at = d.text.toLowerCase().replace(/’/g, "'").indexOf(kw.toLowerCase());
  return at < 0 ? [] : [{ word: d.text.slice(at, at + kw.length), start: at, end: at + kw.length, impact: 1 }];
}

function setTokens(d) {
  if (!d) {
    net.tokens = [{ text: "", w: 0.35 }];
  } else {
    const ev = evidence(d);
    const impact = new Map();
    ev.forEach((k) => { for (const m of d.text.slice(k.start, k.end).matchAll(/\S+/g)) impact.set(k.start + m.index, k.impact); });
    const max = Math.max(0.0001, ...ev.map((k) => k.impact));
    const words = [...d.text.matchAll(/\S+/g)].map((m, i) => ({
      text: m[0].replace(/^[^\w[]+|[^\w\]]+$/g, "") || m[0], i, imp: (impact.get(m.index) || 0) / max,
    }));
    const keep = words.length > 8 ? [...words].sort((a, b) => b.imp - a.imp || a.i - b.i).slice(0, 8).sort((a, b) => a.i - b.i) : words;
    net.tokens = keep.map((t) => ({ text: t.text, w: ev.length ? 0.22 + 0.78 * t.imp : 0.5 }));
  }
  positionTokens();
  net.dirty = true;
}

function pick(weights) {
  const total = weights.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < weights.length; i++) { r -= weights[i]; if (r <= 0) return i; }
  return weights.length - 1;
}

function spawnParticle() {
  if (!net.tokens.length || !net.anchors.fraud) return;
  const tok = net.tokens[pick(net.tokens.map((t) => t.w))];
  const cat = current ? ORDER[pick(ORDER.map((c) => (current.probabilities[c] < 0.02 ? 0 : current.probabilities[c])))]
    : ORDER[Math.floor(Math.random() * 5)];
  const ci = ORDER.indexOf(cat);
  const a = Math.random() < 0.55 ? (ci * 3) % H1 : Math.floor(Math.random() * H1);
  const b = Math.random() < 0.7 ? Math.min(H2 - 1, Math.round((ci * (H2 - 1)) / 4)) : Math.floor(Math.random() * H2);
  const pts = [[tok.x, tok.y], [net.h1[a].x, net.h1[a].y], [net.h2[b].x, net.h2[b].y], [net.anchors[cat].x, net.anchors[cat].y]];
  const nodes = [null, net.h1[a], net.h2[b], cat];
  // A business rule overrode the model: the signal lands where the model pointed, then hops to the routed team.
  if (current && cat === current.model_category && current.category !== cat) {
    const to = net.anchors[current.category];
    pts.push([to.x - 46, (pts[3][1] + to.y) / 2], [to.x, to.y]);
    nodes.push(null, current.category);
  }
  const signal = SIGNALS[Math.floor(Math.random() * SIGNALS.length)];
  net.particles.push({ pts, nodes, seg: 0, t: 0, speed: 230 + Math.random() * 90, color: signal,
    dest: current ? NET_COLORS[cat] : signal, hop: current ? NET_COLORS[current.category] : signal,
    alpha: current ? 1 : 0.5, trail: [] });
}

function tick(ts) {
  requestAnimationFrame(tick);
  const dt = Math.min(0.05, (ts - (net.last || ts)) / 1000);
  net.last = ts;
  if ($("panel-route").hidden || document.hidden || !net.w) return;
  const animate = !reduceMotion.matches;
  if (!animate && !net.dirty) return;
  net.dirty = false;

  if (animate) {
    net.spawn += dt * (current ? 30 : 6);
    while (net.spawn >= 1) { spawnParticle(); net.spawn -= 1; }
  }
  for (const p of net.particles) {
    const [x0, y0] = p.pts[p.seg], [x1, y1] = p.pts[p.seg + 1];
    p.t += (p.speed * dt) / Math.max(1, Math.hypot(x1 - x0, y1 - y0));
    p.x = x0 + (x1 - x0) * Math.min(p.t, 1);
    p.y = y0 + (y1 - y0) * Math.min(p.t, 1);
    p.trail.push([p.x, p.y]);
    if (p.trail.length > 7) p.trail.shift();
    if (p.t >= 1) {
      const node = p.nodes[p.seg + 1];
      if (typeof node === "string") net.glow[node] = Math.min(1, net.glow[node] + 0.35);
      else if (node) node.act = Math.min(1, node.act + 0.4);
      p.seg += 1; p.t = 0;
      if (p.seg === 2) p.color = p.dest;
      if (p.seg >= 3) p.color = p.hop;
      if (p.seg >= p.pts.length - 1) p.done = true;
    }
  }
  net.particles = net.particles.filter((p) => !p.done);
  [...net.h1, ...net.h2].forEach((n) => { n.act *= 0.93; });
  ORDER.forEach((c) => { net.glow[c] *= 0.94; });
  draw();
}

function draw() {
  const g = net.ctx, probs = current?.probabilities;
  g.clearRect(0, 0, net.w, net.h);
  g.lineWidth = 1;

  // connections
  for (const t of net.tokens) for (const n of net.h1) {
    g.strokeStyle = `rgba(165,180,252,${0.04 + t.w * 0.07})`;
    g.beginPath(); g.moveTo(t.x, t.y); g.lineTo(n.x, n.y); g.stroke();
  }
  g.strokeStyle = "rgba(165,180,252,0.06)";
  for (const a of net.h1) for (const b of net.h2) { g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke(); }
  for (const c of ORDER) {
    const an = net.anchors[c];
    if (!an) continue;
    const p = probs ? probs[c] : 0.2;
    g.strokeStyle = probs ? rgba(NET_COLORS[c], 0.03 + p * 0.4) : "rgba(165,180,252,0.06)";
    g.lineWidth = probs ? 1 + p * 1.6 : 1;
    for (const b of net.h2) { g.beginPath(); g.moveTo(b.x, b.y); g.lineTo(an.x, an.y); g.stroke(); }
  }
  g.lineWidth = 1;

  // signals
  g.globalCompositeOperation = "lighter";
  for (const p of net.particles) {
    if (p.trail.length > 1) {
      g.strokeStyle = rgba(p.color, 0.28 * p.alpha);
      g.lineWidth = 1.6;
      g.beginPath(); g.moveTo(...p.trail[0]); p.trail.forEach((q) => g.lineTo(...q)); g.stroke();
    }
    g.fillStyle = rgba(p.color, 0.13 * p.alpha);
    g.beginPath(); g.arc(p.x, p.y, 7, 0, 7); g.fill();
    g.fillStyle = rgba(p.color, 0.55 * p.alpha);
    g.beginPath(); g.arc(p.x, p.y, 2.6, 0, 7); g.fill();
    g.fillStyle = `rgba(248,250,255,${0.9 * p.alpha})`;
    g.beginPath(); g.arc(p.x, p.y, 1.2, 0, 7); g.fill();
  }

  // hidden neurons
  for (const n of [...net.h1, ...net.h2]) {
    if (n.act > 0.02) {
      g.fillStyle = rgba(NEURON, n.act * 0.22);
      g.beginPath(); g.arc(n.x, n.y, 6 + n.act * 11, 0, 7); g.fill();
    }
  }
  g.globalCompositeOperation = "source-over";
  for (const n of [...net.h1, ...net.h2]) {
    g.fillStyle = n.act > 0.05 ? rgba(NEURON, 0.15 + n.act * 0.85) : "#0d1426";
    g.strokeStyle = n.act > 0.05 ? rgba("#e0e7ff", 0.5 + n.act * 0.5) : "rgba(165,180,252,0.35)";
    g.lineWidth = 1.25;
    g.beginPath(); g.arc(n.x, n.y, 4.5, 0, 7); g.fill(); g.stroke();
  }

  // output sockets
  for (const c of ORDER) {
    const an = net.anchors[c];
    if (!an) continue;
    const gl = net.glow[c];
    if (gl > 0.02) { g.fillStyle = rgba(NET_COLORS[c], gl * 0.35); g.beginPath(); g.arc(an.x, an.y, 4 + gl * 10, 0, 7); g.fill(); }
    g.fillStyle = NET_COLORS[c];
    g.beginPath(); g.arc(an.x, an.y, 3, 0, 7); g.fill();
  }

  // input words
  const accent = "#7dd3fc";
  g.font = `500 12px ${getComputedStyle(document.body).getPropertyValue("--mono") || "monospace"}`;
  g.textAlign = "right";
  g.textBaseline = "middle";
  for (const t of net.tokens) {
    if (t.w > 0.6) { g.fillStyle = rgba(accent, 0.22 * t.w); g.beginPath(); g.arc(t.x, t.y, 9, 0, 7); g.fill(); }
    g.fillStyle = t.w > 0.6 ? accent : `rgba(255,255,255,${0.35 + t.w * 0.5})`;
    g.beginPath(); g.arc(t.x, t.y, 3 + t.w * 1.5, 0, 7); g.fill();
    if (t.text) {
      let label = t.text;
      while (label.length > 1 && g.measureText(label).width > net.labelW - 6) label = label.slice(0, -1);
      if (label !== t.text) label = `${label.slice(0, -1)}…`;
      g.fillStyle = t.w > 0.6 ? "#ffffff" : `rgba(238,242,248,${0.4 + t.w * 0.45})`;
      g.fillText(label, t.x - 12, t.y);
    }
  }
  if (!net.tokens[0]?.text) {
    g.textAlign = "left";
    g.fillStyle = "rgba(238,242,248,0.4)";
    g.fillText("Your message", 0, net.tokens[0].y);
  }
}

function clearNet() {
  current = null;
  $("viz").classList.remove("has");
  setTokens(null);
  document.querySelectorAll(".out").forEach((o) => {
    o.classList.remove("win");
    o.querySelector(".out-pct").textContent = "";
    o.querySelector(".out-bar span").style.width = "0";
    o.querySelector(".out-tag").hidden = true;
  });
  document.querySelectorAll("#pipeline li").forEach((li) => li.classList.remove("done", "flag"));
  $("st-pii").textContent = "personal data"; $("st-cat").textContent = "5 categories";
  $("st-topic").textContent = "83 topics"; $("st-rules").textContent = "business rules";
  $("result").hidden = true;
  $("route-btn").disabled = true;
}

function renderNet(d) {
  current = d;
  $("viz").classList.add("has");
  setTokens(d);
  const byRule = d.rules_applied.some((r) => r.rule === "fraud_escalation");
  document.querySelectorAll(".out").forEach((o) => {
    const c = o.dataset.cat, p = d.probabilities[c] ?? 0, win = c === d.category;
    o.classList.toggle("win", win);
    o.querySelector(".out-pct").textContent = win && byRule ? "Rule" : pct(p);
    o.querySelector(".out-bar span").style.width = pct(p);
    const tag = o.querySelector(".out-tag");
    tag.hidden = !(win || (byRule && c === d.model_category));
    tag.className = `out-tag${win ? "" : " model"}`;
    tag.textContent = win ? (d.needs_review ? "Review" : "Routed") : "Model";
  });

  const steps = {
    pii: [d.pii_redacted.length ? `${d.pii_redacted.length} item${d.pii_redacted.length > 1 ? "s" : ""} masked` : "Nothing to mask", false],
    cat: [`${catLabel(d.model_category)} · ${pct(d.probabilities[d.model_category])}`, false],
    topic: [d.intent?.label || "Not found", false],
    rules: [d.rules_applied.length ? d.rules_applied.map((r) => RULE_NAMES[r.rule] || r.rule).join(", ") : "None triggered",
      d.rules_applied.some((r) => r.rule !== "low_confidence")],
  };
  document.querySelectorAll("#pipeline li").forEach((li, i) => {
    const [text, flag] = steps[li.dataset.step];
    li.classList.remove("done", "flag");
    $(`st-${li.dataset.step}`).textContent = text;
    setTimeout(() => { li.classList.add("done"); li.classList.toggle("flag", flag); }, 110 * i);
  });
}

/* ---------- Route: details ---------- */
function highlight(text, keywords, cat) {
  if (!keywords.length) return esc(text);
  const max = Math.max(...keywords.map((k) => k.impact));
  let out = "", pos = 0;
  for (const k of [...keywords].sort((a, b) => a.start - b.start)) {
    const w = (0.35 + 0.65 * (k.impact / max)).toFixed(2);
    out += esc(text.slice(pos, k.start));
    out += `<mark class="c-${cat}" style="--w:${w}" title="Removing this word lowers confidence by ${pct(k.impact, 1)}">${esc(text.slice(k.start, k.end))}</mark>`;
    pos = k.end;
  }
  return out + esc(text.slice(pos));
}

function flagsHTML(pii, rules) {
  const items = [];
  if (pii.length) items.push(`<li class="f-pii"><b>Masked</b> ${pii.map((p) => PII_NAMES[p] || p).join(", ")} before storing</li>`);
  for (const r of rules) {
    const cls = r.rule === "low_confidence" ? "f-review" : "f-rule";
    items.push(`<li class="${cls}"><b>${esc(RULE_NAMES[r.rule] || r.rule)}</b> ${esc(r.detail)}</li>`);
  }
  return items.join("");
}

function renderDetails(d) {
  $("result").hidden = false;
  const cat = d.needs_review ? "review" : d.category;
  const byRule = d.rules_applied.some((r) => r.rule === "fraud_escalation");
  $("r-dot").className = `cat-dot c-${cat}`;
  $("r-cat").textContent = d.needs_review ? "Manual review" : d.label;
  $("r-sub").textContent = d.needs_review ? `Best guess: ${d.label} at ${pct(d.confidence)}`
    : byRule ? `Set by the fraud rule; the model said ${catLabel(d.model_category)}` : "";
  $("r-priority").outerHTML = `<span class="badge p-${d.priority}" id="r-priority">${d.priority[0].toUpperCase() + d.priority.slice(1)} priority</span>`;
  $("r-team").textContent = d.department;
  $("r-conf").textContent = byRule ? "Decided by rule" : pct(d.confidence, 1);
  $("r-conf").className = byRule ? "" : "mono";
  $("r-meter").parentElement.className = `meter c-${cat}`;
  $("r-meter").parentElement.hidden = byRule;
  $("r-meter").style.width = pct(d.confidence);
  $("r-due").textContent = `${d.sla_hours < 1 ? `${d.sla_hours * 60} min` : `${d.sla_hours} h`} · by ${clock(d.due_at)}`;
  $("r-also").textContent = d.secondary_category ? `${catLabel(d.secondary_category)} (${pct(d.probabilities[d.secondary_category])})` : "None";
  $("r-quote").innerHTML = highlight(d.text, evidence(d), d.category);
  $("r-flags").innerHTML = flagsHTML(d.pii_redacted, d.rules_applied);
  const topics = [d.intent, ...d.intent_alternatives].filter(Boolean);
  $("r-topics").innerHTML = topics.map((t) => `
    <li class="c-${d.category}"><div class="t-row"><span>${esc(t.label)}</span><span class="mono">${pctSoft(t.confidence)}</span></div>
      <div class="bar"><span style="width:${t.confidence * 100}%"></span></div></li>`).join("");
}

/* ---------- Route: live classification ---------- */
let liveTimer, liveCtrl, liveSeq = 0;

function setLive(state, text) {
  $("live").className = `live ${state}`;
  $("live-text").textContent = text;
}

async function classifyLive() {
  const text = $("query").value.trim();
  if (text.length < 3) { clearNet(); setLive("", "Waiting for input"); return; }
  liveCtrl?.abort();
  liveCtrl = new AbortController();
  const seq = ++liveSeq;
  setLive("busy", "Analysing…");
  showError($("route-error"), null);
  try {
    const d = await send("/api/v1/classify", "POST", { text, channel: $("channel").value, create_ticket: false }, liveCtrl.signal);
    if (seq !== liveSeq) return;
    renderNet(d);
    renderDetails(d);
    $("route-btn").disabled = false;
    setLive("on", `Live · ${d.latency_ms} ms · not saved`);
  } catch (err) {
    if (err.name === "AbortError") return;
    setLive("", "Paused");
    showError($("route-error"), err);
  }
}

$("query").addEventListener("input", () => {
  clearTimeout(liveTimer);
  $("route-btn").disabled = true;
  $("route-btn").textContent = "Create ticket";
  liveTimer = setTimeout(classifyLive, 350);
});
$("query").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !$("route-btn").disabled) { e.preventDefault(); createTicket(); }
});
$("channel").addEventListener("change", () => { if (current) classifyLive(); });

async function createTicket() {
  const btn = $("route-btn");
  const text = $("query").value.trim();
  if (!text) return;
  btn.disabled = true;
  btn.textContent = "Creating…";
  try {
    const d = await send("/api/v1/classify", "POST", { text, channel: $("channel").value });
    renderNet(d);
    renderDetails(d);
    refreshBadge();
    toast(`<span><b>${d.ticket_ref}</b> created for ${esc(d.department)}</span>`, { label: "Open", run: () => { selectTab($("tab-inbox")); openTicket(d.ticket_ref); } });
    setLive("", "Saved as a ticket");
    btn.textContent = "Ticket created ✓";
    return;
  } catch (err) {
    showError($("route-error"), err);
    btn.disabled = false;
    btn.textContent = "Create ticket";
  }
}
$("route-btn").addEventListener("click", createTicket);

$("samples").innerHTML = SAMPLES.map((s) => `<button type="button" class="chip" data-text="${esc(s)}">${esc(s)}</button>`).join("");
$("samples").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  $("query").value = chip.dataset.text;
  $("route-btn").textContent = "Create ticket";
  clearTimeout(liveTimer);
  classifyLive();
});

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(drawCharts, 120);
});

/* ---------- Inbox ---------- */
const inbox = { status: "open,in_progress", department: "", priority: "", review: false, q: "", page: 1, items: [], total: 0, selected: null };
let searchTimer;

async function refreshBadge() {
  try {
    const r = await api("/api/v1/tickets?status=open,in_progress&priority=urgent&page_size=1");
    $("inbox-count").textContent = r.total || "";
    $("inbox-count").title = `${r.total} urgent tickets open`;
  } catch { /* best effort */ }
}

async function loadQueue(reset) {
  if (reset) { inbox.page = 1; inbox.items = []; }
  const params = new URLSearchParams({ page: inbox.page, page_size: 30 });
  if (inbox.status) params.set("status", inbox.status);
  if (inbox.department) params.set("department", inbox.department);
  if (inbox.priority) params.set("priority", inbox.priority);
  if (inbox.review) params.set("needs_review", "true");
  if (inbox.q) params.set("q", inbox.q);
  try {
    const r = await api(`/api/v1/tickets?${params}`);
    inbox.total = r.total;
    inbox.items = reset ? r.items : inbox.items.concat(r.items);
    renderQueue();
  } catch (err) {
    $("queue").innerHTML = `<li class="error" style="padding:16px">${esc(err.message)}</li>`;
  }
}

function queueItem(t) {
  const late = t.status !== "resolved" && t.sla_breached;
  const cat = t.needs_review ? "review" : t.category;
  return `<li><button type="button" class="q-item" data-ref="${t.ref}" aria-current="${t.ref === inbox.selected}">
      <span class="q-top"><span class="q-ref">${t.ref}</span>${t.priority !== "normal" ? prioBadge(t.priority) : ""}
        <span class="tag c-${cat}">${esc(t.needs_review ? "Needs review" : t.label)}</span></span>
      <span class="q-due ${late ? "late" : ""}">${dueText(t)}</span>
      <span class="q-text">${esc(t.text)}</span>
    </button></li>`;
}

function renderQueue() {
  $("queue-meta").textContent = inbox.total ? `${fmtNum(inbox.total)} ticket${inbox.total === 1 ? "" : "s"}` : "No tickets match these filters";
  $("queue").innerHTML = inbox.items.map(queueItem).join("");
  $("queue-more").hidden = inbox.items.length >= inbox.total;
}

$("queue").addEventListener("click", (e) => {
  const b = e.target.closest(".q-item");
  if (b) openTicket(b.dataset.ref);
});
$("queue-more").addEventListener("click", () => { inbox.page += 1; loadQueue(false); });
segmented($("inbox-status"), (v) => { inbox.status = v; loadQueue(true); });
$("inbox-dept").addEventListener("change", (e) => { inbox.department = e.target.value; loadQueue(true); });
$("inbox-priority").addEventListener("change", (e) => { inbox.priority = e.target.value; loadQueue(true); });
$("inbox-review").addEventListener("change", (e) => { inbox.review = e.target.checked; loadQueue(true); });
$("inbox-q").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { inbox.q = e.target.value.trim(); loadQueue(true); }, 250);
});

async function openTicket(ref) {
  inbox.selected = ref;
  document.querySelectorAll(".q-item").forEach((b) => b.setAttribute("aria-current", b.dataset.ref === ref));
  try {
    renderTicket(await api(`/api/v1/tickets/${ref}`));
    if (window.matchMedia("(max-width: 1024px)").matches) $("ticket").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    $("ticket").innerHTML = `<p class="error">${esc(err.message)}</p>`;
  }
}

function renderTicket(t) {
  const cat = t.needs_review ? "review" : t.category;
  const late = t.status !== "resolved" && t.sla_breached;
  const probs = ORDER.map((c) => `
    <div class="prob c-${c}"><span>${esc(catLabel(c))}</span>
      <span class="bar"><span style="width:${(t.probabilities[c] || 0) * 100}%"></span></span>
      <span class="num">${pct(t.probabilities[c])}</span></div>`).join("");
  const statusBtns = {
    open: [["in_progress", "Start work"], ["resolved", "Resolve"]],
    in_progress: [["resolved", "Resolve"], ["open", "Back to queue"]],
    resolved: [["open", "Reopen"]],
  }[t.status];
  const opts = ORDER.map((c) => `<option value="${c}" ${c === t.category ? "selected" : ""}>${esc(CATS[c].department)}</option>`).join("");
  const flags = flagsHTML(t.pii_redacted, t.rules_applied);
  const topic = t.intent ? t.intent.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "–";

  $("ticket").innerHTML = `
    <div class="t-head">
      <div><div class="t-ref">${t.ref}</div>
        <div class="t-meta">${esc(t.channel)} · ${t.customer_ref ? `${esc(t.customer_ref)} · ` : ""}created ${relTime(t.created_at)}</div></div>
      <div class="t-badges">${prioBadge(t.priority)}<span class="badge">${{ open: "Open", in_progress: "In progress", resolved: "Resolved" }[t.status]}</span></div>
    </div>
    <p class="t-text">${esc(t.text)}</p>
    <dl class="t-grid">
      <div><dt>Team</dt><dd>${esc(t.department)}</dd></div>
      <div><dt>Category</dt><dd><span class="tag c-${cat}">${esc(t.needs_review ? "Needs review" : t.label)}</span>
        ${t.rerouted ? `<span class="hint"> · model said ${esc(catLabel(t.model_category))}</span>` : ""}</dd></div>
      <div><dt>Topic</dt><dd>${esc(topic)}</dd></div>
      <div><dt>Confidence</dt><dd class="mono">${pct(t.confidence, 1)}</dd></div>
      <div><dt>Respond by</dt><dd class="${late ? "late" : ""}">${clock(t.due_at)} · ${dueText(t)}</dd></div>
      <div><dt>Assignee</dt><dd>${esc(t.assignee || "Unassigned")}</dd></div>
    </dl>
    ${flags ? `<ul class="flags">${flags}</ul>` : ""}
    <div class="probs">${probs}</div>
    <div class="actions">
      <div class="action"><span>Status</span><div class="action-ctrl">
        ${statusBtns.map(([v, l], i) => `<button type="button" class="btn btn-sm ${i ? "btn-ghost" : "btn-primary"}" data-status="${v}">${l}</button>`).join("")}</div></div>
      <div class="action"><span>Route to</span><div class="action-ctrl">
        <select id="t-reroute" aria-label="Route to team">${opts}</select>
        <button type="button" class="btn btn-sm btn-ghost" id="t-reroute-btn">Re-route</button></div></div>
      <div class="action"><span>Assignee</span><div class="action-ctrl">
        <input type="text" id="t-assignee" placeholder="Agent name" value="${esc(t.assignee || "")}" maxlength="64" aria-label="Assignee">
        <button type="button" class="btn btn-sm btn-ghost" id="t-assign-btn">Assign</button></div></div>
      <div class="action"><span>Note</span><div class="action-ctrl">
        <input type="text" id="t-note" maxlength="2000" placeholder="Internal note for other agents" aria-label="Internal note">
        <button type="button" class="btn btn-sm btn-ghost" id="t-note-btn">Add</button></div></div>
      <p class="error" id="t-error" hidden></p>
    </div>
    <ol class="timeline">${t.events.slice().reverse().map((e) => `
      <li><span><time datetime="${e.at}">${clock(e.at)} · ${esc(e.actor)}</time>${(EVENT_TEXT[e.type] || (() => esc(e.type)))(e.data)}</span></li>`).join("")}</ol>`;

  const patch = async (body, message) => {
    try {
      const updated = await send(`/api/v1/tickets/${t.ref}`, "PATCH", { actor: "you", ...body });
      renderTicket(updated);
      const i = inbox.items.findIndex((x) => x.ref === t.ref);
      if (i >= 0) { inbox.items[i] = updated; renderQueue(); }
      refreshBadge();
      if (message) toast(message);
    } catch (err) {
      showError($("t-error"), err);
    }
  };
  $("ticket").querySelectorAll("[data-status]").forEach((b) => b.addEventListener("click", () => patch({ status: b.dataset.status })));
  $("t-reroute-btn").addEventListener("click", () => {
    const c = $("t-reroute").value;
    patch({ category: c }, `Re-routed to ${esc(CATS[c].department)}. Saved as training feedback.`);
  });
  $("t-assign-btn").addEventListener("click", () => patch({ assignee: $("t-assignee").value.trim() }));
  $("t-note-btn").addEventListener("click", () => { const note = $("t-note").value.trim(); if (note) patch({ note }); });
}

/* ---------- Batch ---------- */
let batchResults = [];
let batchFilter = "all";
let batchFile = null;

function setFile(f) { batchFile = f || null; $("drop-file").textContent = batchFile ? batchFile.name : ""; }
$("batch-file").addEventListener("change", (e) => setFile(e.target.files[0]));
const drop = $("drop");
["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("over")));
drop.addEventListener("drop", (e) => { e.preventDefault(); setFile(e.dataTransfer.files[0]); });
$("batch-sample").addEventListener("click", () => {
  $("batch-text").value = [
    "There's a payment on my card I didn't make", "My card was used in a shop I've never been to",
    ...SAMPLES, "The ATM swallowed my card", "I want to close my account", "What's the exchange rate for euros?",
    "My phone was stolen and it has my banking app on it", "How do I change my PIN?",
    "Is the interest rate on a personal loan fixed?", "I was charged twice for the same coffee",
    "Email me at sam@example.com, my loan repayment failed", "hello",
  ].join("\n");
  setFile(null);
  $("batch-file").value = "";
});

$("batch-btn").addEventListener("click", async () => {
  const btn = $("batch-btn");
  showError($("batch-error"), null);
  const lines = $("batch-text").value.split("\n").map((l) => l.trim()).filter(Boolean);
  if (!batchFile && !lines.length) { showError($("batch-error"), "Add some messages or upload a CSV first."); return; }
  const createTickets = $("batch-tickets").checked;
  btn.disabled = true;
  btn.textContent = "Routing…";
  try {
    let data;
    if (batchFile) {
      const form = new FormData();
      form.append("file", batchFile);
      form.append("create_tickets", createTickets);
      data = await api("/api/v1/classify/csv", { method: "POST", body: form });
    } else {
      data = await send("/api/v1/classify/batch", "POST", { texts: lines, create_tickets: createTickets });
    }
    batchResults = data.results;
    batchFilter = "all";
    renderBatch(data.summary, createTickets);
    if (createTickets) refreshBadge();
  } catch (err) {
    showError($("batch-error"), err);
  } finally {
    btn.disabled = false;
    btn.textContent = "Route all";
  }
});

function renderBatch(summary, created) {
  $("batch-results").hidden = false;
  const notes = [summary.urgent && `${summary.urgent} urgent`, summary.needs_review && `${summary.needs_review} need review`,
    created && "tickets created"].filter(Boolean).join(" · ");
  $("batch-title").innerHTML = `${summary.total} messages routed${notes ? ` <span class="hint">· ${notes}</span>` : ""}`;
  $("batch-split").innerHTML = ORDER.filter((c) => summary.counts[c])
    .map((c) => `<div class="split-seg c-${c}" style="flex:${summary.counts[c]}" title="${esc(catLabel(c))}: ${summary.counts[c]}"></div>`).join("");
  const fb = (key, label, n, cat) => `<button type="button" class="chip" data-f="${key}" aria-pressed="${batchFilter === key}">${cat ? `<span class="tag c-${cat}"></span>` : ""}${esc(label)} <span class="muted">${n}</span></button>`;
  $("batch-filters").innerHTML = fb("all", "All", summary.total)
    + ORDER.filter((c) => summary.counts[c]).map((c) => fb(c, catLabel(c), summary.counts[c], c)).join("")
    + (summary.needs_review ? fb("review", "Needs review", summary.needs_review, "review") : "");
  renderBatchRows();
}
function renderBatchRows() {
  const rows = batchResults.filter((r) => batchFilter === "all" || (batchFilter === "review" ? r.needs_review : r.category === batchFilter));
  $("batch-rows").innerHTML = rows.map((r) => `
    <tr>
      <td>${esc(r.text)}${r.ticket_ref ? ` <span class="hint mono">${r.ticket_ref}</span>` : ""}</td>
      <td><span class="tag c-${r.needs_review ? "review" : r.category}">${esc(r.needs_review ? `${r.label}?` : r.label)}</span></td>
      <td>${esc(r.intent?.label || "–")}</td>
      <td>${esc(r.department)} ${r.priority === "urgent" ? prioBadge("urgent") : ""}</td>
      <td class="num ${r.needs_review ? "low" : ""}">${pct(r.confidence, 1)}</td>
    </tr>`).join("");
}
$("batch-filters").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  batchFilter = b.dataset.f;
  document.querySelectorAll("#batch-filters button").forEach((x) => x.setAttribute("aria-pressed", x === b));
  renderBatchRows();
});
$("batch-download").addEventListener("click", () => {
  const q = (s) => `"${String(s ?? "").replace(/"/g, '""')}"`;
  const lines = [["text", "category", "topic", "department", "priority", "confidence", "needs_review", "ticket"].join(",")];
  batchResults.forEach((r) => lines.push([q(r.text), r.category, q(r.intent?.label), q(r.department), r.priority,
    r.confidence, r.needs_review, r.ticket_ref || ""].join(",")));
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  Object.assign(document.createElement("a"), { href: url, download: "routed_queries.csv" }).click();
  URL.revokeObjectURL(url);
});

/* ---------- Charts ---------- */
const tip = $("tooltip");
function showTip(e, html) {
  tip.innerHTML = html;
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
  tip.style.left = `${x}px`;
  tip.style.top = `${y}px`;
}
const hideTip = () => { tip.hidden = true; };
function niceMax(v) {
  if (v <= 5) return 5;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].map((m) => m * p).find((m) => m >= v);
}
function axes(W, H, L, T, B, max) {
  const y = (v) => T + (H - T - B) * (1 - v / max);
  const ticks = [0, max / 2, max];
  return [y, `<g class="grid">${ticks.map((t) => `<line x1="${L}" x2="${W}" y1="${y(t)}" y2="${y(t)}"/>`).join("")}</g>
    <g class="axis">${ticks.map((t) => `<text x="${L - 8}" y="${y(t) + 4}" text-anchor="end">${t}</text>`).join("")}</g>`];
}
function stackedDaily(days, W) {
  const H = 240, L = 36, B = 24, T = 8;
  const max = niceMax(Math.max(1, ...days.map((d) => ORDER.reduce((a, c) => a + d[c], 0))));
  const [y, frame] = axes(W, H, L, T, B, max);
  const bw = (W - L) / days.length;
  const every = Math.ceil(days.length / Math.max(2, Math.floor(W / 90)));
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Tickets per day by category">${frame}`;
  days.forEach((d, i) => {
    const x = L + i * bw + bw * 0.2, w = bw * 0.6;
    let acc = 0, segs = "";
    ORDER.forEach((c) => {
      if (!d[c]) return;
      const y0 = y(acc), y1 = y(acc + d[c]);
      segs += `<rect x="${x}" y="${y1}" width="${w}" height="${Math.max(y0 - y1 - 2, 1)}" rx="2" fill="var(--${c})"/>`;
      acc += d[c];
    });
    svg += `<g class="col" data-i="${i}">${segs}<rect class="hit" x="${L + i * bw}" y="${T}" width="${bw}" height="${H - T - B}"/></g>`;
    if (i % every === 0) {
      const label = new Date(`${d.date}T00:00`).toLocaleDateString([], { month: "short", day: "numeric" });
      svg += `<text class="lbl" x="${x + w / 2}" y="${H - 6}" text-anchor="middle">${label}</text>`;
    }
  });
  return `${svg}</svg>`;
}
function histogram(bins, threshold, W) {
  const H = 200, L = 36, B = 24, T = 20;
  const max = niceMax(Math.max(1, ...bins.map((b) => b.count)));
  const [y, frame] = axes(W, H, L, T, B, max);
  const bw = (W - L) / bins.length;
  const tx = L + (W - L) * threshold;
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Distribution of model confidence">${frame}`;
  bins.forEach((b, i) => {
    const below = (i + 1) / 10 <= threshold;
    svg += `<g class="col" data-i="${i}"><rect x="${L + i * bw + 3}" y="${y(b.count)}" width="${bw - 6}" height="${Math.max(y(0) - y(b.count), b.count ? 1 : 0)}" rx="3"
      fill="${below ? "var(--text-3)" : "var(--text-2)"}" opacity="${below ? 0.5 : 0.9}"/>
      <rect class="hit" x="${L + i * bw}" y="${T}" width="${bw}" height="${H - T - B}"/></g>`;
    if (bw > 34 || i % 2 === 0) svg += `<text class="lbl" x="${L + i * bw + bw / 2}" y="${H - 6}" text-anchor="middle">${(i / 10).toFixed(1)}</text>`;
  });
  svg += `<line x1="${tx}" x2="${tx}" y1="${T - 12}" y2="${H - B}" stroke="var(--danger)" stroke-width="1.5" stroke-dasharray="4 3"/>
    <text class="lbl" x="${tx - 6}" y="${T - 4}" text-anchor="end">review below ${pct(threshold)}</text>`;
  return `${svg}</svg>`;
}

/* ---------- Analytics ---------- */
let anDays = 14;
let lastAnalytics = null;
segmented($("an-window"), (v) => { anDays = +v; loadAnalytics(); });

function drawCharts() {
  const a = lastAnalytics;
  const daily = document.querySelector('[data-chart="daily"]');
  const conf = document.querySelector('[data-chart="conf"]');
  if (!a || !daily || !daily.clientWidth) return;
  daily.innerHTML = stackedDaily(a.by_day, Math.max(daily.clientWidth, 300));
  conf.innerHTML = histogram(a.confidence_histogram, TAXO.review_threshold ?? 0.6, Math.max(conf.clientWidth, 280));
  daily.querySelectorAll("g.col").forEach((g) => {
    const d = a.by_day[+g.dataset.i];
    const total = ORDER.reduce((s, c) => s + d[c], 0);
    const html = `<b>${new Date(`${d.date}T00:00`).toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })} · ${total}</b>`
      + ORDER.filter((c) => d[c]).map((c) => `<div><span><i class="c-${c}"></i>${esc(catLabel(c))}</span><span>${d[c]}</span></div>`).join("");
    g.addEventListener("mousemove", (e) => showTip(e, html));
    g.addEventListener("mouseleave", hideTip);
  });
  conf.querySelectorAll("g.col").forEach((g) => {
    const b = a.confidence_histogram[+g.dataset.i];
    g.addEventListener("mousemove", (e) => showTip(e, `<b>Confidence ${b.bin}</b><div><span>Tickets</span><span>${b.count}</span></div>`));
    g.addEventListener("mouseleave", hideTip);
  });
}

async function loadAnalytics() {
  const el = $("analytics");
  try {
    const a = await api(`/api/v1/analytics/summary?days=${anDays}`);
    const k = a.kpis;
    if (!k.tickets) {
      el.innerHTML = `<div class="card empty" style="padding:40px"><p class="empty-title">No tickets in the last ${anDays} days</p>
        <p>Route some messages, or run <code>make seed</code> to load demo traffic.</p></div>`;
      return;
    }
    const kpi = (l, v, s = "") => `<div class="card kpi"><div class="kpi-l">${l}</div><div class="kpi-v">${v}</div>${s ? `<div class="kpi-s">${s}</div>` : ""}</div>`;
    const mixTotal = Object.values(a.category_mix).reduce((x, y) => x + y, 0);
    const deptMax = Math.max(1, ...a.open_by_department.map((d) => d.open));
    el.innerHTML = `
      <div class="kpis">
        ${kpi("Tickets", fmtNum(k.tickets), `last ${anDays} days`)}
        ${kpi("Auto-routed", pct(k.auto_routed_rate, 1), "no manual review")}
        ${kpi("Corrected by agents", pct(k.reroute_rate, 1), "re-routed tickets")}
        ${kpi("Past deadline", fmtNum(k.open_sla_breached), `of ${fmtNum(k.open)} open`)}
        ${kpi("Closed on time", pct(k.sla_met_rate, 1), "of resolved tickets")}
        ${kpi("Routing time", k.latency_p95_ms != null ? `${k.latency_p95_ms} ms` : "–", "95th percentile")}
      </div>
      <div class="charts">
        <div class="card wide"><h3>Tickets per day</h3><p class="card-sub">By final category, after agent corrections.</p>
          <div class="legend">${ORDER.map((c) => `<span class="c-${c}"><i></i>${esc(catLabel(c))}</span>`).join("")}</div>
          <div class="plot" data-chart="daily"></div>
          <details class="table-toggle"><summary>View as table</summary><div class="card table-card"><table>
            <thead><tr><th>Date</th>${ORDER.map((c) => `<th class="num">${esc(catLabel(c))}</th>`).join("")}</tr></thead>
            <tbody>${a.by_day.map((d) => `<tr><td>${d.date}</td>${ORDER.map((c) => `<td class="num">${d[c]}</td>`).join("")}</tr>`).join("")}</tbody>
          </table></div></details>
        </div>
        <div class="card"><h3>Open work by team</h3><p class="card-sub">Striped part is past its response deadline.</p>
          <div class="legend"><span><i style="background:var(--text-2)"></i>Within deadline</span><span><i class="hatch"></i>Past deadline</span></div>
          ${a.open_by_department.length ? a.open_by_department.map((d) => `
            <div class="dept-row"><span class="dept-name">${esc(d.department)}</span>
              <span class="dept-bar">${d.open - d.breached ? `<span style="width:${((d.open - d.breached) / deptMax) * 100}%"></span>` : ""}${d.breached ? `<span class="breach" style="width:${(d.breached / deptMax) * 100}%"></span>` : ""}</span>
              <span class="num">${d.open}${d.breached ? ` <span class="late">· ${d.breached}</span>` : ""}</span></div>`).join("") : '<p class="muted">Nothing open.</p>'}
        </div>
        <div class="card"><h3>Category mix</h3><p class="card-sub">Share of tickets in the period.</p>
          <div class="probs" style="margin:0">${ORDER.map((c) => `<div class="prob c-${c}"><span>${esc(catLabel(c))}</span>
            <span class="bar"><span style="width:${(a.category_mix[c] / mixTotal) * 100}%"></span></span>
            <span class="num">${pct(a.category_mix[c] / mixTotal)}</span></div>`).join("")}</div>
          <p class="hint" style="margin-top:16px">Channels · ${Object.entries(a.channels).sort((x, y) => y[1] - x[1]).map(([c, n]) => `${esc(c)} ${n}`).join(" · ")}</p>
        </div>
        <div class="card"><h3>Model confidence</h3><p class="card-sub">Tickets by top-category confidence · average ${pct(k.avg_confidence, 1)}</p>
          <div class="plot" data-chart="conf"></div>
        </div>
        <div class="card"><h3>Agent corrections</h3><p class="card-sub">Each one is training data for the next model (<code>make retrain</code>).</p>
          ${a.top_corrections.length ? `<div class="card table-card"><table><thead><tr><th>Model said</th><th>Agent chose</th><th class="num">Tickets</th></tr></thead><tbody>
            ${a.top_corrections.map((r) => `<tr><td><span class="tag c-${r.from}">${esc(catLabel(r.from))}</span></td><td><span class="tag c-${r.to}">${esc(catLabel(r.to))}</span></td><td class="num">${r.count}</td></tr>`).join("")}
          </tbody></table></div>` : '<p class="muted">No corrections yet.</p>'}
        </div>
      </div>`;
    lastAnalytics = a;
    drawCharts();
  } catch (err) {
    el.innerHTML = `<p class="error">${esc(err.message)}</p>`;
  }
}

/* ---------- Model ---------- */
async function loadModel() {
  const el = $("model-report");
  try {
    const [m, v] = await Promise.all([api("/api/v1/model"), api("/api/v1/model/versions")]);
    el.innerHTML = modelHTML(m, v.versions);
  } catch (err) {
    el.innerHTML = `<p class="error">${esc(err.message)}</p>`;
  }
}

function modelHTML(m, versions) {
  const t = m.metrics.category, it = m.metrics.intent;
  const cands = [...m.model_selection.candidates].sort((a, b) => b.cv_macro_f1 - a.cv_macro_f1);
  const best = m.category_model.label;
  const params = (o) => Object.entries(o).map(([k, x]) => `${k}=${x}`).join(", ") || "–";
  const bars = cands.map((r) => `<div class="bar-row ${r.model === best ? "best" : ""}"><span>${esc(r.model)}</span>
      <span class="bar"><span style="width:${r.cv_macro_f1 * 100}%"></span></span><span class="num">${r.cv_macro_f1.toFixed(3)}</span></div>`).join("");
  const perClass = t.labels.map((c) => {
    const p = t.per_class[c];
    return `<tr><td><span class="tag c-${c}">${esc(catLabel(c))}</span></td><td class="num">${p.precision.toFixed(3)}</td>
      <td class="num">${p.recall.toFixed(3)}</td><td class="num">${p.f1.toFixed(3)}</td><td class="num">${p.support}</td></tr>`;
  }).join("");
  const n = t.labels.length;
  let cm = `<div class="cm" style="grid-template-columns: 90px repeat(${n}, minmax(0,1fr))"><div></div>`;
  cm += t.labels.map((c) => `<div class="cm-head">${esc(catLabel(c))}</div>`).join("");
  t.confusion_matrix.forEach((row, i) => {
    const total = row.reduce((a, b) => a + b, 0);
    cm += `<div class="cm-head row">${esc(catLabel(t.labels[i]))}</div>`;
    row.forEach((val, j) => {
      const share = total ? val / total : 0;
      const bg = i === j ? `color-mix(in srgb, var(--${t.labels[i]}) ${Math.round(18 + share * 72)}%, transparent)`
        : val ? `color-mix(in srgb, var(--danger) ${Math.min(45, Math.round(6 + share * 300))}%, transparent)` : "var(--surface-2)";
      cm += `<div class="cm-cell" style="background:${bg};color:${i === j && share > 0.5 ? "#fff" : "var(--text)"}" title="Actual ${esc(catLabel(t.labels[i]))}, predicted ${esc(catLabel(t.labels[j]))}: ${val}">${val}</div>`;
    });
  });
  cm += `</div><p class="cm-axis">Rows: actual · Columns: predicted</p>`;
  const gate = m.quality_gate.checks.map((c) => `<div class="gate-row"><span class="${c.passed ? "gate-ok" : "gate-bad"}">${c.passed ? "✓" : "✗"}</span>
    <span>${GATE_NAMES[c.check] || esc(c.check)}</span><span class="mono">${c.value.toFixed(3)} ≥ ${c.threshold.toFixed(3)}</span></div>`).join("");
  const versionRows = versions.map((r) => `<tr><td class="mono">${r.version}${r.production ? '<span class="prod">Live</span>' : ""}</td>
    <td>${esc(r.model)}</td><td class="num">${r.macro_f1.toFixed(3)}</td><td class="num">${r.fraud_recall.toFixed(3)}</td>
    <td class="num">${r.intent_accuracy.toFixed(3)}</td><td>${r.gate_passed ? '<span class="gate-ok">Passed</span>' : '<span class="gate-bad">Failed</span>'}</td></tr>`).join("");
  const figs = [["class_distribution.png", "Queries per category"], ["query_length.png", "Query length"],
    ["model_comparison.png", "Model comparison"], ["confusion_matrix.png", "Confusion matrix"], ["top_terms.png", "Indicator words"]]
    .map(([f, label]) => `<a class="card" href="/api/v1/model/figures/${f}" target="_blank" rel="noopener"><img src="/api/v1/model/figures/${f}" alt="${label}"><span>${label}</span></a>`).join("");
  const terms = ORDER.map((c) => `<div class="terms-row"><span class="tag c-${c}">${esc(catLabel(c))}</span>
    <div class="terms-list">${(m.top_terms[c] || []).slice(0, 10).map((x) => `<span class="term c-${c}">${esc(x.term)}</span>`).join("")}</div></div>`).join("");
  const stat = (v, l) => `<div class="card stat"><div class="stat-v">${v}</div><div class="stat-l">${l}</div></div>`;

  return `
    <header class="page-head">
      <div><h1>Model</h1><p>Production version <span class="mono">${m.version}</span>, evaluated on ${fmtNum(m.data.test_rows)} held-out messages.</p></div>
    </header>
    <div class="stat-row">
      ${stat(pct(t.accuracy, 1), "Category accuracy")}
      ${stat(t.macro_f1.toFixed(3), "Macro F1, every category weighted equally")}
      ${stat(pct(t.per_class.fraud.recall, 1), "Fraud recall, share of fraud reports caught")}
      ${stat(pct(it.accuracy, 1), `Topic accuracy over ${it.n_intents} topics · ${pct(it.top3_accuracy, 1)} in top 3`)}
    </div>
    <div class="charts">
      <div class="card"><div class="card-head"><h3>Release check</h3><span class="hint">Required before going live</span></div>
        <div class="gate">${gate}</div>
        <dl class="kv" style="margin-top:20px;grid-template-columns:120px 1fr">
          <dt>Model</dt><dd>${esc(best)} · ${esc(params(m.category_model.params))}</dd>
          <dt>Training data</dt><dd>${fmtNum(m.data.train_rows)} rows · ${Object.entries(m.data.sources).map(([k, x]) => `${esc(k)} ${fmtNum(x)}`).join(", ")}</dd>
          <dt>Fingerprint</dt><dd class="mono">${m.data.fingerprint}</dd>
          <dt>Trained</dt><dd>${clock(m.created_at)} · ${m.training_seconds}s · scikit-learn ${m.environment.scikit_learn}</dd>
        </dl>
      </div>
      <div class="card"><div class="card-head"><h3>Model comparison</h3><span class="hint">5-fold CV macro F1</span></div>
        ${bars}
        <p class="hint" style="margin-top:14px">Each family is tuned by grid search. The winner is chosen on cross-validation, never on the test set.</p>
      </div>
      <div class="card"><div class="card-head"><h3>Confusion matrix</h3><span class="hint">Test set</span></div>${cm}</div>
      <div class="card"><div class="card-head"><h3>Per-category scores</h3><span class="hint">Fraud recall matters most</span></div>
        <div class="card table-card"><table><thead><tr><th>Category</th><th class="num">Precision</th><th class="num">Recall</th><th class="num">F1</th><th class="num">n</th></tr></thead><tbody>${perClass}</tbody></table></div>
      </div>
      <div class="card wide"><div class="card-head"><h3>Versions</h3><span class="hint">Promote with <code>make promote V=…</code>, then reload without downtime</span></div>
        <div class="card table-card"><table><thead><tr><th>Version</th><th>Model</th><th class="num">Macro F1</th><th class="num">Fraud recall</th><th class="num">Topic acc.</th><th>Release check</th></tr></thead><tbody>${versionRows}</tbody></table></div>
      </div>
      <div class="card"><div class="card-head"><h3>Indicator words</h3><span class="hint">Logistic regression weights</span></div><div class="terms">${terms}</div></div>
      <div class="card"><div class="card-head"><h3>Intended use and limits</h3></div>
        <p style="color:var(--text-2);font-size:13px;margin-bottom:12px">${esc(m.intended_use)}</p>
        <ul class="limits">${m.limitations.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>
      </div>
    </div>
    <div class="section-head"><h2>Report figures</h2><span class="hint">Open full size for the write-up</span></div>
    <div class="gallery">${figs}</div>`;
}

/* ---------- Start ---------- */
(async function init() {
  try {
    const [taxo, ready] = await Promise.all([api("/api/v1/taxonomy"), api("/ready")]);
    TAXO = taxo;
    CATS = taxo.categories;
    $("status").classList.add("ok");
    $("status-text").textContent = ready.model_version;
    const dept = $("inbox-dept");
    ORDER.forEach((c) => dept.insertAdjacentHTML("beforeend", `<option>${esc(CATS[c].department)}</option>`));
    dept.insertAdjacentHTML("beforeend", `<option>${esc(taxo.review_department)}</option>`);
    refreshBadge();
  } catch {
    $("status").classList.add("down");
    $("status-text").textContent = "API offline";
    CATS = Object.fromEntries(ORDER.map((c) => [c, { label: c[0].toUpperCase() + c.slice(1), department: "" }]));
  }
  buildNet();
  if (window.ResizeObserver) new ResizeObserver(() => layoutNet()).observe($("viz"));
})();
