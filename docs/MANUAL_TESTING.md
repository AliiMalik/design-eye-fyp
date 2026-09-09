# Manual testing checklist — DesignEye

The 51 test cases that cannot be run mechanically. Everything else in
`docs/TEST_CASES.md` is automated and already passing (192 / 243 as of
2026-09-07); this file is only the part that needs a person.

Ordered by **where you do it**, not by module, so you set up once per session
instead of switching back and forth.

| Session | Cases | Roughly |
|---|---|---|
| A — Web app in a browser | 27 | 45 min |
| B — Chrome extension | 6 | 15 min |
| C — Failure and environment | 14 | 30 min |
| D — Deployment gates and out of scope | 4 | at deploy time |

**Tester:** ________________  **Date:** ____________  **Build:** `git rev-parse --short HEAD` = ________

---

## Before you start

```bash
docker compose up -d
```

```bash
docker compose exec api python -m app.seed --reset
```

Sign in at http://localhost:3000 as `demo@designeye.app` / `Demo@1234`.

### Test files to have ready

Put these somewhere easy to reach. Sessions A and B both need them.

| # | File | Why | How to get it |
|---|---|---|---|
| 1 | A **non-square** mockup, e.g. 1600×900 | TC-GEO-03/04/05/06 | `inputs/screens/visily-designeye-landing-page.jpg` |
| 2 | A **tall phone** screenshot (roughly 9:19.5) | TC-PASTE-09 | Screenshot your phone, or crop any image tall |
| 3 | A **dark-themed** UI screenshot | TC-DARK-09 | Any app in dark mode — VS Code, YouTube dark |
| 4 | An image **over 10 MB** | TC-PASTE-07 | Export a photo at max quality, or upscale one |
| 5 | A **multi-page PDF** (4+ screens) | TC-BATCH-05 | Figma → export frames to PDF, or `inputs/` samples |
| 6 | **Two** different mockups already analysed | TC-AB-06 | Upload any two before starting |

### How to mark results

Tick the box for a pass. For a failure write what happened in the Notes line —
"looked wrong" is not a bug report; "heatmap sat ~40 px left of the button on a
1600×900 upload" is.

---

## Session A — Web app in a browser

Do these in one sitting with the app open. Cases are ordered so each builds on
the last where possible.

### A1. Upload, drag-drop and browse

| ☐ | ID | What to do | Pass if |
|---|---|---|---|
| ☐ | TC-UP-24 | Drag file #1 over the upload zone, hold, then drop | Zone highlights while hovering → file is accepted and previewed |
| ☐ | TC-UP-25 | Click the upload zone | OS file dialog opens, filtered to PNG/JPG/WEBP/SVG/PDF |

**Notes:** ______________________________________________

### A2. Paste to analyse — the new feature

> These need a **real** screenshot on your clipboard. Automated tests fire a
> synthetic paste event, which is not the same thing — only this session proves
> the OS clipboard path actually works.

| ☐ | ID | What to do | Pass if |
|---|---|---|---|
| ☐ | TC-PASTE-01 | Take a screenshot (Win+Shift+S). Open `/upload`. **Click nothing.** Press Ctrl+V | Image stages with a preview → the drop zone flashes → toast "Screenshot pasted." |
| ☐ | TC-PASTE-02 | Look at the staged filename | Reads `screenshot-2026-09-07-143022.png` style — **not** `image.png` |
| ☐ | TC-PASTE-03 | Reset. Take another screenshot. Click the **"Paste screenshot"** button | Same result as Ctrl+V |
| ☐ | TC-PASTE-04 | Copy some **text**, then click "Paste screenshot" | Toast: "No image on the clipboard. Take a screenshot, then try again." |
| ☐ | TC-PASTE-06 | With text still copied, press Ctrl+V on the upload page | Nothing stages, no error. Then click into any text field and Ctrl+V — **the text still pastes normally** |
| ☐ | TC-PASTE-07 | Copy file #4 (>10 MB) as an image and paste it | Refused, message names the 10 MB limit |
| ☐ | TC-PASTE-08 | Paste a screenshot, then click Analyse | Runs exactly like a browsed file → result page shows the stamped filename |
| ☐ | TC-PASTE-09 | Copy file #2 (tall phone screenshot) and paste it | The **screen-size question** (phone/tablet/desktop) appears, as it would for a browsed tall image |
| ☐ | TC-PASTE-10 | With one staged, paste a different screenshot | The new one replaces the old; only one staged at a time |
| ☐ | TC-PASTE-11 | Start an analysis, then press Ctrl+V while it runs | Nothing stages; no error |

**Notes:** ______________________________________________

### A3. Coordinate correctness — the highest-value checks here

> `CLAUDE.md` names the letterbox crop order as the single most likely
> regression in the codebase. The automated tests prove the output **dimensions**
> are right; only your eye proves the heatmap is in the right **place**.

| ☐ | ID | What to do | Pass if |
|---|---|---|---|
| ☐ | TC-GEO-03 | Upload file #1 (non-square, 1600×900). Open the result. Switch to the **heatmap** view | Hot regions sit **on** the actual UI elements. No visible offset, no shift toward one edge |
| ☐ | TC-GEO-04 | Zoom in with the + control, then pan around | Numbered focus dots stay locked to the same UI features at every zoom level |
| ☐ | TC-GEO-05 | With the result open, resize the browser window narrow then wide | Overlay and dots re-fit correctly; nothing drifts out of place |
| ☐ | TC-GEO-06 | Switch to the **focus order** view and compare dot 1 with the design | Dot 1 sits on what genuinely draws the eye first — a headline, a button, a face |

**Notes:** ______________________________________________

### A4. Result presentation

| ☐ | ID | What to do | Pass if |
|---|---|---|---|
| ☐ | TC-SCORE-14 | Look at the Clarity gauge on a few results | Band label matches the number: ≥75 "Strong", 40–74.9 "Moderate", <40 "Needs work" |
| ☐ | TC-DARK-09 | Upload file #3 (dark-themed UI) and open the result | The page **says plainly** that a brightened copy was scored — the compensation is never silent |
| ☐ | TC-PATH-01 | Open the **"Watch the replay"** tab | Playback animates across the mockup in the predicted viewing order |
| ☐ | TC-PATH-02 | While the replay is visible, read the surrounding text. Also export the PDF and check it | The **"simulation, not a recording"** disclaimer appears in both places |
| ☐ | TC-AB-06 | Compare the two designs from file #6. Scroll and zoom **one** side | The other side follows in sync |
| ☐ | TC-BATCH-05 | Upload file #5 (multi-page PDF) via the flow route and **watch while it runs** | Per-screen progress is visible, status reads "processing", then settles to complete — it never sticks |

**Notes:** ______________________________________________

### A5. Session handling

| ☐ | ID | What to do | Pass if |
|---|---|---|---|
| ☐ | TC-AUTH-32 | Sign in, then hard-refresh the browser (Ctrl+Shift+R) | Still signed in; no redirect to login |
| ☐ | TC-AUTH-34 | Open DevTools → Network. Open dashboard, then quickly navigate to results and projects | On an expired token you see **one** `/auth/refresh` call, not three |

**Notes:** ______________________________________________

### A6. Accessibility and responsive

| ☐ | ID | What to do | Pass if |
|---|---|---|---|
| ☐ | TC-NFR-07 | Put the mouse away. Tab through login → dashboard → upload → results | Every control reachable; focus ring always visible; Enter/Space activate buttons |
| ☐ | TC-NFR-08 | DevTools device toolbar at 375 px, 768 px, 1440 px | Layout holds at all three. **No horizontal scrollbar** on the page body |
| ☐ | TC-NFR-10 | Toggle dark/light theme and walk every page | Text readable everywhere; no white-on-white or black-on-black |

**Notes:** ______________________________________________

---

## Session B — Chrome extension

> The node harness covers `popup.js` logic (18 automated cases). It cannot load
> the extension into a real browser — which is exactly the gap that let the
> stale-ZIP problem through. These six close it.

**Setup.** Remove any existing DesignEye extension first, then
`chrome://extensions` → Developer mode on → **Load unpacked** →
`D:\FYP\designeye project\designeye\extension`.

> Loading **unpacked from that folder** means future edits need only the ↻
> reload button. Loading from the downloaded ZIP gives you a frozen snapshot —
> that is what caused the earlier confusion.

| ☐ | ID | What to do | Pass if |
|---|---|---|---|
| ☐ | TC-EXT-01 | Load unpacked and look at the card | No manifest errors; toolbar icon appears; card shows version 1.0.0 |
| ☐ | TC-EXT-06 | Open a **long** real page (a news homepage). Popup → tick "Whole page" → Analyse | Page visibly scrolls, then a score and heatmap return. The heatmap covers the **whole** page, not just the fold |
| ☐ | TC-EXT-16 | Drag an image file onto the popup's paste zone | Zone highlights → image stages with thumbnail, name and size |
| ☐ | TC-EXT-17 | Click the paste zone | File chooser opens → picking an image stages it |
| ☐ | TC-EXT-23 | Expand "Server address", change it, click Save, reopen the popup | The new address persisted and is used for the next call |
| ☐ | TC-EXT-25 | Download the ZIP from the site's **Chrome Extension** page, unzip, load it | Popup shows the **paste zone**. If it does not, the frontend image needs rebuilding — see below |

**If TC-EXT-25 fails:**

```bash
python scripts/build_extension.py && docker compose build frontend && docker compose up -d frontend
```

**Notes:** ______________________________________________

---

## Session C — Failure and environment behaviour

> These restart containers or induce failures. Do them **last** — some briefly
> take the site down, and one wipes data.

| ☐ | ID | What to do | Pass if |
|---|---|---|---|
| ☐ | TC-NFR-11 | `docker compose stop api`, then use the web app | Clear "Cannot reach the server" messaging — **not** a blank page or an infinite spinner. Then `docker compose start api` |
| ☐ | TC-INF-09 | `docker compose stop redis`, then open http://localhost:8000/health | `status: "ok"` with `redis: false` — DEV_MODE runs inference inline so Redis is not required. Then `docker compose start redis` |
| ☐ | TC-NFR-05 | Note your project count. `docker compose down` then `docker compose up -d`. Sign back in | **Every project and result still there** — the named Mongo volume survived |
| ☐ | TC-AUTH-33 | Sign in, wait **16 minutes** (access token is 15 min), then edit your display name on Settings | Saves successfully. It must refresh transparently — this is the bug fixed in `lib/api.ts`, so it is worth confirming |
| ☐ | TC-AUTH-23 | Request a password reset, wait **31 minutes**, then use the token | 400 "This reset link has expired." |
| ☐ | TC-INF-11 | Upload, then immediately `docker compose stop api` so the task never settles | Frontend polls, eases off after 30 s, hard-stops at 3 min and offers a retry — it does not spin forever |
| ☐ | TC-INF-12 | Upload a mockup, then delete its file from Cloudinary/storage mid-run | Task ends `failed` with a clean message; the asset shows failed; nothing hangs |
| ☐ | TC-NFR-04 | Upload three different mockups in three tabs at once | All three complete; each result matches its own upload — no mixing |
| ☐ | TC-LLM-11 | Generate suggestions more than `LLM_RATE_LIMIT_PER_DAY` (50) times in one day | `rate_limited` status with a clear "try again tomorrow" message |
| ☐ | TC-LLM-12 | Set `LLM_PROVIDER=anthropic` **without** installing its SDK, restart the API | App still **starts**; logs name the fix; suggestions report `unavailable` |
| ☐ | TC-INF-10 | Set `DEV_MODE=false`, `docker compose up -d --build api worker`, upload | Identical result to the inline path; worker logs show it picked up the task |
| ☐ | TC-PASTE-05 | Open the app in Firefox and click "Paste screenshot" | Message points at Ctrl+V instead of dead-ending (Firefox lacks image clipboard read) |
| ☐ | TC-NFR-06 | **Destructive.** `docker compose down -v`, then `up -d`, then reseed | App starts cleanly against an empty DB; indexes created; no crash |
| ☐ | TC-SEC-08 | **Risky.** Upload a small PNG that decodes to ~200 M pixels | Should be refused. ⚠️ Run against a throwaway instance — it can exhaust memory |

**Notes:** ______________________________________________

---

## Session D — Deployment gates and out of scope

Not runnable now. The first two are **checks to perform at deploy time**, and
they are the two that matter most for going live.

| ☐ | ID | When | What to verify |
|---|---|---|---|
| ☐ | TC-SEC-10 | **Before deploying** | `EXPOSE_RESET_TOKEN=false`. It is `true` in both your `.env` files right now — correct locally, an account-takeover hole in production |
| ☐ | TC-SEC-09 | **Before deploying** | `JWT_SECRET` is a real random value in the Hugging Face secrets, not the shipped default. Currently set correctly locally |
| ☐ | TC-PASTE-12 | If a Mac is available | The paste hint renders ⌘ V, not Ctrl V; no hydration warning in the console |
| ☐ | TC-NFR-09 | If testable | Turn on OS-level "reduce motion" → animations respect it; no content stranded invisible |
| ☐ | — | At deploy | Also confirm `DEV_MODE=false`, `CORS_ORIGINS` names the Firebase domain, and `NEXT_PUBLIC_API_URL` is set **before** the frontend build |

**Notes:** ______________________________________________

---

## Summary

| Session | Total | Passed | Failed | Not run |
|---|---|---|---|---|
| A — Web app | 27 | | | |
| B — Extension | 6 | | | |
| C — Environment | 14 | | | |
| D — Deployment | 4 | | | |
| **Total** | **51** | | | |

**Overall result:** ☐ Pass  ☐ Pass with defects  ☐ Fail

**Defects raised:** ______________________________________________

**Signed:** ________________  **Date:** ____________

---

### If you only have twenty minutes

Do these six. They cover the highest risk per minute:

1. **TC-GEO-03** — heatmap alignment. The named most-likely regression.
2. **TC-PASTE-01** — real clipboard paste. No automated test can prove this one.
3. **TC-EXT-06** — whole-page capture on a real site.
4. **TC-PATH-02** — the simulation disclaimer. An academic-integrity point, not just a UI one.
5. **TC-NFR-05** — data survives a restart.
6. **TC-AUTH-33** — token refresh on Settings. Recently fixed; worth confirming.
