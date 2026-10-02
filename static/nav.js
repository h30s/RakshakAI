"use strict";

// Shared app shell for every page: the navigation bar (with a menu on tablets and phones),
// the icon set, the live clock and the header status. Load it first: other scripts use the
// elements it creates (tab links, counts, status, bell, sound button).

const ICONS = {
  logo: '<path d="M12 2.5 4 5.8v5.7c0 5 3.4 8.9 8 10 4.6-1.1 8-5 8-10V5.8z"/><path d="M7.5 12s1.7-3 4.5-3 4.5 3 4.5 3-1.7 3-4.5 3-4.5-3-4.5-3z"/><circle cx="12" cy="12" r="1.2"/>',
  overview: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  cameras: '<path d="m16 13 5.2 3.1a.5.5 0 0 0 .8-.4V8.3a.5.5 0 0 0-.8-.4L16 11"/><rect x="2" y="6" width="14" height="12" rx="2"/>',
  people: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  sources: '<circle cx="12" cy="10" r="8"/><circle cx="12" cy="10" r="3"/><path d="M7 22h10M12 18v4"/>',
  modes: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
  reports: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 18v-3M12 18v-6M16 18v-2"/>',
  bell: '<path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  close: '<path d="M18 6 6 18M6 6l12 12"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="M12 8v4M12 16h.01"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  cameraOff: '<path d="m2 2 20 20"/><path d="M7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h12"/><path d="M9.5 4h5L17 7h3a2 2 0 0 1 2 2v7.5"/><path d="M14.12 15.12a3 3 0 1 1-4.24-4.24"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/>',
  chart: '<path d="M3 3v18h18"/><path d="M18 17V9M13 17V5M8 17v-3"/>',
  back: '<path d="m12 19-7-7 7-7M19 12H5"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5M12 15V3"/>',
  building: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>',
  live: '<circle cx="12" cy="12" r="2"/><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"/>',
  check: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  route: '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
  qr: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3"/>',
  usb: '<circle cx="10" cy="7" r="1"/><circle cx="4" cy="20" r="1"/><path d="M4.7 19.3 19 5M21 3l-3 1 2 2z"/><path d="M9.26 7.68 5 12l2 5M10 14l5 2 3.5-3.5"/><path d="m18 12 1-1 1 1-1 1z"/>',
  laptop: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M2 20h20"/>',
  phone: '<rect x="6" y="2" width="12" height="20" rx="2.5"/><path d="M11 18h2"/>',
  eye: '<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 10.75 10.75 0 0 1-19.88 0"/><circle cx="12" cy="12" r="3"/>',
  user: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
  message: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.8A8 8 0 1 1 21 12z"/><path d="M8.5 12h.01M12 12h.01M15.5 12h.01"/>',
};

function icon(name, cls = "") {
  return `<svg class="ic${cls ? ` ${cls}` : ""}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

const NAV_ITEMS = [
  { id: "tab-overview", href: "/app#overview", icon: "overview", label: "Overview" },
  { id: "tab-cameras", href: "/app#cameras", icon: "cameras", label: "Cameras" },
  { id: "tab-people", href: "/app#people", icon: "people", label: "People", count: "people-count" },
  { id: "tab-sources", href: "/app#sources", icon: "sources", label: "Sources", count: "sources-count" },
  { id: "tab-modes", href: "/modes", icon: "modes", label: "Detection Modes", page: "modes" },
  { id: "tab-reports", href: "/reports", icon: "reports", label: "Reports", page: "reports" },
  { id: "tab-decision", href: "/decision", icon: "shield", label: "Ranked Alerts", page: "decision" },
];

(function renderNav() {
  try { sessionStorage.setItem("rk-visited-app", "1"); } catch { /* storage unavailable */ }  // lets the feedback form pre-tick "I tried the prototype"
  const header = document.getElementById("app-nav");
  if (!header) return;
  const page = header.dataset.page || "dashboard";
  header.className = "nav";
  header.innerHTML = `
    <div class="nav-inner">
      <a class="nav-brand" href="/" aria-label="Rakshak AI home page">
        <span class="nav-logo">${icon("logo")}</span>
        <span class="nav-title">Rakshak AI<small>Operations console</small></span>
      </a>
      <nav class="nav-links" id="nav-links" aria-label="Main">
        ${NAV_ITEMS.map((n) => `<a id="${n.id}" class="nav-link${n.page === page ? " active" : ""}" href="${n.href}"
            ${n.page === page ? 'aria-current="page"' : ""}>${icon(n.icon)}<span>${n.label}</span>${n.count ? `<span id="${n.count}" class="nav-count"></span>` : ""}</a>`).join("")}
      </nav>
      <div class="nav-right">
        <span id="sys-status" class="sys-status" title="System status"><span class="sys-dot"></span><span class="sys-text">Checking…</span></span>
        <span id="conn" class="conn" title="Video stream"></span>
        <span id="clock" class="clock"></span>
        ${page === "dashboard" ? '<button id="sound-btn" class="icon-btn" type="button" title="Alarm sound"></button>' : ""}
        <a class="btn nav-feedback" href="/#feedback" title="Tell us what you think of the prototype">${icon("message")}<span>Feedback</span></a>
        <a id="bell" class="icon-btn bell" href="/app#overview" title="Open threats">${icon("bell")}<span id="bell-count" class="bell-count" hidden></span></a>
        <span class="avatar" title="Operator (this dashboard has no user accounts)">${icon("user")}</span>
        <button class="icon-btn nav-toggle" type="button" aria-label="Menu" aria-expanded="false" aria-controls="nav-links">${icon("menu", "i-open")}${icon("close", "i-close")}</button>
      </div>
    </div>`;

  const toggle = header.querySelector(".nav-toggle");
  const setOpen = (open) => {
    header.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
  };
  toggle.addEventListener("click", () => setOpen(!header.classList.contains("nav-open")));
  header.querySelectorAll(".nav-link").forEach((a) => a.addEventListener("click", () => setOpen(false)));
  window.addEventListener("hashchange", () => setOpen(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
  document.addEventListener("click", (e) => { if (!header.contains(e.target)) setOpen(false); });

  // Fill static icon placeholders: <i data-icon="camera"></i>
  document.querySelectorAll("i[data-icon]").forEach((el) => { el.outerHTML = icon(el.dataset.icon, el.className); });

  const clock = document.getElementById("clock");
  const tick = () => { clock.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }); };
  tick();
  setInterval(tick, 1000);
})();

// Header status (the dashboard's threats.js does this itself, with the full overview).
function setHeaderStatus(summary) {
  const el = document.getElementById("sys-status");
  if (!el) return;
  let text = "All clear", cls = "ok";
  if (summary.active) { text = `${summary.active} active threat${summary.active > 1 ? "s" : ""}`; cls = "bad"; }
  else if (summary.in_progress) { text = `${summary.in_progress} being handled`; cls = "warn"; }
  else if (summary.camera_issues) { text = `${summary.camera_issues} camera issue${summary.camera_issues > 1 ? "s" : ""}`; cls = "warn"; }
  el.className = `sys-status ${cls}`;
  el.querySelector(".sys-text").textContent = text;
  const open = summary.active + summary.in_progress;
  const count = document.getElementById("bell-count");
  count.hidden = !open;
  count.textContent = open;
  count.classList.toggle("bad", summary.active > 0);
  document.getElementById("bell").title = open ? `${open} open threat${open > 1 ? "s" : ""}` : "No open threats";
}

window.addEventListener("load", () => {
  if (typeof pollThreats === "function") return;  // the dashboard updates the header itself
  const poll = async () => {
    try {
      const res = await fetch("/api/threats/overview");
      if (res.ok) setHeaderStatus((await res.json()).summary);
    } catch { /* retry */ }
  };
  poll();
  setInterval(poll, 5000);
});
