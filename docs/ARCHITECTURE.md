# Architecture

Three-tier client–server, as the SDS narrowed to in Sprint 1.

---

## Request flow: upload to result

```
1. POST /upload  (multipart)
   ├─ JWT verified               core/deps.py       -> 401 if absent/expired
   ├─ bytes sniffed              services/images.py -> 400 on bad type/size
   ├─ SVG/PDF rasterised         cairosvg / PyMuPDF
   ├─ PNG persisted              services/storage.py  key = {user_id}/uploads/{asset_id}.png
   ├─ MockupAsset inserted       status=pending
   └─ job dispatched             services/jobs.py   -> Celery, or inline if DEV_MODE
   =>  202 Accepted { asset_id, task_id, status }

2. pipeline  (services/pipeline.py) — writes `stage` at each step
   preprocessing -> running_inference -> computing_analytics -> persisting -> complete
   ├─ letterbox 224x224           ml/preprocess.py
   ├─ forward pass (no_grad)      ml/inference.py    singleton model
   ├─ crop letterbox padding      <- correctness-critical
   ├─ rescale to original dims
   ├─ analytics                   services/analytics.py
   ├─ overlay PNG + saliency .npy persisted
   └─ HeatmapResult upserted by asset_id

3. GET /status/{task_id}          polled every 2s by the frontend
   =>  { status, stage, clarity_score, focus_nodes, result_url }

4. GET /results/{asset_id}        full analysis payload
5. POST /results/{id}/suggestions LLM, generated after the fact, never blocking
```

A multi-page PDF can instead go to `POST /upload/batch`, which runs step 1 once
per page and returns N task ids under one `batch_id`. Steps 2-4 are unchanged
per screen; step 5 becomes `POST /batches/{id}/suggestions`, which reviews every
screen in **one** provider call. See "Multi-screen flows" below.

---

## Backend modules

| Module | Responsibility |
|---|---|
| `app/main.py` | app factory, lifespan (DB + model load), CORS, error handler, `/storage` mount |
| `app/config.py` | Pydantic settings, validated enums for storage and LLM provider |
| `app/db/mongo.py` | Motor client lifecycle, collection names, health ping |
| `app/db/indexes.py` | every index, including the refresh-denylist TTL |
| `app/models/domain.py` | document models mirroring the SDS schema tables |
| `app/schemas/` | request/response models; every endpoint is typed |
| `app/core/security.py` | bcrypt hashing, JWT issue/decode, `TokenError` |
| `app/core/deps.py` | `get_current_user`, `owned_or_403` tenant guard |
| `app/core/errors.py` | client-safe error constructors |
| `app/ml/model.py` | **locked** SalGAN architecture — never edit |
| `app/ml/preprocess.py` | letterbox + the inverse transform |
| `app/ml/inference.py` | singleton loader, predict, JET overlay |
| `app/ml/theme.py` | dark-mode detection and the brightened copy fed to the model |
| `app/services/analytics.py` | Clarity Score, Focus Order, region grid |
| `app/services/images.py` | format sniffing, rasterisation, validation |
| `app/services/storage.py` | `StorageService` + local/Cloudinary impls |
| `app/services/pipeline.py` | orchestration, identical under Celery and inline |
| `app/services/jobs.py` | dispatch decision + fallback |
| `app/services/llm.py` | provider-agnostic adapter, schema validation, retry |
| `app/services/pdf.py` | ReportLab result and comparison reports |
| `app/services/scanpath.py` | replay frame compositing, GIF and MP4 encoding, PDF contact sheet |
| `app/services/quota.py` | the daily LLM allowance, shared by both reviewers |
| `app/services/viewports.py` | scroll-aware segmentation: slice a long page, stitch the saliency back |
| `app/api/v1/batches.py` | multi-page fan-out, batch progress, the single batched flow review |
| `app/workers/` | Celery app; loads the model once per worker process |

---

## Why the model is a singleton

`ml/inference.py` holds a module-level `_model` behind a lock. Loading a 99 MB
checkpoint costs ~1.4 s; doing it per request would dominate the 250 ms inference
time by 6×. It is loaded in the FastAPI lifespan and, separately, in Celery's
`worker_process_init` signal.

Celery tasks open their **own** Motor client inside `asyncio.run`, because a
Motor client is bound to the event loop that created it and the API's loop does
not exist in the worker process.

---

## The coordinate contract

The single most error-prone part of this pipeline is coordinate space.

- The model works at **224×224 letterboxed**.
- The API always returns coordinates in **original image pixels**.
- The browser renders at **arbitrary container sizes**.

Backend: `letterbox_with_meta()` returns a `LetterboxMeta` carrying the padding
offsets and content size. `unletterbox_saliency()` crops that padding **before**
resizing to the original dimensions. Reversing that order leaves the heatmap
offset on every non-square upload.

Frontend: `lib/coords.ts` is the only place that converts. `computeFit()` derives
scale and letterbox offsets for the container; `toScreenCoords()` maps a node in;
`toImageCoords()` maps back out. No component does ad-hoc maths.

---

## Analytics

```
focus_raw  = 1 - entropy(saliency on a fixed 224 grid) / log2(N)
focus      = clamp((focus_raw - FOCUS_RAW_MIN) / (FOCUS_RAW_MAX - FOCUS_RAW_MIN), 0, 1)
edge_den   = mean(sobel_magnitude(gray, long side 512) > EDGE_THRESHOLD)
clutter    = clamp(edge_den / EDGE_DENSITY_SCALE, 0, 1)
clarity    = 100 * (FOCUS_WEIGHT * focus + CLUTTER_WEIGHT * (1 - clutter))
```

Both reductions use **fixed sizes** so the score does not change when the same
design is exported at a different resolution — otherwise A/B comparison would be
meaningless. Constants and their calibration live in `docs/DEVIATIONS.md` §4.

Focus Order: light Gaussian blur → iterative non-maximum suppression at
`max(20px, 8% of the long side)` → top 5 peaks ranked by intensity, in original
pixel coordinates, no duplicates.

---

## Scroll-aware scoring

A full-page export has an aspect ratio nobody views at once, and the letterbox
makes that fatal rather than merely inaccurate: at 15:1 the page occupies **6.2%**
of the model's 224×224 input, and the 512px edge grid collapses to 33×512. Both
score terms clamp and the Clarity Score is forced to 0.0 for every such page.

`services/viewports.py` therefore slices a page taller than `SEGMENT_TRIGGER`
viewports into overlapping viewport-shaped tiles **before inference** — the
whole-page saliency map is derived from that sliver, so there is nothing left in
it to partition afterwards. Each tile runs the ordinary single-screen path; the
headline score is the mean, and the per-viewport breakdown is reported alongside.

The tiles' saliency is stitched back into a full-page map with a linear feather
across the overlaps, and Focus Order, the replay and the region grid all read from
that stitched map. This keeps every coordinate in the uploaded page's pixel space,
so nothing downstream needs to know segmentation happened. See
`docs/DEVIATIONS.md` §19.

---

## Multi-screen flows

A multi-page PDF fans out into one `MockupAsset` per page, each tagged with
`batch_id` and `page_number`. Every screen is therefore an ordinary asset:
results, rerun, scanpath, per-screen PDF and the `owned_or_403` tenant guard all
apply with no parallel code path. The `ScreenBatch` document only groups them.

Batch status is **derived on read** by `_derive_status`, not stored, so a worker
that dies mid-batch cannot pin the batch at "processing" forever. The list and
the detail view both call it — when the list read the stored field instead,
finished flows showed as "processing" on the projects page while the detail page
said complete. The list derives it in one aggregation for the whole page rather
than a query per batch.

The flow review is a single provider call for the whole journey. Twelve screens
as twelve calls would exhaust a free daily quota in two uploads, and no call
could compare screens because each would see only its own numbers. The one reply
is fanned back out into a `SuggestionDoc` per screen, so
`GET /results/{id}/suggestions` is unchanged, plus a flow summary on the batch.
Flows longer than `MAX_SCREENS_PER_CALL` are chunked, and the weakest/strongest
screens are recomputed from our own clarity scores rather than trusted to a
model that never saw all the chunks together. See `docs/DEVIATIONS.md` §18.

---

## Frontend structure

```
app/
├─ page.tsx                  landing (server component)
├─ login|register|forgot-password|reset-password/
└─ (app)/                    route group: AuthGuard + AppShell
   ├─ dashboard/  projects/  projects/[id]/
   ├─ upload/     results/[assetId]/
   ├─ batches/[id]/             multi-screen flow view
   └─ compare/    settings/
components/
├─ ui/            Bezel, Button, primitives (design system)
├─ app/           AppShell, HeatmapViewer, ClarityGauge, SuggestionsPanel
└─ marketing/     SiteNav, HeroDemo
lib/              api (axios + refresh queue), auth-store, coords, utils
hooks/use-api.ts  every query and mutation, plus task polling
```

**Auth refresh** is queued: concurrent 401s share one in-flight refresh rather
than minting N tokens.

**Polling** runs at 2 s, eases off after 30 s, and hard-stops at 3 minutes with a
retry affordance.

**Reduced motion** is handled globally by `MotionConfig reducedMotion="user"`.
Components must never branch their rendered *structure* on `useReducedMotion()`:
that value differs between server and client, and the hydration mismatch strands
revealed content at `opacity: 0`.

---

## Data model

```
users ──< projects ──< mockup_assets ──1:1── heatmap_results ──1:1── suggestions
  │                          │
  │                          └──< inference_tasks
  ├──< ab_comparisons (asset_id_a, asset_id_b)
  └──< batches ──< mockup_assets (batch_id, page_number)

refresh_denylist   jti + TTL index
llm_usage          (user_id, day) daily counter
```

A batch does not own its screens exclusively — it groups assets that remain
ordinary assets. That is why every single-screen feature works on them for free.

Indexes: `users.email` unique · `projects.user_id` · `mockup_assets.project_id`
· `mockup_assets.user_id` · `mockup_assets.batch_id` ·
`heatmap_results.asset_id` unique · `inference_tasks.task_id` ·
`batches.batch_id` unique · `batches.(user_id, created_at)` · TTL on
`refresh_denylist.expires_at`.

---

## Deployment

`docker-compose.yml` runs mongo, redis, api, worker, frontend. Mongo uses the
named volume `mongo_data` so data survives `docker compose down`; uploads and
heatmaps use `storage_data` when STORAGE_BACKEND=local.

The model weights ARE baked into the image (`COPY app ./app` includes
`app/ml/weights/`), so the image is self-contained and deployable to a host that
has never seen the repo. The compose bind mount merely overlays them, which lets
you swap a checkpoint without rebuilding. The build context must therefore
contain the .pth at build time even though git does not track it.

The API image installs torch from the CPU wheel index — the default wheel pulls
~2 GB of CUDA payload a CPU container never uses. The frontend builds to a Next
standalone bundle and runs as a non-root user.
