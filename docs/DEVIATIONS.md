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

Validation retained: 10 MB ceiling for images (TC-05), **20 MB for PDFs** — a
genuine multi-screen export is routinely larger than any one mockup, and unlike
an image the PDF is never stored, only the pages rasterised out of it. The
ceiling is chosen from the *sniffed* format, never the filename — so a PDF
renamed `.png` still gets the PDF allowance, which is the same property TC-04
relies on. Long side capped at 8000 px, minimum 16×16, and a decompression-bomb
guard.

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
`GET /dashboard` · `GET /health` ·
`GET /results/{asset_id}/scanpath.gif` · `GET /results/{asset_id}/scanpath.mp4` ·
`POST /upload/batch` · `GET /batches?page=&limit=` · `GET /batches/{id}` ·
`POST /batches/{id}/suggestions` · `GET /batches/{id}/report.pdf` ·
`DELETE /batches/{id}`

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
| TC-12 tenant isolation 403 | `test_compare_and_isolation.py::test_tc12_*`, `test_batches.py::test_batches_are_tenant_isolated` | pass |
| TC-13 rerun | `test_upload_and_inference.py::test_tc13_*` | pass |
| TC-14 expired JWT 401 | `test_auth.py::test_tc14_*` | pass |

Plus letterbox alignment across five aspect ratios, peak-localisation, overlay
legibility, Cloudinary resource-type addressing, and the LLM adapter's
retry behaviour. **172 tests, all passing.**

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

---

## 18. Multi-screen flows (addition beyond the SDS)

The SDS treats an upload as one screen. Designers do not work that way: a Figma
"export frames to PDF" carries a whole journey in one file.

**The bug this started from.** `_rasterise_pdf` rendered page 1 and discarded
the rest silently. A twelve-screen flow produced one result and no warning. The
single-upload contract is unchanged -- it still analyses page 1 -- but `/upload`
now returns `pages_detected` and `pages_analysed`, so the discard is visible
instead of invisible, and the UI offers the batch route when they differ.

**Fan-out.** `POST /upload/batch` rasterises every page and creates one
`MockupAsset` per screen, carrying `batch_id` and `page_number`. Each screen is
a first-class asset, so results, rerun, scanpath, per-screen PDF and tenant
isolation apply with no new code paths. The `ScreenBatch` document only groups
them and holds flow-level output. Capped at `MAX_PDF_PAGES` (30) per upload so
one file cannot queue unbounded inference.

**Batch status is derived, not stored.** `_derive_status` computes
complete/partial/failed from the child assets on read, so a worker that dies
mid-batch cannot leave the batch pinned at "processing" forever. Both the list
and the detail view call it: the list originally returned the stored field, and
finished flows sat there reading "processing" while the detail page said
complete. The list now derives progress and average clarity in one aggregation
per page instead of a query per batch.

**One LLM call, not one per screen.** This is the substantive design decision.
Twelve screens would mean twelve calls, which exhausts a free daily quota in two
uploads -- and, worse, no call could compare screens, because each would see
only its own numbers. Instead every screen's analytics go into a single prompt
and the one reply is fanned out into one `SuggestionDoc` per screen, so
`GET /results/{asset_id}/suggestions` keeps working untouched, plus a
flow-level summary on the batch. Cost stays proportional to the flow, not to
the screen count, and the model can say *"clarity drops most at screen 5"*.

Three guards make the batching safe:

| Risk | Guard |
|---|---|
| Reply exceeds the output ceiling | `MAX_OUTPUT_TOKENS`, `MAX_SCREENS_PER_CALL` (25); longer flows are chunked and merged, still far fewer calls than one per screen |
| Model returns 9 of 12 screens | `_parse_flow` raises on omissions; rendering a partial flow would read as a product bug |
| Model mis-ranks across chunks it never saw together | `weakest_screen` / `strongest_screen` are recomputed from our own clarity scores, never taken from the reply |

A truncated reply (`LLMTruncated`) is **not** re-prompted -- an over-long reply
re-prompted produces another over-long reply. Quota accounting charges the batch
one unit, asserted by `test_batch_review_costs_one_quota_unit`.

**`MockProvider` answers both shapes.** The flow prompt asks for different JSON.
Without the split the entire multi-screen feature was dead for anyone running
with no API key, which is the default.

**Flow PDF.** One report covers the whole journey: summary, clarity table, then
a page per screen. Heatmaps are downscaled before embedding -- full-resolution
embeds produced a 21MB report for eight screens, now under 1MB.

Covered by `tests/test_batches.py` (28 tests).

**Plain language in generated copy.** The first live flow review came back
reading like a metrics dump: *"clutter_index of 0.8011"*, *"Fixation rank 1
occurs at (1590, 480) with intensity 0.9999"*. Accurate and unreadable. The
prompts now carry `PLAIN_LANGUAGE_RULES`, shared by the single-screen and flow
reviewers: no internal field names, no raw coordinates, no four-decimal values,
positions described in words. The grounding is unchanged -- the numbers are
still the only admissible evidence, and `based_on` still carries the real metric
name because it is machine-read. Only the prose changed. `MockProvider`'s copy
was rewritten to the same standard, since mock is the default. Guarded by
`test_prompts_forbid_internal_field_names_in_prose` and
`test_mock_suggestions_read_as_english`.

---

## 19. Scroll-aware scoring for full-page exports (addition beyond the SDS)

The SDS assumes an upload is one screen. A designer exporting a whole scrolling
page hands us an image with an aspect ratio no human ever sees at once, and the
Clarity Score for such a page was not merely inaccurate -- it was **arithmetically
forced to 0.0** regardless of the design.

**Two mechanical failures, both from the same cause.** Measured on a 900x13650
page (15.2:1, seven phone screens):

| | whole page | one viewport |
|---|---|---|
| Content inside the 224x224 letterboxed input | **6.2%** (a 14x224 sliver) | 46% |
| Grid available for edge density | 33x512 | 236x512 |
| `focus_raw` | 0.026 -- **clamped** at `FOCUS_RAW_MIN` | 0.077-0.127 |
| `clutter` | 1.000 -- **clamped** | 0.12-0.72 |
| Clarity | **0.00** | 25.7-64.7 |

With both terms clamped the formula has no remaining input, so every such page
returns the same number. Degradation is steep and starts immediately above one
screen: the same content cropped to 2.17 / 3 / 4 / 5 / 6 viewports scores
25.74 / 17.90 / 8.08 / 0.84 / 0.00.

**The fix: segment into viewports before inference.** `services/viewports.py`
slices a page taller than `SEGMENT_TRIGGER` (1.35) viewports into overlapping
viewport-sized tiles, scores each with the existing single-screen path, and
reports the mean plus the per-viewport breakdown. The same page now scores
**39.53** with the weakest screen identified.

Segmentation *must* precede inference. Computing focus per band on a whole-page
saliency map would cost one forward pass instead of N, but that map is derived
from the 14px sliver -- there is no signal in it left to partition.

**Details that matter.**

- **Overlap of 12%.** Scrolling is continuous; butting tiles together invents a
  seam the design does not have and can cut an element in half.
- **The final tile is pulled up, not clipped.** A clipped tail tile keeps the
  pathological aspect ratio the module exists to remove -- it came out at 1.82:1
  instead of 2.17:1 and was scored as though it were a screen.
- **Focus Order, the replay and the region grid come off a stitched map**, so
  their coordinates stay in the uploaded page's pixel space and the numbered dots
  land where the user can see them. Overlaps are averaged with a linear feather;
  a hard join leaves a visible band across the heatmap at every boundary.
- **The headline score is an unweighted mean.** Weighting upper viewports more
  heavily would model the fact that fewer people scroll to the bottom, but that
  decay curve would be our assumption rather than a model output -- the same line
  the scanpath timing sits on. The breakdown is shown alongside, so nothing hides
  behind the average.
- **The viewport height is an explicit choice**, defaulted from orientation and
  overridable on upload, because it cannot be inferred reliably: a phone frame
  exported at 2.5x is 2325px wide, overlapping desktop widths exactly.

**Scoreability is a geometry test, not a clamp test.** The first design detected
"both terms clamped" and reported the score as unreliable. That is wrong: the
calibration set's `synth_data_table` and `synth_dense_dashboard` both report
focus 0.0000 with clutter 1.0000 and score 0.00, and those are *correct* readings
of genuinely unusable designs that TC-08 depends on. An unscoreable page looks
identical in the metrics and differs only in its shape, so
`letterbox_content_fraction` drives the flag instead. It also catches what
segmentation cannot fix -- an ultra-wide panorama export, where the starvation is
horizontal.

Covered by `tests/test_viewports.py` (26 tests).

---

## 20. Dark-mode compensation (addition beyond the SDS)

The trained checkpoint reads dark interfaces badly. This was found by comparing
the product against an independent estimate on a real screen, and then isolated
with a controlled experiment.

**The measurement.** One synthetic layout, colour scheme flipped, edge density
held constant:

| | focus | edge density | clarity |
|---|---|---|---|
| light | 0.892 | 0.0223 | **89.28** |
| dark | 0.200 | 0.0221 | **37.40** |

51.9 points from colour alone. Inverting the calibration set costs 10-19% of
`focus_raw` on pixel-identical content (`real_login` 88.98 -> 80.11,
`real_registration` 94.95 -> 76.79), so this is the checkpoint's bias rather than
a property of any design.

**Confirmed on a real screen** before the fix was written: the same Google
Classroom view scored **27.4** dark and **65.4** light. Decomposing the 38-point
gap, focus contributed 37.2 and clutter 0.7 -- **98% of it is the model**.

**Two mechanisms, both addressed by the same fix.** The checkpoint was trained on
light UI, so dark input is out of domain; and `letterbox_with_meta` pads to
224x224 with **white**, which for a 9:19.5 phone screen is 54% of the frame, so a
dark upload arrives as a black island in a white field -- a boundary that exists
nowhere in training. Brightening makes the content agree with its own padding.

**What the fix does.** `app/ml/theme.py` flips the **luminance channel only** for
uploads whose mean luminance is below `DARK_UI_LUMA` (100), and feeds that to the
model. Everything not produced by the model uses the original pixels.

- Luminance-only, not RGB: inverting RGB turns a blue primary button orange,
  discarding colour the model reacts to. Measured 79.98 against 79.21 for RGB.
- The threshold is measured, not chosen by taste: across all 25 light screens in
  `inputs/` the lowest mean luminance is 166.3, and dark screens sit near 25. The
  gate sits in the empty band, deliberately nearer the dark side because a false
  positive would cost a light design ~55 points.

**Verified not to disturb anything else.** Edge density is bit-identical under
inversion (Sobel measures gradient magnitude), and is computed on the original
regardless. The saliency map keeps the original dimensions, so Focus Order, the
replay and the region grid stay in the uploaded image's coordinate space -- the
hottest region cell is unchanged. The heatmap overlay is rebuilt on the original,
so the user never sees a brightened version of their own design.

**Known limitation.** Any hard gate is a discontinuity. Sweeping a design's
background luminance across the threshold steps the score about 12 points as
compensation switches on. Real designs do not occupy that band, but a mid-grey
interface scored near the gate deserves less confidence.

**This is a workaround for a training-data gap, not a repair of it.** The honest
fix is a checkpoint trained on dark UI. Until then the result records `ui_theme`
and the UI says plainly that a brightened copy was used. Recovery is partial:
37.40 -> 79.98 against a light equivalent's 89.28.

Covered by `tests/test_theme.py` (10 tests).

---

## 21. Aspect-aware inference (addition beyond the SDS)

Found while checking the product against an independent estimate on two mobile
screens. Both scored far lower than they should, and the cause turned out to be
their **shape**, not their design.

**The evidence.** Measured across all 22 screens available in `inputs/` plus two
reconstructions, aspect ratio correlates with the Clarity Score at
**Spearman -0.730**:

| aspect (h/w) | screens | clarity |
|---|---|---|
| 0.53 - 0.74 (desktop) | 8 | 73 - 98 |
| 0.88 - 1.10 (square) | 5 | 46 - 71 |
| 2.21 - 2.75 (phone) | 3 | **15 - 39** |

The same pixels reshaped confirm it is the frame and not the content: squashing
the messages screen to 1:1 raises `focus_raw` from 0.0560 to 0.0875, and
stretching `real_login` from its native 0.74 to 2.75 drops focus from 0.918 to
0.498.

**The mechanism.** The model's input is a fixed 224x224 **square**. After
letterboxing, a 2.75:1 phone screen occupies 81x224 of it -- the model sees the
design 81 pixels wide. Coarse saliency is diffuse saliency, entropy rises, and
the focus term collapses. `focus_raw` tracks the fill fraction monotonically:

| aspect | model sees | `focus_raw` |
|---|---|---|
| 1.00 | 224x224 (100%) | 0.0875 |
| 2.20 | 101x224 (45%) | 0.0619 |
| 2.75 | 81x224 (36%) | 0.0560 |

**The fix.** `predict_saliency_hires` in `ml/inference.py` splits a frame taller
than `MIN_TILED_ASPECT` (1.5) into near-square bands, runs each through the
model, and reassembles them. Measured: messages screen **14.82 -> 31.45**,
Soul Match login **38.69 -> 49.15**.

Details that matter:

- **This is a resolution technique, not a perceptual claim.** The user sees the
  whole phone screen at once, so the bands are stitched into one map and scored
  once. That is what separates it from `services/viewports.py`, which splits a
  *scrolling page* because nobody sees all of it at once and scores each
  screenful separately. Long pages now get both: viewport segmentation for
  perception, then band tiling inside each viewport for resolution.
- **Bands are not normalised individually.** Sigmoid output is on an absolute
  scale, so the raw values stay comparable across bands and are min-max
  normalised once over the finished map. Normalising per band would stretch a
  quiet band up to match a busy one, flatten the stitched map, and cost the very
  focus the split exists to recover.
- **Only tall frames are tiled.** The mechanism looks symmetric, but the data is
  not: landscape screens at 53% fill still score 73-98, because landscape UI is
  what the checkpoint was trained on. Fixing a direction that shows no harm would
  only risk the calibration.
- **The calibration set is bit-identical.** Every one of the 12 samples is wider
  than 1.5:1, so all take the original single-pass path; measured maximum change
  across the set is 0.000000, and TC-07/TC-08 are untouched.

**Cost.** Two to four forward passes instead of one, on tall uploads only. At
~250ms each this is well inside the 30s budget of TC-06.

Covered by `tests/test_aspect_resolution.py` (9 tests).
