# DesignEye

Predictive visual-attention analysis for static UI mockups.

Upload a design and a pre-trained SalGAN-style saliency model predicts where
human eyes will land — returning an attention heatmap, a Clarity Score (0–100),
a ranked Focus Order, grounded design suggestions, A/B comparison, and PDF
export. **No users, no traffic, no tracking script required**, which is what
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

74 tests covering SDS test cases TC-01…TC-14, plus letterbox alignment, tenant
isolation across every owned resource, token expiry, and the LLM adapter's
retry-once behaviour. Mapping table in [`docs/DEVIATIONS.md`](docs/DEVIATIONS.md) §14.

Tests run against a real MongoDB and the real model — a mocked model would not
prove that TC-07/TC-08 actually land in their score bands.

---

## Configuration

`backend/.env` (see `backend/.env.example`). Notable values:

| Variable | Default | Notes |
|---|---|---|
| `DEV_MODE` | `true` | inline inference; no Redis needed |
| `JWT_SECRET` | — | **generate a real one** |
| `STORAGE_BACKEND` | `local` | or `cloudinary` |
| `LLM_PROVIDER` | `mock` | `anthropic` \| `openai` \| `gemini` \| `mock` \| `none` |
| `MAX_UPLOAD_MB` | `10` | |
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
