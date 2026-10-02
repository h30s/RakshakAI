"use strict";

// Hindi / English for operator screens. Keys are the English text itself, so a missing
// translation simply shows English. Mark static text with data-i18n (and data-i18n-placeholder);
// translate dynamic text with t("English text", { var: value }).
// Translations need review by a native Hindi speaker before any field use.

const I18N_HI = {
  // navigation (static/nav.js)
  "Overview": "अवलोकन",
  "Cameras": "कैमरे",
  "People": "लोग",
  "Sources": "स्रोत",
  "Detection Modes": "डिटेक्शन मोड",
  "Reports": "रिपोर्ट",
  "Border Pulse": "बॉर्डर पल्स",
  "Operations console": "संचालन कंसोल",
  "Feedback": "प्रतिक्रिया",
  "Alert budget": "अलर्ट बजट",
  "Ranked Alerts": "प्राथमिकता वाले अलर्ट",
  "Only the movements that are most unusual for this post, this hour and this kind of day reach the operator, at most a fixed number per shift. Everything else is kept in the shift digest.":
    "इस चौकी, इस समय और इस तरह के दिन के लिए सबसे असामान्य गतिविधियाँ ही ऑपरेटर तक पहुँचती हैं, हर पाली में एक तय संख्या तक। बाकी सब पाली के सारांश में रखा जाता है।",
  "Verify ledger": "लेजर जाँचें",
  "Mode": "मोड",
  "Ranked": "प्राथमिकता",
  "Learning": "सीख रहा है",
  "Borrowed": "उधार बेसलाइन",
  "Baseline from {n} days": "{n} दिनों की बेसलाइन",
  "{d}/{m} days learned · fence rules within the budget": "{d}/{m} दिन सीखे · बजट के भीतर बाड़ नियम",
  "Similar post's baseline · {d}/{m} own days": "मिलती-जुलती चौकी की बेसलाइन · अपने {d}/{m} दिन",
  "Alerts this shift": "इस पाली के अलर्ट",
  "In the digest": "सारांश में",
  "Day type": "दिन का प्रकार",
  "Normal": "सामान्य",
  "Haat day": "हाट का दिन",
  "Festival": "त्योहार",
  "Border sealed": "सीमा सील",
  "Sealed ledger entries": "सील की गई लेजर प्रविष्टियाँ",
  "Head {h}…": "हेड {h}…",
  "Surge mode": "सर्ज मोड",
  "Alerts, most recent first": "अलर्ट, सबसे नए पहले",
  "No alerts yet. In learning mode the system alerts only on virtual-fence crossings.":
    "अभी कोई अलर्ट नहीं। सीखने के दौरान सिस्टम केवल वर्चुअल बाड़ पार करने पर अलर्ट देता है।",
  "Automatic": "स्वचालित",
  "Force on": "चालू करें",
  "Force off": "बंद करें",
  "Automatic: the budget lifts when far more unusual movements than usual arrive within an hour.":
    "स्वचालित: जब एक घंटे में सामान्य से बहुत अधिक असामान्य गतिविधियाँ हों, तो बजट की सीमा हट जाती है।",
  "Watch Order": "वॉच ऑर्डर",
  "Camera": "कैमरा",
  "For (minutes)": "अवधि (मिनट)",
  "Reason": "कारण",
  "e.g. tip-off: crossing near the nala": "जैसे: सूचना — नाले के पास से पार",
  "Raise sensitivity": "संवेदनशीलता बढ़ाएँ",
  "until {t}": "{t} तक",
  "Acknowledge": "स्वीकार करें",
  "Escalate": "आगे भेजें",
  "Dismiss": "खारिज करें",
  "Status: {s}": "स्थिति: {s}",
  "New": "नया",
  "Acknowledged": "स्वीकार किया",
  "Escalated": "आगे भेजा",
  "Dismissed": "खारिज",
  "anomaly score": "असामान्यता स्कोर",
  "Clip sealed · SHA-256 {h} · ledger #{n}": "क्लिप सील · SHA-256 {h} · लेजर #{n}",
  "Sealed in ledger #{n}": "लेजर #{n} में सील",
  "§63(4) Part A draft": "§63(4) भाग A मसौदा",
  "Evidence packet": "साक्ष्य पैकेट",
  "off usual path": "सामान्य रास्ते से हटकर",
  "unusual hour": "असामान्य समय",
  "unusual speed": "असामान्य गति",
  "unusual dwell": "असामान्य ठहराव",
  "low posture / crawl": "झुककर / रेंगकर",
  "group": "समूह",
  "Unusual for this post, hour and day": "इस चौकी, समय और दिन के लिए असामान्य",
  "Fence crossing (learning mode)": "बाड़ पार (सीखने का मोड)",
  "Watchlist person": "निगरानी सूची का व्यक्ति",
  "Fence crossing while the border is sealed": "सीमा सील होने के दौरान बाड़ पार",
  "Virtual-fence breach into a restricted zone at night": "रात में वर्जित क्षेत्र में वर्चुअल बाड़ पार",
  "Operator decisions this week: {p}% actionable, below 50%. The baseline may be out of date.":
    "इस सप्ताह ऑपरेटर के निर्णय: {p}% काम के, 50% से कम। बेसलाइन पुरानी हो सकती है।",
  "Re-baseline now": "बेसलाइन अभी दोबारा बनाएँ",
  "Sector HQ link up · {n} entries waiting": "सेक्टर मुख्यालय लिंक चालू · {n} प्रविष्टियाँ बाकी",
  "Sector HQ link down · {n} entries held, sent when the link returns":
    "सेक्टर मुख्यालय लिंक बंद · {n} प्रविष्टियाँ रुकी हैं, लिंक लौटने पर भेजी जाएँगी",
  "Ledger intact": "लेजर सुरक्षित",
  "{n} entries, every hash, signature and evidence clip checks out.": "{n} प्रविष्टियाँ; हर हैश, हस्ताक्षर और साक्ष्य क्लिप सही है।",
  "Ledger problems found": "लेजर में गड़बड़ी मिली",
  "Shift report": "पाली रिपोर्ट",
  "Shift digest: not alerted, highest score first": "पाली सारांश: जिन पर अलर्ट नहीं गया, सबसे ऊँचा स्कोर पहले",
  "Nothing in this shift's digest yet.": "इस पाली के सारांश में अभी कुछ नहीं।",
  "Usual for this post and hour": "इस चौकी और समय के लिए सामान्य",
  "Shift budget used; ranked in the digest": "पाली का बजट खत्म; सारांश में रखा गया",
  "Learning this post's normal": "इस चौकी का सामान्य सीख रहा है",
  "Shift budget used; fence crossing in the digest": "पाली का बजट खत्म; बाड़ पार सारांश में",
  "Alert latency": "अलर्ट में लगा समय",
  "From the camera frame that triggered the alert. p95 = 95% of alerts were faster.":
    "अलर्ट शुरू करने वाले कैमरा फ्रेम से। p95 = 95% अलर्ट इससे तेज़ थे।",
  "Sealed": "सील हुआ",
  "On console": "कंसोल पर",
  "SMS sent": "SMS भेजा",
  "alerts": "अलर्ट",
  "Check an alert SMS (duty phone)": "अलर्ट SMS जाँचें (ड्यूटी फ़ोन)",
  "loiter in restricted zone": "वर्जित क्षेत्र में देर तक रुकना",
  // SMS check (duty phone)
  "Check an alert SMS": "अलर्ट SMS जाँचें",
  "Paste the alert SMS. This phone checks its signature against the post's key: no internet needed. A forged or changed SMS fails.":
    "अलर्ट SMS यहाँ चिपकाएँ। यह फ़ोन चौकी की कुंजी से उसके हस्ताक्षर की जाँच करता है: इंटरनेट की ज़रूरत नहीं। नकली या बदला हुआ SMS जाँच में फ़ेल होगा।",
  "Check signature": "हस्ताक्षर जाँचें",
  "Post public key (set once, from the post's console or HQ)": "चौकी की सार्वजनिक कुंजी (एक बार, चौकी कंसोल या मुख्यालय से)",
  "Set the post public key first (64 characters).": "पहले चौकी की सार्वजनिक कुंजी डालें (64 अक्षर)।",
  "Genuine: signed by this post and not changed.": "असली: इसी चौकी का हस्ताक्षर, कोई बदलाव नहीं।",
  "Genuine, but from {m} minutes ago. If you were not expecting an old alert, it may be a replay: call the post.":
    "असली, लेकिन {m} मिनट पुराना। अगर आप पुराने अलर्ट की उम्मीद नहीं कर रहे थे, तो यह दोबारा भेजा गया हो सकता है: चौकी को फ़ोन करें।",
  "NOT genuine: forged, changed, or from another post. Do not act on it; call the post.":
    "असली नहीं: नकली, बदला हुआ या किसी और चौकी का। इस पर कार्रवाई न करें; चौकी को फ़ोन करें।",
  "Post": "चौकी",
  "Alert": "अलर्ट",
  "Key fingerprint {f}… compare it with the one on the post console.": "कुंजी की पहचान {f}… चौकी कंसोल वाली से मिलाएँ।",
  // Shift report
  "Print": "प्रिंट",
  "Summary": "सारांश",
  "Alerts": "अलर्ट",
  "Time": "समय",
  "Score": "स्कोर",
  "Status": "स्थिति",
  "Ledger": "लेजर",
  "Officer actions": "अधिकारी की कार्रवाई",
  "Evidence": "साक्ष्य",
  "Duty operator handing over (name, signature, time)": "ड्यूटी सौंपने वाला ऑपरेटर (नाम, हस्ताक्षर, समय)",
  "Duty operator taking over (name, signature, time)": "ड्यूटी लेने वाला ऑपरेटर (नाम, हस्ताक्षर, समय)",
  "Post commander (name, signature)": "चौकी कमांडर (नाम, हस्ताक्षर)",
  "Shift {n}": "पाली {n}",
  "{a} alerts (budget {b} routine per shift), {d} movements kept in the digest. Mode: {m}.":
    "{a} अलर्ट (हर पाली {b} सामान्य अलर्ट का बजट), {d} गतिविधियाँ सारांश में। मोड: {m}।",
  "Console latency p95 {p} s over {n} alerts.": "कंसोल पर p95 समय {p} सेकंड, {n} अलर्ट पर।",
  "No alerts in this shift.": "इस पाली में कोई अलर्ट नहीं।",
  "None.": "कोई नहीं।",
  "{n} entries": "{n} प्रविष्टियाँ",
  "head": "हेड",
  // Border Pulse
  "New intelligence": "नई जानकारी",
  "What changed at this post in the last 7 days, compared with the 4 weeks before: new paths, paths used far more than usual, a shifted peak hour, night activity and repeat crossers.":
    "पिछले 4 हफ़्तों की तुलना में पिछले 7 दिनों में इस चौकी पर क्या बदला: नए रास्ते, सामान्य से बहुत ज़्यादा इस्तेमाल हुए रास्ते, बदला हुआ व्यस्त समय, रात की गतिविधि और बार-बार पार करने वाले।",
  "usual path (thicker = more used)": "सामान्य रास्ता (मोटी रेखा = ज़्यादा इस्तेमाल)",
  "new this week": "इस हफ़्ते नया",
  "far more than usual": "सामान्य से बहुत ज़्यादा",
  "No movements logged yet. Border Pulse needs at least a week of history.": "अभी कोई गतिविधि दर्ज नहीं। बॉर्डर पल्स के लिए कम से कम एक हफ़्ते का रिकॉर्ड चाहिए।",
  "Repeat crossers are pseudonymous tracker IDs that reset when the system restarts: leads for review, never an identification.":
    "बार-बार पार करने वाले छद्म ट्रैकर आईडी हैं जो सिस्टम दोबारा चालू होने पर बदल जाते हैं: ये जाँच के सुराग हैं, पहचान नहीं।",
  "Paths on camera {c}": "कैमरा {c} पर रास्ते",
  "New path {p}: {n} times this week, never in the weeks before": "नया रास्ता {p}: इस हफ़्ते {n} बार, पिछले हफ़्तों में कभी नहीं",
  "Path {p}: {n} times, usually {u} a week": "रास्ता {p}: {n} बार, आमतौर पर हफ़्ते में {u}",
  "Peak hour moved: {a}:00 → {b}:00": "व्यस्त समय बदला: {a}:00 → {b}:00",
  "Repeat crosser {p}: {n} fence crossings on {d}": "बार-बार पार करने वाला {p}: {d} को {n} बार बाड़ पार",
  "movements this week (usual {u})": "इस हफ़्ते की गतिविधियाँ (सामान्य {u})",
  "at night, 22:00-05:00 (usual {u})": "रात में, 22:00-05:00 (सामान्य {u})",
  "No change from the usual weeks.": "सामान्य हफ़्तों से कोई बदलाव नहीं।",
  "Week ending {w}, compared with {n} week(s) before.": "{w} को खत्म हुआ हफ़्ता, पिछले {n} हफ़्ते से तुलना।",
};

let LANG = (() => { try { return localStorage.getItem("rk-lang") === "hi" ? "hi" : "en"; } catch { return "en"; } })();

function t(text, vars = {}) {
  let out = (LANG === "hi" && I18N_HI[text]) || text;
  for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v));
  return out;
}

function applyI18n(root = document) {
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    if (el.dataset.i18nSrc === undefined) el.dataset.i18nSrc = el.textContent.trim().replace(/\s+/g, " ");
    el.textContent = t(el.dataset.i18nSrc);
  });
  root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    if (el.dataset.i18nSrc === undefined) el.dataset.i18nSrc = el.placeholder;
    el.placeholder = t(el.dataset.i18nSrc);
  });
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-lang-toggle]").forEach((b) => { b.textContent = LANG === "hi" ? "English" : "हिन्दी"; });
}

function setLang(lang) {
  LANG = lang === "hi" ? "hi" : "en";
  try { localStorage.setItem("rk-lang", LANG); } catch { /* private mode: this page only */ }
  applyI18n();
  document.dispatchEvent(new CustomEvent("langchange"));
}

document.addEventListener("click", (e) => {
  if (e.target.closest("[data-lang-toggle]")) setLang(LANG === "hi" ? "en" : "hi");
});
