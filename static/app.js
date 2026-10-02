"use strict";

const COLORS = { threat: "#ff4d4f", person: "#3fb68b", other: "#f5b83d", select: "#4ea1ff" };

const $ = (id) => document.getElementById(id);
const gridView = $("grid-view");
const detailView = $("detail-view");
const detailCanvas = $("detail-canvas");
const detailTime = $("detail-time");
const objectsList = $("objects");
const objectsEmpty = $("objects-empty");
const peopleView = $("people-view");
const personCanvas = $("person-canvas");
const connEl = $("conn");

let cameras = [];        // [{index, id, name, group, tile, canvas, time, badge, summary, frame}]
let view = null;         // overview | grid | camera | people | sources
let selected = null;     // camera shown in the camera detail view
let objectsTimer = null;
let personId = null;     // person shown in the people view
let personData = null;   // latest /api/persons/{id} response
let personCam = null;    // camera whose feed the people view shows
let personStatus = "active";
let peopleTimers = [];

// ---------- Rendering ----------

function fitCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  return dpr;
}

// Detection row: [x1, y1, x2, y2, label, conf, threat, personId]
function draw(canvas, frame, highlight = null) {
  if (!frame?.image || !canvas.clientWidth) return;
  const dpr = fitCanvas(canvas);
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.drawImage(frame.image, 0, 0, W, H);

  const big = canvas === detailCanvas || canvas === personCanvas || canvas.id === "src-canvas";
  const font = Math.round((big ? 14 : 11) * dpr);
  const pad = Math.round(4 * dpr);
  const lw = Math.max(1.5, (big ? 2.5 : 1.75) * dpr);
  ctx.font = `600 ${font}px Inter, "Segoe UI", system-ui, sans-serif`;
  ctx.textBaseline = "top";

  // Threats last so they sit on top; a highlighted person above everything else.
  const rank = (d) => (highlight && d[7] === highlight ? 2 : d[6]);
  const dets = [...frame.dets].sort((a, b) => rank(a) - rank(b));
  for (const [x1, y1, x2, y2, label, conf, threat, pid] of dets) {
    const chosen = highlight && pid === highlight;
    let color = threat ? COLORS.threat : label === "Person" ? COLORS.person : COLORS.other;
    if (chosen) color = COLORS.select;
    ctx.globalAlpha = highlight && !chosen && !threat ? 0.35 : 1;
    const x = x1 * W, y = y1 * H, w = (x2 - x1) * W, h = (y2 - y1) * H;
    ctx.lineWidth = chosen ? lw * 1.6 : lw;
    ctx.strokeStyle = color;
    ctx.strokeRect(x, y, w, h);

    const th = font + pad * 1.5;
    const text = `${label} ${conf}%`;
    const tw = ctx.measureText(text).width + pad * 2;
    const ty = y - th >= 0 ? y - th : y;          // above the box, or inside if at the top edge
    const tx = Math.min(x, W - tw);
    ctx.fillStyle = color;
    ctx.fillRect(tx, ty, tw, th);
    ctx.fillStyle = threat ? "#fff" : "#0d1014";
    ctx.fillText(text, tx + pad, ty + pad * 0.75);

    if (pid) {  // person ID tag in the box's bottom-left corner
      const iw = ctx.measureText(pid).width + pad * 2;
      const iy = Math.min(y + h, H) - th;
      ctx.fillStyle = "rgba(13,16,20,.85)";
      ctx.fillRect(x, iy, iw, th);
      ctx.fillStyle = color;
      ctx.fillText(pid, x + pad, iy + pad * 0.75);
    }
  }
  ctx.globalAlpha = 1;
}

const fmtTime = (t) => new Date(t * 1000).toLocaleTimeString([], { hour12: false });

function fmtAgo(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  return `${Math.floor(seconds / 3600)} h ago`;
}

function fmtDuration(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  return seconds < 60 ? `${seconds} s` : `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

function updateTile(cam) {
  const { dets, time } = cam.frame;
  cam.time.textContent = fmtTime(time);
  const threats = dets.filter((d) => d[6]);
  const people = dets.filter((d) => d[4] === "Person").length;
  cam.tile.classList.toggle("threat", threats.length > 0);
  cam.badge.hidden = threats.length === 0;
  if (threats.length) cam.badge.textContent = `⚠ ${[...new Set(threats.map((d) => d[4]))].join(", ")} detected`;
  cam.summary.textContent = `${people} ${people === 1 ? "person" : "people"} · ${dets.length} objects`;
}

const isLiveConnected = (cam) => cam.rx && performance.now() - cam.rx < 3000;

// Live-source tiles show "Not connected" (and drop a stale picture and alert) without a device.
function updateLiveTiles() {
  for (const cam of cameras) {
    if (!cam.live) continue;
    const on = isLiveConnected(cam);
    if (cam.offline.hidden === on) continue;
    cam.offline.hidden = on;
    if (!on) {
      cam.frame = null;
      cam.canvas.getContext("2d").clearRect(0, 0, cam.canvas.width, cam.canvas.height);
      cam.time.textContent = "";
      cam.summary.textContent = "";
      cam.badge.hidden = true;
      cam.tile.classList.remove("threat");
    }
  }
}

// ---------- Stream ----------

function wantsImage(cam) {
  return view === "grid" || (view === "camera" && cam === selected) || (view === "people" && cam === personCam)
    || (view === "sources" && cam.id === src.selected);
}

function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { connEl.textContent = "● Live"; connEl.className = "conn ok"; };
  ws.onclose = () => {
    connEl.textContent = "Disconnected — retrying…"; connEl.className = "conn bad";
    setTimeout(connect, 2000);
  };
  ws.onmessage = async (ev) => {
    // [uint8 camera index][uint16 meta length][meta json][jpeg]
    const dv = new DataView(ev.data);
    const cam = cameras[dv.getUint8(0)];
    if (!cam) return;
    const metaLen = dv.getUint16(1);
    const meta = JSON.parse(new TextDecoder().decode(new Uint8Array(ev.data, 3, metaLen)));
    cam.rx = performance.now();  // live sources: shows whether a device is connected
    if (!wantsImage(cam)) { cam.frame = { ...meta, image: cam.frame?.image }; return; }

    const image = await createImageBitmap(new Blob([new Uint8Array(ev.data, 3 + metaLen)], { type: "image/jpeg" }));
    cam.frame?.image?.close?.();
    cam.frame = { ...meta, image };
    if (view === "camera" && cam === selected) {
      draw(detailCanvas, cam.frame);
      detailTime.textContent = fmtTime(meta.time);
    } else if (view === "people" && cam === personCam) {
      draw(personCanvas, cam.frame, personId);
      $("person-time").textContent = fmtTime(meta.time);
    } else if (view === "sources") {
      sourcesFrame(cam);
    } else if (view === "grid") {
      draw(cam.canvas, cam.frame);
      updateTile(cam);
    }
  };
}

// ---------- Camera detail view ----------

function renderObjects(items, list = objectsList, empty = objectsEmpty, count = $("obj-count")) {
  empty.hidden = items.length > 0;
  count.textContent = items.length ? `(${items.length})` : "";
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

async function pollObjects() {
  if (!selected) return;
  const cam = selected;
  try {
    const res = await fetch(`/api/cameras/${cam.id}/objects`);
    if (res.ok && selected === cam) renderObjects(await res.json());
  } catch { /* server restarting; next poll retries */ }
}

function openCamera(cam) {
  selected = cam;
  $("detail-title").textContent = cam.name;
  detailView.hidden = false;
  renderObjects([]);
  draw(detailCanvas, cam.frame);
  pollObjects();
  objectsTimer = setInterval(pollObjects, 1000);
}

function closeCamera() {
  selected = null;
  clearInterval(objectsTimer);
  detailView.hidden = true;
}

// Clicking a person in the large view opens their journey.
detailCanvas.addEventListener("click", (e) => {
  const dets = selected?.frame?.dets || [];
  const r = detailCanvas.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
  const hits = dets.filter((d) => d[7] && x >= d[0] && x <= d[2] && y >= d[1] && y <= d[3]);
  hits.sort((a, b) => (a[2] - a[0]) * (a[3] - a[1]) - (b[2] - b[0]) * (b[3] - b[1]));
  if (hits.length) location.hash = `person=${hits[0][7]}`;
});

// ---------- People view ----------

const listRows = new Map();  // person id -> <li>

function statusText(p, asOf) {
  return p.active ? "Active" : `Last seen ${fmtAgo(asOf - p.last_seen)}`;
}

function renderPeopleList({ as_of: asOf, persons }) {
  $("plist-count").textContent = `(${persons.length})`;
  $("person-list-empty").hidden = persons.length > 0;
  const list = $("person-list");
  const keep = new Set();
  persons.forEach((p, i) => {
    keep.add(p.id);
    let li = listRows.get(p.id);
    if (!li) {
      li = document.createElement("li");
      li.innerHTML = `<button type="button" class="prow">
          <img alt=""><div><div class="prow-id"></div><div class="prow-loc"></div></div>
          <div class="prow-status"><span class="dot"></span><span></span></div></button>`;
      li.querySelector("button").addEventListener("click", () => { location.hash = `person=${p.id}`; });
      li.querySelector(".prow-id").textContent = p.id;
      listRows.set(p.id, li);
    }
    const img = li.querySelector("img");
    if (p.thumbnail && img.getAttribute("src") !== p.thumbnail) img.src = p.thumbnail;
    li.querySelector(".prow-loc").textContent = p.location + (p.steps > 1 ? ` · ${p.steps} locations` : "");
    li.querySelector(".dot").classList.toggle("on", p.active);
    li.querySelector(".prow-status span:last-child").textContent =
      p.active ? "Active" : fmtAgo(asOf - p.last_seen);
    li.querySelector("button").classList.toggle("selected", p.id === personId);
    if (list.children[i] !== li) list.insertBefore(li, list.children[i] || null);
  });
  for (const [id, li] of listRows) if (!keep.has(id)) { li.remove(); listRows.delete(id); }
}

async function pollPeople() {
  const q = $("person-search").value.trim();
  try {
    const res = await fetch(`/api/persons?status=${personStatus}&q=${encodeURIComponent(q)}`);
    if (res.ok && view === "people") renderPeopleList(await res.json());
  } catch { /* retry on next poll */ }
}

function renderPerson(p) {
  personData = p;
  $("person-empty").hidden = true;
  $("person-detail").hidden = false;
  $("p-id").textContent = p.id;
  if (p.thumbnail) $("p-photo").src = p.thumbnail;
  const pill = $("p-status");
  pill.className = "pill" + (p.active ? " on" : "");
  pill.textContent = p.active ? "● Currently detected" : `○ ${statusText(p, p.as_of)}`;
  $("p-meta").textContent = `First seen ${fmtTime(p.first_seen)}` + (p.site ? ` · ${p.site}` : "");

  const route = $("p-route");
  route.innerHTML = "";
  p.journey.forEach((s, i) => {
    if (i) route.append(Object.assign(document.createElement("span"), { className: "arrow", textContent: "→" }));
    const last = i === p.journey.length - 1;
    route.append(Object.assign(document.createElement("span"), {
      className: "stop" + (last && p.active ? " now" : ""), textContent: s.location,
    }));
  });

  $("p-loc").textContent = p.location;
  $("p-cam").textContent = p.camera;
  const cur = p.journey[p.journey.length - 1];
  $("p-loc-since").textContent = p.active ? `since ${fmtTime(cur.start)}` : `last seen ${fmtTime(p.last_seen)}`;
  $("person-feed-note").hidden = p.active;
  const cam = cameras.find((c) => c.id === p.camera_id);
  if (cam !== personCam) { personCam = cam; draw(personCanvas, cam?.frame, personId); }

  $("p-steps").textContent = `${p.journey.length} ${p.journey.length === 1 ? "location" : "locations"}`;
  const ol = $("journey");
  ol.innerHTML = "";
  p.journey.forEach((s, i) => {
    if (i) {
      const gap = s.start - p.journey[i - 1].end;
      const link = document.createElement("li");
      link.className = "jlink";
      link.innerHTML = "<span></span><span></span>";
      link.lastChild.textContent = gap > 1 ? `↓  ${fmtDuration(gap)} later` : "↓";
      ol.append(link);
    }
    const now = i === p.journey.length - 1 && p.active;
    const li = document.createElement("li");
    li.className = "jstep" + (now ? " now" : "");
    li.innerHTML = `<span class="jtime"></span><div class="jnode"><div class="jloc"></div><div class="jcam"></div></div>`;
    li.querySelector(".jtime").textContent = fmtTime(s.start);
    li.querySelector(".jloc").textContent = s.location;
    if (now) li.querySelector(".jloc").append(Object.assign(document.createElement("span"), { className: "jnow", textContent: "NOW" }));
    li.querySelector(".jcam").textContent = s.end - s.start < 1
      ? `${s.camera} · seen at ${fmtTime(s.start)}`
      : `${s.camera} · ${fmtTime(s.start)} – ${fmtTime(s.end)} (${fmtDuration(s.end - s.start)})`;
    ol.append(li);
  });
}

async function pollPerson() {
  if (!personId) return;
  const id = personId;
  try {
    const res = await fetch(`/api/persons/${encodeURIComponent(id)}`);
    if (id !== personId) return;
    if (res.ok) renderPerson(await res.json());
    else if (res.status === 404) showPersonMissing(id);
  } catch { /* retry on next poll */ }
}

function showPersonMissing(id) {
  personData = null; personCam = null;
  $("person-detail").hidden = true;
  $("person-empty").hidden = false;
  $("person-empty").firstElementChild.textContent = `No person with ID ${id} has been seen yet.`;
}

function openPeople(id) {
  const changed = id !== personId;
  personId = id;
  if (changed) {
    personData = null; personCam = null;
    $("person-detail").hidden = true;
    $("person-empty").hidden = false;
    $("person-empty").firstElementChild.textContent = id
      ? "Loading…" : "Select a person to see where they are and where they have been.";
  }
  peopleView.hidden = false;
  for (const [pid, li] of listRows) li.querySelector("button").classList.toggle("selected", pid === id);
  if (!peopleTimers.length) {
    pollPeople();
    peopleTimers = [setInterval(pollPeople, 2000), setInterval(pollPerson, 1000)];
  }
  pollPerson();
}

function closePeople() {
  peopleTimers.forEach(clearInterval);
  peopleTimers = [];
  personId = null; personData = null; personCam = null;
  peopleView.hidden = true;
}

$("person-search").addEventListener("input", pollPeople);
$("person-search").addEventListener("keydown", (e) => {
  const q = e.target.value.trim().toUpperCase();
  if (e.key === "Enter" && /^P-?\d+$/.test(q)) location.hash = `person=P-${q.replace(/\D/g, "").padStart(3, "0")}`;
});
document.querySelectorAll(".seg-btn").forEach((b) => b.addEventListener("click", () => {
  personStatus = b.dataset.status;
  document.querySelectorAll(".seg-btn").forEach((o) => o.classList.toggle("active", o === b));
  pollPeople();
}));

async function pollPeopleCount() {
  try {
    const res = await fetch("/api/persons/summary");
    if (res.ok) { const s = await res.json(); $("people-count").textContent = s.active ? s.active : ""; }
  } catch { /* retry */ }
}

// ---------- Routing ----------

function route() {
  const params = new URLSearchParams(location.hash.slice(1));
  const cam = cameras.find((c) => c.id === params.get("cam"));
  const person = params.get("person");
  const h = location.hash;
  const next = cam ? "camera" : person !== null || h === "#people" ? "people"
    : h === "#sources" ? "sources" : h === "#cameras" ? "grid" : "overview";

  if (view === "camera" && (next !== "camera" || cam !== selected)) closeCamera();
  if (view === "people" && next !== "people") closePeople();
  if (view === "sources" && next !== "sources") closeSources();
  if (view === "overview" && next !== "overview") closeOverview();
  const opening = view !== next;
  view = next;
  gridView.hidden = view !== "grid";
  if (view === "camera" && cam !== selected) openCamera(cam);
  if (view === "people") openPeople(person ? person.toUpperCase() : null);
  if (view === "sources" && opening) openSources();
  if (view === "overview" && opening) openOverview();
  $("tab-overview").classList.toggle("active", view === "overview");
  $("tab-cameras").classList.toggle("active", view === "grid" || view === "camera");
  $("tab-people").classList.toggle("active", view === "people");
  $("tab-sources").classList.toggle("active", view === "sources");
}

// ---------- Setup ----------

async function init() {
  const list = await (await fetch("/api/cameras")).json();
  const tpl = document.getElementById("tile-template");
  const groups = new Map();
  cameras = list.map((c) => {
    if (!groups.has(c.group)) {
      const section = document.createElement("div");
      section.className = "group";
      const groupIcon = c.group === "Live Sources" ? "sources" : c.multi_camera ? "route" : "building";
      section.innerHTML = `<div class="group-head"><div class="group-icon">${icon(groupIcon)}</div><h2></h2><span></span></div><div class="grid"></div>`;
      section.querySelector("h2").textContent = c.group;
      gridView.append(section);
      groups.set(c.group, section);
    }
    const section = groups.get(c.group);
    const tile = tpl.content.firstElementChild.cloneNode(true);
    tile.querySelector(".tile-name").textContent = c.name;
    tile.setAttribute("aria-label", `Open ${c.name}`);
    const cam = { ...c };
    tile.addEventListener("click", () => {
      if (c.live && !isLiveConnected(cam)) { src.selected = c.id; location.hash = "sources"; }
      else location.hash = `cam=${c.id}`;
    });
    if (c.live) {  // live source: placeholder while no device is connected
      tile.querySelector(".feed").insertAdjacentHTML("beforeend",
        '<div class="feed-offline"><b>Not connected</b><span>Connect it in Camera Sources</span></div>');
    }
    section.querySelector(".grid").append(tile);
    return Object.assign(cam, {
      tile, frame: null,
      canvas: tile.querySelector("canvas"),
      time: tile.querySelector(".feed-time"),
      badge: tile.querySelector(".alert-badge"),
      summary: tile.querySelector(".tile-summary"),
      offline: tile.querySelector(".feed-offline"),
    });
  });
  for (const [name, section] of groups) {
    const n = section.querySelectorAll(".tile").length;
    const linked = list.some((c) => c.group === name && c.multi_camera);
    const live = list.some((c) => c.group === name && c.live);
    section.querySelector(".group-head span").textContent = live ? "webcam, USB camera and phone · connect them in Camera Sources"
      : `${n} cameras` + (linked ? " · people are followed from camera to camera" : "");
  }
  $("back").addEventListener("click", () => { location.hash = "cameras"; });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && view === "camera") location.hash = "cameras";
  });
  window.addEventListener("hashchange", route);
  initSources();
  initThreats();
  setInterval(updateLiveTiles, 1000);
  route();
  connect();
  pollPeopleCount();
  setInterval(pollPeopleCount, 3000);
}

init();
