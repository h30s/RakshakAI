"use strict";

// Sends a camera's video to the server as JPEG frames over a WebSocket. Used by the
// dashboard's Camera Sources tab (webcam / USB camera) and by the phone page. The server
// feeds the frames into the same detection loop as every other camera.

const SEND_FPS = 12;                   // the feeds' frame rate (config.FEED_FPS)
const SEND_W = 640, SEND_H = 360;      // the feeds' frame size (config.FRAME_W/H)

class FrameSender {
  // onStatus(state, detail): state is "connecting" | "live" | "replaced" | "denied" | "stopped"
  // video: an on-page <video> to play the stream in (iOS only decodes video that is on the page).
  constructor({ source, token = "", device = "Camera", video = null, onStatus = () => {} }) {
    Object.assign(this, { source, token, device, onStatus });
    this.canvas = Object.assign(document.createElement("canvas"), { width: SEND_W, height: SEND_H });
    // Kept in the page (invisibly): browsers may stop decoding video elements that are not.
    this.ownVideo = !video;
    this.video = video || document.body.appendChild(Object.assign(document.createElement("video"), {
      style: "position:fixed;width:2px;height:2px;opacity:0;pointer-events:none;left:0;top:0",
    }));
    this.video.muted = true;
    this.video.playsInline = true;
    this.video.setAttribute("playsinline", "");
    this.ws = null;
    this.timer = null;
    this.busy = false;
    this.running = false;
  }

  async start(stream) {
    this.halt();
    this.running = true;
    this.video.srcObject = stream;
    await this.video.play().catch(() => {});
    this.connect();
    // Tick from a worker: timers in a background tab are slowed to once a second, worker
    // timers are not, so a webcam keeps streaming while you look at another tab.
    this.timer = new Worker(URL.createObjectURL(new Blob(
      [`setInterval(() => postMessage(0), ${Math.round(1000 / SEND_FPS)})`], { type: "text/javascript" })));
    this.timer.onmessage = () => this.sendFrame();
  }

  connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const q = new URLSearchParams({ t: this.token, device: this.device });
    const ws = new WebSocket(`${proto}://${location.host}/ws/sources/${this.source}/publish?${q}`);
    this.ws = ws;
    this.onStatus("connecting");
    ws.onopen = () => this.onStatus("live");
    ws.onclose = (ev) => {
      if (this.ws !== ws || !this.running) return;
      this.ws = null;
      if (ev.code === 4409 || ev.code === 4403 || ev.code === 4404) {
        this.stop(false);
        this.onStatus(ev.code === 4409 ? "replaced" : "denied");
      } else {
        this.onStatus("connecting");
        setTimeout(() => { if (this.running && !this.ws) this.connect(); }, 2000);
      }
    };
  }

  sendFrame() {
    const v = this.video, ws = this.ws;
    if (this.busy || !ws || ws.readyState !== WebSocket.OPEN || !v.videoWidth) return;
    if (ws.bufferedAmount > 256 * 1024) return;  // network is behind: skip rather than queue up
    // Fit the whole picture into 16:9 (black bars for portrait video) - cropping a portrait
    // phone picture to 16:9 would cut most of it away.
    const ctx = this.canvas.getContext("2d");
    const s = Math.min(SEND_W / v.videoWidth, SEND_H / v.videoHeight);
    const w = v.videoWidth * s, h = v.videoHeight * s;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, SEND_W, SEND_H);
    ctx.drawImage(v, (SEND_W - w) / 2, (SEND_H - h) / 2, w, h);
    this.busy = true;
    this.canvas.toBlob(async (blob) => {
      try {
        if (blob && ws.readyState === WebSocket.OPEN) ws.send(await blob.arrayBuffer());
      } finally {
        this.busy = false;
      }
    }, "image/jpeg", 0.75);
  }

  stop(notify = true) {
    const wasRunning = this.halt();
    if (this.ownVideo) this.video.remove();
    if (notify && wasRunning) this.onStatus("stopped");
  }

  halt() {  // stop sending; returns whether it was running
    const wasRunning = this.running;
    this.running = false;
    this.timer?.terminate();
    this.timer = null;
    const ws = this.ws;
    this.ws = null;
    ws?.close();
    this.video.srcObject = null;
    return wasRunning;
  }
}

// Open a camera: a device id (from enumerateDevices) or a facing mode ("environment"/"user").
async function openVideoStream({ deviceId, facingMode } = {}) {
  const video = { width: { ideal: 1280 }, height: { ideal: 720 } };
  if (deviceId) video.deviceId = { exact: deviceId };
  else if (facingMode) video.facingMode = { ideal: facingMode };
  return navigator.mediaDevices.getUserMedia({ video, audio: false });
}

function describeCameraError(err) {
  if (!window.isSecureContext || !navigator.mediaDevices) return "Camera access needs a secure (https) page.";
  if (err?.name === "NotAllowedError") return "Camera permission was denied. Allow it in the browser's site settings and try again.";
  if (err?.name === "NotFoundError" || err?.name === "OverconstrainedError") return "That camera was not found. Is it plugged in?";
  if (err?.name === "NotReadableError") return "The camera is in use by another app, or the system blocked it.";
  return `Could not open the camera${err?.message ? `: ${err.message}` : "."}`;
}
