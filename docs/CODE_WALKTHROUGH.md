# DesignEye — Complete Code Walkthrough

A guide to reading this codebase. Open the file being discussed in your editor
and read this alongside it.

Every section answers four questions:

1. **What is it?**
2. **How does it work?**
3. **Where is it?**
4. **Why was it built this way?** — usually the most useful one, because it is
   what a viva actually asks.

---

## Contents

| Part | Topic |
|---|---|
| 0 | How to use this document |
| 1 | What DesignEye is — the mental model |
| 2 | The stack: every technology and why it is there |
| 3 | Repository map |
| 4 | **The journey of one upload** — the spine of the whole system |
| 5 | The machine-learning core |
| 6 | The scoring mathematics |
| 7 | The four hard problems (the real contributions) |
| 8 | Backend foundations |
| 9 | The API, endpoint by endpoint |
| 10 | The services layer |
| 11 | The frontend |
| 12 | The Chrome extension |
| 13 | Infrastructure |
| 14 | The tests |
| 15 | Glossary |
| 16 | Viva questions and answers |

---

# Part 0 — How to use this document

**Read Parts 1–4 first, in order.** They give you the mental model. After that
you can jump to whichever part you need.

**Part 4 is the spine.** It traces one upload from the button click to the
heatmap on screen. Every later part is a zoom-in on one step of that journey.
If you only understand Part 4, you can already explain the system.

Notation: `backend/app/ml/preprocess.py → letterbox_with_meta()` means open
that file and find that function.

---

# Part 1 — What DesignEye is

## The one-paragraph version

You upload a picture of a user interface. A neural network predicts **where
human eyes would land** on it. From that prediction the app calculates a
**Clarity Score out of 100**, marks the **top 5 spots** people would look at in
order, animates that as a **replay**, and asks an AI to write **suggestions**
grounded only in those numbers.

## Why it is not just "another analytics tool"

Hotjar and Crazy Egg also show heatmaps, but they need **real users on a live
site**. They record what people did. DesignEye **predicts** what people will do,
from a static image, before anyone has seen the design.

That single difference is the project's reason to exist: it works **before
launch**, when changing the design is still cheap.

## The chain of ideas

```
image  →  saliency map  →  numbers  →  meaning
```

- A **saliency map** is a greyscale image the same size as your design, where
  bright = "eyes likely land here" and dark = "eyes likely skip this".
- From that map you can compute **how concentrated** attention is (focused
  design) or **how scattered** it is (confusing design).
- Combined with how visually **busy** the design is, that becomes the Clarity
  Score.

Everything else in the codebase is plumbing around those three steps.

---

# Part 2 — The stack

## Backend

| Technology | What it does | Why this one |
|---|---|---|
| **Python 3.11** | Language | PyTorch is Python; no sensible alternative |
| **FastAPI** | Web framework — turns functions into HTTP endpoints | Async by default (needed: inference is slow), and auto-generates the Swagger docs at `/docs` |
| **PyTorch** | Runs the neural network | The checkpoint was trained in PyTorch |
| **MongoDB** | Database | Documents vary in shape (a result has viewports only sometimes); no migrations needed for an evolving FYP |
| **Motor** | Async MongoDB driver | A normal driver would block the event loop on every query |
| **Pydantic v2** | Validates data in and out | Every request body and response is a typed class, so bad data is rejected before it reaches your logic |
| **PyJWT + passlib/bcrypt** | Login tokens and password hashing | SDS specified Firebase; that was replaced with plain Python (see `DEVIATIONS.md` §1) |
| **Celery + Redis** | Background job queue | Inference takes ~250 ms–2 s; without a queue the API thread is blocked |
| **ReportLab** | Generates PDF reports | Pure Python, no external binary |
| **OpenCV + Pillow + NumPy** | Image maths | Resizing, colour maps, Sobel edges, array handling |

## Frontend

| Technology | What it does | Why this one |
|---|---|---|
| **Next.js 15 (App Router)** | React framework | File-based routing, server components for the landing page |
| **TypeScript** | Types for JavaScript | Catches "this field doesn't exist" before runtime |
| **Tailwind CSS v4** | Styling via utility classes | No separate CSS files to keep in sync |
| **TanStack Query** | Server-state management | Handles caching, refetching and **polling** — big for this app, since results arrive asynchronously |
| **Zustand** | Client state (just the auth session) | Far simpler than Redux for one small store |
| **Framer Motion** | Animation | Declarative, and respects "reduce motion" globally |
| **Recharts** | Charts | The per-screen clarity chart on the flow page |
| **Axios** | HTTP client | Its interceptors are what make the silent token-refresh possible |

## Why two separate applications?

The backend is a pure JSON API with no HTML. That means the **same API** serves
the web app *and* the Chrome extension, with no duplicated logic. Adding a
mobile app later would need no backend changes.

---

# Part 3 — Repository map

```
designeye/
├── backend/
│   ├── app/
│   │   ├── main.py            ← app starts here
│   │   ├── config.py          ← every setting, read from .env
│   │   ├── api/v1/            ← the HTTP endpoints
│   │   ├── core/              ← security, dependencies, errors
│   │   ├── db/                ← MongoDB connection and indexes
│   │   ├── ml/                ← the neural network and its preprocessing
│   │   ├── models/            ← what a document looks like in the database
│   │   ├── schemas/           ← what JSON goes in and out over HTTP
│   │   ├── services/          ← the actual work (the biggest folder)
│   │   └── workers/           ← Celery background jobs
│   └── tests/                 ← 187 automated tests
├── frontend/
│   ├── app/                   ← pages (folder name = URL)
│   ├── components/            ← reusable UI pieces
│   ├── hooks/use-api.ts       ← every API call in one file
│   └── lib/                   ← api client, auth store, coordinate maths
├── extension/                 ← the Chrome extension
├── scripts/                   ← verification and calibration tools
├── docs/                      ← this file and its siblings
└── docker-compose.yml         ← runs all five containers
```

## The layer rule

Data flows **downward only**:

```
api/  →  services/  →  ml/  and  db/
```

An endpoint in `api/` never touches PyTorch directly, and `ml/` never knows
that HTTP or MongoDB exist. That is why the ML core can be tested by
`scripts/verify_model.py` with no server and no database running.

## models/ vs schemas/ — the confusing pair

Both are Pydantic classes, and beginners mix them up constantly.

| | `models/domain.py` | `schemas/` |
|---|---|---|
| Describes | A row **in the database** | JSON **over HTTP** |
| Example field | `password_hash` | never `password_hash` |
| Used by | services, when writing | endpoints, in and out |

**Why separate?** Because they must differ. `User` in `models/` holds
`password_hash`; `UserResponse` in `schemas/` deliberately does not — that is
what stops the API from ever returning a password hash to a browser. One shared
class would make that leak a single careless edit away.

---

# Part 4 — The journey of one upload

**This is the most important section.** Follow it once and the rest is detail.

## Step 0 — The user picks a file

`frontend/app/(app)/upload/page.tsx`

Three ways in, all ending at the same function `accept()`:

- drag and drop
- click and browse
- **paste** (Ctrl+V) — handled by `frontend/lib/clipboard.ts`

`accept()` checks the extension and the size, then does something subtle: it
loads the image invisibly to **measure it**, and if it is taller than ~1.35
screens it asks *"which screen size should we assume?"*. Part 7 explains why
that question cannot be skipped.

## Step 1 — The request leaves the browser

`frontend/hooks/use-api.ts → useUpload()` builds a `FormData` and POSTs to
`/upload`. On the way out, `frontend/lib/api.ts` attaches the login token in an
`Authorization: Bearer …` header automatically.

## Step 2 — The server accepts it

`backend/app/api/v1/uploads.py → upload_mockup()`

In order:

1. **Who are you?** `CurrentUser` runs `core/deps.py → get_current_user()`,
   which decodes the token. No token → **401**.
2. **Read the bytes.** `raw = await file.read()`.
3. **What actually is this file?** `services/images.py → sniff_format()` reads
   the first few bytes — the "magic number". A PNG always starts with
   `\x89PNG\r\n\x1a\n`.

   > **Why not just look at the extension?** Because anyone can rename
   > `virus.exe` to `design.png`. The filename is user input and is never
   > trusted. Test: `test_tc04_extension_is_not_trusted`.

4. **Size check** — 10 MB for images, 20 MB for PDFs. Note the ordering: sniff
   **first**, then measure, because the limit depends on the real format.
5. **Convert to PNG.** SVG is rasterised by cairosvg, PDF page 1 by PyMuPDF.
   Everything downstream can then assume it has a PNG.
6. **Save the file.** `services/storage.py` writes it at
   `{user_id}/uploads/{asset_id}.png`.
7. **Record it.** A `MockupAsset` document is inserted with `status: pending`.
8. **Queue the work.** `services/jobs.py → enqueue_analysis()`.
9. **Reply immediately** with `202 Accepted` and a `task_id`.

> **Why 202 and not the result?** Inference takes seconds. Holding the HTTP
> connection open would tie up a server thread and time out behind most
> proxies. Instead: "accepted, here's a ticket number, ask me later."

## Step 3 — The analysis runs

`backend/app/services/pipeline.py → run_inference_pipeline()`

This is the heart of the system. It writes its progress into the database at
each step, which is what drives the progress bar the user sees:

```
preprocessing → running_inference → computing_analytics → persisting → complete
```

What it actually does:

1. Load the stored PNG back from storage.
2. `ml/theme.py → detect_theme()` — is this a dark design? (Part 7.2)
3. `services/viewports.py → slice_viewports()` — is this a long scrolling page
   that must be cut into screenfuls? (Part 7.3)
4. Run the model — **once** for a normal design, or **per slice** for a long page.
5. `services/analytics.py → analyse()` — turn the saliency map into numbers.
6. Save the heatmap PNG and the result document.
7. Mark the task `complete`.

> **Why does this function never raise?** Look at the `except` at the bottom: it
> records the failure on both the task and the asset, then returns `None`. If it
> raised, the background task would die silently and the frontend would poll a
> task that never changes — a spinner forever. Failing *loudly into the
> database* is what lets the UI show a real error.

## Step 4 — The browser polls

`frontend/hooks/use-api.ts → useTaskPolling()` calls `GET /status/{task_id}`:

- every **2 seconds** normally
- **eases off** after 30 seconds
- **gives up** at 3 minutes and offers a retry

> **Why give up at all?** A task that will never finish would otherwise poll
> forever, hammering the server and leaving the user staring at a spinner with
> no way out.

## Step 5 — The result is displayed

`frontend/app/(app)/results/[assetId]/page.tsx` fetches the full result and
renders it. The heatmap is drawn on a `<canvas>` by
`components/app/heatmap-viewer.tsx`.

## Step 6 — Suggestions (optional, later)

Only when the user clicks. `POST /results/{id}/suggestions` sends **the numbers
only** to an AI provider and stores what comes back.

> **Why is this separate from the analysis?** Because the AI can be slow, down,
> or unconfigured — and none of that should stop you seeing your heatmap. The
> core product works with no AI at all.

## The whole journey in one picture

```
BROWSER                          SERVER                       BACKGROUND
   |                                |                              |
   |-- POST /upload --------------->|                              |
   |                                |-- validate, store, insert    |
   |                                |-- queue job ---------------->|
   |<-- 202 { task_id } ------------|                              |
   |                                |                    load image
   |-- GET /status/{id} ----------->|                    detect theme
   |<-- { stage: "running" } -------|                    run model
   |                                |                    compute numbers
   |-- GET /status/{id} ----------->|                    save result
   |<-- { status: "complete" } -----|                              |
   |                                |                              |
   |-- GET /results/{asset_id} ---->|                              |
   |<-- full payload ---------------|                              |
```

---

# Part 5 — The machine-learning core

## 5.1 The model

`backend/app/ml/model.py`

**What:** A neural network called a **SalGAN-style generator**. It takes an
image and outputs a one-channel saliency map.

**Shape:** an *encoder–decoder with skip connections* (a "U-Net").

```
input 224×224×3
   ↓ encoder (VGG16) — squeezes the image down, learning "what is here"
   ↓ 14×14×512  ← tiny but semantically rich
   ↑ decoder — expands back up, learning "where exactly"
output 224×224×1
```

**Skip connections** are the sideways arrows: each decoder stage is handed the
matching encoder stage's output. Without them the decoder knows *what* is in the
image but has lost *precisely where*, and the output is a blurry blob.

**Why is this file locked?** The comment at the top says never to edit it. The
saved checkpoint (`stage3_ui_best_val.pth`) is a dictionary of weights keyed by
layer name — `enc2.5.weight` and so on. Loading uses `strict=True`, which fails
if a single name or shape differs. Renaming even one layer breaks the model
permanently. The odd indices (`vgg[5:9]`, `vgg[10:16]`) exist because slicing an
`nn.Sequential` preserves the original numbering.

## 5.2 Preprocessing — the letterbox

`backend/app/ml/preprocess.py`

**The problem:** the model only accepts 224×224 squares. Your design is 1600×900.

**Wrong fix:** squash it to a square — that distorts everything.

**The fix — "letterbox":** shrink it to fit, then pad the leftover with white,
exactly like black bars on a widescreen film.

```
1600×900  →  shrink to 224×126  →  pad 49px white above and below  →  224×224
```

`letterbox_with_meta()` returns both the padded canvas **and** a `LetterboxMeta`
recording exactly how much padding went where.

## 5.3 The single most important line in the codebase

`preprocess.py → unletterbox_saliency()`

The model returns a 224×224 saliency map — but 49 rows at the top and bottom
are **padding**, not your design. To map it back you must:

```python
cropped = saliency[top:bottom, left:right]   # 1. remove the padding
resized = cv2.resize(cropped, (orig_w, orig_h))  # 2. THEN scale up
```

**Reverse those two lines and every heatmap on every non-square upload sits
visibly offset from the design.** The padding gets stretched along with the
content, shifting everything.

This is why `CLAUDE.md` calls it "the single most likely regression here", why
`scripts/verify_model.py` has a dedicated check, and why five aspect ratios are
tested in `test_letterbox_alignment_preserves_dimensions`.

## 5.4 Running the model

`backend/app/ml/inference.py`

**The singleton.** `load_model()` caches the loaded network in a module-level
variable behind a thread lock.

> **Why?** Loading a 99 MB checkpoint takes ~1.4 seconds. Inference takes
> ~250 ms. Loading per request would make the app **six times slower** for no
> benefit. It is loaded once in the FastAPI startup and once per Celery worker
> process.

**`torch.no_grad()`** wraps the forward pass. Training needs to remember every
intermediate value to compute gradients; prediction does not. This turns that
bookkeeping off — faster and far less memory.

**`build_overlay()`** paints the saliency map over your design with the JET
colour map (blue = cold, red = hot). Note the per-pixel alpha: transparency
scales with intensity, so cold regions stay readable.

> **Why not a flat 50% blend everywhere (as the SDS said)?** Because it tints
> the entire mockup blue where attention is near zero — hiding the very design
> you are reviewing. See `DEVIATIONS.md` §6.

---

# Part 6 — The scoring mathematics

`backend/app/services/analytics.py`

## 6.1 The formula

```
clarity = 100 × (0.75 × focus  +  0.25 × (1 − clutter))
```

Two ingredients. High focus is good. High clutter is bad.

## 6.2 Focus — how concentrated is attention?

Built on **entropy**, a measure of "spread-out-ness" from information theory.

- All attention on one button → low entropy → **high focus**
- Attention smeared everywhere → high entropy → **low focus**

```python
grid = resize(saliency, (224, 224))     # always the same size
sal_norm = grid / grid.sum()            # make it sum to 1, like probabilities
entropy = -Σ (p × log₂ p)
focus_raw = 1 − entropy / log₂(N)
```

**Then a rescale:**

```python
focus = clamp((focus_raw − 0.04) / (0.19 − 0.04), 0, 1)
```

> **Why the rescale?** In practice `focus_raw` only ever lands between about
> 0.03 and 0.20. Fed straight into the formula, the best possible design would
> score around 30/100 — and TC-07 requires clean designs above 75. The rescale
> stretches the *observed* range onto 0–1. `FOCUS_RAW_MIN/MAX` are the
> calibrated bounds. See `DEVIATIONS.md` §4.

## 6.3 Clutter — how visually busy is it?

Uses a **Sobel filter**, which detects edges by measuring how fast brightness
changes between neighbouring pixels.

```python
gray = resize(image, long_side=512)   # always the same size
magnitude = sobel(gray)
edge_density = mean(magnitude > 50)   # fraction of pixels that are "edges"
clutter = clamp(edge_density / 0.215, 0, 1)
```

Lots of edges (borders, dividers, dense text) → high clutter.

## 6.4 The invariance rule — subtle and important

Notice both computations **resize to a fixed size first** (224 for entropy, 512
for edges).

> **Why?** Without it, exporting the same design at 2× resolution gives a
> different score — twice the pixels means twice the edges. The A/B comparison
> feature would then be meaningless, because you could "improve" a design just
> by exporting it smaller.

## 6.5 Focus Order

`extract_focus_order()` finds the top peaks using **non-maximum suppression**:

1. Blur slightly (so single stray pixels do not win).
2. Find the brightest pixel — that is rank 1.
3. **Blank out a circle around it**, so rank 2 cannot be its neighbour.
4. Repeat.

The radius is `max(20px, 8% of the long side)`.

> **Why not the flat 20 px in the SDS?** On a 3294 px tall page, all five points
> landed inside one headline, spanning 110 px. Useless as a viewing sequence.
> The 20 px became a floor, scaled by image size. `DEVIATIONS.md` §5.

**One extraction, two views.** `analyse()` extracts **10** points, then slices
the first 5 for `focus_nodes` and keeps all 10 for the replay.

> **Why not extract them separately?** Because the two lists would drift apart,
> and the animation would show a different order from the numbered list beside
> it. Extracting once makes disagreement structurally impossible.

---

# Part 7 — The four hard problems

**This is where the FYP's real engineering lives.** Each is a case of the model
being *wrong for a reason that has nothing to do with the design*, found by
measurement and fixed deliberately.

## 7.1 The pattern

All four share a shape:

> The model's input is a **fixed 224×224 square**, and it was trained on
> **light-mode interfaces**. Any design that violates those assumptions gets
> scored badly for reasons the designer cannot act on.

## 7.2 Dark designs

`backend/app/ml/theme.py`

**Symptom:** the same layout, colours flipped, edge density unchanged, scored
**89.3 light vs 37.4 dark**. Confirmed on a real screen: 65.4 vs 27.4.

**Cause:** two things. The checkpoint was trained on light UI, so dark input is
out-of-domain. And the letterbox pads with **white** — so a dark screenshot
reaches the model as a black island in a white field, a boundary that appears
nowhere in training data.

**Fix:** if mean brightness < 100, show the model a **brightened copy**.

**The important detail:** only the **luminance** channel is flipped, in LAB
colour space — not RGB.

> **Why?** Inverting RGB turns a blue button orange. That is not "the same
> design in light mode", and it throws away colour the model learned from.
> Measured: 37.40 uncompensated, 79.21 via RGB inversion, **79.98** preserving
> hue.

**And critically:** only the model's *input* changes. The heatmap, the clutter
index and every coordinate come from your original pixels. `ui_theme` is
recorded on the result so the compensation is never silent.

## 7.3 Long scrolling pages

`backend/app/services/viewports.py`

**Symptom:** a full-page export scored **0.0**, no matter how good it was.

**Cause — and it is arithmetic, not opinion:** at a 15:1 aspect ratio the page
occupies **6.2%** of the 224×224 input; the other 94% is white padding. Both
score terms hit their limits and the formula is forced to zero.

**Fix:** cut the page into overlapping **viewport-sized** slices *before*
inference, score each, and average.

> **Why before inference and not after?** This is the key insight. Slicing the
> whole-page saliency map afterwards would be cheaper — one forward pass instead
> of N. But that map was derived from a 14-pixel-wide sliver. **There is no
> information in it left to partition.** You must give the model real pixels.

The slices overlap by 12% so nothing sitting across a fold is missed, and
`stitch_saliency()` blends them back into one full-page map so the numbered dots
still land on the page you uploaded.

**Why the app asks "phone, tablet or desktop?"** Because a "screenful" has no
meaning without knowing the device. A phone frame exported at 2.5× is wider than
a laptop screen, so the image alone cannot tell you. It genuinely cannot be
inferred — so it is asked.

## 7.4 Tall phone screens

`backend/app/ml/inference.py → predict_saliency_hires()`

**Symptom:** phone screens scored 15–39 while desktop screens scored 73–98.
Aspect ratio correlated with the Clarity Score at **−0.730**.

**Cause:** a 2.75:1 phone screenshot letterboxes to an **81-pixel-wide** strip.
The model genuinely sees your design 81 pixels across. Blurry input produces
diffuse saliency, which raises entropy, which collapses the focus term.

**Fix:** split a tall frame into near-square horizontal bands, run each, stitch.

**The subtle bit:** bands are deliberately **not** normalised individually.

> **Why?** Sigmoid output is on an absolute scale, so bands are already
> comparable. Normalising each one would stretch a quiet band up to match a busy
> one — flattening the stitched map and destroying exactly the focus the split
> was meant to recover.

**7.3 vs 7.4 — what is the difference?** They look similar but the reasoning
differs:

| | 7.3 Long pages | 7.4 Tall frames |
|---|---|---|
| Problem | Nobody sees it all at once | Resolution is wasted |
| Fix | Score each screenful **separately** | Stitch into **one** map |
| Result | N scores, averaged | **One** score |

## 7.5 Whole design flows

`backend/app/api/v1/batches.py`

**What:** export a whole journey from Figma as one PDF; each page becomes a
screen and gets its own analysis.

**The structural decision:** a batch does **not** own its screens. Each page
becomes an ordinary `MockupAsset` tagged with a `batch_id`. The `ScreenBatch`
document only *groups* them.

> **Why does that matter so much?** Because every single-screen feature —
> results, rerun, scanpath, PDF export, the tenant-isolation guard — works on
> batch screens **for free**, with no parallel code path. A design where batches
> were their own thing would need every feature written twice.

**Derived status.** `_derive_status()` computes a batch's status by counting its
children **on every read**, rather than storing it.

> **Why?** A worker that dies mid-batch would otherwise leave it reading
> "processing" forever. Derived status cannot get stuck.

**One AI call for the whole flow.**

> **Why not one per screen?** Two reasons. Twelve screens would use twelve of a
> daily quota of fifty — two uploads and you are out. And more importantly, each
> call would only see its own numbers, so *"clarity drops most at screen 5"*
> becomes literally unsayable. Only one call that sees everything can compare.

---

# Part 8 — Backend foundations

## 8.1 Startup

`backend/app/main.py`

The `lifespan` function runs once at startup: connect MongoDB, create indexes,
load the model. Then the app serves requests. On shutdown it closes the DB.

Note both `try/except` blocks: a database or model failure **logs and continues**
rather than crashing. The failure then surfaces through `/health` — a container
that is up but degraded is more debuggable than one that refuses to boot.

The `unhandled_exception_handler` catches anything unexpected, logs the real
detail server-side, and returns a **generic** message to the client. Stack
traces reveal file paths and library versions and never go over the wire.

## 8.2 Settings

`backend/app/config.py`

One `Settings` class reads everything from `.env`. Validators reject invalid
values at startup — `STORAGE_BACKEND` must be `local` or `cloudinary`,
`LLM_PROVIDER` must be one of five known names. Failing at boot beats failing on
the first upload.

## 8.3 Security

`backend/app/core/security.py`

**Passwords** are hashed with **bcrypt at cost 12** — deliberately slow, so
brute-forcing a stolen database is impractical. Hashing is one-way: the app can
verify a password but never recover it.

**Tokens** are JWTs, in two kinds:

| | Access token | Refresh token |
|---|---|---|
| Lifetime | 15 minutes | 7 days |
| Used for | Every API call | Getting a new access token |

> **Why two?** A short access token limits the damage if it leaks. A long
> refresh token means the user is not logged out every 15 minutes. The refresh
> token is used rarely, so it is exposed less.

**Logout** cannot delete a JWT — it is just a signed string the client holds.
Instead its `jti` (unique id) goes into a `refresh_denylist` collection with a
**TTL index**, so MongoDB deletes the row automatically when the token would
have expired anyway.

**`token_predates_revocation()`** compares a token's issue time against
`users.tokens_valid_from`. Changing or resetting a password stamps that field,
which invalidates **every** token issued earlier.

> **Why?** Without it, an attacker holding a stolen refresh token keeps access
> for up to 7 days *after* the victim "recovers" the account.

## 8.4 Tenant isolation

`backend/app/core/deps.py → owned_or_403()`

Look carefully — it fetches the document **without** filtering by user, then
compares:

```python
doc = await db[collection].find_one({id_field: id_value})
if doc is None:            raise not_found(label)
if doc["user_id"] != user_id:  raise forbidden(...)
```

> **Why not just add `user_id` to the query?** That would return **404** for
> another user's resource, which is arguably better security (it does not
> confirm the resource exists). But the SDS's **TC-12 requires 403**. The
> docstring says exactly this — choosing the spec's behaviour and documenting
> the trade-off is the honest engineering call.

## 8.5 Indexes

`backend/app/db/indexes.py`

An index is a lookup table that turns "scan every document" into "jump straight
there". Without one on `mockup_assets.user_id`, listing your uploads reads
**every** upload by **every** user.

Two special ones:
- `users.email` is **unique** — the database itself refuses duplicates, even if
  two registrations race.
- `refresh_denylist.expires_at` is a **TTL index** — rows self-delete.

---

# Part 9 — The API, endpoint by endpoint

Base path: `/api/v1`. All except `/health` need a token.

## Auth — `api/v1/auth.py`

| Method | Path | Does |
|---|---|---|
| POST | `/auth/register` | Create account, return tokens |
| POST | `/auth/login` | Exchange credentials for tokens |
| POST | `/auth/refresh` | New access token from a refresh token |
| POST | `/auth/logout` | Denylist the refresh token |
| POST | `/auth/reset-password` | Start a password reset |
| POST | `/auth/reset-password/confirm` | Finish it |
| POST | `/auth/change-password` | Change while signed in |
| GET/PATCH | `/auth/me` | Read / update profile |
| POST/DELETE | `/auth/me/avatar` | Profile picture |

> **The trap at the top of this file.** It must **not** use
> `from __future__ import annotations`. The `@limiter.limit` decorator replaces
> the function, and FastAPI then resolves type annotations against *slowapi's*
> module namespace instead of ours. With postponed annotations the request
> models silently degrade into query parameters and every rate-limited endpoint
> returns 422. This is documented at the top of the file because it was hit
> once and is invisible when it happens.

**Account enumeration** is prevented deliberately: wrong password and unknown
email return the *identical* message, and a reset request replies the same way
whether or not the address exists.

## Upload, results, projects, compare, suggestions, batches

| Method | Path | Notes |
|---|---|---|
| POST | `/upload` | 202 + task_id |
| POST | `/upload/batch` | Multi-page PDF → N tasks |
| GET | `/status/{task_id}` | Polled every 2 s |
| GET | `/results` | Paginated history |
| GET | `/results/{asset_id}` | Full payload |
| POST | `/results/{id}/rerun` | Re-analyse without re-uploading |
| DELETE | `/results/{asset_id}` | Cascades |
| GET | `/results/{id}/report.pdf` | PDF report |
| GET | `/results/{id}/scanpath.gif` `.mp4` | Replay exports |
| GET/POST | `/results/{id}/suggestions` | Cached AI review |
| GET/POST/PATCH/DELETE | `/projects…` | CRUD |
| GET | `/dashboard` | Aggregate stats |
| POST/GET/DELETE | `/compare…` | A/B comparison |
| GET/DELETE | `/batches…` | Flow view |

---

# Part 10 — The services layer

## storage.py — where files live

An **abstract base class** with two implementations: local disk and Cloudinary.
The rest of the app calls `get_storage()` and never knows which is active.

> **Why abstract it?** Local disk for development (no account needed);
> Cloudinary for deployment (container filesystems are wiped on restart).
> Switching is one env var and zero code changes.

Every key is `{user_id}/...` so tenants are separated on disk too.

**The Cloudinary trap** (`_address()`): Cloudinary stores images and raw files
in **separate namespaces addressed differently** — an image's id drops the
extension, a raw file's keeps it. Get it wrong for `.npy` and it uploads fine
then fails to read back. Derived in exactly one place for that reason.

## images.py — validation

Magic-byte sniffing, size ceilings per format, rasterisation of SVG and PDF, and
dimension limits. Note the asymmetry: the **short** side is capped at 8000 px
but the **long** side at 30000 px, because a scrolling page is legitimately
enormous down one axis.

## jobs.py — where work goes

```python
if settings.DEV_MODE:
    background.add_task(run_inference_pipeline, ...)   # inline
else:
    run_inference_task.delay(...)                       # Celery
```

> **Why both?** `DEV_MODE` lets the whole product run with **no Redis and no
> worker process** — one command on a demo laptop. Production routes through
> Celery so a forward pass never occupies the API thread. Note the fallback: if
> Celery dispatch throws, it runs inline rather than losing the job.

## workers/ — Celery

Each task opens its **own** MongoDB client inside `asyncio.run()`.

> **Why not reuse the API's?** A Motor client is bound to the event loop that
> created it, and that loop does not exist in the worker process. Reusing it
> fails with "attached to a different loop".

## llm.py — the AI adapter

Four providers behind one interface, plus a `MockProvider` that returns valid
canned JSON so the feature demonstrates with **no API key**.

Key behaviours:
- Imports are **lazy** — only the configured provider's SDK is loaded.
- The reply is validated against a Pydantic schema.
- A parse failure gets **exactly one** re-prompt.
- A **truncated** reply is *not* retried — re-asking an over-long answer
  produces another over-long answer. Reduce scope instead.
- Timeouts are bounded, because some providers stall past 80 seconds.

`MockProvider` must answer **both** prompt shapes (single screen and flow),
detected via `FLOW_PROMPT_MARKER`. When it only knew one, every batch review
failed validation — and mock is the default, so the entire multi-screen feature
was dead without an API key.

**The AI never sees your image.** It receives only the analytics JSON, and the
prompt forbids claiming to see any specific button, colour or text.

## scanpath.py — the replay

Renders frames of a marker travelling between predicted fixations, pausing at
each. Exports as GIF (Pillow, no external binary) or MP4 (ffmpeg).

**It is a simulation, not a recording.** The model predicts *where*, not *when*.
The pauses come from published eye-tracking research, not from this model. Every
surface showing the replay says so — that is an honesty requirement, not a UI
preference.

## cleanup.py — cascade deletion

One function, `purge_assets()`, called by all three delete endpoints.

> **Why one function?** Because when they were written separately they drifted:
> the project delete removed the documents but left every stored file and every
> suggestion behind — permanently unreachable, because the documents holding the
> storage keys had just been deleted. Storage objects are removed **first**, for
> exactly that reason.

---

# Part 11 — The frontend

## 11.1 Routing

Next.js App Router: **folder name = URL**.

```
app/page.tsx              →  /
app/login/page.tsx        →  /login
app/(app)/dashboard/…     →  /dashboard
app/(app)/results/[assetId]/…  →  /results/abc123
```

`(app)` in brackets is a **route group** — it does not appear in the URL. It
exists so every page inside shares one layout: the auth guard and the sidebar.

## 11.2 State — three kinds, three tools

| Kind | Example | Tool |
|---|---|---|
| Server data | your projects | TanStack Query |
| Session | who is logged in | Zustand |
| Local UI | is this menu open | `useState` |

> **Why not one tool?** Server data needs caching, refetching and staleness —
> `useState` gives you none of that. Session must persist across reloads.
> Menu state needs neither.

## 11.3 The API client

`frontend/lib/api.ts`

Two Axios **interceptors**:

1. **Request** — attach the token to every call.
2. **Response** — on a 401, refresh the token and retry **once**.

**The single-flight refresh:**

```javascript
refreshing = refreshing ?? refreshAccessToken().finally(() => { refreshing = null; });
const token = await refreshing;
```

> **Why?** Open the dashboard and three requests fire together. All three get
> 401. Without this you would send three refresh requests and mint three tokens.
> The shared promise makes the other two wait for the first.

`NO_REFRESH_ROUTES` lists routes where a 401 means "wrong credentials", not
"expired token" — login, register, refresh, reset. Everything else under
`/auth/` (like `/auth/me`) **does** refresh normally.

## 11.4 The coordinate contract

`frontend/lib/coords.ts` — small, and load-bearing.

Three coordinate spaces exist:

| Space | Size |
|---|---|
| Model | 224×224 |
| API | original pixels (e.g. 1600×900) |
| Screen | whatever the browser container is |

The API **always** returns original pixels. `computeFit()` works out the scale
and offsets for the container; `toScreenCoords()` and `toImageCoords()` convert.

> **Why one file?** So no component does its own maths. If three components each
> converted coordinates their own way, they would disagree, and the bug would
> appear only at certain window sizes.

## 11.5 The heatmap viewer

`frontend/components/app/heatmap-viewer.tsx`

Draws on a `<canvas>`, not layered CSS images, for pixel-accurate compositing.

Details worth knowing:
- **devicePixelRatio** — the canvas is drawn at up to 2× and scaled down in CSS,
  otherwise it looks blurry on retina screens.
- **ResizeObserver** — re-fits when the container changes.
- **Ctrl+scroll to zoom** — plain scroll still scrolls the page.

## 11.6 The hydration trap

`frontend/app/providers.tsx` carries a warning worth understanding.

Next.js renders pages **twice**: once on the server (HTML) and once in the
browser. If the two disagree, React gets confused — "hydration mismatch".

`useReducedMotion()` returns different values on server and client. Branching
*rendered structure* on it leaves revealed content stuck at `opacity: 0` —
invisible, with no error. Reduced motion is therefore handled globally by
`MotionConfig reducedMotion="user"` instead.

The same reasoning is why the paste hint on the upload page resolves ⌘ vs Ctrl
in a `useEffect` and not during render.

---

# Part 12 — The Chrome extension

`extension/`

**What it adds:** analyse **any live web page**, not just files you export.

## The three pieces

| File | Runs where | Does |
|---|---|---|
| `manifest.json` | — | Declares permissions and the pinned id |
| `background.js` | Service worker | Capture, upload, poll |
| `popup.js` | The popup window | The UI |

> **Why is capture in the background and not the popup?** Two reasons.
> `chrome.tabs.captureVisibleTab` is unavailable to popup scripts. And the popup
> is destroyed the instant focus moves — an upload running there would die
> halfway.

## Whole-page capture

`captureFullPage()` scrolls the page one screenful at a time, screenshots each,
and stitches them into one tall image. The 260 ms gap between shots exists
because Chrome rate-limits `captureVisibleTab`; without it the stitch fails
partway down.

## Paste support

The popup accepts Ctrl+V, drag-drop, or a file picker.

> **Why Ctrl+V rather than a "read clipboard" button?** A real paste event needs
> **no permission**. `navigator.clipboard.read()` would require `clipboardRead`
> and its "Read data you copy and paste" install warning — a scary prompt for
> something the keystroke already does.

## The pinned id

`manifest.json` contains a `key` field, which fixes the extension's id. That is
why the API's CORS allow-list can name one exact extension instead of opening up
to all of them.

---

# Part 13 — Infrastructure

## Docker Compose — five containers

| Container | Role |
|---|---|
| `mongo` | Database (named volume, survives restarts) |
| `redis` | Celery's message broker |
| `api` | FastAPI |
| `worker` | Celery worker |
| `frontend` | Next.js |

`depends_on: condition: service_healthy` means the API waits for Mongo and Redis
to be **healthy**, not merely started.

## The backend image

Two decisions worth noting:

- **Torch from the CPU index.** The default wheel pulls ~2 GB of CUDA payload a
  CPU container never uses.
- **LLM SDKs are opt-in** via a build argument, because
  `google-generativeai` alone pulls a large dependency tree.

## The frontend image and the rebuild rule

A three-stage build ending in a Next **standalone** bundle, run as a non-root
user.

> **The thing that catches everyone:** `NEXT_PUBLIC_*` variables are **compiled
> into the JavaScript at build time**, not read at runtime. Changing
> `NEXT_PUBLIC_API_URL` requires rebuilding the image. The same applies to
> anything in `public/` — including the extension ZIP the website hands out.

```bash
docker compose build api worker frontend && docker compose up -d
```

`docker compose restart` will **not** pick up code changes — the code is baked
into the image.

## Scripts

| Script | Purpose |
|---|---|
| `verify_model.py` | 13 checks on the inference path — no server or DB needed |
| `calibrate_clarity.py` | Scores the calibration samples; `--tune` grid-searches the constants |
| `make_samples.py` | Regenerates the calibration set |
| `seed_demo.py` | Seeds the demo account |
| `build_extension.py` | Packages `extension/` into the downloadable ZIP |
| `build_brand_assets.py` | Generates every logo tier from one source image |

---

# Part 14 — The tests

## What exists

| Suite | Count | Command |
|---|---|---|
| Backend | 187 | `cd backend && pytest` |
| Extension | 85 | `node test/*.test.mjs` |
| Model | 13 | `python scripts/verify_model.py` |

## The design decision that matters

Tests run against a **real MongoDB and the real model** — nothing is mocked.

> **Why?** The point of TC-07 and TC-08 is that a clean design scores above 75
> and a cluttered one below 40. A mocked model would prove only that the mock
> returns what the mock was told to return.

The cost is slowness (every test runs real inference). The benefit is that a
pass means the real thing works.

## conftest.py

Fixtures shared by every test. Note it pins environment variables **before**
importing the app, including `STORAGE_BACKEND=local` — without that, a developer
whose `.env` says `cloudinary` would upload every test artefact to a real
account.

`pytest.ini` pins fixtures and tests to **one session-scoped event loop**,
because Motor clients are bound to the loop that created them.

---

# Part 15 — Glossary

| Term | Meaning |
|---|---|
| **Saliency** | How much something visually stands out |
| **Saliency map** | A greyscale image where bright = likely looked at |
| **Letterbox** | Padding an image to a square without distorting it |
| **Entropy** | A measure of spread-out-ness; low = concentrated |
| **Sobel filter** | Edge detector — finds fast brightness changes |
| **NMS** | Non-maximum suppression: pick a peak, blank its neighbours, repeat |
| **Sigmoid** | Squashes any number into 0–1 |
| **Checkpoint** | A saved file of trained network weights (`.pth`) |
| **Forward pass** | Running data through the network to get a prediction |
| **JWT** | A signed token proving who you are |
| **jti** | A JWT's unique id, used to revoke it |
| **bcrypt** | A deliberately slow password-hashing algorithm |
| **TTL index** | A MongoDB index that auto-deletes expired rows |
| **Tenant isolation** | Ensuring one user cannot see another's data |
| **Celery** | A background job queue |
| **Motor** | The async MongoDB driver |
| **Pydantic** | Validates and types data |
| **Interceptor** | Code that runs before/after every HTTP call |
| **Hydration** | React taking over server-rendered HTML in the browser |
| **CC / NSS** | Standard saliency accuracy metrics |
| **Viewport** | One screenful |
| **Aspect ratio** | Width ÷ height |

---

# Part 16 — Viva questions and answers

## About the model

**Q. Did you train this model?**
No. It is a pre-trained SalGAN-style checkpoint. The engineering contribution is
the *system* around it — and specifically the four compensations in Part 7 for
cases where the model is wrong for reasons unrelated to the design.

**Q. How accurate is it?**
The checkpoint records CC 0.675 and NSS 2.43 on its validation set. Be precise:
those numbers were recorded by the training run and are **not** independently
re-measured in this project.

**Q. Why is `model.py` locked?**
The checkpoint is a dictionary keyed by layer name, loaded with `strict=True`.
Any rename or shape change breaks loading permanently.

## About correctness

**Q. Why does the heatmap line up on non-square uploads?**
Because `unletterbox_saliency()` crops the padding **before** rescaling.
Reversing those two steps offsets every non-square heatmap. It is asserted
across five aspect ratios and has a dedicated check in `verify_model.py`.

**Q. Why is the score resolution-invariant?**
Entropy is computed on a fixed 224 grid and edge density at a fixed 512 long
side. Without that, the same design exported at 2× would score differently and
A/B comparison would be meaningless.

## About the four problems

**Q. Why segment a long page before inference, not after?**
Because at 15:1 the page fills 6.2% of the model's input. The whole-page
saliency map is derived from a 14-pixel sliver — there is no signal left in it to
partition. Slicing after would be cheaper and worthless.

**Q. Why flip only luminance for dark designs?**
Inverting RGB turns a blue button orange, which is not the same design in light
mode. Measured: 37.40 uncompensated, 79.21 RGB-inverted, 79.98 luminance-only.

**Q. Why not normalise each band when splitting a tall frame?**
Sigmoid output is absolute, so bands are already comparable. Normalising each
would stretch a quiet band to match a busy one and flatten the very focus the
split recovers.

**Q. Why one AI call per flow instead of per screen?**
Twelve screens would use twelve of a fifty-per-day quota. More fundamentally,
per-screen calls each see only their own numbers, so "clarity drops most at
screen 5" could never be said.

## About the system

**Q. Why 403 and not 404 for another user's asset?**
SDS TC-12 specifies 403. `owned_or_403()` fetches without the user filter, then
compares. The trade-off — that 403 confirms the resource exists — was accepted
to meet the spec and is documented.

**Q. Why does the upload return 202 instead of the result?**
Inference takes seconds. Holding the connection open ties up a thread and times
out behind proxies. The client gets a ticket and polls.

**Q. What happens if the AI provider is down?**
Nothing important. Suggestions are generated separately from the analysis; the
endpoint returns an `unavailable` status and the heatmap, score and focus order
are unaffected.

## The honest ones — prepare these

**Q. Is the Clarity Score validated against real human judgement?**
**No.** The constants were calibrated against 12 sample images, and there is no
held-out set and no user study. This is the project's main limitation and the
first thing a further-work section should name.

**Q. Are the cluttered samples real designs?**
No — all five are synthetic, generated by `make_samples.py`. The clean set
includes four real screens.

**Q. What would you do with more time?**
In order: a held-out validation set; real cluttered screens; a small human
ranking study to correlate against the score; and a checkpoint fine-tuned on
dark interfaces, which would remove the need for the compensation in Part 7.2
entirely.

---

## Where to go next

| To understand | Read |
|---|---|
| Why anything deviates from the SDS | `docs/DEVIATIONS.md` |
| Module responsibilities at a glance | `docs/ARCHITECTURE.md` |
| Conventions and traps already hit | `CLAUDE.md` |
| What is tested | `docs/TEST_CASES.md` |
| What still needs manual testing | `docs/MANUAL_TESTING.md` |

**Suggested first session with the code**, in this order:

1. `backend/app/ml/preprocess.py` — small, and the letterbox is the key idea
2. `backend/app/services/analytics.py` — the score, start to finish
3. `backend/app/services/pipeline.py` — how the pieces connect
4. `backend/app/api/v1/uploads.py` — one endpoint end to end
5. `frontend/lib/coords.ts` — small and load-bearing
6. `frontend/app/(app)/upload/page.tsx` — the UI side of the same journey
