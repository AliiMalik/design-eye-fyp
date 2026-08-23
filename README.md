# DesignEye

Predictive visual-attention analysis for static UI mockups.

Upload a design and a pre-trained SalGAN-style saliency model predicts where
human eyes will land — returning an attention heatmap, a Clarity Score (0–100),
a ranked Focus Order, an animated replay of the predicted viewing order
(exportable as GIF or MP4), grounded design suggestions, A/B comparison, and
PDF export. **No users, no traffic, no tracking script required**, which is what
separates it from Hotjar and Crazy Egg: it works before launch.

Final Year Project — Group S26CS003, University of Central Punjab.

---

## Quick start

The model weights (`stage3_ui_best_val.pth`, ~99 MB) are gitignored. Put them at
`backend/app/ml/weights/stage3_ui_best_val.pth` before starting.

```bash
cp .env.example .env && python -c "import secrets;print(secrets.token_urlsafe(48))"
```

Paste that value into `JWT_SECRET` in `.env`, then:

```bash
docker compose up -d --build
```

```bash
docker compose exec api python -m app.seed --reset
```

Open **http://localhost:3000** and sign in.

| | |
|---|---|
| **Demo account** | `demo@designeye.app` |
| **Password** | `Demo@1234` |
| Frontend | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

---

## Running without Docker

Two terminals. `DEV_MODE=true` means no Redis and no Celery worker are needed —
inference runs inline in the API process.

```bash
python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt
```

```bash
cd backend && ../.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend && npm install && npm run dev
```

MongoDB must be reachable at `MONGODB_URI`. The quickest way:

```bash
docker run -d --name designeye-mongo -p 27017:27017 -v designeye_mongo_data:/data/db mongo:7
```

---

## Architecture

```
Next.js 15 (App Router, TS)          FastAPI (async, Python 3.11)
  ├─ Canvas heatmap + SVG focus  ──▶   ├─ JWT auth (bcrypt 12 + PyJWT)
  ├─ TanStack Query polling            ├─ Upload validation & rasterisation
  └─ Zustand auth · Framer Motion      ├─ SalGAN inference (singleton)
                                       ├─ Analytics (entropy + Sobel)
                                       ├─ LLM adapter (4 providers)
                                       └─ ReportLab PDF
                                            │
                    MongoDB (Motor) ────────┼──────── Redis + Celery
                    Storage: local │ Cloudinary        (optional; DEV_MODE
                                                        runs inline)
```

Full detail in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### The model

A SalGAN-style encoder–decoder: VGG16 encoder with U-Net skip connections,
outputting 1-channel logits at 224×224. The checkpoint reports **CC 0.675 /
NSS 2.43** on held-out validation at epoch 19. It is loaded **once** per process
and every forward pass runs under `torch.no_grad()`.

Preprocessing letterboxes to 224×224 with white padding. The padding offsets are
returned and used to **crop the saliency map before rescaling to the original
dimensions** — skip that and the heatmap sits visibly offset from the UI on every
non-square upload. This is asserted across five aspect ratios in the test suite.

Verify the whole inference path independently:

```bash
python scripts/verify_model.py
```

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/verify_model.py` | 13 checks: strict checkpoint load, output shape/range, synthetic peak localisation, letterbox alignment |
| `scripts/make_samples.py` | Regenerates the clarity calibration set |
| `scripts/calibrate_clarity.py` | Scores the samples; `--tune` grid-searches the constants |
| `scripts/seed_demo.py` | Seeds the demo account; `--reset` rebuilds it. Inside the container use `python -m app.seed` — the implementation lives in `backend/app/seed.py` so it ships in the image, and falls back to generated mockups when `inputs/` is absent. |
| `scripts/make_demo_assets.py` | Renders the landing-page hero from real model output |

---

## Tests

```bash
cd backend && ../.venv/Scripts/python -m pytest
```

172 tests covering SDS test cases TC-01…TC-14, plus letterbox alignment, tenant
isolation across every owned resource, token expiry, and the LLM adapter's
retry-once behaviour. Mapping table in [`docs/DEVIATIONS.md`](docs/DEVIATIONS.md) §14.

Tests run against a real MongoDB and the real model — a mocked model would not
prove that TC-07/TC-08 actually land in their score bands.

---

## The replay

The results page has a **Watch the replay** tab that plays the predicted viewing
order back over your mockup, and exports it as a looping GIF or an MP4. The PDF
report gets a six-frame contact sheet of the same sequence.

It is a **simulation, not a recording**. DesignEye predicts *where* people are
most likely to look; the replay orders those spots strongest-first and spaces
them using pause lengths from published eye-tracking research. The interface
states this plainly wherever the replay appears. See
[`docs/DEVIATIONS.md`](docs/DEVIATIONS.md) section 17.

MP4 export needs `ffmpeg`, which is installed in the API image. Without it the
endpoint returns 503 and points you at the GIF instead.

---

## Whole flows, not just single screens

Export your frames from Figma as one PDF and drop it on the upload page.
DesignEye splits it into its screens, analyses each one, and gives you a single
result covering the whole journey: a clarity score per screen, a chart showing
where attention holds up and where it falls apart, and the weakest screen called
out by name.

Asking for AI suggestions on a flow sends **one request covering every screen**,
not one per screen. That matters twice over: a twelve-screen flow costs one use
of your daily allowance instead of twelve, and because the model sees all the
screens together it can actually compare them — "clarity drops most at screen 5"
is not something twelve separate requests could ever say.

Up to 30 screens and 20MB per upload — a PDF gets double the image ceiling,
because a real multi-screen export is routinely larger than any single mockup
and the PDF itself is never stored, only the pages rasterised out of it.
**Export flow PDF** gives you one report for the whole thing.

A single-image upload works exactly as before; if you upload a multi-page PDF
through the normal route it still analyses page one, but now it tells you how
many screens it found and offers to analyse them all.

---

## Long, scrolling designs

If you export a whole page rather than a single screen, DesignEye scores it **one
screenful at a time** and averages the results, because nobody sees a long page
all at once — and neither can the model.

This matters more than it sounds. Fed a seven-screen page as one image, the model
receives a 14-pixel-wide sliver inside its square input (94% of the frame is
padding), both halves of the Clarity Score hit their limits, and the score is
forced to **0.0 no matter how good the design is**. The same page scored screen by
screen comes out at 39.5, with the weakest screen named.

The results page shows the per-screen breakdown so you can see exactly where
attention holds up and where it falls away. Screens overlap slightly, so nothing
sitting across a fold gets missed. When a design is longer than one screen the
upload page asks which screen size to assume — phone, tablet or desktop — because
that genuinely cannot be inferred from the image (a phone frame exported at 2.5×
is wider than a laptop). See [`docs/DEVIATIONS.md`](docs/DEVIATIONS.md) §19.

---

## Dark designs

The attention model was trained on light interfaces and reads dark ones badly —
on one test layout, flipping only the colour scheme moved the score from 89.3 to
37.4, with the visual density unchanged. On a real screen the same view scored
27.4 dark and 65.4 light.

So when an upload is dark, DesignEye shows the model a **brightened copy** and
scores that. Your design is never altered — the heatmap, the report and every
measurement that doesn't come from the model use your original pixels, and the
results page says plainly when this happened.

It is a workaround, not a cure: the real fix is a model trained on dark
interfaces. Recovery is good but partial (37.4 → 80.0 against a light
equivalent's 89.3), so treat dark-mode scores as slightly conservative. See
[`docs/DEVIATIONS.md`](docs/DEVIATIONS.md) §20.

---

## Phone screens

A phone screen is much taller than it is wide, and the attention model's input is
a **square**. Left alone, a 2.75:1 screenshot reaches the model as an 81-pixel-wide
strip — it genuinely sees your design at 81 pixels across, and the blurry result
drags the score down for reasons that have nothing to do with your design.

Measured across every screen we have, aspect ratio correlated with the Clarity
Score at **-0.73**: desktop screens scored 73–98 while phone screens scored 15–39.
Squashing the *same* pixels to a square shape tripled the focus reading.

So DesignEye now splits a tall upload into near-square bands, runs each through
the model, and reassembles them into one map. Your design is untouched and still
gets a single score — it just gets looked at properly. Measured: a messages list
went from 14.8 to 31.5, a login screen from 38.7 to 49.2.

Desktop-shaped uploads are unaffected, and take exactly the path they always did.
See [`docs/DEVIATIONS.md`](docs/DEVIATIONS.md) §21.

---

## Chrome extension

`extension/` analyses **any live web page**, not just files you export — open a
site, click the toolbar icon, and the same model returns a Clarity Score and a
heatmap. A whole-page capture scrolls the page and stitches the screenfuls into
one tall image, which DesignEye then scores a screenful at a time.

You can create an account from the popup itself, so someone handed the extension
never has to open the web app first. Captures are filed into a project named
after the site they came from, so repeat captures of one site collect together.

Get it from **Chrome Extension** in the app's sidebar: download, unzip, and
load unpacked. Chrome only auto-installs from its own Web Store, so that step is
manual — but once it is in, the page connects it to your account for you, so you
never sign in twice. See [`extension/README.md`](extension/README.md). It needs a DesignEye server it can reach: it defaults to
`http://localhost:8000`, and the address is editable in the popup, so sending it
to someone else means deploying the API first.

The extension id is pinned by the `key` in its manifest, so the API's CORS
allow-list names that exact id rather than opening up to every extension.
See [`extension/README.md`](extension/README.md).

---

## Configuration

`backend/.env` (see `backend/.env.example`). Notable values:

| Variable | Default | Notes |
|---|---|---|
| `DEV_MODE` | `true` | inline inference; no Redis needed |
| `JWT_SECRET` | — | **generate a real one** |
| `STORAGE_BACKEND` | `local` | or `cloudinary` |
| `LLM_PROVIDER` | `mock` | `anthropic` \| `openai` \| `gemini` \| `mock` \| `none` |
| `MAX_UPLOAD_MB` | `10` | images |
| `MAX_PDF_UPLOAD_MB` | `20` | PDFs; the file itself is never stored, only its pages |
| `CORS_ORIGINS` | `http://localhost:3000` | explicit allow-list, never `*` |

### Enabling real AI suggestions

The suggestions module ships working but dormant on a mock provider, so the
feature is demonstrable with no API key. To make it live, edit `.env` only —
**no code change**:

```bash
pip install -r backend/requirements-llm.txt
```

For the **Docker** stack, set `INSTALL_LLM_SDKS=true` in the root `.env` and
rebuild (`docker compose build api worker`) so the SDK is baked into the image.

```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

The provider SDKs are deliberately **not** in `requirements.txt`: they are
imported lazily, only the configured provider is ever constructed, and
`google-generativeai` alone pulls in the entire Google API client stack. If a
provider is configured without its SDK the app logs the fix and falls back to
`unavailable` rather than failing to start.

The LLM never sees your image. It receives only the analytics JSON
(`clarity_score`, `focus_index`, `clutter_index`, `focus_nodes`,
`region_saliency`, `image_meta`) and is instructed never to claim it can see a
specific button, colour, or piece of copy. Responses are validated against a
Pydantic schema with one automatic re-prompt on a parse failure, cached per
result, and rate-limited per user per day. With `LLM_PROVIDER=none` the endpoint
returns `{"suggestions": [], "llm_status": "unavailable"}` and the UI offers a
retry — the rest of the product is unaffected.

---

## Deploying to a host

The API image is **self-contained**: the model weights are baked in by
`COPY app ./app`, so a host that has never seen this repo can run it. The build
context must contain the `.pth` at build time even though git does not track it.

Set these in the root `.env` before `docker compose up -d --build`:

| Variable | Why |
|---|---|
| `JWT_SECRET` | must be a real random value |
| `CORS_ORIGINS` | your frontend origin, comma-separated; never `*` |
| `NEXT_PUBLIC_API_URL` | **compiled into the frontend bundle** — changing it needs `docker compose build frontend` |
| `MONGODB_URI` | e.g. a MongoDB Atlas connection string |
| `STORAGE_BACKEND=cloudinary` | plus the three `CLOUDINARY_*` values |
| `DEV_MODE=false` | routes inference through the Celery worker so the API thread is never occupied by a forward pass |
| `INSTALL_LLM_SDKS=true` | if using a real LLM provider |

**Check your host's request body limit.** A 20MB flow PDF is a large multipart
upload, and several PaaS platforms cap request bodies below that at their edge —
you would get a 413 from the proxy before FastAPI ever sees the file. Uvicorn
itself imposes no limit, so this only bites behind a managed proxy.

`NEXT_PUBLIC_API_URL` is the one that catches people out: Next inlines
`NEXT_PUBLIC_*` at build time, so a running container cannot pick up a new value
from the environment. Rebuild the frontend image when it changes.

With `STORAGE_BACKEND=cloudinary` the API no longer mounts `/storage`, so URLs
stored by a previous local run will 404. Reseed after switching:

```bash
docker compose exec api python -m app.seed --reset
```

Verify the storage backend before trusting it with real data:

```bash
.venv/Scripts/python scripts/verify_cloudinary.py
```

---

## Security

- bcrypt cost 12; plaintext passwords never stored or logged
- 15-minute access tokens, 7-day refresh tokens, HS256
- Logout denylists the refresh `jti` under a Mongo TTL index
- **Tenant isolation**: every asset, result, project, task, and comparison query
  filters on the caller's `user_id`; another user's resource returns **403**, not
  404. Stored files live under a `{user_id}/` prefix.
- Rate limiting on `/auth/login` and `/auth/register` (slowapi)
- CORS from an env allow-list
- Generic errors over the wire, detailed logs server-side, no stack traces leaked
- Upload content type sniffed from magic bytes — the filename is never trusted

---

## Troubleshooting

**`/health` shows `model_loaded: false`** — the weights are missing. Confirm
`backend/app/ml/weights/stage3_ui_best_val.pth` exists; the compose file mounts
that directory read-only into the container.

**`/health` shows `redis: false`** — expected and harmless when `DEV_MODE=true`.
The status stays `ok` because inference runs inline.

**Uploads 400 with "Invalid file format"** — the content is checked, not the
extension. A file renamed to `.png` is still rejected.

**SVG or PDF upload returns "rasterisation is unavailable"** — the native cairo /
PyMuPDF libraries are missing. They are installed in the Docker image; on a bare
local run, export the mockup as PNG instead.

**Heatmap looks offset from the design** — the letterbox crop is being skipped.
Run `python scripts/verify_model.py`; the alignment checks catch exactly this.

**Frontend can't reach the API** — check `NEXT_PUBLIC_API_URL` in
`frontend/.env.local` and that the origin is listed in `CORS_ORIGINS`.

**Data disappeared after `docker compose down`** — it should not. Mongo uses the
named volume `mongo_data`. Verify with `docker volume ls | grep mongo_data`.

---

## What you still have to do manually

1. Place `stage3_ui_best_val.pth` in `backend/app/ml/weights/` (gitignored, ~99 MB).
2. Set a real `JWT_SECRET` in `.env`.
3. *(Optional)* Add an LLM API key to switch suggestions from mock to live.
4. *(Optional)* Add Cloudinary credentials if you want remote storage.

---

## Documentation

- [`docs/PLAN.md`](docs/PLAN.md) — build phases and decisions
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module decomposition and data flow
- [`docs/SCREENS.md`](docs/SCREENS.md) — Figma export → route mapping
- [`docs/DEVIATIONS.md`](docs/DEVIATIONS.md) — **every departure from the SDS, with reasons**
- [`CLAUDE.md`](CLAUDE.md) — conventions and locked decisions
