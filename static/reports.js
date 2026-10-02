"use strict";

// Reports page: the full threat history with filters, details and CSV export.

const rp = { status: "all" };
const rpEl = (id) => document.getElementById(id);

function query() {
  return new URLSearchParams({ status: rp.status, q: rpEl("q").value.trim(), days: rpEl("days").value });
}

async function load() {
  try {
    const res = await fetch(`/api/threats?${query()}`);
    if (res.ok) render(await res.json());
  } catch { /* retry on next refresh */ }
  rpEl("export").href = `/api/threats/export.csv?${query()}`;
}

function render({ counts, threats }) {
  rpEl("st-total").textContent = counts.total;
  rpEl("st-active").textContent = counts.active;
  rpEl("st-progress").textContent = counts.in_progress;
  rpEl("st-resolved").textContent = counts.resolved;
  const times = threats.filter((t) => t.time_to_resolve).map((t) => t.time_to_resolve);
  rpEl("st-ttr").textContent = times.length ? tuDuration(times.reduce((a, b) => a + b, 0) / times.length) : "–";
  rpEl("empty").hidden = threats.length > 0;
  rpEl("rows").innerHTML = threats.map((t) => `
    <tr data-details="${t.id}" tabindex="0">
      <td><b>${tuDateTime(t.detected_at)}</b><div class="muted">${tuEsc(t.id)}</div></td>
      <td>${tuEsc(t.camera)}</td>
      <td>${tuEsc(t.location)}</td>
      <td>${tuEsc(t.type)}</td>
      <td class="num">${tuLevelPill(t.level, t.score)}</td>
      <td>${tuStatusChip(t.status)}</td>
      <td class="rp-action">${tuEsc(t.last_action || "—")}</td>
      <td>${t.resolved_at ? `${tuDateTime(t.resolved_at)}<div class="muted">after ${tuDuration(t.time_to_resolve)}</div>` : "—"}</td>
    </tr>`).join("");
}

TU.onChange = () => load();
rpEl("rows").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-details]");
  if (tr) openThreatDetails(tr.dataset.details);
});
rpEl("rows").addEventListener("keydown", (e) => {
  const tr = e.target.closest("tr[data-details]");
  if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openThreatDetails(tr.dataset.details); }
});
rpEl("q").addEventListener("input", load);
rpEl("days").addEventListener("change", load);
document.querySelectorAll(".seg-btn").forEach((b) => b.addEventListener("click", () => {
  rp.status = b.dataset.status;
  document.querySelectorAll(".seg-btn").forEach((o) => o.classList.toggle("active", o === b));
  load();
}));
load();
setInterval(load, 5000);
