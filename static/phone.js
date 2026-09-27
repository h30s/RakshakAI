"use strict";

// Phone camera page, opened from the QR code in Camera Sources (or over USB with adb).

const $ = (id) => document.getElementById(id);
const preview = $("preview");
const token = new URLSearchParams(location.search).get("t") || "";
const phoneName = /iPhone|iPad/.test(navigator.userAgent) ? "iPhone"
  : /Android/.test(navigator.userAgent) ? "Android phone" : "Phone";

let facing = "environment";  // start with the back camera
let stream = null;
let sender = null;
let wakeLock = null;

function setStatus(text, kind = "") {
  $("status").textContent = text;
  $("status").className = "status" + (kind ? ` ${kind}` : "");
}

function showRunning(running) {
  $("start").hidden = running;
  $("stop").hidden = !running;
  $("flip").hidden = !running;
  $("placeholder").hidden = running;
  $("badge").hidden = !running;
}

async function start() {
  if (!window.isSecureContext || !navigator.mediaDevices) {
    setStatus("Camera access needs a secure page. Open the https:// link from the QR code.", "bad");
    return;
  }
  stopCamera();
  setStatus("Opening the camera…");
  try {
    stream = await openVideoStream({ facingMode: facing });
  } catch (err) {
    setStatus(describeCameraError(err), "bad");
    return;
  }
  const device = `${phoneName} · ${facing === "environment" ? "back" : "front"} camera`;
  sender = new FrameSender({ source: "live-mobile", token, device, video: preview, onStatus });
  await sender.start(stream);
  showRunning(true);
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch { /* optional */ }
}

function onStatus(state) {
  const badge = $("badge");
  badge.classList.toggle("on", state === "live");
  badge.textContent = state === "live" ? "● Live" : "Connecting…";
  if (state === "live") setStatus("Connected. The monitor is receiving this camera.", "ok");
  else if (state === "connecting") setStatus("Connecting to the monitor…");
  else if (state === "replaced") { stopCamera(); setStatus("Disconnected: another device took over, or the monitor disconnected this phone.", "bad"); }
  else if (state === "denied") { stopCamera(); setStatus("The monitor refused the connection. Scan the current QR code again.", "bad"); }
}

function stopCamera() {
  sender?.stop(false);
  sender = null;
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  preview.srcObject = null;
  wakeLock?.release().catch(() => {});
  wakeLock = null;
  showRunning(false);
}

$("start").addEventListener("click", start);
$("stop").addEventListener("click", () => { stopCamera(); setStatus("Stopped. Tap Start camera to stream again."); });
$("flip").addEventListener("click", () => { facing = facing === "environment" ? "user" : "environment"; start(); });
// The wake lock is released when the page is hidden; take it again when it comes back.
document.addEventListener("visibilitychange", async () => {
  if (!document.hidden && sender && !wakeLock) {
    try { wakeLock = await navigator.wakeLock?.request("screen"); } catch { /* optional */ }
  }
});
