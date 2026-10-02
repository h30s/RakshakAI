"use strict";

// Ranked Alerts page: polls /api/decision/overview and renders the alert budget, surge mode,
// Watch Orders, drift watch, the Sector HQ link and each alert with the score terms that made it
// fire. Text goes through t() (static/i18n.js) for the Hindi / English toggle.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hhmm = (t) => new Date(t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
const DAY = { normal: "Normal", haat: "Haat day", festival: "Festival", seal: "Border sealed" };
const STATUS = { new: "New", acknowledged: "Acknowledged", escalated: "Escalated", dismissed: "Dismissed" };
const MODE = { ranked: "Ranked", learning: "Learning", borrowed: "Borrowed" };
let last = null, renderedAlerts = "";

async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.headers.get("content-type")?.includes("json") ? res.json() : res.text();
}

function alertCard(a) {
  const max = Math.max(1, ...a.terms.map((x) => x.value));
  const terms = a.terms.map((x) => `<li><span>${esc(t(x.term))}</span><span class="dc-bar"><i style="width:${(100 * x.value / max).toFixed(0)}%"></i></span><b>+${x.value.toFixed(1)}</b></li>`).join("");
  const sealed = a.clip_sha256
    ? t("Clip sealed · SHA-256 {h} · ledger #{n}", { h: `${a.clip_sha256.slice(0, 8)}…${a.clip_sha256.slice(-4)}`, n: a.ledger_seq })
    : t("Sealed in ledger #{n}", { n: a.ledger_seq });
  const id = encodeURIComponent(a.id);
  return `<article class="dc-alert ${a.status === "new" ? "new" : ""}">
    <div class="dc-top">
      <div><span class="dc-id">${esc(a.id)}</span><span class="dc-meta">${hhmm(a.t)} · ${esc(a.camera_name)} · ${esc(t(DAY[a.day_type] || a.day_type))}${a.person ? ` · ${esc(a.person)}` : ""}</span>
        <div class="dc-title">${esc(t(a.reason))}</div>
        <div class="dc-meta">${esc(t("Status: {s}", { s: t(STATUS[a.status] || a.status) }))}</div></div>
      <div class="dc-score">${a.score.toFixed(1)}<small>${esc(t("anomaly score"))}</small></div>
    </div>
    ${terms ? `<ul class="dc-terms">${terms}</ul>` : ""}
    <div class="dc-actions">
      <button class="btn" data-act="acknowledged" data-id="${esc(a.id)}">${esc(t("Acknowledge"))}</button>
      <button class="btn bad" data-act="escalated" data-id="${esc(a.id)}">${esc(t("Escalate"))}</button>
      <button class="btn" data-act="dismissed" data-id="${esc(a.id)}">${esc(t("Dismiss"))}</button>
    </div>
    <div class="dc-seal">✓ ${esc(sealed)}</div>
    <div class="dc-sms" title="The same alert as one signed SMS (${a.sms.length} characters)">SMS · ${esc(a.sms)}</div>
    <p><a href="/api/decision/alerts/${id}/certificate" target="_blank" rel="noopener">${esc(t("§63(4) Part A draft"))}</a>
      · <a href="/api/decision/alerts/${id}/packet">${esc(t("Evidence packet"))}</a></p>
  </article>`;
}

function render(o) {
  last = o;
  $("st-mode").textContent = t(MODE[o.mode] || o.mode);
  $("st-mode-sub").textContent = o.mode === "ranked" ? t("Baseline from {n} days", { n: o.days_learned })
    : o.mode === "borrowed" ? t("Similar post's baseline · {d}/{m} own days", { d: o.days_learned, m: o.min_days })
      : t("{d}/{m} days learned · fence rules within the budget", { d: o.days_learned, m: o.min_days });
  $("st-used").textContent = `${o.used_this_shift} / ${o.per_shift}`;
  $("st-digest").textContent = o.digest_count;
  $("st-day").textContent = t(DAY[o.day_type] || o.day_type);
  $("st-ledger").textContent = o.ledger.entries;
  $("st-ledger-sub").textContent = t("Head {h}…", { h: o.ledger.head.slice(0, 10) });
  $("surge").hidden = !o.surge.active;
  $("surge-reason").textContent = o.surge.reason || "";
  $("drift").hidden = !o.drift?.rebaseline;
  if (o.drift?.rebaseline) $("drift-text").textContent = t("Operator decisions this week: {p}% actionable, below 50%. The baseline may be out of date.", { p: Math.round(100 * o.drift.precision) });
  $("hq").hidden = !o.hq;
  if (o.hq) $("hq").textContent = t(o.hq.link === "down" ? "Sector HQ link down · {n} entries held, sent when the link returns" : "Sector HQ link up · {n} entries waiting", { n: Math.max(0, o.hq.pending) });
  const mode = o.surge.manual === true ? "on" : o.surge.manual === false ? "off" : "auto";
  document.querySelectorAll("[data-surge]").forEach((b) => b.classList.toggle("active", b.dataset.surge === mode));
  // Rebuild the cards only when they change, so a tap never lands on a button being replaced.
  const key = LANG + JSON.stringify(o.alerts);
  if (key !== renderedAlerts) {
    renderedAlerts = key;
    $("alerts").innerHTML = o.alerts.map(alertCard).join("");
  }
  $("empty").hidden = o.alerts.length > 0;
  $("orders").innerHTML = o.watch_orders.map((w) => `<li>${esc(w.camera)} ${esc(t("until {t}", { t: hhmm(w.until) }))}${w.reason ? ` · ${esc(w.reason)}` : ""}</li>`).join("");
}

async function poll() {
  try { render(await api("/api/decision/overview")); } catch { /* retry on next tick */ }
}

document.addEventListener("click", async (e) => {
  const act = e.target.closest("[data-act]");
  if (act) { await api(`/api/decision/alerts/${encodeURIComponent(act.dataset.id)}/status`, { status: act.dataset.act }); poll(); }
  const surge = e.target.closest("[data-surge]");
  if (surge) { await api("/api/decision/surge", { mode: surge.dataset.surge }); poll(); }
});

document.addEventListener("langchange", () => { if (last) render(last); });

$("rebaseline").addEventListener("click", async () => { render(await api("/api/decision/rebaseline", {})); });

$("watch").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/decision/watch-orders", { camera: $("w-camera").value, minutes: Number($("w-minutes").value), reason: $("w-reason").value });
  $("w-reason").value = "";
  poll();
});

$("verify").addEventListener("click", async () => {
  const v = await api("/api/decision/ledger/verify");
  const out = $("verify-out");
  out.hidden = false;
  out.innerHTML = v.intact
    ? `<b class="dc-ok">${esc(t("Ledger intact"))}</b><span class="dc-note">${esc(t("{n} entries, every hash, signature and evidence clip checks out.", { n: v.entries }))}</span>`
    : `<b class="dc-bad">${esc(t("Ledger problems found"))}</b><ul class="dc-orders">${v.problems.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>`;
});

(async () => {
  applyI18n();
  try {
    const cams = await api("/api/cameras");
    $("w-camera").innerHTML = cams.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}</option>`).join("");
  } catch { /* cameras list unavailable */ }
  poll();
  setInterval(poll, 3000);
})();
