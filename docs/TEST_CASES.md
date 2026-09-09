# Test Cases — DesignEye

Complete test suite for the system, organised by module. Extends SDS Table 13
(TC-01…TC-14), which is preserved verbatim in §16 with a traceability matrix.

---

## How to read this

| Column | Meaning |
|---|---|
| **ID** | `TC-<MODULE>-<n>`. SDS ids keep their original `TC-01` form. |
| **Scenario** | What is being done, precisely enough to repeat. |
| **Expected result** | The observable outcome. A test with a vague expected result is not a test. |
| **P** | Priority — **C**ritical (demo-blocking), **H**igh, **M**edium, **L**ow. |
| **Type** | **A** = automated (name given), **M** = manual, **A+M** = automated core, manual UI check. |

**Environment.** Docker stack up (`docker compose up -d`), demo account seeded
(`python -m app.seed --reset`), `DEV_MODE=true`, `LLM_PROVIDER=mock`,
`STORAGE_BACKEND=local`. Automated tests run with `MONGODB_DB=designeye_test`.

**Run the automated suite:**

```bash
cd backend && ../.venv/Scripts/python -m pytest -q
```

```bash
cd extension && node test/popup.test.mjs && node test/external.test.mjs && node test/zip.test.mjs
```

```bash
python scripts/verify_model.py
```

**Test data.** `inputs/samples/clean/` (7 images), `inputs/samples/cluttered/`
(5 images), `inputs/screens/` (13 real Visily exports). Synthetic fixtures are
generated inside the suite by `make_png()` and `make_pdf()` in the test helpers.

---

## 1. Authentication and session — `TC-AUTH`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-AUTH-01 | Register with a valid email and password ≥ 8 chars | 201; access + refresh token returned; user object includes `user_id`, `email`, `role: designer` | C | A `test_tc01_register_valid_credentials` |
| TC-AUTH-02 | Register with an email already in use | 409 "Email already in use."; no duplicate document created | C | A `test_tc02_duplicate_email_rejected` |
| TC-AUTH-03 | Register with the same email in different case (`A@b.com` vs `a@b.com`) | 409; email is normalised to lowercase before the uniqueness check | H | A `test_tc02_duplicate_is_case_insensitive` |
| TC-AUTH-04 | Register with a password under 8 characters | 422 validation error; no account created | H | A `test_weak_password_rejected` |
| TC-AUTH-05 | Register with a malformed email (`notanemail`) | 422; `email-validator` rejects it | M | M |
| TC-AUTH-06 | Register with a password over 72 bytes | Rejected cleanly, not silently truncated by bcrypt | M | M |
| TC-AUTH-07 | Log in with correct credentials | 200; new token pair; `last_login_at` updated | C | A `test_login_success_and_wrong_password` |
| TC-AUTH-08 | Log in with a wrong password | 401 "Invalid email or password." | C | A `test_login_success_and_wrong_password` |
| TC-AUTH-09 | Log in with an unregistered email | 401 with the **identical** message and shape as a wrong password — no account enumeration | H | A `test_login_unknown_email_is_indistinguishable` |
| TC-AUTH-10 | Inspect the stored user document after registering | `password_hash` is a bcrypt digest; the plaintext appears nowhere in the document or the logs | C | A `test_password_never_stored_in_plaintext` |
| TC-AUTH-11 | Exchange a valid refresh token at `/auth/refresh` | 200; a fresh access token; `expires_in` = 900 s | H | A `test_refresh_rotates_access_token` |
| TC-AUTH-12 | Send a refresh token to an endpoint expecting an access token | 401 — token `type` claim is checked, not just the signature | H | A `test_refresh_token_cannot_be_used_as_access_token` |
| TC-AUTH-13 | Log out, then reuse the same refresh token | 401 "This session has been revoked."; `jti` is in the denylist | H | A `test_logout_denylists_the_refresh_token` |
| TC-AUTH-14 | Verify the denylist TTL index exists on `refresh_denylist.expires_at` | Index present with `expireAfterSeconds: 0`; revoked entries self-expire | M | M |
| TC-AUTH-15 | Call any protected endpoint with an expired access token | 401; the UI prompts a re-login | C | A `test_tc14_expired_token_returns_401` |
| TC-AUTH-16 | Call a protected endpoint with a malformed or wrongly-signed JWT | 401; no stack trace leaked | H | A `test_tc14_malformed_and_wrongly_signed_tokens_rejected` |
| TC-AUTH-17 | Call `/results`, `/projects`, `/dashboard`, `/compare` with no `Authorization` header | 401 on every one | C | A `test_tc11_unauthenticated_requests_rejected` |
| TC-AUTH-18 | Exceed the auth rate limit (>10 requests/minute to `/auth/login`) | 429 Too Many Requests | H | A `test_auth_endpoints_are_rate_limited` |
| TC-AUTH-19 | Request a password reset for a registered email | 200; token stored **as a SHA-256 digest**, never in plaintext | H | A `test_reset_token_is_never_stored_in_the_clear` |
| TC-AUTH-20 | Request a reset for an unregistered email | Identical 200 reply, `reset_token: null` — cannot enumerate accounts | H | A `test_reset_for_unknown_email_does_not_leak` |
| TC-AUTH-21 | Complete a reset with a valid token, then log in with the new password | Reset succeeds; new password works; old password returns 401 | C | A `test_password_reset_flow` |
| TC-AUTH-22 | Replay the same reset token a second time | 400 "invalid or has already been used" | H | A `test_reset_is_single_use` |
| TC-AUTH-23 | Use a reset token older than 30 minutes | 400 "This reset link has expired." | M | M |
| TC-AUTH-24 | Reset the password, then use an access/refresh token issued **before** the reset | 401 on both — `tokens_valid_from` revokes every earlier session | H | A `test_reset_revokes_sessions_issued_beforehand` |
| TC-AUTH-25 | Change password while signed in, then reuse the earlier token | 401 — change-password revokes prior sessions too | H | M |
| TC-AUTH-26 | Update display name and bio via `PATCH /auth/me` | 200; changes persist and appear in the header and settings page | M | A `test_me_and_profile_update` |
| TC-AUTH-27 | Upload a profile picture | 200; stored as a square thumbnail under `{user_id}/avatar/{hash}.png` | M | A `test_stored_avatar_is_a_square_thumbnail` |
| TC-AUTH-28 | Upload a PDF / corrupt bytes / empty file as an avatar | 400 with a message naming the accepted formats | M | A `test_rejects_what_is_not_a_picture` |
| TC-AUTH-29 | Re-upload the identical avatar image | Kept, not deleted — the content-hash key guards the replace path | L | A `test_reuploading_the_same_image_keeps_it` |
| TC-AUTH-30 | Replace an avatar with a different image | Previous object removed from storage | L | A `test_replacing_drops_the_previous_object` |
| TC-AUTH-31 | Delete the avatar | 200; `avatar_key` cleared; object gone from storage | L | A `test_delete_clears_it` |
| TC-AUTH-32 | Sign in on the web app, refresh the browser | Session restored from `localStorage`; no re-login required | H | M |
| TC-AUTH-33 | Let the access token expire, then edit the profile on the settings page | Request refreshes transparently and succeeds — `/auth/me` is **not** excluded from refresh | H | M |
| TC-AUTH-34 | Trigger several concurrent 401s (open dashboard + results + projects together) | Exactly **one** refresh request is issued; the rest queue behind it | M | M |

---

## 2. Upload and file validation — `TC-UP`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-UP-01 | Upload a valid PNG mockup | 202 Accepted; `asset_id`, `task_id`, `status: pending` returned | C | A `test_tc03_upload_valid_mockup` |
| TC-UP-02 | Upload JPG, JPEG, WEBP | All accepted — the SDS's SVG/PDF-only rule is a documented deviation (§2) | C | A `test_tc04_raster_formats_are_accepted` |
| TC-UP-03 | Upload an SVG | Rasterised at 2× and analysed; or a clear "rasterisation unavailable" message if cairo is missing | M | M |
| TC-UP-04 | Upload a single-page PDF | Page 1 rasterised at 150 DPI and analysed | H | M |
| TC-UP-05 | Upload a `.txt` renamed to `.png` | 400 "Invalid file format." — content is sniffed from magic bytes, the filename is never trusted | C | A `test_tc04_extension_is_not_trusted` |
| TC-UP-06 | Upload an unsupported real format (e.g. GIF, BMP) | 400 naming the supported formats | H | A `test_tc04_unsupported_format_rejected` |
| TC-UP-07 | Upload an empty (0-byte) file | 400 "Uploaded file is empty." | H | A `test_empty_file_rejected` |
| TC-UP-08 | Upload an image over 10 MB | 400 "File size exceeds 10MB limit." | C | A `test_tc05_oversize_file_rejected` |
| TC-UP-09 | Upload a PDF between 10 MB and 20 MB | Accepted — PDFs get the higher ceiling | H | A `test_batch_accepts_a_pdf_over_the_image_ceiling` |
| TC-UP-10 | Upload a PDF over 20 MB | 400 naming the 20 MB limit | H | A `test_batch_rejects_a_pdf_over_the_pdf_ceiling` |
| TC-UP-11 | Upload an image whose **short** side exceeds 8000 px | 400 explaining the shorter side must be under 8000 px | M | M |
| TC-UP-12 | Upload an image whose long side exceeds 30000 px | 400 explaining it is too long to analyse | M | M |
| TC-UP-13 | Upload a legitimately long page (e.g. 900 × 13650) | **Accepted** — the long axis is deliberately not capped at 8000 | H | A `test_a_long_page_is_not_rejected_for_being_long` |
| TC-UP-14 | Upload an image smaller than 16 × 16 | 400 "Image is too small to analyse." | L | M |
| TC-UP-15 | Upload a PNG with transparency | Alpha flattened onto **white**, not black — a dark composite would falsely trigger dark-mode compensation | M | A `test_transparency_flattens_to_white_not_black` |
| TC-UP-16 | Upload without selecting a project | Asset filed into a "My Uploads" project, created on first use | M | A `test_upload_creates_default_project_when_none_given` |
| TC-UP-17 | Upload into an explicitly chosen project | Asset carries that `project_id` | M | A `test_upload_into_explicit_project` |
| TC-UP-18 | Upload into another user's `project_id` | 403 Forbidden | C | A `test_tc12_isolation_across_every_owned_resource` |
| TC-UP-19 | Upload passing an explicit screen size (`phone` / `tablet` / `desktop`) | Accepted; the choice is stored on the asset so a rerun reproduces it | H | A `test_upload_accepts_an_explicit_screen_size` |
| TC-UP-20 | Upload passing an unknown screen size (`watch`) | 400 listing the valid options | M | A `test_upload_rejects_an_unknown_screen_size` |
| TC-UP-21 | Upload a multi-page PDF through the **single** upload route | Page 1 analysed; response reports the true `pages_detected` so the UI can offer batch analysis | H | A `test_single_upload_reports_extra_pages` |
| TC-UP-22 | Upload a single image | `pages_detected: 1`, `pages_analysed: 1` | M | A `test_single_image_upload_reports_one_page` |
| TC-UP-23 | Two different users each create a project titled "Landing" | Both succeed; project titles are scoped per user | M | A `test_project_titles_are_per_user` |
| TC-UP-24 | Drag and drop a file onto the upload zone | Zone highlights on drag-over; file is accepted on drop | H | M |
| TC-UP-25 | Click the zone and browse for a file | Native file dialog opens filtered to supported types | H | M |

---

## 3. Paste-to-analyse (web app) — `TC-PASTE`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-PASTE-01 | Take a screenshot, open `/upload`, press Ctrl/⌘+V without clicking anything | Screenshot is staged with a preview; drop zone flashes; toast "Screenshot pasted." | C | M |
| TC-PASTE-02 | Inspect the staged filename | Stamped `screenshot-YYYY-MM-DD-HHMMSS.png`, never a bare `image.png` | H | M |
| TC-PASTE-03 | Click "Paste screenshot" with an image on the clipboard | Same result as Ctrl+V | H | M |
| TC-PASTE-04 | Click "Paste screenshot" with **no** image on the clipboard | Toast: "No image on the clipboard. Take a screenshot, then try again." | M | M |
| TC-PASTE-05 | Click "Paste screenshot" in a browser that blocks the Clipboard API (or deny the prompt) | Toast points at the Ctrl+V shortcut instead of dead-ending | M | M |
| TC-PASTE-06 | Copy **text** and press Ctrl+V on the upload page | Nothing is staged; the keystroke is not swallowed; normal text paste still works in fields | H | M |
| TC-PASTE-07 | Paste an image larger than 10 MB | Rejected with the same size message as a browsed file | H | M |
| TC-PASTE-08 | Paste, then upload | Analysis runs identically to a browsed file; result page shows the stamped filename | C | M |
| TC-PASTE-09 | Paste a tall screenshot (e.g. a phone screen) | The screen-size question appears, exactly as for a browsed tall image | M | M |
| TC-PASTE-10 | Paste a second screenshot while one is already staged | The new one replaces it | L | M |
| TC-PASTE-11 | Press Ctrl+V while an analysis is already running | Ignored — the picker is gone and no new file is staged | L | M |
| TC-PASTE-12 | Open the page on macOS | The hint reads ⌘ V, not Ctrl V; no hydration warning in the console | L | M |

---

## 4. Inference pipeline and task status — `TC-INF`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-INF-01 | Upload and poll `/status/{task_id}` to completion | Terminal status `complete` within 30 s for a single screen | C | A `test_tc06_inference_completes_within_sla` |
| TC-INF-02 | Observe `stage` while polling | Progresses `preprocessing → running_inference → computing_analytics → persisting → complete` | H | A `test_status_reports_stage_progression` |
| TC-INF-03 | Poll another user's `task_id` | 403 Forbidden | C | A `test_tc12_isolation_across_every_owned_resource` |
| TC-INF-04 | Fetch the result after completion | Full payload: heatmap URL, clarity score, focus nodes, region grid, scanpath timeline | C | A `test_analytics_surface_through_the_api` |
| TC-INF-05 | Rerun analysis on a stored asset without re-uploading | New `task_id`; result replaced in place; asset unchanged | H | A `test_tc13_rerun_without_reupload` |
| TC-INF-06 | Rerun when the stored file is missing from storage | 400 "no longer available" — not a 500 | M | M |
| TC-INF-07 | Verify the model loads once per process | `/health` reports `model_loaded: true`; load time is not paid per request | H | M |
| TC-INF-08 | Check `/health` fields | `status`, `model_loaded`, `db`, `redis`, `version`, `model_info` all present | M | A `test_health_reports_every_field` |
| TC-INF-09 | `/health` with `DEV_MODE=true` and Redis down | `status: ok`, `redis: false` — inline inference does not need the broker | M | M |
| TC-INF-10 | Run with `DEV_MODE=false` and a live Celery worker | Identical result payload to the inline path | H | M |
| TC-INF-11 | Let the frontend poll a task that never settles | Polling backs off after 30 s and hard-stops at 3 minutes with a retry affordance | M | M |
| TC-INF-12 | Force an inference failure (corrupt the stored object mid-run) | Task ends `failed` with a generic client message; asset marked `failed`; no hang | H | M |
| TC-INF-13 | Verify checkpoint integrity and inference path | 13/13 checks pass | C | A `scripts/verify_model.py` |
| TC-INF-14 | Forward pass output shape and range | `[1,1,224,224]` logits; sigmoid output within [0,1]; not constant | H | A `test_forward_pass_shape_and_range` |
| TC-INF-15 | Synthetic peak localisation | Predicted peak lands within 15 % of the known target's centre | H | A `test_peak_lands_on_a_known_target` |

---

## 5. Letterbox and coordinate correctness — `TC-GEO`

> The single most regression-prone area. The crop must happen **before** the rescale.

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-GEO-01 | Analyse images at 1600×900, 800×1400, 1000×1000, 1920×620, 500×1600 | Saliency and overlay come back at **exactly** the input dimensions in every case | C | A `test_letterbox_alignment_preserves_dimensions` |
| TC-GEO-02 | Inspect letterbox padding on a non-square image | Padding is centred; offsets recorded in `LetterboxMeta` | H | A `test_letterbox_padding_is_centred` |
| TC-GEO-03 | View the heatmap over a non-square mockup in the browser | Hot regions sit **on** the UI elements, with no visible offset | C | M |
| TC-GEO-04 | Zoom and pan the heatmap viewer | Focus-node dots stay locked to the same UI features at every zoom level | H | M |
| TC-GEO-05 | Resize the browser window with a result open | Overlay and nodes re-fit correctly; no drift | M | M |
| TC-GEO-06 | Compare focus-node coordinates against the rendered image | Coordinates are in original image pixels; `lib/coords.ts` is the only converter | H | M |

---

## 6. Clarity Score and analytics — `TC-SCORE`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-SCORE-01 | Score all 7 clean calibration samples | Every one > 75 | C | A `test_tc07_clean_designs_score_above_75` |
| TC-SCORE-02 | Score all 5 cluttered calibration samples | Every one < 40 | C | A `test_tc08_cluttered_designs_score_below_40` |
| TC-SCORE-03 | Compare the two bands | Worst clean strictly above best cluttered | H | A `test_clean_scores_strictly_above_cluttered` |
| TC-SCORE-04 | Regenerate the samples and re-score | Bit-identical to the recorded calibration table | H | A `test_calibration_samples_are_bit_identical` |
| TC-SCORE-05 | Upload the same design exported at 1× and 2× resolution | Clarity scores match — fixed 224 entropy grid and 512 edge side make the score resolution-invariant | C | A `test_clarity_score_is_bounded` + M |
| TC-SCORE-06 | Verify the weights | `FOCUS_WEIGHT + CLUTTER_WEIGHT == 1.0` | M | A `test_clarity_weights_sum_to_one` |
| TC-SCORE-07 | Score any design | Result always within [0, 100] | H | A `test_clarity_score_is_bounded` |
| TC-SCORE-08 | Score a genuinely awful but normally-shaped design | Score near 0 **and** `score_in_range: true` — a bad design is measurable, not unmeasurable | H | A `test_a_legitimately_terrible_design_stays_scoreable` |
| TC-SCORE-09 | Score an ultra-wide panorama export | `score_in_range: false` — geometry, not the design, makes it unscoreable | M | A `test_ultra_wide_is_caught_too` |
| TC-SCORE-10 | Request Focus Order | Exactly 5 ranked nodes, no duplicate coordinates | C | A `test_tc09_focus_order_returns_top5_without_duplicates` |
| TC-SCORE-11 | Check spacing between focus nodes | Every pair separated by at least the suppression radius | H | A `test_tc09_nodes_respect_the_suppression_radius` |
| TC-SCORE-12 | Check the NMS radius on a large image | `max(20 px, 8 % of the long side)` — 20 px is a floor, not a constant | M | A `test_nms_radius_keeps_20px_as_the_floor` |
| TC-SCORE-13 | Inspect `region_saliency` | Nine named cells `top_left`…`bot_right`, each in [0, 1] | M | A `test_region_saliency_has_nine_named_cells` |
| TC-SCORE-14 | Read the Clarity gauge on the results page | Band label (Strong / Moderate / Needs work) matches the numeric score at the 75 and 40 boundaries | M | M |

---

## 7. Scroll-aware scoring (long pages) — `TC-VIEW`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-VIEW-01 | Upload a page taller than 1.35 viewports | Segmented into overlapping viewport-shaped tiles before inference | C | A `test_a_long_page_is_segmented` |
| TC-VIEW-02 | Upload a design that fits one screen | **Not** segmented; `viewport_count: 1`; scored exactly as before | C | A `test_a_single_screen_is_not_segmented` |
| TC-VIEW-03 | Score a 7-viewport page whole vs per viewport | Whole page forces 0.0 arithmetically; per-viewport returns a meaningful score | C | A `test_whole_page_clutter_saturates_but_per_viewport_does_not` |
| TC-VIEW-04 | Inspect the per-viewport breakdown on the results page | One row per screenful with its own score; the weakest is called out by name | H | A `test_long_page_is_scored_per_viewport` + M |
| TC-VIEW-05 | Check slice coverage | Slices cover the whole page and overlap by ~12 % | H | A `test_slices_cover_the_whole_page_and_overlap` |
| TC-VIEW-06 | Check the final slice's shape | Pulled up to end at the page bottom, keeping viewport proportions — not a clipped sliver | M | A `test_every_slice_is_viewport_shaped` |
| TC-VIEW-07 | Choose phone vs tablet vs desktop for the same image | Different segmentation and different per-viewport counts | H | A `test_device_choice_changes_the_segmentation` |
| TC-VIEW-08 | Upload a landscape image with no explicit device | Defaults to `desktop`; portrait defaults to `phone` | M | A `test_default_device_uses_orientation_not_size` |
| TC-VIEW-09 | Verify the stitched map keeps page geometry | Stitched saliency matches the uploaded page's shape and stays within [0, 1] | H | A `test_stitch_restores_the_page_shape` |
| TC-VIEW-10 | Verify focus nodes on a segmented page | Coordinates land in the uploaded page's pixel space, so the dots sit where the user can see them | C | A `test_focus_order_still_maps_onto_the_uploaded_page` |
| TC-VIEW-11 | Segment a page taller than 12 viewports | Capped at 12 slices — one upload cannot queue unbounded inference | M | A `test_tiling_is_capped` |
| TC-VIEW-12 | Verify a degenerate final slice (< 16 px) | Dropped rather than scored | L | A `test_degenerate_slice_is_dropped_not_scored` |

---

## 8. Dark-mode compensation — `TC-DARK`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-DARK-01 | Upload a dark-themed UI | `ui_theme: "dark"`; the model is shown a brightened copy | C | A `test_dark_upload_is_compensated_end_to_end` |
| TC-DARK-02 | Upload a light-themed UI | `ui_theme: "light"`; image passed through untouched | C | A `test_light_upload_is_unaffected` |
| TC-DARK-03 | Compare the same layout light vs dark | Dark score recovers substantially instead of collapsing | H | A `test_inversion_recovers_focus_on_a_dark_screen` |
| TC-DARK-04 | Inspect the returned heatmap for a dark upload | Overlay is built on the **original** pixels, not the brightened copy | C | A `test_dark_upload_is_compensated_end_to_end` |
| TC-DARK-05 | Check hue after compensation | Only the luminance channel is flipped — a blue button does not become orange | H | A `test_compensation_preserves_hue` |
| TC-DARK-06 | Check dimensions and orientation after compensation | Unchanged | M | A `test_compensation_does_not_resize_or_reorient` |
| TC-DARK-07 | Check clutter on a dark vs light pair | Edge density is inversion-invariant | M | A `test_edge_density_is_invariant_to_inversion` |
| TC-DARK-08 | Verify the detection threshold against every light sample | No light calibration sample or real screen falls below `DARK_UI_LUMA` | H | A `test_threshold_clears_every_real_light_screen` |
| TC-DARK-09 | View a dark-mode result in the UI | The page states plainly that a brightened copy was scored | H | M |

---

## 9. Aspect-aware inference (phone screens) — `TC-TILE`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-TILE-01 | Upload a tall phone screenshot (≈ 2.75:1) | Split into near-square bands, run separately, stitched into one map, scored once | C | A `test_tall_frames_are_split_towards_square` |
| TC-TILE-02 | Upload a desktop-shaped screen | Takes the original single-pass path unchanged | C | A `test_near_square_frames_are_not_tiled` |
| TC-TILE-03 | Compare a phone screen scored with and without tiling | Tiled score is materially higher; the gain comes from resolution, not the design | H | A `test_tiling_recovers_focus_on_a_phone_screen` |
| TC-TILE-04 | Confirm the starvation the split fixes | An untiled tall frame demonstrably reaches the model at very low effective width | H | A `test_a_tall_frame_really_does_starve_the_model` |
| TC-TILE-05 | Verify the stitched output | Keeps the frame's shape and stays in range; not normalised per band | H | A `test_stitched_map_keeps_the_frame_shape_and_range` |
| TC-TILE-06 | Upload an extremely tall frame | Band count capped at 4 | M | A `test_tiling_is_capped` |
| TC-TILE-07 | Re-score every calibration sample after the tiling change | All bit-identical — none is tall enough to trigger it | C | A `test_calibration_samples_are_bit_identical` |
| TC-TILE-08 | End-to-end phone upload through the API | Score improves versus the pre-tiling baseline | H | A `test_phone_upload_scores_better_end_to_end` |

---

## 10. Multi-screen flows (batches) — `TC-BATCH`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-BATCH-01 | Upload a multi-page PDF to `/upload/batch` | 202; one asset and one task per page under a single `batch_id` | C | A `test_batch_upload_fans_out_to_one_asset_per_screen` |
| TC-BATCH-02 | Upload a single-page PDF to the batch route | 400 directing the user to the normal upload | H | A `test_batch_rejects_a_single_page_pdf` |
| TC-BATCH-03 | Upload a non-PDF to the batch route | 400 explaining batch expects a multi-page PDF | H | A `test_batch_rejects_a_non_pdf` |
| TC-BATCH-04 | Upload a PDF with more than 30 pages | Fan-out capped at 30; `pages_skipped` reports the remainder | M | A `test_page_cap_is_enforced` |
| TC-BATCH-05 | Poll a batch while screens are still processing | Status `processing`; per-screen progress visible | H | M |
| TC-BATCH-06 | Complete a batch | Status `complete`; average clarity and a per-screen chart shown | C | A `test_batch_list_reports_derived_status` |
| TC-BATCH-07 | Kill the worker mid-batch, then reload | Status is **derived on read**, so the batch can never pin at "processing" forever | H | A `test_status_derivation_covers_every_mix` |
| TC-BATCH-08 | Compare batch list vs batch detail status | Identical — both call the same derivation | H | A `test_batch_list_reports_derived_status` |
| TC-BATCH-09 | Fail some screens but not others | Status `partial`; usable screens still viewable | M | A `test_status_derivation_covers_every_mix` |
| TC-BATCH-10 | Request AI review for a 12-screen flow | Exactly **one** provider call for the whole flow | C | A `test_flow_review_uses_exactly_one_provider_call` |
| TC-BATCH-11 | Check the quota cost of a flow review | One unit, regardless of screen count | H | A `test_batch_review_costs_one_quota_unit` |
| TC-BATCH-12 | Fetch per-screen suggestions after a flow review | The single reply is fanned out into one `SuggestionDoc` per screen; `GET /results/{id}/suggestions` unchanged | H | A `test_batch_review_fans_out_to_per_screen_documents` |
| TC-BATCH-13 | Review a flow longer than 25 screens | Chunked into multiple calls and merged, never truncated | M | A `test_long_flow_is_chunked_rather_than_truncated` |
| TC-BATCH-14 | Check `weakest_screen` / `strongest_screen` | Recomputed from our own clarity scores, not trusted to the model | H | A `test_extremes_are_computed_from_our_own_scores` |
| TC-BATCH-15 | Model omits a screen from its reply | Validation fails and re-prompts once, rather than silently rendering 9 of 12 | M | A `test_flow_parse_requires_every_screen` |
| TC-BATCH-16 | Access another user's batch | 403 Forbidden | C | A `test_batches_are_tenant_isolated` |
| TC-BATCH-17 | Call batch routes with no token | 401 | H | A `test_batch_routes_require_auth` |
| TC-BATCH-18 | Delete a batch | Batch, every screen, every result and every stored file removed | H | A `test_deleting_a_batch_removes_every_screen` |
| TC-BATCH-19 | Export the flow PDF | One report covering the whole journey | M | A `test_flow_report_pdf` |
| TC-BATCH-20 | Open a single screen from a batch | Results, rerun, scanpath and PDF all work — a batch screen is an ordinary asset | H | M |

---

## 11. Replay / scanpath — `TC-PATH`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-PATH-01 | Open "Watch the replay" on a result | Animated playback of the predicted viewing order over the mockup | H | M |
| TC-PATH-02 | Check the disclaimer wherever the replay appears | Plain-language "simulation, not a recording" text is present | C | M |
| TC-PATH-03 | Compare the first 5 scanpath nodes to Focus Order | Identical — one extraction, two views | C | A `test_scanpath_first_five_match_focus_nodes` |
| TC-PATH-04 | Re-run extraction on the same saliency map | Deterministic; identical nodes | H | A `test_scanpath_extraction_is_deterministic` |
| TC-PATH-05 | Inspect scanpath node coordinates | No duplicates | H | A `test_scanpath_nodes_have_no_duplicate_coordinates` |
| TC-PATH-06 | Inspect the timeline | Monotonic, separated by saccade gaps; dwell scales with predicted strength | M | A `test_timeline_is_monotonic_and_gapped_by_saccades`, `test_dwell_scales_with_predicted_strength` |
| TC-PATH-07 | Download the GIF | Valid animated GIF; loops | H | A `test_gif_encodes_to_valid_bytes`, `test_gif_download_endpoint` |
| TC-PATH-08 | Download the MP4 with ffmpeg installed | Valid H.264 MP4 with even dimensions | M | A `test_mp4_encodes_or_reports_missing_ffmpeg`, `test_clip_dimensions_are_even_for_h264` |
| TC-PATH-09 | Download the MP4 **without** ffmpeg | 503 pointing the user at the GIF — not a 500 | M | A `test_mp4_encodes_or_reports_missing_ffmpeg` |
| TC-PATH-10 | Download a scanpath for another user's asset | 403 | C | A `test_scanpath_downloads_are_tenant_isolated` |
| TC-PATH-11 | Download a scanpath with no token | 401 | H | A `test_scanpath_download_requires_auth` |
| TC-PATH-12 | Build a clip from a result with no focus nodes | Rejected cleanly with a 400-level message | L | A `test_build_clip_rejects_an_empty_sequence` |
| TC-PATH-13 | Check the PDF contact sheet | Six-frame filmstrip of the same sequence | M | A `test_filmstrip_is_a_png_contact_sheet` |

---

## 12. AI suggestions — `TC-LLM`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-LLM-01 | Request suggestions with `LLM_PROVIDER=mock` | Valid schema-conformant suggestions returned; feature demonstrable with no API key | C | A `test_suggestions_endpoint_generates_and_caches` |
| TC-LLM-02 | Request suggestions twice for the same result | Second call served from cache, no second provider call | H | A `test_suggestions_endpoint_generates_and_caches` |
| TC-LLM-03 | Request with `regenerate: true` | A fresh generation replaces the cached set | M | M |
| TC-LLM-04 | Set `LLM_PROVIDER=none` | `{"suggestions": [], "llm_status": "unavailable"}`; the rest of the product is unaffected | H | A `test_provider_none_degrades_to_unavailable` |
| TC-LLM-05 | Provider raises or times out | `llm_status: error`; the heatmap and score are untouched | H | A `test_broken_provider_is_reported_not_raised`, `test_suggestions_do_not_block_the_core_result` |
| TC-LLM-06 | Provider returns malformed JSON | Exactly **one** re-prompt, then a clean error | H | A `test_invalid_json_triggers_one_retry` |
| TC-LLM-07 | Provider reply hits the output ceiling | Reported as truncated, **not** blindly retried | M | A `test_truncated_reply_is_not_blindly_retried` |
| TC-LLM-08 | Provider wraps JSON in code fences | Parsed successfully | M | A `test_extract_json_tolerates_code_fences` |
| TC-LLM-09 | Inspect what is sent to the provider | Analytics JSON only — the image is never transmitted | C | A `test_llm_prompt_never_receives_the_image` |
| TC-LLM-10 | Read the generated prose | No internal field names (`clutter_index`, `focus_nodes`), no raw pixel coordinates | H | A `test_prompts_forbid_internal_field_names_in_prose` |
| TC-LLM-11 | Exceed the daily suggestion quota | `llm_status: rate_limited` with a clear message | M | M |
| TC-LLM-12 | Configure a real provider without its SDK installed | App logs the fix and falls back to `unavailable` rather than failing to start | M | M |
| TC-LLM-13 | Request suggestions for another user's result | 403 | C | A `test_tc12_isolation_across_every_owned_resource` |
| TC-LLM-14 | Pass free-text context with the request | Included as background; the model still grounds every claim in the numbers | L | M |

---

## 13. A/B comparison, projects, dashboard — `TC-AB` / `TC-PROJ`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-AB-01 | Compare two analysed variants | Both heatmaps returned with a clarity delta and a winner | C | A `test_tc10_compare_returns_both_heatmaps_and_delta` |
| TC-AB-02 | Retrieve a saved comparison | Same payload as when created | H | A `test_tc10_comparison_is_retrievable` |
| TC-AB-03 | Compare an asset with itself | 400 "Choose two different designs to compare." | M | A `test_compare_requires_two_distinct_assets` |
| TC-AB-04 | Compare with an asset that has not finished analysis | 400 naming which side is not ready | M | A `test_compare_rejects_unanalysed_asset` |
| TC-AB-05 | Compare against another user's asset | 403 | C | A `test_tc12_isolation_across_every_owned_resource` |
| TC-AB-06 | Scroll/zoom one side of the split view | The other side follows in sync | M | M |
| TC-AB-07 | Export the comparison PDF | Both heatmaps and the delta in one report | M | A `test_comparison_report_pdf` |
| TC-PROJ-01 | Create, list, rename and delete a project | All four succeed; 404 after deletion | H | A `test_project_crud` |
| TC-PROJ-02 | Delete a project that owns assets, results, suggestions and a batch | **Everything** cascades: documents, stored files, suggestions and the batch document | C | A `test_deleting_the_project_takes_the_batch_and_its_files` |
| TC-PROJ-03 | Delete a single result | Asset, result, tasks, suggestions and stored objects all removed | H | A `test_delete_removes_asset_and_result` |
| TC-PROJ-04 | View the dashboard | Total projects, total analyses, average clarity and a trend sparkline | H | A `test_dashboard_aggregates` |
| TC-PROJ-05 | Paginate a long result history | Correct page slicing and total count | M | M |
| TC-PROJ-06 | Open the dashboard as a brand-new user | Empty states everywhere, no crashes and no NaN | M | M |

---

## 14. Chrome extension — `TC-EXT`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-EXT-01 | Load the extension unpacked | Loads with no manifest errors; toolbar icon appears | C | M |
| TC-EXT-02 | Open the popup while signed out | Sign-in view shown | C | A `popup.test.mjs §1` |
| TC-EXT-03 | Create an account from the popup | Account created; popup moves to the ready view | H | A `popup.test.mjs §9` |
| TC-EXT-04 | Sign in with a wrong password | Error shown; stays on the sign-in view | H | A `popup.test.mjs §3` |
| TC-EXT-05 | Analyse the visible area of a live page | Clarity score and heatmap returned in the popup | C | A `popup.test.mjs §5` |
| TC-EXT-06 | Analyse a whole page with "Whole page" ticked | Page scrolled and stitched; scored one screenful at a time | C | M |
| TC-EXT-07 | Analyse on a `chrome://` page | Clear message explaining capture is blocked **and** offering paste instead | M | A `popup.test.mjs §8` |
| TC-EXT-08 | Check where a capture was filed | Project named after the site's hostname; repeat captures collect together | M | A `test_project_title_groups_captures_by_site` |
| TC-EXT-09 | Session expires mid-analysis | Popup signs out and asks for a re-login | H | A `popup.test.mjs §7` |
| TC-EXT-10 | "Open full analysis" from the popup | Deep-links to the web app's result page for that asset | M | A `popup.test.mjs §5` |
| TC-EXT-11 | Connect the extension from the website | Session adopted; no second sign-in | H | A `external.test.mjs §4` |
| TC-EXT-12 | Send `PING` from the website | Reports installed, version and signed-in state — **never** the token | C | A `external.test.mjs §3` |
| TC-EXT-13 | Send `CONNECT` with no token | Rejected; existing session left intact | C | A `external.test.mjs §5` |
| TC-EXT-14 | Paste a screenshot into the popup (Ctrl+V) | Staged with thumbnail, stamped name and size | C | A `popup.test.mjs §12` |
| TC-EXT-15 | Analyse the pasted screenshot | `ANALYSE_IMAGE` sent; result rendered; filed under "Pasted screenshots" | C | A `popup.test.mjs §13` |
| TC-EXT-16 | Drop an image onto the popup's paste zone | Same result as pasting | H | M |
| TC-EXT-17 | Click the paste zone and choose a file | Same result as pasting | H | M |
| TC-EXT-18 | Paste text (not an image) into the popup | Ignored; the keystroke is not swallowed; form fields still accept text | H | A `popup.test.mjs §14` |
| TC-EXT-19 | Paste a GIF | Refused: "Use a PNG, JPG, or WEBP image." | M | A `popup.test.mjs §14` |
| TC-EXT-20 | Paste an image over 10 MB | Refused **before** upload, naming the limit | M | A `popup.test.mjs §14` |
| TC-EXT-21 | Remove a staged screenshot | Card and analyse button withdrawn | L | A `popup.test.mjs §15` |
| TC-EXT-22 | Session expires while analysing a pasted image | Signs out identically to the capture path | H | A `popup.test.mjs §15` |
| TC-EXT-23 | Change the server address in the popup | Saved and used for subsequent calls | M | M |
| TC-EXT-24 | Verify the packaged ZIP | Matches `extension/` exactly and contains every required file | H | A `zip.test.mjs` |
| TC-EXT-25 | Download the ZIP from the website and load it | Contains the current build — rebuild the frontend image after changing `extension/` | H | M |
| TC-EXT-26 | Verify the extension origin in CORS | API allow-list names the pinned extension id, never a wildcard | C | M |

---

## 15. Security, tenancy and non-functional — `TC-SEC` / `TC-NFR`

| ID | Scenario | Expected result | P | Type |
|---|---|---|---|---|
| TC-SEC-01 | Access another user's asset, result, task, project, comparison or batch | **403 Forbidden** on every one — not 404 | C | A `test_tc12_isolation_across_every_owned_resource` |
| TC-SEC-02 | List results, projects, comparisons and batches as user B | User A's records never appear | C | A `test_tc12_listings_never_leak_across_tenants` |
| TC-SEC-03 | Inspect stored object keys | Every key prefixed with the owner's `user_id` | H | A `test_stored_files_are_prefixed_by_tenant`, `test_tenant_prefix_helper` |
| TC-SEC-04 | Check the CORS configuration | Explicit allow-list; never `*` | C | A `test_cors_is_an_allow_list_not_wildcard` |
| TC-SEC-05 | Trigger a server-side error | Generic client message; detail only in server logs; no stack trace over the wire | H | M |
| TC-SEC-06 | Search logs for secrets | No passwords, no reset tokens, no API keys | H | M |
| TC-SEC-07 | Attempt a path-traversal storage key | Rejected; nothing written outside the storage root | M | M |
| TC-SEC-08 | Upload a decompression-bomb PNG (small file, enormous pixel count) | Rejected rather than exhausting memory | M | M |
| TC-SEC-09 | Confirm `JWT_SECRET` is not the shipped default before deployment | Deployment checklist item; tokens are forgeable otherwise | C | M |
| TC-SEC-10 | Confirm `EXPOSE_RESET_TOKEN=false` before deployment | Reset tokens must never be returned over the wire in production | C | M |
| TC-NFR-01 | Single-screen analysis latency | Completes within 30 s (SDS NFR) | C | A `test_tc06_inference_completes_within_sla` |
| TC-NFR-02 | Cap oversized saliency arrays before storage | Downscaled to stay under the object-size limit | M | A `test_oversized_saliency_is_downscaled_before_storage` |
| TC-NFR-03 | Cloudinary addressing for images vs raw `.npy` | Consistent across upload, URL, exists and delete | H | A `test_cloudinary_addressing_is_consistent_across_operations` |
| TC-NFR-04 | Run three uploads concurrently | All complete; no cross-contamination of results | M | M |
| TC-NFR-05 | Restart the stack (`docker compose down && up`) | Data survives via the named Mongo volume | H | M |
| TC-NFR-06 | Cold start with an empty database | Indexes created; app healthy; no crash | M | M |
| TC-NFR-07 | Navigate the app by keyboard only | Every control reachable and operable; focus visible | M | M |
| TC-NFR-08 | View the app at 375 px, 768 px and 1440 px | Layout holds; no horizontal overflow | M | M |
| TC-NFR-09 | Enable "reduce motion" at OS level | Animations respect it; no content stranded at `opacity: 0` | M | M |
| TC-NFR-10 | Toggle dark and light theme across every page | Readable contrast throughout | M | M |
| TC-NFR-11 | Stop the API and use the web app | Clear "cannot reach the server" messaging, not a blank screen | M | M |
| TC-NFR-12 | Frontend build health | `npx tsc --noEmit` and `npx next lint` both clean | H | M |

---

## 16. Traceability to the SDS

SDS Table 13 defined 14 test cases. Every one is covered; four are covered by a
rewritten equivalent because the implementation deviates from the SDS with a
documented reason (see `docs/DEVIATIONS.md`).

| SDS | Covered by | Note |
|---|---|---|
| TC-01 register | TC-AUTH-01 | Custom Python JWT, not Firebase — §1 |
| TC-02 duplicate email | TC-AUTH-02, TC-AUTH-03 | |
| TC-03 valid upload | TC-UP-01 | Storage is pluggable, not Cloudinary-only — §3 |
| TC-04 invalid format | TC-UP-05, TC-UP-06 | **Rewritten**: raster formats are accepted — §2 |
| TC-05 oversize file | TC-UP-08 | PDFs get a higher ceiling — §8 |
| TC-06 inference < 30 s | TC-INF-01 | |
| TC-07 clean > 75 | TC-SCORE-01 | Constants recalibrated — §4 |
| TC-08 cluttered < 40 | TC-SCORE-02 | Constants recalibrated — §4 |
| TC-09 top-5 focus order | TC-SCORE-10, TC-SCORE-11 | NMS radius became a floor — §5 |
| TC-10 A/B delta | TC-AB-01, TC-AB-02 | |
| TC-11 unauthenticated 401 | TC-AUTH-17 | |
| TC-12 tenant isolation 403 | TC-SEC-01, TC-SEC-02 | |
| TC-13 rerun | TC-INF-05 | |
| TC-14 expired JWT 401 | TC-AUTH-15, TC-AUTH-16 | |

### Features beyond the SDS

These have no SDS test case because the feature itself is an addition; each is
justified in `docs/DEVIATIONS.md` at the section given.

| Feature | Test cases | Deviation |
|---|---|---|
| Scanpath replay | TC-PATH-01…13 | §17 |
| Multi-screen flows | TC-BATCH-01…20 | §18 |
| Scroll-aware scoring | TC-VIEW-01…12 | §19 |
| Dark-mode compensation | TC-DARK-01…09 | §20 |
| Aspect-aware inference | TC-TILE-01…08 | §21 |
| Chrome extension | TC-EXT-01…26 | — |
| Paste to analyse | TC-PASTE-01…12, TC-EXT-14…22 | — |

---

## 17. Execution record

### Cycle 1 — 2026-09-07

| Suite | Result |
|---|---|
| `pytest` (backend) | **187 collected, 186 passed, 1 skipped** — the skip is the MP4 case; `ffmpeg` is absent locally and present in the API image |
| `popup.test.mjs` + `external.test.mjs` + `zip.test.mjs` | **85 / 85 passed** |
| `scripts/verify_model.py` | **13 / 13 passed** |
| `npx tsc --noEmit` · `npx next lint` | clean · 0 warnings, 0 errors |
| Manual cases executed mechanically | **23 / 23 passed** (listed below) |

**192 of 243 cases (79 %) executed and passing.** The remaining 51 need a human
or an environment change; they are enumerated in §18.

Cases marked *manual* in the tables above but verified mechanically in this
cycle, run in-process against a throwaway database with `LLM_PROVIDER=mock` and
local storage:

| ID | Result |
|---|---|
| TC-AUTH-05 | 422 on a malformed email |
| TC-AUTH-06 | 422 on a >72-byte password — rejected, not a 500 |
| TC-AUTH-14 | TTL index `expires_at_1` present with `expireAfterSeconds=0` |
| TC-AUTH-25 | change-password revokes prior sessions: old access **401**, old refresh **401** |
| TC-UP-03 | SVG returns a clean "rasterisation unavailable" message where cairo is absent |
| TC-UP-04 | single-page PDF accepted, `pages_detected=1` |
| TC-UP-11 | 8001×8001 rejected, message names the shorter side |
| TC-UP-12 | 100×30001 rejected as too long |
| TC-UP-14 | 8×8 rejected as too small |
| TC-INF-06 | rerun with the stored object deleted → **400**, not a 500 |
| TC-INF-07 | `load_model()` returns the same cached instance |
| TC-LLM-03 | cache hit makes **no** provider call; `regenerate` makes exactly one and replaces the document rather than appending |
| TC-LLM-14 | free-text context accepted, 4 grounded suggestions returned |
| TC-PROJ-05 | 7 projects → pages of 3 / 3 / 1, no overlap between pages |
| TC-PROJ-06 | new account: all counters 0, all lists empty, no NaN |
| TC-BATCH-20 | a batch screen behaves as an ordinary asset — result 200, PDF 200 (`%PDF`), GIF 200 (`GIF`), rerun 200 |
| TC-SEC-05 | unhandled error → generic 500 body; no internal detail, no traceback |
| TC-SEC-06 | API logs carry no passwords, tokens or keys — the only `password` matches are URL paths in access lines |
| TC-SEC-07 | traversal key raises `ValueError`; nothing written outside the storage root |
| TC-SEC-09 | `JWT_SECRET` set to a 64-char value in both env files, not the shipped default |
| TC-SEC-10 | `EXPOSE_RESET_TOKEN=true` — correct for local use, **must be `false` before deployment** |
| TC-EXT-26 | CORS is an explicit allow-list naming the pinned extension id; never `*` |
| TC-NFR-12 | `tsc` and `next lint` both clean |

### Later cycles

| Cycle | Date | Automated | Manual executed | Passed | Failed | Notes |
|---|---|---|---|---|---|---|
| 2 | | | | | | |

---

## 18. Cases still requiring a human

51 cases. Grouped by why they cannot be executed mechanically.

### 18.1 UI behaviour — needs a browser and an eye (26)

Real code paths that can be *driven* by automation, but whose pass criterion is
visual or depends on a genuine OS clipboard.

| ID | What to check |
|---|---|
| TC-PASTE-01 | Take a real screenshot, open `/upload`, press Ctrl/⌘+V with nothing focused — it stages, the zone flashes, a toast appears |
| TC-PASTE-02 | Staged name is `screenshot-YYYY-MM-DD-HHMMSS.png`, not `image.png` |
| TC-PASTE-03 | "Paste screenshot" button with an image on the clipboard |
| TC-PASTE-04 | Same button with nothing on the clipboard → "No image on the clipboard…" |
| TC-PASTE-06 | Copy text, press Ctrl+V → nothing staged, keystroke not swallowed |
| TC-PASTE-07 | Paste an image over 10 MB → refused with the size message |
| TC-PASTE-08 | Paste then upload → analysis runs, result shows the stamped filename |
| TC-PASTE-09 | Paste a tall phone screenshot → the screen-size question appears |
| TC-PASTE-10 | Paste a second image over a staged one → it replaces |
| TC-PASTE-11 | Ctrl+V during an analysis → ignored |
| TC-UP-24 | Drag and drop onto the zone → highlights, then accepts |
| TC-UP-25 | Click the zone → OS file dialog opens, filtered |
| TC-GEO-03 | **Highest value on this list.** Heatmap sits exactly on the UI on a non-square mockup, no offset |
| TC-GEO-04 | Zoom and pan — focus dots stay locked to the same features |
| TC-GEO-05 | Resize the window with a result open — no drift |
| TC-GEO-06 | Focus-node coordinates line up with the rendered image |
| TC-SCORE-14 | Clarity gauge band matches the number at the 75 and 40 boundaries |
| TC-DARK-09 | A dark upload's result page states plainly that a brightened copy was scored |
| TC-PATH-01 | "Watch the replay" plays back over the mockup |
| TC-PATH-02 | The "simulation, not a recording" disclaimer is present wherever the replay appears |
| TC-AB-06 | Split view — scrolling/zooming one side moves the other |
| TC-AUTH-32 | Refresh the browser → session restored, no re-login |
| TC-AUTH-34 | Open dashboard + results + projects together on an expired token → one refresh, not three |
| TC-NFR-07 | Keyboard-only navigation, focus always visible |
| TC-NFR-08 | 375 px / 768 px / 1440 px — no horizontal overflow |
| TC-NFR-10 | Dark and light theme across every page — readable contrast |
| TC-BATCH-05 | Watch a batch mid-run — per-screen progress visible, then settles |

### 18.2 Chrome extension — needs a real browser with it loaded (6)

The node harness covers `popup.js` logic (18 automated cases); these need the
extension actually installed. This is the gap that let the stale-zip problem
through earlier.

| ID | What to check |
|---|---|
| TC-EXT-01 | Loads unpacked with no manifest errors; toolbar icon appears |
| TC-EXT-06 | "Whole page" capture scrolls, stitches and scores correctly on a long real page |
| TC-EXT-16 | Drop an image onto the popup's paste zone |
| TC-EXT-17 | Click the paste zone and choose a file |
| TC-EXT-23 | Change the server address and confirm later calls use it |
| TC-EXT-25 | Download the ZIP from the site and load it — must contain the current build |

### 18.3 Needs an environment change (14)

Each is straightforward but would disturb the running stack, wipe data, or
require a paid provider.

| ID | What it needs |
|---|---|
| TC-NFR-05 | `docker compose down && up` — verify Mongo volume survives |
| TC-NFR-06 | Cold start against an empty database |
| TC-NFR-11 | Stop the API, confirm the web app messages clearly |
| TC-INF-09 | Stop Redis, confirm `/health` stays `ok` under `DEV_MODE` |
| TC-INF-10 | `DEV_MODE=false` + live Celery worker → identical results |
| TC-INF-11 | A task that never settles → backoff then hard stop at 3 min |
| TC-INF-12 | Corrupt a stored object mid-run → clean `failed`, no hang |
| TC-LLM-11 | Exhaust the daily quota → `rate_limited` |
| TC-LLM-12 | Configure a real provider with its SDK absent → falls back, still starts |
| TC-NFR-04 | Three concurrent uploads, no cross-contamination |
| TC-AUTH-23 | A reset token older than 30 minutes |
| TC-AUTH-33 | Let the access token expire, then edit the profile — must refresh transparently |
| TC-PASTE-05 | A browser that blocks the Clipboard API, or deny the prompt |
| TC-SEC-08 | Decompression-bomb PNG — **run against a disposable instance**, it can exhaust memory |

### 18.4 Cannot be run here (5)

| ID | Why |
|---|---|
| TC-PASTE-12 | macOS ⌘ rendering — needs a Mac |
| TC-NFR-09 | OS-level "reduce motion"; forcing the media query tests the override, not the setting |
| TC-EXT-01…25 | (counted in §18.2) |
| TC-SEC-09 · TC-SEC-10 | Verified for the current config in cycle 1, but they are **deployment gates** — re-check at deploy time, not now |
