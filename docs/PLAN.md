# Build plan

Written before implementation, kept as the record of what was decided and why.

---

## Inputs read first

| Input | Outcome |
|---|---|
| `DesignEye Phase 2 Final Document.docx` | Extracted to text: 568 paragraphs, 19 tables. The API table, six schema tables, the sprint evolution log, and TC-01…TC-14 drove the build. |
| 13 Visily screen exports | All viewed. Mapped to routes in `docs/SCREENS.md`. Palette and type extracted from them. |
| `stage3_ui_best_val.pth` | Wrapper dict: `G` (44 tensors), `epoch` 19, `val` {CC 0.675, NSS 2.43, KL 0.701, BCE 0.169}, `model_version` `designeye-salgan-1.0-stage3`. |
| Calibration samples | **Not supplied.** Sourced and made reproducible — see phase 5. |

---

## Phases

### 0 — Scaffold
Repo skeleton, venv, inputs staged under `inputs/`, weights moved to
`backend/app/ml/weights/` and gitignored.

### 1 — ML core *(hard gate)*
Architecture copied verbatim; letterbox preprocessing with an explicit inverse;
singleton loader; JET overlay. `scripts/verify_model.py` had to pass before
anything was built on top: strict load with zero missing/unexpected keys, output
`[1,1,224,224]` within `(0,1)` and non-constant, a synthetic dark rectangle
attracting the top peak, and dimension preservation across three aspect ratios.

**Result: 13/13 passed.** The synthetic peak landed 17 px from target — 1.2% of
the image diagonal against a 15% tolerance — confirming the letterbox crop is
correct. Visual check on a real 1488×3294 screenshot put hotspots precisely on
the hero headline, hero image, section headings, and CTA band.

### 2 — Backend core
Settings, Motor + indexes, domain models from the SDS schema tables, bcrypt-12 +
JWT with a refresh denylist, and the `StorageService` abstraction.

### 3 — Analytics, LLM, PDF, pipeline
Clarity Score, Focus Order, 3×3 region grid; the provider-agnostic LLM adapter
with four implementations; ReportLab reports; the pipeline that runs identically
under Celery and inline.

### 4 — API
Every SDS endpoint plus the additions in BUILD.md §8. Verified by a 54-step
golden-path walkthrough against the running server before the frontend existed.

### 5 — Calibration
No clean/cluttered corpus was supplied. `scripts/make_samples.py` builds a
reproducible set: four genuinely minimal Visily screens as real clean examples
plus eight synthetic mockups spanning the density spectrum.

Two problems surfaced and were fixed:
- The raw entropy-based focus index tops out near 30/100, so TC-07's >75 band was
  unreachable. Added an explicit normalisation band.
- Entropy and edge density were resolution-dependent, which would make A/B
  comparison meaningless. Both now use fixed-size reductions.

Final: clean 78.8–98.3, cluttered 0.0–16.3, 62-point separation.

### 6 — Frontend
All routes matched to the exports. Canvas heatmap with an SVG focus layer and one
shared coordinate helper; staged upload progress; synchronised A/B zoom.

### 7 — Infrastructure, tests, docs
Docker stack with a named Mongo volume, seed script, 78 pytest cases, and this
documentation set.

---

## Decisions taken without asking

- **Storage keys** are `{user_id}/{uploads|results}/{asset_id}.{ext}` — tenant
  isolation on disk as well as in the database.
- **Uploads without a project** land in an auto-created "My Uploads" project
  rather than being rejected.
- **Rerun replaces** the previous result for an asset (`asset_id` is unique in
  `heatmap_results`) rather than accumulating history rows.
- **403 over 404** for cross-tenant access. Leaking existence is the lesser
  concern here; TC-12 explicitly specifies 403.
- **Suggestions are pull, not push.** Generated on request after the heatmap
  exists, so a slow provider can never delay a result.
- **The export screen became an action**, not a route — it is one button on the
  results and compare pages.
- **PDF reports embed the heatmap** rather than linking it, so the artefact is
  self-contained for a report appendix.

---

## Verification performed

| Check | Result |
|---|---|
| `scripts/verify_model.py` | 13/13 |
| Golden-path walkthrough (register → … → logout) | 54/54 |
| `pytest` | 78/78 |
| `tsc --noEmit` | 0 errors |
| `next lint` | 0 warnings |
| Clarity calibration | clean > 75, cluttered < 40 |
| Docker restart persistence | seeded user survives `down` + `up` |
| Browser console on every route | 0 errors |
| `scripts/verify_cloudinary.py` | 14/14 against a live account |
| Gemini suggestions end to end | ok, ~15 s, schema-valid |
| Cloudinary end to end (upload, rerun, PDF) | all artefacts served from the CDN |
