"use strict";

// Camera Sources tab: connect this computer's webcam / USB cameras, or a phone (QR code or USB
// cable). Frames are sent to the server (capture.js), where each source is an ordinary camera
// in the shared detection loop; its processed feed comes back over the dashboard stream (/ws)
// like any other camera. Uses app.js globals (cameras, view, draw, renderObjects, fmtTime).
// Local cameras keep streaming while you switch to other tabs of the dashboard.

const SRC_STALE_MS = 3000;
const BUILTIN_CAMERA = /integrated|built-?in|facetime|internal|front|rear|back camera/i;

const src = {
  selected: "live-webcam",
  status: {},        // source id -> {connected, device} from /api/sources
  local: {},         // source id -> {sender, stream, state}
  timers: [],
  phoneUrl: null,
};

const srcCanvas = document.getElementById("src-canvas");
const srcCard = (id) => document.querySelector(`.src-card[data-source="${id}"]`);
const srcCam = (id) => cameras.find((c) => c.id === id);
const frameIsFresh = (cam) => cam?.rx && performance.now() - cam.rx < SRC_STALE_MS;

function srcMessage(el, text, bad = true) {
  el.hidden = !text;
  el.textContent = text || "";
  el.classList.toggle("bad", bad);
}

// ---------- Local cameras (webcam, USB) ----------

async function refreshDevices() {
  if (!navigator.mediaDevices?.enumerateDevices) return;
  const devices = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
  for (const card of document.querySelectorAll('.src-card[data-kind="builtin"], .src-card[data-kind="external"]')) {
    const select = card.querySelector(".src-device");
    const previous = select.value;
    select.innerHTML = "";
    if (!devices.length) {
      select.append(new Option("No camera found", ""));
      continue;
    }
    devices.forEach((d, i) => select.append(new Option(d.label || `Camera ${i + 1}`, d.deviceId)));
    // Built-in webcams are often named just "USB Camera", so names can't be relied on: with one
    // camera it is the laptop's; with several, prefer one named built-in for the Laptop Webcam
    // card and a different one for the USB card.
    const builtin = devices.find((d) => BUILTIN_CAMERA.test(d.label)) || devices[0];
    const other = devices.find((d) => d !== builtin);
    let pick = card.dataset.kind === "builtin" ? builtin : other || devices[0];
    if (previous && devices.some((d) => d.deviceId === previous)) pick = devices.find((d) => d.deviceId === previous);
    select.value = pick.deviceId;
    if (card.dataset.kind === "external" && !src.local[card.dataset.source]) {
      srcMessage(card.querySelector(".src-msg"), devices.length < 2
        ? "Only one camera is connected (it is the laptop webcam). Plug in a USB camera and it will appear here." : "", false);
    }
  }
}

async function startLocal(card) {
  try {
    await connectLocal(card);
  } catch (err) {  // unexpected: show it instead of failing silently
    console.error(err);
    stopLocal(card.dataset.source);
    srcMessage(card.querySelector(".src-msg"), `Could not connect: ${err?.message || err}`);
  }
}

async function connectLocal(card) {
  const id = card.dataset.source;
  const select = card.querySelector(".src-device");
  const msg = card.querySelector(".src-msg");
  stopLocal(id);
  srcMessage(msg, "");
  setLocalState(id, "opening");
  srcMessage(msg, "Allow camera access if the browser asks.", false);
  let stream;
  try {
    stream = await openVideoStream({ deviceId: select.value || undefined });
  } catch (err) {
    setLocalState(id, null);
    srcMessage(msg, describeCameraError(err));
    return;
  }
  srcMessage(msg, "");
  const track = stream.getVideoTracks()[0];
  const device = track?.label || select.selectedOptions[0]?.textContent || "Camera";
  const sender = new FrameSender({ source: id, device, onStatus: (s) => setLocalState(id, s) });
  src.local[id] = { sender, stream, state: "connecting" };
  track?.addEventListener("ended", () => { stopLocal(id); srcMessage(msg, "The camera was disconnected."); });
  await sender.start(stream);
  selectSource(id);
  refreshDevices();  // labels become available once permission is granted
}

function stopLocal(id) {
  const l = src.local[id];
  if (!l) return;
  delete src.local[id];
  l.sender.stop(false);
  l.stream.getTracks().forEach((t) => t.stop());
  setLocalState(id, null);
}

function setLocalState(id, state) {
  if (src.local[id]) src.local[id].state = state;
  if (state === "replaced") {
    const l = src.local[id];
    delete src.local[id];
    l?.stream.getTracks().forEach((t) => t.stop());
    srcMessage(srcCard(id).querySelector(".src-msg"), "Disconnected: another device took over this source.");
  }
  renderCard(id);
}

// ---------- Cards ----------

function renderCard(id) {
  const card = srcCard(id);
  if (!card) return;
  const server = src.status[id] || {};
  const local = src.local[id];
  const connected = server.connected || frameIsFresh(srcCam(id));
  let text = "Not connected";
  if (local?.state === "opening") text = "Opening camera…";
  else if (connected) text = `Connected · ${server.device || "camera"}`;
  else if (local || server.device) text = "Connecting…";
  const state = card.querySelector(".src-state");
  state.textContent = text;
  state.classList.toggle("on", !!connected);
  card.classList.toggle("connected", !!connected);
  const active = !!local || (card.dataset.kind === "phone" && !!server.device);
  card.querySelector(".src-stop").hidden = !active;
  const start = card.querySelector(".src-start");
  if (start) start.textContent = local ? "Switch camera" : "Connect";
}

function selectSource(id) {
  src.selected = id;
  for (const card of document.querySelectorAll(".src-card")) card.classList.toggle("selected", card.dataset.source === id);
  const cam = srcCam(id);
  document.getElementById("src-title").textContent = cam?.name || "";
  renderObjects([], document.getElementById("src-objects"), document.getElementById("src-objects-empty"),
    document.getElementById("src-obj-count"));
  renderStage();
  pollSourceObjects();
}

// ---------- Stage: the processed feed of the selected source ----------

function renderStage() {
  const cam = srcCam(src.selected);
  const fresh = frameIsFresh(cam);
  const empty = document.getElementById("src-empty");
  empty.hidden = fresh;
  if (!fresh) {
    const ctx = srcCanvas.getContext("2d");
    ctx.clearRect(0, 0, srcCanvas.width, srcCanvas.height);
    document.getElementById("src-time").textContent = "";
    document.getElementById("src-lag").textContent = "";
    document.getElementById("src-alert").hidden = true;
    document.getElementById("src-feed").classList.remove("threat");
    const status = src.status[src.selected];
    empty.textContent = status?.connected || src.local[src.selected]?.state === "live"
      ? "Starting live analysis…" : "Not connected. Connect this source on the left.";
  }
}

function sourcesFrame(cam) {
  if (cam.id !== src.selected) return;
  const { dets, time } = cam.frame;
  draw(srcCanvas, cam.frame);
  document.getElementById("src-empty").hidden = true;
  document.getElementById("src-time").textContent = fmtTime(time);
  document.getElementById("src-lag").textContent =
    `Detection view · ${Math.max(0, Math.round(Date.now() / 1000 - time))} s behind live, like every feed`;
  // Same alert as a dashboard tile: red frame and badge while a weapon is in view.
  const threats = dets.filter((d) => d[6]);
  document.getElementById("src-feed").classList.toggle("threat", threats.length > 0);
  const badge = document.getElementById("src-alert");
  badge.hidden = !threats.length;
  if (threats.length) badge.textContent = `⚠ ${[...new Set(threats.map((d) => d[4]))].join(", ")} detected`;
}

async function pollSourceObjects() {
  const id = src.selected;
  if (view !== "sources") return;
  const list = document.getElementById("src-objects"), empty = document.getElementById("src-objects-empty");
  const count = document.getElementById("src-obj-count");
  if (!frameIsFresh(srcCam(id))) { renderObjects([], list, empty, count); return; }
  try {
    const res = await fetch(`/api/cameras/${id}/objects`);
    if (res.ok && id === src.selected && view === "sources") renderObjects(await res.json(), list, empty, count);
  } catch { /* retry on next poll */ }
}

// ---------- Server status ----------

async function pollSources() {
  try {
    const res = await fetch("/api/sources");
    if (!res.ok) return;
    const data = await res.json();
    src.status = Object.fromEntries(data.sources.map((s) => [s.id, s]));
    src.phoneUrl = data.phone.ready ? data.phone.url : null;
    const n = data.sources.filter((s) => s.connected).length;
    document.getElementById("sources-count").textContent = n || "";
    for (const s of data.sources) renderCard(s.id);
    if (view === "sources") renderStage();
  } catch { /* retry */ }
}

function toggleQr() {
  const box = document.getElementById("qr-box");
  const msg = document.getElementById("usb-msg");
  if (!box.hidden) { box.hidden = true; return; }
  if (!src.phoneUrl) {
    srcMessage(msg, "The phone connection is not available: the HTTPS listener did not start (see the server log).");
    return;
  }
  srcMessage(msg, "");
  document.getElementById("qr-img").src = `/api/sources/qr.svg?${Date.now()}`;
  document.getElementById("qr-url").textContent = src.phoneUrl.replace(/\?.*/, "");
  box.hidden = false;
  selectSource("live-mobile");
}

async function connectUsbPhone() {
  const msg = document.getElementById("usb-msg");
  document.getElementById("qr-box").hidden = true;
  srcMessage(msg, "Looking for a phone on USB…", false);
  try {
    const r = await (await fetch("/api/sources/usb-phone", { method: "POST" })).json();
    srcMessage(msg, r.message, !r.ok);
    document.getElementById("usb-help").hidden = r.ok;
    if (r.ok) selectSource("live-mobile");
  } catch {
    srcMessage(msg, "Could not reach the server.");
  }
}

// ---------- Tab open/close (called by app.js routing) ----------

function openSources() {
  document.getElementById("sources-view").hidden = false;
  selectSource(src.selected);
  refreshDevices();
  if (!src.timers.length) src.timers = [setInterval(pollSourceObjects, 1000), setInterval(renderStage, 1000)];
}

function closeSources() {
  document.getElementById("sources-view").hidden = true;
  src.timers.forEach(clearInterval);
  src.timers = [];
}

function initSources() {
  for (const card of document.querySelectorAll(".src-card")) {
    const id = card.dataset.source;
    card.querySelector(".src-head").addEventListener("click", () => selectSource(id));
    card.querySelector(".src-start")?.addEventListener("click", () => startLocal(card));
    card.querySelector(".src-device")?.addEventListener("change", () => { if (src.local[id]) startLocal(card); });
    card.querySelector(".src-stop").addEventListener("click", () => {
      if (src.local[id]) stopLocal(id);
      else fetch(`/api/sources/${id}/disconnect`, { method: "POST" }).then(pollSources);
    });
  }
  document.getElementById("qr-toggle").addEventListener("click", toggleQr);
  document.getElementById("usb-phone").addEventListener("click", connectUsbPhone);
  navigator.mediaDevices?.addEventListener?.("devicechange", refreshDevices);
  pollSources();
  setInterval(pollSources, 2000);
}
