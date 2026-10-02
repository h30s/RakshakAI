"use strict";

// Detection modes page: pick a condition (night, fog, ...) and watch the live detection
// pipeline run on footage recorded in it.

const COLORS = { threat: "#ff4d4f", person: "#3fb68b", other: "#f5b83d" };
const VEHICLES = new Set(["Car", "Truck", "Bus", "Motorcycle", "Bicycle", "Train", "Boat"]);
const MODE_ICONS = {  // 24x24 stroke icons
  normal: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  night: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  thermal: '<path d="M14 14.8V5a2 2 0 1 0-4 0v9.8a4 4 0 1 0 4 0z"/><path d="M12 11v6"/>',
  fog: '<path d="M4 9h13M7 13h13M4 17h11M9 5h8"/>',
  weather: '<path d="M7 15a5 5 0 1 1 9.6-2H17a3 3 0 0 1 0 6H8"/><path d="M8 21l1-2M12 21l1-2M16 21l1-2"/>',
};

const $ = (id) => document.getElementById(id);
const canvas = $("stage-canvas");
const loader = $("loader");
const poster = $("poster");
const connEl = $("conn");

let modes = [];
let current = null;   // {mode, clip}
let ws = null;
let frame = null;     // {idx, time, dets, image}

// ---------- Rendering ----------

function fitCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  return dpr;
}

// Detection row: [x1, y1, x2, y2, label, conf, threat, personId]
function draw() {
  if (!frame?.image || !canvas.clientWidth) return;
  const dpr = fitCanvas();
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.drawImage(frame.image, 0, 0, W, H);
  const font = Math.round(14 * dpr), pad = Math.round(4 * dpr);
  ctx.font = `600 ${font}px Inter, "Segoe UI", system-ui, sans-serif`;
  ctx.textBaseline = "top";
  ctx.lineWidth = Math.max(1.5, 2.5 * dpr);
  for (const [x1, y1, x2, y2, label, conf, threat] of [...frame.dets].sort((a, b) => a[6] - b[6])) {
    const color = threat ? COLORS.threat : label === "Person" ? COLORS.person : COLORS.other;
    const x = x1 * W, y = y1 * H;
    ctx.strokeStyle = color;
    ctx.strokeRect(x, y, (x2 - x1) * W, (y2 - y1) * H);
    const text = `${label} ${conf}%`;
    const th = font + pad * 1.5, tw = ctx.measureText(text).width + pad * 2;
    const ty = y - th >= 0 ? y - th : y, tx = Math.min(x, W - tw);
    ctx.fillStyle = color;
    ctx.fillRect(tx, ty, tw, th);
    ctx.fillStyle = threat ? "#fff" : "#0d1014";
    ctx.fillText(text, tx + pad, ty + pad * 0.75);
  }
}

function updateStats() {
  const dets = frame?.dets;
  const set = (id, v) => { $(id).textContent = v; };
  if (!dets) { ["stat-people", "stat-vehicles", "stat-weapons", "stat-conf"].forEach((id) => set(id, "–")); return; }
  const weapons = dets.filter((d) => d[6]).length;
  set("stat-people", dets.filter((d) => d[4] === "Person").length);
  set("stat-vehicles", dets.filter((d) => VEHICLES.has(d[4])).length);
  set("stat-weapons", weapons);
  $("stat-weapons-box").classList.toggle("alert", weapons > 0);
  set("stat-conf", dets.length ? `${Math.round(dets.reduce((s, d) => s + d[5], 0) / dets.length)}%` : "–");
}

function renderObjects(items) {
  const list = $("objects");
  $("objects-empty").hidden = items.length > 0;
  $("objects-empty").textContent = frame ? "No objects detected." : "Waiting for detections…";
  $("obj-count").textContent = items.length ? `(${items.length})` : "";
  list.innerHTML = "";
  for (const o of items) {
    const li = document.createElement("li");
    li.className = "obj" + (o.threat ? " threat" : "");
    const img = o.thumbnail ? document.createElement("img") : document.createElement("div");
    if (o.thumbnail) { img.src = o.thumbnail; img.alt = o.label; } else img.className = "noimg";
    const body = document.createElement("div");
    body.className = "obj-body";
    body.innerHTML = `
      <div class="obj-title"><span class="obj-name"></span><span class="obj-seen"></span></div>
      <div class="obj-conf">Confidence: <b></b></div>
      <div class="obj-details"></div>`;
    body.querySelector(".obj-name").textContent = o.label;
    body.querySelector(".obj-seen").textContent = o.in_view ? "In view" : `${o.seconds_ago}s ago`;
    body.querySelector(".obj-conf b").textContent = `${o.confidence}%`;
    body.querySelector(".obj-details").textContent = o.details;
    li.append(img, body);
    list.append(li);
  }
}

const fmtTime = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false });
const posterUrl = (clip) => `/api/modes/clips/${clip.id}/poster.jpg`;

// ---------- Stream ----------

function connect() {
  disconnect();
  if (!current || document.hidden) return;
  const clip = current.clip;
  const sock = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/modes/${clip.id}`);
  ws = sock;
  sock.binaryType = "arraybuffer";
  connEl.textContent = "Connecting…"; connEl.className = "conn";
  sock.onclose = () => {
    if (ws !== sock) return;  // closed on purpose (clip changed)
    ws = null;
    connEl.textContent = "Disconnected — retrying…"; connEl.className = "conn bad";
    setTimeout(() => { if (!ws && current?.clip === clip) connect(); }, 2000);
  };
  sock.onmessage = async (ev) => {
    // [uint8 camera index][uint16 meta length][meta json][jpeg]
    const dv = new DataView(ev.data);
    const metaLen = dv.getUint16(1);
    const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(ev.data, 3, metaLen)));
    const image = await createImageBitmap(new Blob([new Uint8Array(ev.data, 3 + metaLen)], { type: "image/jpeg" }));
    if (ws !== sock) { image.close?.(); return; }
    frame?.image?.close?.();
    frame = { ...meta, image };
    loader.hidden = true;
    connEl.textContent = "● Live"; connEl.className = "conn ok";
    draw();
    $("stage-time").textContent = fmtTime(meta.time);
    updateStats();
  };
}

function disconnect() {
  const sock = ws;
  ws = null;
  sock?.close();
}

async function pollObjects() {
  const clip = current?.clip;
  if (!clip || !frame) return;
  try {
    const res = await fetch(`/api/modes/clips/${clip.id}/objects`);
    if (res.ok && current?.clip === clip) renderObjects(await res.json());
  } catch { /* server restarting; next poll retries */ }
}

// ---------- Selection ----------

function renderCards() {
  const nav = $("mode-cards");
  nav.innerHTML = "";
  for (const m of modes) {
    const a = document.createElement("a");
    a.className = "mode-card";
    a.href = `#${m.id}`;
    a.dataset.mode = m.id;
    a.innerHTML = `
      <div class="mode-thumb">
        <img alt="" loading="lazy">
        <span class="mode-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round">${MODE_ICONS[m.id] || ""}</svg></span>
      </div>
      <div class="mode-text"><div class="mode-name"></div><div class="mode-tag"></div></div>`;
    a.querySelector("img").src = posterUrl(m.clips[0]);
    a.querySelector(".mode-name").textContent = `${m.name} Mode`;
    a.querySelector(".mode-tag").textContent = m.tagline;
    nav.append(a);
  }
}

function select(mode, clip) {
  if (current?.clip === clip) return;
  current = { mode, clip };
  for (const card of document.querySelectorAll(".mode-card")) {
    const on = card.dataset.mode === mode.id;
    card.classList.toggle("active", on);
    if (on) card.setAttribute("aria-current", "true"); else card.removeAttribute("aria-current");
    // On phones the cards are one scrolling row: bring the selected one into view.
    if (on) card.parentElement.scrollTo({ left: card.offsetLeft - card.parentElement.offsetLeft - 16, behavior: "smooth" });
  }
  $("mode-name").textContent = `${mode.name} Mode`;
  $("mode-tagline").textContent = mode.tagline;
  $("mode-about").textContent = mode.about;
  const chips = $("mode-challenges");
  chips.innerHTML = "";
  for (const c of mode.challenges) {
    const li = document.createElement("li");
    li.textContent = c;
    chips.append(li);
  }
  const sw = $("clip-switch");
  sw.innerHTML = "";
  mode.clips.forEach((c, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "seg-btn" + (c === clip ? " active" : "");
    b.textContent = c.name;
    b.onclick = () => { location.hash = i ? `${mode.id}/${i + 1}` : mode.id; };
    sw.append(b);
  });

  poster.src = posterUrl(clip);
  start();
}

// (Re)start the current clip. The server restarts it from the beginning and buffers a few
// seconds before the first frame, so show the loader over a still of the clip meanwhile.
function start() {
  frame?.image?.close?.();
  frame = null;
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  loader.hidden = false;
  $("stage-time").textContent = "";
  updateStats();
  renderObjects([]);
  connect();
}

function route() {
  const [modeId, n] = location.hash.slice(1).split("/");
  const mode = modes.find((m) => m.id === modeId) || modes[0];
  const clip = mode.clips[Math.min(mode.clips.length, Math.max(1, parseInt(n, 10) || 1)) - 1];
  select(mode, clip);
}

async function init() {
  modes = await (await fetch("/api/modes")).json();
  renderCards();
  window.addEventListener("hashchange", route);
  window.addEventListener("resize", draw);
  // Stop the clip (and its detection) while the page is in the background.
  document.addEventListener("visibilitychange", () => (document.hidden ? disconnect() : start()));
  setInterval(pollObjects, 1000);
  route();
}

init();
