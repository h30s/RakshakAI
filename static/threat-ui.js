"use strict";

// Shared by the dashboard (Overview tab) and the Reports page: threat details dialog, the
// "Working on it" / "Mark as resolved" actions, formatting, and the alarm sound.

const TU = {
  statusText: { active: "Active", in_progress: "In progress", resolved: "Resolved" },
  onChange: () => {},  // called after an action changes a threat
};

const tuEsc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tuTime = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const tuDateTime = (t) => new Date(t * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function tuAgo(t, now = Date.now() / 1000) {
  const s = Math.max(0, Math.round(now - t));
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return tuDateTime(t);
}

function tuDuration(s) {
  s = Math.round(s);
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}

const tuLevelClass = (level) => ({ High: "lv-high", Medium: "lv-medium", Low: "lv-low" }[level] || "lv-none");
const tuStatusChip = (status) => `<span class="st-chip st-${status}">${TU.statusText[status]}</span>`;
const tuLevelPill = (level, score) => `<span class="lv-pill ${tuLevelClass(level)}">${tuEsc(level)}${score != null ? ` · ${score}` : ""}</span>`;

// Action buttons for an incident (open ones get both actions; resolved ones can be reopened).
function tuActions(t, compact = false) {
  if (t.status === "resolved") return compact ? "" : `<button type="button" class="btn" data-act="active" data-id="${t.id}">Reopen</button>`;
  const working = t.status === "active"
    ? `<button type="button" class="btn warn" data-act="in_progress" data-id="${t.id}">Working on it</button>` : "";
  return `${working}<button type="button" class="btn ok" data-act="resolved" data-id="${t.id}">Mark as resolved</button>`;
}

async function tuSetStatus(id, status, note = "") {
  const res = await fetch(`/api/threats/${encodeURIComponent(id)}/status`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status, note }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const t = await res.json();
  TU.onChange(t);
  return t;
}

// Clicks on any [data-act] button anywhere run that action.
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b) return;
  e.stopPropagation();
  b.disabled = true;
  const note = b.closest(".tdialog")?.querySelector("#td-note")?.value || "";
  try {
    const t = await tuSetStatus(b.dataset.id, b.dataset.act, note);
    if (tuDialog?.open && tuDialog.dataset.id === t.id) {
      const n = tuDialog.querySelector("#td-note");
      if (n) n.value = "";  // the note was saved with the action
      renderThreatDetails(t);
    }
  } catch {
    b.disabled = false;
  }
}, true);

// ---------- Details dialog ----------

let tuDialog = null;

function tuEnsureDialog() {
  if (tuDialog) return tuDialog;
  tuDialog = document.createElement("dialog");
  tuDialog.className = "tdialog";
  tuDialog.addEventListener("click", (e) => { if (e.target === tuDialog) tuDialog.close(); });  // backdrop
  document.body.append(tuDialog);
  return tuDialog;
}

async function openThreatDetails(id) {
  const d = tuEnsureDialog();
  d.dataset.id = id;
  d.innerHTML = `<div class="td-loading">Loading…</div>`;
  if (!d.open) d.showModal();
  try {
    const res = await fetch(`/api/threats/${encodeURIComponent(id)}`);
    if (res.ok && d.dataset.id === id) renderThreatDetails(await res.json());
  } catch { d.innerHTML = `<div class="td-loading">Could not load the threat.</div>`; }
}

function renderThreatDetails(t) {
  const d = tuEnsureDialog();
  const note = d.querySelector("#td-note")?.value || "";
  const img = t.snapshot ? `/api/threats/${t.id}/snapshot.jpg` : t.thumbnail;
  const facts = [
    ["Threat type", tuEsc(t.type)],
    ["Camera", `${tuEsc(t.camera)} <a class="td-link" href="/app#cam=${encodeURIComponent(t.camera_id)}">Open live view</a>`],
    ["Location", tuEsc(t.location)],
    ["Detected", `${tuDateTime(t.detected_at)}`],
    ["Last seen", `${tuDateTime(t.last_seen)}${t.sightings > 1 ? ` · seen ${t.sightings} times` : ""}`],
    ["Threat score", `${tuLevelPill(t.level, t.score)} <span class="muted">detection confidence ${t.confidence}%</span>`],
    ["Status", tuStatusChip(t.status) + (t.resolved_at ? ` <span class="muted">after ${tuDuration(t.time_to_resolve)}</span>` : "")],
  ];
  d.innerHTML = `
    <div class="td-head ${tuLevelClass(t.level)}">
      <div><span class="td-id">${tuEsc(t.id)}</span><h2>${tuEsc(t.type)} detected</h2></div>
      <button type="button" class="td-close" aria-label="Close">×</button>
    </div>
    <div class="td-body">
      <div class="td-media">${img ? `<img src="${tuEsc(img)}" alt="Detection snapshot">` : `<div class="td-noimg">No snapshot</div>`}
        <span class="muted">Snapshot at detection</span></div>
      <dl class="td-facts">${facts.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
    </div>
    <div class="td-actions">
      <textarea id="td-note" rows="2" maxlength="500" placeholder="Update or action taken (optional), e.g. “Guard sent to the entrance”"></textarea>
      <div class="td-buttons">${tuActions(t)}<button type="button" class="btn" id="td-save-note">Add note</button></div>
    </div>
    <div class="td-history"><h3>Actions & updates</h3><ol>${t.history.slice().reverse().map((h) => `
      <li class="ev-${h.event}"><span class="td-when">${tuDateTime(h.t)}</span>
        <span>${tuEsc(h.text)}${h.note ? `<q>${tuEsc(h.note)}</q>` : ""}</span></li>`).join("")}</ol></div>`;
  d.querySelector("#td-note").value = note;
  d.querySelector(".td-close").onclick = () => d.close();
  d.querySelector("#td-save-note").onclick = async () => {
    const text = d.querySelector("#td-note").value.trim();
    if (!text) return;
    const res = await fetch(`/api/threats/${t.id}/note`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note: text }),
    });
    if (res.ok) { d.querySelector("#td-note").value = ""; const u = await res.json(); TU.onChange(u); renderThreatDetails(u); }
  };
}

// ---------- Alarm sound (generated, no audio file) ----------

const Alarm = {
  ctx: null,
  get enabled() { try { return localStorage.getItem("alarmSound") !== "off"; } catch { return true; } },
  set enabled(on) { try { localStorage.setItem("alarmSound", on ? "on" : "off"); } catch { /* ignore */ } },
  // Browsers only allow sound after the user has interacted with the page.
  unlock() {
    if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.ctx.state === "suspended") this.ctx.resume();
  },
  get ready() { return !!this.ctx && this.ctx.state === "running"; },
  play() {
    if (!this.enabled || !this.ready) return false;
    const ctx = this.ctx, t0 = ctx.currentTime + 0.05;
    for (let i = 0; i < 6; i++) {  // three rising/falling two-tone pulses, ~1.8 s
      const osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.type = "square";
      osc.frequency.value = i % 2 ? 660 : 990;
      const t = t0 + i * 0.3;
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.12, t + 0.02);
      gain.gain.setValueAtTime(0.12, t + 0.24);
      gain.gain.linearRampToValueAtTime(0, t + 0.28);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.3);
    }
    return true;
  },
};
["pointerdown", "keydown"].forEach((ev) => document.addEventListener(ev, () => Alarm.unlock(), { capture: true }));
