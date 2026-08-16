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

---

## Before calling anything done

```bash
python scripts/verify_model.py                    # 13 checks
cd backend && ../.venv/Scripts/python -m pytest    # 74 tests
cd frontend && npx tsc --noEmit && npx next lint   # 0 errors, 0 warnings
```

If you change the Clarity Score constants, re-run
`python scripts/calibrate_clarity.py` and update the table in
`docs/DEVIATIONS.md` §4. Clean samples must stay > 75 and cluttered < 40.

Any new departure from the SDS goes in `docs/DEVIATIONS.md` with its reason —
the FYP report depends on that trail.
