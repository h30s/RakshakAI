// Rakshak AI landing page: navigation, reveal-on-scroll, the base-rate calculator,
// the prototype gallery and the feedback form.
const $ = (id) => document.getElementById(id);

/* ---------- Navigation ---------- */
(function nav() {
  const bar = $("nav");
  const toggle = bar.querySelector(".nav-toggle");
  const onScroll = () => bar.classList.toggle("scrolled", window.scrollY > 8);
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const setOpen = (open) => { bar.classList.toggle("open", open); toggle.setAttribute("aria-expanded", String(open)); };
  toggle.addEventListener("click", () => setOpen(!bar.classList.contains("open")));
  bar.querySelectorAll(".nav-links a").forEach((a) => a.addEventListener("click", () => setOpen(false)));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") setOpen(false); });
  document.addEventListener("click", (e) => { if (!bar.contains(e.target)) setOpen(false); });

  // Highlight the section being read.
  const links = new Map([...bar.querySelectorAll('.nav-links a[href^="#"]')].map((a) => [a.getAttribute("href").slice(1), a]));
  if (!("IntersectionObserver" in window)) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      links.forEach((a) => a.classList.remove("active"));
      links.get(en.target.id)?.classList.add("active");
    });
  }, { rootMargin: "-45% 0px -50% 0px" });
  links.forEach((_, id) => { const el = $(id); if (el) io.observe(el); });
})();

/* ---------- Stacked tables on phones: label each cell with its column heading ---------- */
document.querySelectorAll("table.stackable").forEach((t) => {
  const heads = [...t.querySelectorAll("thead th")].map((th) => th.textContent.trim());
  t.querySelectorAll("tbody tr").forEach((tr) => [...tr.children].forEach((td, i) => { if (heads[i]) td.dataset.label = heads[i]; }));
});

/* ---------- Reveal on scroll ----------
   Anything that has reached the viewport, or been scrolled past (e.g. after jumping to an anchor),
   is shown. Checked on scroll rather than per element, so fast jumps never leave content hidden. */
(function reveal() {
  let pending = [...document.querySelectorAll(".reveal")];
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
    pending.forEach((el) => el.classList.add("in"));
    return;
  }
  let queued = false;
  const sweep = () => {
    queued = false;
    const limit = window.innerHeight * 0.94;
    pending = pending.filter((el) => {
      if (el.getBoundingClientRect().top < limit) { el.classList.add("in"); return false; }
      return true;
    });
    if (!pending.length) { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); clearInterval(timer); }
  };
  // a short timer rather than requestAnimationFrame, which some embedded viewers never run
  const onScroll = () => { if (!queued) { queued = true; setTimeout(sweep, 60); } };
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  window.addEventListener("hashchange", sweep);
  // Backstop for viewers that deliver scroll events late (they are tied to animation frames).
  const timer = setInterval(sweep, 700);
  sweep();
})();

/* ---------- Base-rate calculator ---------- */
(function calculator() {
  const inp = { total: $("c-total"), bad: $("c-bad"), sens: $("c-sens"), spec: $("c-spec") };
  const out = { total: $("o-total"), bad: $("o-bad"), sens: $("o-sens"), spec: $("o-spec") };
  const note = $("c-note");
  const dots = $("dots");
  for (let i = 0; i < 100; i++) dots.appendChild(document.createElement("i"));
  const NOTES = {
    raw: "Every movement is a candidate, as with a virtual fence or tripwire.",
    context: "Illustrative: judged against this post's normal for the hour, only 50 movements are unusual enough to be candidates. " +
      "This assumes the 10 unlawful ones are among them.",
    custom: "Your own numbers.",
  };
  const PRESETS = {
    raw: { total: 10000, bad: 10, sens: 99, spec: 99 },
    context: { total: 50, bad: 10, sens: 99, spec: 99 },
  };
  const fmt = (n) => (n >= 100 ? Math.round(n).toLocaleString("en-IN") : n.toLocaleString("en-IN", { maximumFractionDigits: 1 }));

  function render(mode) {
    let total = +inp.total.value;
    const bad = Math.min(+inp.bad.value, total);
    const sens = +inp.sens.value / 100, spec = +inp.spec.value / 100;
    const tp = bad * sens, fp = (total - bad) * (1 - spec);
    const alerts = tp + fp;
    const falseShare = alerts ? fp / alerts : 0;
    out.total.textContent = total.toLocaleString("en-IN");
    out.bad.textContent = bad.toLocaleString("en-IN");
    out.sens.textContent = `${(+inp.sens.value).toFixed(1)}%`;
    out.spec.textContent = `${(+inp.spec.value).toFixed(1)}%`;
    const big = $("r-false");
    big.textContent = `${Math.round(falseShare * 100)}%`;
    big.classList.toggle("good", falseShare < 0.5);
    $("r-alerts").textContent = fmt(alerts);
    $("r-fp").textContent = fmt(fp);
    $("r-tp").textContent = fmt(tp);
    const genuine = Math.round((1 - falseShare) * 100);
    [...dots.children].forEach((d, i) => d.classList.toggle("t", i < genuine));
    if (mode) note.textContent = NOTES[mode];
  }

  const seg = document.querySelectorAll(".seg button");
  seg.forEach((b) => b.addEventListener("click", () => {
    const p = PRESETS[b.dataset.preset];
    Object.entries(p).forEach(([k, v]) => { inp[k].value = v; });
    seg.forEach((x) => x.classList.toggle("on", x === b));
    render(b.dataset.preset);
  }));
  Object.values(inp).forEach((el) => el.addEventListener("input", () => {
    seg.forEach((x) => x.classList.remove("on"));
    render("custom");
  }));
  render("raw");
})();

/* ---------- Prototype gallery ---------- */
(function gallery() {
  const SHOTS = [
    { id: "overview", tab: "Overview", icon: "grid", title: "Operations overview",
      text: "One screen answers “is anything wrong right now?”: an overall threat score, active and in-progress incidents, camera health, high-risk areas and the latest alerts. It refreshes every few seconds and plays a sound on new threats.",
      link: "/app#overview" },
    { id: "cameras", tab: "Camera grid", icon: "cctv", title: "Every feed, analysed together",
      text: "Thirteen feeds from two sites run through one shared detection pipeline. Boxes show people, vehicles and objects; tiles with a confirmed weapon are outlined in red and badged.",
      link: "/app#cameras" },
    { id: "detail", tab: "Camera detail", icon: "scan", title: "Live view with detections",
      text: "The full feed with every detected object, its confidence and its tracking ID. Video runs a few seconds behind live so each box sits on the exact frame that was analysed, not on a later one.",
      link: "/app#cameras" },
    { id: "journey", tab: "Journeys", icon: "route", title: "Following a person across cameras",
      text: "Each person gets an ID and a timeline of where they were seen. Across the five synchronised school-building cameras, a link is made only between cameras a person can walk between, and a timing check rules out being in two places at once.",
      link: "/app#people" },
    { id: "modes", tab: "Detection modes", icon: "moon", title: "Night, thermal, fog, rain",
      text: "The same pipeline, with no per-condition tuning, on footage recorded in low light, from thermal cameras, in fog and in rain and snow. This is the start of a condition-by-condition performance matrix.",
      link: "/modes" },
    { id: "threat", tab: "Incident", icon: "alert", title: "An incident, not a flood of alarms",
      text: "Repeated sightings of the same threat on a camera fold into one incident, with its snapshot, confidence, level and every operator action on a timeline: “Working on it”, notes, “Resolved”.",
      link: "/app#overview" },
    { id: "reports", tab: "Reports", icon: "chart", title: "Complete incident history",
      text: "Every incident with its outcome and time to resolve, searchable and filterable, and exportable to CSV. Records persist across restarts.",
      link: "/reports" },
    { id: "sources", tab: "Camera sources", icon: "qr", title: "Any camera, the same pipeline",
      text: "Add a laptop or USB webcam, or scan a QR code to stream a phone camera over the local network (encrypted). A phone can also connect by USB cable. Every source gets the same detection and alerts.",
      link: "/app#sources" },
  ];
  const tabs = document.querySelector(".g-tabs");
  const shot = $("g-shot");
  const text = $("g-text");
  const imgs = {};
  SHOTS.forEach((s, i) => {
    const b = document.createElement("button");
    b.type = "button"; b.role = "tab"; b.id = `tab-${s.id}`;
    b.setAttribute("aria-controls", "g-text");
    b.innerHTML = `<svg class="ic"><use href="#i-${s.icon}"/></svg>${s.tab}`;
    b.addEventListener("click", () => show(i));
    tabs.appendChild(b);
    const img = new Image();
    img.alt = `${s.title}: screenshot of the Rakshak AI prototype`;
    img.loading = i ? "lazy" : "eager"; img.decoding = "async";
    img.width = 1440; img.height = 900;
    img.src = `/static/site/shot-${s.id}.jpg`;
    shot.appendChild(img);
    imgs[s.id] = img;
  });
  function show(i) {
    const s = SHOTS[i];
    [...tabs.children].forEach((b, j) => b.setAttribute("aria-selected", String(i === j)));
    Object.values(imgs).forEach((im) => im.classList.remove("on"));
    imgs[s.id].loading = "eager";
    imgs[s.id].classList.add("on");
    text.setAttribute("aria-labelledby", `tab-${s.id}`);
    text.innerHTML = `<span class="tag run">Working in prototype</span><h3>${s.title}</h3><p>${s.text}</p>
      <a class="btn sm" href="${s.link}">Open this screen<svg class="ic arrow"><use href="#i-arrow"/></svg></a>`;
  }
  tabs.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const cur = [...tabs.children].findIndex((b) => b.getAttribute("aria-selected") === "true");
    const next = (cur + (e.key === "ArrowRight" ? 1 : SHOTS.length - 1)) % SHOTS.length;
    show(next); tabs.children[next].focus();
  });
  show(0);
})();

/* ---------- Feedback ---------- */
(function feedback() {
  const form = $("fb-form");
  const msg = $("fb-msg");
  const btn = $("fb-submit");
  try { if (sessionStorage.getItem("rk-visited-app")) $("fb-demo").checked = true; } catch { /* storage unavailable */ }
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const role = form.role.value;
    const rating = form.querySelector('input[name="rating"]:checked')?.value;
    if (!role || !rating) {
      msg.className = "fb-msg bad";
      msg.textContent = !role ? "Please choose your role." : "Please choose a rating from 1 to 5.";
      (!role ? form.role : form.querySelector('input[name="rating"]')).focus();
      return;
    }
    const body = {
      role, rating: +rating,
      useful: form.useful.value.trim(), improve: form.improve.value.trim(),
      organisation: form.organisation.value.trim(), name: form.name.value.trim(), email: form.email.value.trim(),
      follow_up: form.follow_up.checked, tried_demo: form.tried_demo.checked,
    };
    btn.disabled = true;
    msg.className = "fb-msg"; msg.textContent = "Sending…";
    try {
      const r = await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error(r.status === 429 ? "Please wait a few seconds and try again." : "The server did not accept the feedback.");
      form.innerHTML = `<div class="fb-done"><div class="card-ic green"><svg class="ic"><use href="#i-check"/></svg></div>
        <h3>Thank you. Your feedback was received.</h3><p>Every response is read by the team.</p></div>`;
    } catch (err) {
      btn.disabled = false;
      msg.className = "fb-msg bad";
      msg.textContent = err.message.includes("fetch") ? "Couldn't reach the server. Please try again." : err.message;
    }
  });
})();
