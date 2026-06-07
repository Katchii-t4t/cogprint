"use strict";

// ---------------------------------------------------------------------------
// CogPrint quick-log popup. Reuses the same backend the web app does:
//   POST {baseUrl}/sessions  (mirrors frontend/src/api.ts -> logSession)
// Settings (participant id, backend url, optional api key) live in
// chrome.storage.local. No build step — plain MV3 + vanilla JS.
// ---------------------------------------------------------------------------

const DEFAULTS = { baseUrl: "http://localhost:8000", participantId: "", apiKey: "" };

const $ = (id) => document.getElementById(id);

function getSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get(DEFAULTS, (s) => resolve({ ...DEFAULTS, ...s }));
  });
}
function saveSettings(s) {
  return new Promise((resolve) => chrome.storage.local.set(s, resolve));
}

function autoTimeOfDay() {
  const h = new Date().getHours();
  if (h >= 5 && h < 12) return "morning";
  if (h >= 12 && h < 17) return "afternoon";
  if (h >= 17 && h < 21) return "evening";
  return "night";
}

function show(view) {
  $("settings").classList.toggle("hidden", view !== "settings");
  $("logView").classList.toggle("hidden", view !== "log");
}

// --- Settings view ---------------------------------------------------------

function openSettings(current) {
  $("participantId").value = current.participantId || "";
  $("baseUrl").value = current.baseUrl || DEFAULTS.baseUrl;
  $("apiKey").value = current.apiKey || "";
  $("settingsMsg").textContent = "";
  show("settings");
}

$("saveSettings").addEventListener("click", async () => {
  const participantId = $("participantId").value.trim();
  const baseUrl = ($("baseUrl").value.trim() || DEFAULTS.baseUrl).replace(/\/+$/, "");
  const apiKey = $("apiKey").value.trim();
  if (!participantId || isNaN(Number(participantId))) {
    return setMsg("settingsMsg", "Enter a valid participant ID.", "err");
  }
  await saveSettings({ participantId, baseUrl, apiKey });
  initLogView({ participantId, baseUrl, apiKey });
});

$("gear").addEventListener("click", async () => openSettings(await getSettings()));

// --- Log view --------------------------------------------------------------

let SETTINGS = null;

function initLogView(s) {
  SETTINGS = s;
  $("pidLabel").textContent = s.participantId;
  // highlight auto-detected time of day
  const tod = autoTimeOfDay();
  document.querySelectorAll("#tod button").forEach((b) =>
    b.classList.toggle("active", b.dataset.v === tod)
  );
  $("logMsg").textContent = "";
  show("log");
}

// time-of-day segmented control
document.querySelectorAll("#tod button").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll("#tod button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
  })
);

// range value labels
$("duration").addEventListener("input", (e) => ($("durVal").textContent = e.target.value));
$("quiz").addEventListener("input", (e) => ($("quizVal").textContent = e.target.value));

function selectedTod() {
  const b = document.querySelector("#tod button.active");
  return b ? b.dataset.v : autoTimeOfDay();
}

function setMsg(id, text, kind) {
  const el = $(id);
  el.textContent = text;
  el.className = "msg" + (kind ? " " + kind : "");
}

$("submit").addEventListener("click", async () => {
  if (!SETTINGS) return;
  const body = {
    user_id: Number(SETTINGS.participantId),
    technique: $("technique").value,
    duration_minutes: Number($("duration").value),
    time_of_day: selectedTod(),
    quiz_score: Number($("quiz").value) / 100,
  };
  const sleep = $("sleep").value.trim();
  const stress = $("stress").value.trim();
  if (sleep) body.sleep_hours = Number(sleep);
  if (stress) body.stress_level = Number(stress);

  $("submit").disabled = true;
  setMsg("logMsg", "Saving…", "");
  try {
    const headers = { "Content-Type": "application/json" };
    if (SETTINGS.apiKey) headers["X-API-Key"] = SETTINGS.apiKey;
    const res = await fetch(`${SETTINGS.baseUrl}/sessions`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(typeof err.detail === "string" ? err.detail : "Request failed");
    }
    const s = await res.json();
    setMsg("logMsg", `✓ Session #${s.id} logged. Fingerprint updating…`, "ok");
    // brief reset so a second session can be logged quickly
    setTimeout(() => {
      $("quiz").value = 70;
      $("quizVal").textContent = "70";
      setMsg("logMsg", "", "");
    }, 2500);
  } catch (e) {
    const msg = String(e.message || e);
    setMsg(
      "logMsg",
      /Failed to fetch/.test(msg)
        ? "Could not reach the backend. Check the Backend URL in ⚙️ and that the server is running."
        : msg,
      "err"
    );
  } finally {
    $("submit").disabled = false;
  }
});

// --- Boot ------------------------------------------------------------------

(async function boot() {
  const s = await getSettings();
  if (!s.participantId) openSettings(s);
  else initLogView(s);
})();
