"use strict";

// Border Pulse page: draws each camera's paths on its 4 x 3 grid (the same grid the decision
// layer uses) from /api/decision/pulse, and lists what changed this week.

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const COLS = 4, ROWS = 3, W = 320, H = 180;
let data = null;

function centre(cell) {
  const m = /^r(\d)c(\d)$/.exec(cell);
  if (!m) return null;
  return [(Number(m[2]) + 0.5) * W / COLS, (Number(m[1]) + 0.5) * H / ROWS];
}

function arrow(path, colour, width, id) {
  const [a, b] = path.split(">");
  const p = centre(a), q = centre(b);
  if (!p || !q) return "";
  if (a === b) return `<circle cx="${p[0]}" cy="${p[1]}" r="${6 + width}" fill="none" stroke="${colour}" stroke-width="${width}" opacity=".85"/>`;
  return `<line x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" stroke="${colour}" stroke-width="${width}" stroke-linecap="round" marker-end="url(#${id})" opacity=".85"/>`;
}

function map(cam, i) {
  const grid = [];
  for (let c = 1; c < COLS; c++) grid.push(`<line class="cell" x1="${c * W / COLS}" y1="0" x2="${c * W / COLS}" y2="${H}"/>`);
  for (let r = 1; r < ROWS; r++) grid.push(`<line class="cell" x1="0" y1="${r * H / ROWS}" x2="${W}" y2="${r * H / ROWS}"/>`);
  const max = Math.max(1, ...cam.usual_paths.map((p) => p.usual));
  const usual = cam.usual_paths.map((p) => arrow(p.path, "var(--muted)", 1 + 5 * p.usual / max, `ah-u${i}`));
  const rising = cam.rising_paths.map((p) => arrow(p.path, "var(--warn)", 4, `ah-r${i}`));
  const fresh = cam.new_paths.map((p) => arrow(p.path, "#ff5c63", 4, `ah-n${i}`));
  const marker = (id, colour) => `<marker id="${id}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0 10 5 0 10z" fill="${colour}"/></marker>`;
  return `<svg class="pl-map" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("Paths on camera {c}", { c: cam.camera }))}">
    <defs>${marker(`ah-u${i}`, "var(--muted)")}${marker(`ah-r${i}`, "var(--warn)")}${marker(`ah-n${i}`, "#ff5c63")}</defs>
    ${grid.join("")}${usual.join("")}${rising.join("")}${fresh.join("")}</svg>`;
}

function card(cam, i) {
  const flags = [
    ...cam.new_paths.map((p) => `<li class="new">${esc(t("New path {p}: {n} times this week, never in the weeks before", { p: p.path, n: p.count }))}</li>`),
    ...cam.rising_paths.map((p) => `<li>${esc(t("Path {p}: {n} times, usually {u} a week", { p: p.path, n: p.count, u: p.usual }))}</li>`),
    ...(cam.peak_shifted ? [`<li>${esc(t("Peak hour moved: {a}:00 → {b}:00", { a: cam.usual_peak_hour, b: cam.peak_hour }))}</li>`] : []),
    ...cam.repeat_crossers.map((r) => `<li>${esc(t("Repeat crosser {p}: {n} fence crossings on {d}", { p: r.person, n: r.crossings, d: r.day }))}</li>`),
  ];
  return `<section class="pl-card">
    <h2>${esc(cam.camera)}</h2>
    ${map(cam, i)}
    <div class="pl-facts">
      <div><b>${cam.movements}</b>${esc(t("movements this week (usual {u})", { u: cam.usual_movements }))}</div>
      <div><b>${cam.night}</b>${esc(t("at night, 22:00-05:00 (usual {u})", { u: cam.usual_night }))}</div>
    </div>
    ${flags.length ? `<ul class="pl-flags">${flags.join("")}</ul>` : `<p class="dc-note">${esc(t("No change from the usual weeks."))}</p>`}
  </section>`;
}

function render() {
  if (!data) return;
  $("pl-week").textContent = t("Week ending {w}, compared with {n} week(s) before.", { w: data.week_ending.replace("T", " "), n: data.compared_with_weeks });
  $("pl-cards").innerHTML = data.cameras.map(card).join("");
  $("pl-empty").hidden = data.cameras.length > 0;
}

document.addEventListener("langchange", render);

(async () => {
  applyI18n();
  try {
    const res = await fetch("/api/decision/pulse");
    data = await res.json();
  } catch { data = { week_ending: "", compared_with_weeks: 0, cameras: [] }; }
  render();
})();
