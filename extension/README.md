# CogPrint — Quick Session Log (browser extension)

A Manifest V3 browser extension that logs a CogPrint study session in one click
from the toolbar, without opening the full web app. It talks to the same backend
(`POST /sessions`) as the web frontend.

No build step — it's plain HTML/CSS/JS. Load it unpacked.

## Install (Chrome / Edge / Brave)

1. Go to `chrome://extensions` (or `edge://extensions`).
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select this `extension/` folder.
4. Pin the CogPrint icon to the toolbar.

## First-run setup

Click the icon → the settings panel opens:

- **Participant ID** — your CogPrint participant number (same one the web app uses).
- **Backend URL** — defaults to `http://localhost:8000`. Set this to your deployed
  backend for real use.
- **API key** — only needed if the backend has `COGPRINT_API_KEY` set.

Settings are stored in `chrome.storage.local` (per browser). Change them anytime
via the ⚙️ button.

## Logging a session

Pick technique, duration, time-of-day (auto-selected from the current hour),
and quiz score; optionally add sleep/stress. Hit **Log session**. The session
posts to the backend and the cognitive-fingerprint rebuild kicks off there.

## Deploying against a non-local backend

The manifest's `host_permissions` currently allows only `localhost:8000`. To use
a deployed backend, add its origin to `host_permissions` in `manifest.json`,
e.g.:

```json
"host_permissions": [
  "http://localhost:8000/*",
  "https://cogprint-api.onrender.com/*"
]
```

then reload the extension. (MV3 grants the popup CORS-free fetch only to hosts
listed here.)

## Files

| File | Purpose |
|---|---|
| `manifest.json` | MV3 manifest (action popup, storage, host permissions) |
| `popup.html` | Popup markup (settings view + log form) |
| `popup.css` | Styling (matches the app's indigo theme) |
| `popup.js` | Logic: settings, auto time-of-day, POST /sessions |
| `icons/` | Toolbar icons (16/48/128) |

## Possible next step

A background service worker + `notifications` permission could nudge you when a
24h/7d retention check comes due (`GET /users/{id}/pending-checks`). Not built
yet — see the "Retensjons-påminningar" option in the project plan.
