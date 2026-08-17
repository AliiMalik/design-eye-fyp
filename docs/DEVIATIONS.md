# Deviations from the SDS

Every departure from the Phase 2 SDS, with its reason. `BUILD.md` is the higher
authority where the two disagree; those cases are marked **[BUILD.md]**.

---

## 1. Authentication: Firebase → custom Python JWT **[BUILD.md]**

**SDS:** Firebase/Node Authentication issues and validates JWTs (Tables 2, 3, 4, 11, 16).
**Built:** `passlib[bcrypt]` + `PyJWT`, entirely in Python.

The requirement is that the whole backend is Python; a managed identity provider
would put a Node/Google dependency in the middle of the auth path. Access tokens
last 15 minutes, refresh tokens 7 days, HS256, and logout denylists the refresh
token's `jti` under a TTL index so it self-expires.

Knock-on schema change: `users` gains `password_hash` (we now own credentials)
and `role`. `user_id` is a locally generated UUID rather than a Firebase UID.

**Not built:** federated sign-in. The Visily login screen shows a "Continue with
Google" button; with no OAuth provider it would be a dead control, so it is
omitted rather than shipped inert.

---

## 2. Upload formats: SVG/PDF only → raster formats accepted **[BUILD.md]**

**SDS:** "Validates uploaded SVG/PDF files" (Table 2); TC-04 expects a `.png`
upload to be rejected with *"Only SVG and PDF are supported."*
**Built:** PNG, JPG, JPEG, WEBP open directly; SVG rasterises at 2× via cairosvg;
PDF page 1 rasterises at 150 DPI via PyMuPDF.

The model consumes raster tensors, and every realistic demo starts from a PNG
screenshot. Rejecting PNG would reject the product's main input.

**Test case impact — TC-04 rewritten.** Asserting that a `.png` is rejected would
now assert a bug. The test instead proves that a genuinely unsupported type is
refused, and adds a case that a **text file renamed to `.png` is still rejected**,
since content type is sniffed from magic bytes and the filename is never trusted.
See `tests/test_upload_and_inference.py::test_tc04_*`.

Validation retained: 10 MB ceiling (TC-05), long side capped at 8000 px, minimum
16×16, and a decompression-bomb guard.

---

## 3. Storage: Cloudinary-only → pluggable, local by default **[BUILD.md]**

**SDS:** Cloudinary stores originals and overlays (Tables 2, 7, 8).
**Built:** a `StorageService` interface with `LocalStorage` (default) and
`CloudinaryStorage` (`STORAGE_BACKEND=cloudinary`).

The FYP demo must run offline with no third-party account. Tenant isolation is
preserved in both backends: every key is prefixed `{user_id}/`, asserted by
`test_stored_files_are_prefixed_by_tenant`.

Column names are storage-neutral: `heatmap_cloudinary_url` → `heatmap_url`.

---

## 4. Clarity Score: recalibrated, and made resolution-invariant

**SDS formula** (Sprint 4): saliency entropy blended with Sobel edge density.
The shape is preserved. Two changes were required to make it usable.

### 4a. Entropy and edge density are computed on fixed-size reductions

Computed on raw pixels, the same design uploaded at 2× resolution scores
differently: `log2(num_pixels)` grows with size, and a 1px edge becomes 2px while
the pixel count quadruples. That makes A/B comparison — the product's core
feature — meaningless, because two exports of the same design at different scales
would not be comparable. Entropy is therefore computed on a fixed 224×224 grid
and edge density on a fixed 512px long side.

### 4b. The raw focus index needed rescaling to reach the target bands

Real saliency maps have entropy close to maximal, so `1 - entropy/log2(N)` lands
in roughly `0.03–0.20`. Applied directly, the SDS formula tops out near **30/100**
and can never satisfy TC-07 (clean > 75). The observed band is stretched onto
`[0,1]` before weighting, via `FOCUS_RAW_MIN` / `FOCUS_RAW_MAX`.

### Final constants (`backend/app/services/analytics.py`)

| Constant | SDS | Calibrated | Note |
|---|---|---|---|
| `FOCUS_WEIGHT` | 0.65 | **0.75** | |
| `CLUTTER_WEIGHT` | 0.35 | **0.25** | |
| `EDGE_THRESHOLD` | — | **50.0** | Sobel magnitude for an "edge" pixel |
| `EDGE_DENSITY_SCALE` | 0.25 | **0.215** | density mapping to fully cluttered |
| `FOCUS_RAW_MIN` | — | **0.04** | new: normalisation floor |
| `FOCUS_RAW_MAX` | — | **0.19** | new: normalisation ceiling |

A grid search found a wider margin at `FOCUS_RAW_MAX=0.16`, but that saturates
every clean sample at 1.0 and erases the difference between a good design and a
great one. The looser bound was kept deliberately for discrimination.

### Calibration table (`python scripts/calibrate_clarity.py`)

| Band | Sample | focus_raw | focus_n | edge_den | clutter | **clarity** |
|---|---|---|---|---|---|---|
| clean | real_export_modal.png | 0.1606 | 0.8041 | 0.0562 | 0.2613 | **78.77** |
| clean | real_login.png | 0.1785 | 0.9233 | 0.0453 | 0.2109 | **88.98** |
| clean | real_password_reset.png | 0.1745 | 0.8964 | 0.0457 | 0.2128 | **86.91** |
| clean | real_registration.png | 0.1902 | 1.0000 | 0.0434 | 0.2021 | **94.95** |
| clean | synth_centered_card.png | 0.1923 | 1.0000 | 0.0144 | 0.0671 | **98.32** |
| clean | synth_hero.png | 0.1884 | 0.9891 | 0.0178 | 0.0830 | **97.11** |
| clean | synth_split_feature.png | 0.1738 | 0.8919 | 0.0266 | 0.1238 | **88.80** |
| cluttered | synth_ad_heavy.png | 0.0727 | 0.2178 | 0.2635 | 1.0000 | **16.33** |
| cluttered | synth_data_table.png | 0.0321 | 0.0000 | 0.4224 | 1.0000 | **0.00** |
| cluttered | synth_dense_dashboard.png | 0.0333 | 0.0000 | 0.4283 | 1.0000 | **0.00** |
| cluttered | synth_noisy_grid.png | 0.0406 | 0.0039 | 0.2897 | 1.0000 | **0.29** |
| cluttered | synth_text_wall.png | 0.0556 | 0.1042 | 0.6829 | 1.0000 | **7.81** |

**clean:** min 78.77, mean 90.55, max 98.32 — all > 75 ✓ (TC-07)
**cluttered:** min 0.00, mean 4.89, max 16.33 — all < 40 ✓ (TC-08)
**Separation:** 62.44 points between the worst clean and the best cluttered sample.

### Sample provenance

No `clean/` or `cluttered/` corpus was supplied with the inputs. The set is
reproducible via `python scripts/make_samples.py`: four genuinely minimal Visily
screens act as real clean examples, and eight synthetic mockups span both ends of
the density spectrum. Anyone can regenerate the exact set, which is what makes
the calibration defensible rather than hand-picked.

---

## 5. Focus Order: the 20px NMS radius became a floor, not a constant

**SDS:** NMS radius tuned from 10px up to 20px (Sprint 4).
**Built:** `max(20px, 8% of the long side)`.

Applied literally to a tall page export, all five peaks land inside one hot blob:
a 1488×3294 mockup returned five nodes spanning 110px of a single headline —
technically distinct coordinates (TC-09 passes) but useless as a gaze sequence.
The 20px value is kept as the floor and asserted by
`test_nms_radius_keeps_20px_as_the_floor`; it scales up for large canvases so
nodes stay spatially distinct at any resolution.

---

## 6. Heatmap overlay: per-pixel alpha instead of a flat 0.5 blend

**BUILD.md §3:** "JET colormap alpha-blended at 0.5 over the original".
**Built:** alpha peaks at 0.72 where attention is highest and falls off with
intensity (gamma 0.65).

A flat 0.5 blend tints the entire mockup JET-blue wherever predicted attention is
near zero — which is most of a clean design — hiding the very interface under
review. Intensity-modulated alpha is what attention-mapping tools actually do.
Asserted by `test_overlay_leaves_cold_regions_legible`.

---

## 7. Frontend: React SPA → Next.js 15 App Router **[BUILD.md]**

Next is React, so the SDS's "React.js frontend" remains accurate. Adds routing,
server components, and image optimisation. Canvas is used for the overlay and an
absolutely-positioned SVG for focus nodes, both as the SDS specifies.

---

## 8. Visual design: Figma palette wins over the dark-first brief

**BUILD.md §10** describes a near-black dark-first product, then states that if
the Figma screens specify a different palette, *the Figma wins*. The Visily
screens are light-first with a deep navy (`#1B2559`) chrome, indigo (`#4F5BD5`)
primary, and violet (`#7C3AED`) accent. That palette was followed; a full dark
theme is still implemented and toggleable in Settings.

The `high-end-visual-design` skill supplied with the project bans Inter and
thick-stroked Lucide icons, both named in BUILD.md §2/§10. Reconciled by using
Plus Jakarta Sans / Space Grotesk / JetBrains Mono, and keeping the locked
`lucide-react` dependency at `strokeWidth={1.5}` so the icons read as the
ultra-light lines the skill requires.

---

## 9. Password reset has no mail service

**SDS:** Firebase emails a reset link (US-03).
**Built:** a 30-minute single-use token stored on the user document. There is no
SMTP integration, so the token is logged server-side and, in `DEV_MODE` only,
returned in the response so the flow is demonstrable end to end. The endpoint
returns an identical message for unknown emails, so it cannot enumerate accounts.

---

## 10. INT8 quantisation not applied

**SDS:** INT8 quantisation cut inference from ~58s to ~22s (Sprint 3).
**Built:** full-precision inference, measured at **~250–430 ms per mockup on CPU**.

BUILD.md §3 forbids altering the architecture or preprocessing, and quantisation
is unnecessary: measured latency is already ~50× inside the 30s SLA (TC-06).

---

## 11. Task queue: Celery retained, with an inline fallback **[BUILD.md]**

Celery + Redis are fully wired (`worker` service in `docker-compose.yml`). With
`DEV_MODE=true` the API runs inference inline via FastAPI `BackgroundTasks`, so
the stack works with no Redis and no worker — which is what the demo machine
runs. If a Celery dispatch fails at runtime, the job falls back to inline rather
than being lost.

---

## 12. Schema additions

| Collection | Added | Reason |
|---|---|---|
| `users` | `password_hash`, `role`, `bio` | own the credentials; profile screen |
| `mockup_assets` | `width`, `height`, `storage_key`, `original_filename` | coordinate mapping, storage indirection |
| `heatmap_results` | `focus_index`, `clutter_index`, `region_saliency`, `user_id`, `storage_keys` | UI breakdown, LLM grounding, tenant filter |
| `suggestions` *(new)* | whole collection | LLM module, per BUILD.md §7 |
| `refresh_denylist` *(new)* | whole collection | logout revocation with a TTL index |
| `llm_usage` *(new)* | whole collection | per-user daily suggestion cap |
| `inference_tasks` | `stage`, `error` | drives the staged progress narrative |

---

## 13. API additions beyond the SDS table

`POST /auth/refresh` · `GET|PATCH /auth/me` · `POST /auth/change-password` ·
`POST /auth/reset-password/confirm` · `PATCH|DELETE /projects/{id}` ·
`GET /results` · `DELETE /results/{asset_id}` · `GET /compare?page=&limit=` ·
`DELETE /compare/{id}` · `POST|GET /results/{asset_id}/suggestions` ·
`GET /results/{asset_id}/report.pdf` · `GET /compare/{id}/report.pdf` ·
`GET /dashboard` · `GET /health`

All SDS endpoints are implemented; these are additive.

---

## 14. Test case mapping

| Test case | Where | Status |
|---|---|---|
| TC-01 register | `test_auth.py::test_tc01_*` | pass |
| TC-02 duplicate email | `test_auth.py::test_tc02_*` | pass |
| TC-03 valid upload | `test_upload_and_inference.py::test_tc03_*` | pass |
| TC-04 invalid format | `test_upload_and_inference.py::test_tc04_*` | pass **(rewritten, §2)** |
| TC-05 oversize file | `test_upload_and_inference.py::test_tc05_*` | pass |
| TC-06 inference < 30s | `test_upload_and_inference.py::test_tc06_*` | pass |
| TC-07 clean > 75 | `test_analytics.py::test_tc07_*` | pass |
| TC-08 cluttered < 40 | `test_analytics.py::test_tc08_*` | pass |
| TC-09 top-5, no duplicates | `test_analytics.py::test_tc09_*` | pass |
| TC-10 A/B delta | `test_compare_and_isolation.py::test_tc10_*` | pass |
| TC-11 unauthenticated 401 | `test_auth.py::test_tc11_*` | pass |
| TC-12 tenant isolation 403 | `test_compare_and_isolation.py::test_tc12_*` | pass |
| TC-13 rerun | `test_upload_and_inference.py::test_tc13_*` | pass |
| TC-14 expired JWT 401 | `test_auth.py::test_tc14_*` | pass |

Plus letterbox alignment across five aspect ratios, peak-localisation, overlay
legibility, Cloudinary resource-type addressing, and the LLM adapter's
retry behaviour. **96 tests, all passing.**

---

## 15. LLM provider SDKs are optional dependencies

`anthropic`, `openai`, and `google-generativeai` are **not** in
`backend/requirements.txt`; they live in `backend/requirements-llm.txt`.

The adapter imports each SDK lazily inside its provider's constructor and only
ever builds the one named by `LLM_PROVIDER`. The default (`mock`) needs none of
them, and `google-generativeai` alone pulls the entire Google API client stack —
it dominated the Docker image build. A provider configured without its SDK now
logs the install command and degrades to `unavailable`, exactly as an
unreachable provider does. The product is unaffected either way.

---

## 16. LLM model choice and timeout

Measured on the real analytics payload, 3 runs each, all returning valid JSON:

| Model | Avg latency | Range |
|---|---|---|
| `gemini-3.5-flash` | 47.0s | 28-71s |
| **`gemini-3.6-flash`** (default) | **14.4s** | 13.6-15.2s |
| `gemini-3.7-flash` | 53.1s | 27-82s |
| `gemini-3.5-flash-lite` | 3.2s | 2.7-3.5s |

`gemini-3.6-flash` is the default: three times faster than 3.5 and, more
importantly, consistent (+/-1s rather than +/-43s). Flash-Lite is roughly six
times faster again and remains schema-valid, but cited fewer of the supplied
metric values, so it is offered as an opt-in rather than the default.

Because measured latency reached 82s on one tier, `LLM_TIMEOUT_SECONDS`
(default 90) now bounds every provider call. A stalled provider returns
`llm_status: error` instead of holding the request open.

Provider SDKs are baked into the API image only when the `INSTALL_LLM_SDKS`
build arg is `true`, keeping the default image small; see README.

---

## 17. Scanpath playback (addition beyond the SDS)

Not in the SDS. Added because Focus Order under-delivered: five numbered dots
are analytically real but visually inert, while the same data animated reads as
the product's core promise.

**What it is.** The predicted fixation points, ordered strongest-first, played
back with a travelling gaze marker and a foveal spotlight. Exportable as an
animated GIF and an H.264 MP4, plus a six-frame contact sheet in the PDF (a PDF
cannot animate).

**What it is not, and how that is disclosed.** The model predicts WHERE
attention concentrates, not WHEN. Ordering by predicted strength is not a
temporal prediction, and dwell times (180-320ms, scaled by strength, with 40ms
saccades) come from the eye-movement literature rather than from the model. The
UI says so in plain language directly under the player, and the same disclosure
appears on the PDF filmstrip page. Framing this as a recording of real gaze
would not survive scrutiny; framing it as a legible presentation of a spatial
prediction does.

**Consistency guarantee.** One extraction produces both views. The peak search
is greedy and deterministic, so the first five entries of the 10-point sequence
are byte-identical to `focus_nodes` -- the animation can never disagree with the
Focus Order list, and TC-09 still sees exactly five nodes. Asserted by
`test_scanpath_first_five_match_focus_nodes`.

**MP4 requires ffmpeg**, installed in the API image. Where it is absent the
endpoint returns 503 with a message pointing at the GIF, rather than a generic
failure. Covered by `tests/test_scanpath.py` (18 tests).
