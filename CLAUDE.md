# CLAUDE.md — conventions and locked decisions

Read before changing anything in this repo.

---

## Never change these

**`backend/app/ml/model.py`** — the SalGAN architecture is matched bit-for-bit to
the trained checkpoint. Any change to layer shapes or naming breaks
`load_state_dict(..., strict=True)`. The odd-looking encoder indices (`enc2.5`,
`enc3.10`) are correct: slicing an `nn.Sequential` preserves the original keys.

**The preprocessing in `backend/app/ml/preprocess.py`** — letterbox to 224×224
with white fill, ImageNet mean/std normalisation. Changing it produces noise.

**The letterbox crop order** — crop the padding off the 224×224 saliency map
*before* rescaling to the original dimensions. Reversing this leaves the heatmap
offset on every non-square upload. It is the single most likely regression here.

After touching anything under `app/ml/`, run:

```bash
python scripts/verify_model.py
```

---

## Locked stack

Backend is **100% Python**: FastAPI, Motor, Pydantic v2, `passlib[bcrypt]` +
PyJWT (no Firebase/Auth0/Clerk), Celery + Redis with a `DEV_MODE` inline
fallback, PyTorch CPU-compatible, ReportLab.

Frontend is **Next.js 15 App Router + TypeScript**, Tailwind v4, shadcn-style
components we own, Framer Motion, Lenis, TanStack Query, Zustand, react-hook-form
+ zod, Recharts, lucide-react.

---

## Conventions

- Files stay under ~300 lines; split by responsibility.
- Everything typed: Python hints + Pydantic, TypeScript with **no `any`**.
- Every endpoint returns a Pydantic schema, never a bare dict.
- Comments explain *why*, never *what*. Delete a comment that restates the code.
- Client-facing errors are generic; details go to the server log.
- No mock data in the product. `MockProvider` in `services/llm.py` is the single
  intentional exception and is env-gated.

### Tenant isolation is not optional

Every query for an asset, result, project, task, or comparison must filter on
`user_id`. Use `owned_or_403()` from `core/deps.py` — it deliberately looks the
document up *without* the user filter, then compares, so another tenant gets
**403 rather than 404** (TC-12). Stored objects are keyed `{user_id}/...`.

---

## Traps already hit — do not re-introduce

**`from __future__ import annotations` in `api/v1/auth.py`.** slowapi's
`@limiter.limit` replaces the route function, and FastAPI resolves string
annotations against `call.__globals__` — slowapi's module, not ours. With
postponed annotations the request models silently degrade to query parameters and
every rate-limited endpoint 422s. That module must keep eager annotations.

**Branching rendered structure on `useReducedMotion()`.** It disagrees between
server and client; the hydration mismatch leaves revealed content stuck at
`opacity: 0`. Reduced motion is handled globally by `MotionConfig
reducedMotion="user"` in `app/providers.tsx`.

**Reading component state set inside `mutate()` callbacks.** React Query drops
those callbacks if the component unmounts mid-flight, which Strict Mode's
double-mount does in dev. Put the result in the query cache from the hook-level
`onSuccess` instead — see `useCreateComparison` / `useCurrentComparison`.

**Importing JSON out of `public/`.** That directory is for static serving; a
module import from it breaks Turbopack resolution. Generated data belongs in
`lib/` (see `lib/demo-data.json`).

**Regenerating an asset at a stable path.** `next/image` caches hard by URL.
Generated demo assets carry a content hash in the filename.

**`.test` email addresses in tests.** `email-validator` rejects reserved TLDs.
Use `@designeye.dev`.

**Motor and event loops.** A Motor client is bound to the loop that created it.
`pytest.ini` pins fixtures *and* tests to one session loop; Celery tasks open
their own client inside `asyncio.run`.

**Cloudinary resource types.** Images and raw files live in separate
namespaces and are addressed differently: an image's `public_id` drops the
extension, a raw object's keeps it. Derive both from the key in
`CloudinaryStorage._address()` and nowhere else. Getting `.npy` wrong uploads
fine and then fails to read back, breaking rerun and A/B silently. Run
`scripts/verify_cloudinary.py` after touching that class.

**Scanpath and Focus Order come from one extraction.** `analyse()` runs the
peak search once at SCANPATH_NODES and slices the first TOP_N_FOCUS_NODES for
`focus_nodes`. Never extract them separately -- they would drift apart, and
TC-09 pins focus_nodes at exactly 5. Timing lives only in
`analytics.scanpath_timeline()` so the player, the video, and the PDF filmstrip
cannot disagree.

**The checkpoint under-reads dark UI, and is shown a brightened copy.**
Measured: one layout, colours flipped, edge density held constant, clarity 89.28
-> 37.40 -- 51.9 points from colour alone. Confirmed on a real screen at 65.4
light versus 27.4 dark, of which 98% was the focus term. `ml/theme.py` flips the
**luminance channel only** below `DARK_UI_LUMA`; inverting RGB would turn a blue
button orange and scored worse. Only the model's INPUT is changed -- edge
density, the overlay and every coordinate come from the original pixels, and
`ui_theme` is recorded so the compensation is never silent.

**A tall frame is split into near-square bands before inference.** The model's
input is a fixed 224x224 square, so a 2.75:1 phone screen reaches it as 81x224 --
the design seen 81 pixels wide. Aspect ratio correlated with the Clarity Score at
Spearman -0.730 before this. `predict_saliency_hires` splits above
`MIN_TILED_ASPECT` and stitches once. Bands are deliberately NOT normalised
individually: sigmoid output is absolute, and per-band normalisation flattens the
stitched map and destroys the focus the split recovers. Tall frames only -- every
calibration sample is wider than 1.5:1 and must stay bit-identical.

**A long page is segmented BEFORE inference, never after.** The letterbox is why:
at 15:1 the page fills 6.2% of the model's 224×224 input and the rest is padding,
so the whole-page saliency map is derived from a 14px sliver. Computing focus per
band on that map would be cheaper than N forward passes and completely worthless
-- there is no signal in it to partition. `services/viewports.py` slices first.

**Scoreability is a geometry test, not a clamp test.** `focus_raw` clamping at
`FOCUS_RAW_MIN` together with `clutter` clamping at 1.0 does *not* mean the score
is unreliable: `synth_data_table` and `synth_dense_dashboard` both look exactly
like that and score 0.00 correctly, and TC-08 depends on it. Only the frame's
shape distinguishes unmeasurable from awful, so `letterbox_content_fraction`
drives `score_in_range`.

**A flow is reviewed in ONE provider call, never one per screen.** Per-screen
calls exhaust the free daily quota in two uploads and, worse, cannot compare
screens -- each call would only ever see its own numbers, so "clarity drops most
at screen 5" becomes unsayable. The single reply is fanned out into one
`SuggestionDoc` per screen so `GET /results/{id}/suggestions` stays untouched.
Never trust the reply's `weakest_screen`/`strongest_screen`: they are recomputed
in `generate_flow_suggestions` from our own clarity scores, because a chunked
flow means the model never saw every screen together.

**`MockProvider` must answer both prompt shapes.** A flow review asks for
different JSON. When it only knew the single-screen shape, every batch review
failed validation -- and mock is the default, so the whole multi-screen feature
was dead without an API key. `FLOW_PROMPT_MARKER` is how the two are told apart;
if you reword `build_flow_prompt`'s opening line, keep the marker.

**A truncated LLM reply is not re-prompted.** `LLMTruncated` means the output
ceiling was hit; asking again produces another over-long reply. Reduce scope
(chunk further) or report the error.

**The scanpath is a simulation and must always say so.** The model predicts
where, not when. Any surface that shows the playback carries the plain-language
disclaimer. Do not reword it into a claim about real gaze.

**`NEXT_PUBLIC_*` is compiled into the bundle**, not read at runtime. Changing
`NEXT_PUBLIC_API_URL` requires rebuilding the frontend image.

**`<Button asChild>` when wrapping a `<Link>`.** Without it you get invalid
`<button><a>` nesting. With it, the child must be a single element — never a
Fragment, or Radix `Slot` puts `className` on the Fragment.

---

## Design system

The Visily exports in `inputs/screens/` are the visual ground truth and win over
any generic palette guidance. Light-first, navy `#1B2559` chrome, indigo
`#4F5BD5` primary, violet `#7C3AED` accent; full dark theme via next-themes.

Craft rules: double-bezel nested cards (`Bezel`), button-in-button trailing
icons, macro whitespace (`py-24`+ on marketing sections), custom cubic-bezier
`(0.32, 0.72, 0, 1)` — never `linear` or `ease-in-out`, scroll reveals via
`whileInView` (never a scroll listener), animate only `transform` and `opacity`,
`backdrop-blur` only on fixed/sticky elements. Lucide icons at
`strokeWidth={1.5}`.

**The brand mark is generated, never hand-edited.**
`inputs/brand/logo-source.png` is the only source; `python
scripts/build_brand_assets.py` produces every tier and both theme variants and
rebuilds the extension archive as its last step. Editing a PNG under
`frontend/assets/brand/`, `frontend/app/icon.png` or `extension/icons/` is
undone by the next run.

Three things that script encodes, so do not "simplify" them away:
the supplied rings were **#FE0500 and #FE9200**, within a few points of
`--color-danger` and `--color-warning`, and are recoloured onto the brand ramp
with the order reversed so the bright ring lands on the pupil; the mark is
**redrawn as it shrinks** (five rings above ~48px, three in app chrome, a filled
lens at favicon and toolbar sizes, where the pupil-to-ring gap is under a pixel
and no stroke weight survives); and there are **two artworks per tier** because
the pupil is dark -- the app sidebar is navy in *both* themes, so `tone="light"`
pins the dark artwork instead of following next-themes.

---

## Before calling anything done

```bash
python scripts/verify_model.py                    # 13 checks
cd backend && ../.venv/Scripts/python -m pytest    # 172 tests
cd frontend && npx tsc --noEmit && npx next lint   # 0 errors, 0 warnings
```

If you change the Clarity Score constants, re-run
`python scripts/calibrate_clarity.py` and update the table in
`docs/DEVIATIONS.md` §4. Clean samples must stay > 75 and cluttered < 40.

Any new departure from the SDS goes in `docs/DEVIATIONS.md` with its reason —
the FYP report depends on that trail.
