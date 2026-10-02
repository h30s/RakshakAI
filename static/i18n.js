"use strict";

// Hindi / English for operator screens. Keys are the English text itself, so a missing
// translation simply shows English. Mark static text with data-i18n (and data-i18n-placeholder);
// translate dynamic text with t("English text", { var: value }).
// Translations need review by a native Hindi speaker before any field use.

const I18N_HI = {
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
