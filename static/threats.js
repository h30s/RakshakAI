"use strict";

// Overview tab: threat score, camera status, alerts and actions. Also raises alerts (toast +
// alarm sound + header bell) for new threats whichever tab is open. Uses threat-ui.js.

const ov = { data: null, seen: null, visible: false };
const ovEl = (id) => document.getElementById(id);

// ---------- Polling and new-alert detection ----------

async function pollThreats() {
  try {
    const res = await fetch("/api/threats/overview");
    if (!res.ok) return;
    const data = await res.json();
    ov.data = data;
    checkNewAlerts(data);
    renderHeaderStatus(data);
    if (ov.visible) renderOverview(data);
  } catch { /* server restarting; next poll retries */ }
}

function checkNewAlerts(data) {
  const ids = data.alerts.map((a) => a.id);
  if (!ov.seen) {  // first load: existing threats are not "new"
    ov.seen = new Set(ids);
    return;
  }
  const fresh = data.alerts.filter((a) => !ov.seen.has(a.id)).reverse();
  fresh.forEach((a) => ov.seen.add(a.id));
  if (!fresh.length) return;
  const serious = fresh.some((a) => a.level === "High" && a.status === "active");
  const played = serious && Alarm.play();
  fresh.slice(-3).forEach((a) => showToast(a, serious && !played && Alarm.enabled));
}

function showToast(a, soundBlocked) {
  const box = ovEl("toasts");
  const el = document.createElement("div");
  el.className = `toast ${tuLevelClass(a.level)}`;
  el.setAttribute("role", "alert");
  el.innerHTML = `
    <div class="toast-title">Threat detected</div>
    <div class="toast-text"><b>${tuEsc(a.type)}</b> detected on ${tuEsc(a.camera)}</div>
    <div class="toast-meta">Location: ${tuEsc(a.location)} · ${tuTime(a.detected_at)} · ${tuLevelPill(a.level, a.score)}</div>
    ${soundBlocked ? `<div class="toast-note">Alarm sound is blocked until you click on the page.</div>` : ""}
    <div class="toast-actions"><button type="button" class="btn" data-view>View details</button>
      <button type="button" class="toast-x" aria-label="Dismiss">×</button></div>`;
  el.querySelector("[data-view]").onclick = () => { openThreatDetails(a.id); el.remove(); };
  el.querySelector(".toast-x").onclick = () => el.remove();
  box.prepend(el);
  setTimeout(() => el.remove(), 20000);
}

function renderHeaderStatus(data) {
  setHeaderStatus(data.summary);  // nav.js
}

// ---------- Overview rendering ----------

function renderOverview(d) {
  const s = d.summary, now = d.now;
  ovEl("ov-updated").textContent = `Updated ${new Date(now * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;

  // Banner: the most serious threat nobody has taken on yet.
  const top = d.open.find((t) => t.status === "active");
  const banner = ovEl("ov-banner");
  banner.hidden = !top;
  if (top) {
    const more = d.open.filter((t) => t.status === "active").length - 1;
    banner.className = `ov-banner ${tuLevelClass(top.level)}`;
    banner.innerHTML = `
      <div class="ob-icon" aria-hidden="true">${icon("alert")}</div>
      <div class="ob-text">
        <div class="ob-kicker">Threat detected${more > 0 ? ` · ${more + 1} active` : ""}</div>
        <div class="ob-title">${tuEsc(top.type)} on ${tuEsc(top.camera)}</div>
        <div class="ob-meta">
          <span>${icon("pin")}<b>${tuEsc(top.location)}</b></span>
          <span>${icon("clock")}<b>${tuTime(top.detected_at)}</b></span>
          <span>Threat level ${tuLevelPill(top.level, top.score)}</span>
        </div>
      </div>
      <div class="ob-actions">${tuActions(top)}<button type="button" class="btn" data-details="${top.id}">Details</button></div>`;
  }

  // Summary cards
  ovEl("ov-score").textContent = s.score;
  const lv = ovEl("ov-level");
  lv.textContent = s.level;
  lv.className = `lv-pill ${tuLevelClass(s.level)}`;
  const bar = ovEl("ov-score-bar");
  bar.style.width = `${s.score}%`;
  bar.className = tuLevelClass(s.level);
  ovEl("card-score").className = `ov-card ${s.score ? tuLevelClass(s.level) : ""}`;
  ovEl("ov-active").textContent = s.active;
  ovEl("ov-active-sub").textContent = `${s.in_progress} in progress · ${s.resolved} resolved (${s.resolved_today} today)`;
  ovEl("card-active").className = `ov-card${s.active ? " lv-high" : ""}`;
  ovEl("ov-online").textContent = s.cameras_online;
  ovEl("ov-total").textContent = `/${s.cameras_total}`;
  ovEl("ov-online-sub").textContent = s.camera_issues ? "some cameras need attention" : "all cameras working";
  ovEl("ov-issues").textContent = s.camera_issues;
  const firstIssue = d.cameras.find((c) => c.status !== "online");
  ovEl("ov-issues-sub").textContent = firstIssue ? `${firstIssue.name}: ${firstIssue.issue}` : "no problems";
  ovEl("card-issues").className = `ov-card${s.camera_issues ? " warn" : ""}`;

  // Cameras
  ovEl("ov-camera-list").innerHTML = d.cameras.map((c) => {
    const latest = c.latest_threat
      ? `${tuEsc(c.latest_threat.type)} · ${tuAgo(c.latest_threat.t, now)} ${tuStatusChip(c.latest_threat.status)}`
      : `<span class="muted">No threats</span>`;
    const activity = c.last_activity ? `${tuEsc(c.last_activity.text)} · ${tuAgo(c.last_activity.t, now)}` : "No activity yet";
    return `<a class="cam-row" href="#cam=${encodeURIComponent(c.id)}">
      <span class="cam-dot st-${c.status}" title="${tuEsc(c.status_text)}"></span>
      <span class="cam-name"><b>${tuEsc(c.name)}</b><span class="muted">${tuEsc(c.area)}</span></span>
      <span class="cam-state st-${c.status}">${tuEsc(c.status_text)}${c.issue ? `<small>${tuEsc(c.issue)}</small>` : ""}</span>
      <span class="cam-level">${tuLevelPill(c.level, c.score)}</span>
      <span class="cam-latest"><small>Latest threat</small>${latest}</span>
      <span class="cam-activity"><small>Last activity</small>${activity}</span>
    </a>`;
  }).join("");

  // Recent alerts
  ovEl("ov-alerts-empty").hidden = d.alerts.length > 0;
  ovEl("ov-alert-list").innerHTML = d.alerts.map((a) => `
    <li class="alert-item ${tuLevelClass(a.level)} is-${a.status}" data-details="${a.id}">
      <div class="ai-top"><b>${icon(a.status === "resolved" ? "check" : "alert")}${tuEsc(a.type)} detected</b>${tuStatusChip(a.status)}</div>
      <div class="ai-meta">${tuEsc(a.camera)} · ${tuEsc(a.location)}</div>
      <div class="ai-meta">${tuTime(a.detected_at)} (${tuAgo(a.detected_at, now)}) · ${tuLevelPill(a.level, a.score)}</div>
      ${a.status !== "resolved" ? `<div class="ai-actions">${tuActions(a, true)}</div>` : ""}
    </li>`).join("");

  // Threat level by camera
  ovEl("ov-bars").innerHTML = d.cameras.slice().sort((a, b) => b.score - a.score || a.order - b.order).map((c) => `
    <div class="sb-row"><span class="sb-name" title="${tuEsc(c.name)}">${tuEsc(c.name)}</span>
      <span class="bar"><span class="${tuLevelClass(c.level)}" style="width:${Math.max(c.score, 1)}%"></span></span>
      <span class="sb-val">${c.score}</span></div>`).join("");

  // High-risk areas
  ovEl("ov-areas-count").textContent = s.high_risk_areas ? `${s.high_risk_areas} at risk` : "";
  ovEl("ov-areas").innerHTML = d.areas.length ? d.areas.map((a) => `
    <li><span class="area-name">${tuEsc(a.area)}</span>${tuLevelPill(a.level)}
      <span class="muted">${a.open ? `${a.open} open threat${a.open > 1 ? "s" : ""} · ` : ""}${a.recent} in the last hour</span></li>`).join("")
    : `<li class="empty">No high-risk areas: no threats in the last hour.</li>`;

  // Recent activity
  ovEl("ov-activity").innerHTML = d.activity.length ? d.activity.map((e) => `
    <li class="act-${e.level}"${e.incident ? ` data-details="${e.incident}"` : ""}>
      <span class="act-time">${tuTime(e.t)}</span><span class="act-dot"></span><span>${tuEsc(e.text)}</span></li>`).join("")
    : `<li class="empty">Nothing yet.</li>`;
}

// ---------- Setup ----------

function renderSoundButton() {
  const b = ovEl("sound-btn");
  const on = Alarm.enabled;
  b.innerHTML = on
    ? '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/></svg>'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 5 6 9H2v6h4l5 4z"/><path d="m22 9-6 6M16 9l6 6"/></svg>';
  b.classList.toggle("off", !on);
  b.classList.toggle("blocked", on && !Alarm.ready);
  b.title = !on ? "Alarm sound is off (click to turn on)"
    : Alarm.ready ? "Alarm sound is on (click to turn off)" : "Alarm sound is on; the browser allows it after your first click on the page";
  b.setAttribute("aria-label", b.title);
}

function openOverview() {
  ov.visible = true;
  ovEl("overview-view").hidden = false;
  if (ov.data) renderOverview(ov.data);
}

function closeOverview() {
  ov.visible = false;
  ovEl("overview-view").hidden = true;
}

function initThreats() {
  TU.onChange = () => pollThreats();
  document.addEventListener("click", (e) => {  // open details from alerts, banner and activity
    const el = e.target.closest("[data-details]");
    if (el && !e.target.closest("[data-act], a")) openThreatDetails(el.dataset.details);
  });
  ovEl("sound-btn").addEventListener("click", () => {
    Alarm.enabled = !Alarm.enabled;
    Alarm.unlock();
    if (Alarm.enabled) setTimeout(() => Alarm.play(), 50);  // let the operator hear it once
    renderSoundButton();
  });
  document.addEventListener("pointerdown", () => setTimeout(renderSoundButton, 100), { once: true });
  renderSoundButton();
  pollThreats();
  setInterval(pollThreats, 2000);
}
