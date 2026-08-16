# Screen map

The 13 Visily exports in `inputs/screens/` are the design ground truth. Each is
mapped to the route that implements it.

## Palette extracted from the exports

| Token | Hex | Used for |
|---|---|---|
| navy-900 | `#1B2559` | sidebar, top nav, primary dark buttons |
| navy-950 | `#101636` | deepest chrome |
| indigo-600 | `#4F5BD5` | primary action, active nav |
| violet-600 | `#7C3AED` | accent, gradient CTA, rank-1 focus node |
| canvas | `#F5F7FA` | app background |
| surface | `#FFFFFF` | cards |

Type: Space Grotesk (display) · Plus Jakarta Sans (body) · JetBrains Mono
(numerals). See `docs/DEVIATIONS.md` §8 for why these replace Inter.

---

## Mapping

| Export | Route | Components |
|---|---|---|
| `visily-designeye-landing-page.jpg` | `/` | `SiteNav` (floating glass island), `HeroDemo` (real model output cycling mockup → heatmap → focus order), capability cards, 3-step flow, model-accuracy panel, gradient CTA, footer |
| `visily-designeye-login.jpg` | `/login` | `AuthShell`, react-hook-form + zod, show/hide password |
| `visily-designeye-user-registration.jpg` | `/register` | `AuthShell`, live password-strength meter |
| `visily-container.jpg` | `/forgot-password` | `AuthShell`, success state; DEV_MODE surfaces the reset token |
| `visily-container-268.jpg` | `/upload` | dropzone that scales and glows on drag-over, selected-asset card, project picker, staged progress narrative |
| `visily-designeye-designer-dashboard.jpg` | `/dashboard` | `AppShell` sidebar, 3 stat cards, Recharts clarity trend, recent-analysis grid |
| `visily-acme-corp.-project-management-dashboard.jpg` | `/projects` | search + status filter, analysis rows with `ClarityPill`, view/rerun/delete actions, pagination |
| `visily-designeye-heatmap-analysis-1.jpg` | `/results/[assetId]` | `HeatmapViewer` (Canvas + SVG), `ClarityGauge`, metrics rail, PDF export |
| `visily-designeye-heatmap-analysis.jpg` | `/results/[assetId]` (Focus order mode) | same view, `mode="focus"`; ranked node list with attention share |
| `visily-designeye-a-b-heatmap-comparison.jpg` | `/compare` | split screen, synchronised zoom/pan, animated delta badge, winner badge, per-side indices |
| `visily-designeye-profile-settings.jpg` | `/settings` | profile form, security form, appearance, live system status |
| `visily-zenith-dynamics-user-settings.jpg` | `/settings` (variant) | same content; the navy sidebar variant was chosen for consistency with the rest of the app |
| `visily-export-analysis-report-generation.jpg` | export action | folded into the results and compare pages as "Export PDF" rather than a separate route — it is one action, not a destination |

---

## Screens designed without an export

| Route | Reason |
|---|---|
| `/reset-password` | The exports cover requesting a reset but not entering the new password. Built to match `/forgot-password`. |
| `/projects/[id]` | No project-detail export. Built from the `/projects` and `/dashboard` vocabulary: header with inline rename, asset grid reusing the dashboard card. |

---

## Deliberate departures from the exports

- **"Continue with Google"** on the login export is omitted. The backend is
  custom JWT with no OAuth provider, so the button would be inert.
- **Search bar in the dashboard top bar** is omitted; search lives on `/projects`
  where there is a list to search. A control that filters nothing is noise.
- **Stat figures** in the exports (24 projects, 158 analyses, 76.4 average) are
  mock values. The build renders real aggregates from `GET /dashboard`.
- **"Upgrade to Enterprise"** banner is omitted — there is no billing tier.

---

## Rendering contract

API coordinates are always in **original image pixel space**. Every conversion
goes through `lib/coords.ts`:

```
computeFit(imageW, imageH, containerW, containerH) -> ImageFit
toScreenCoords(point, fit)   // image px -> stage px
toImageCoords(point, fit)    // stage px -> image px
focusPath(nodes, fit)        // SVG path in stage px
```

No component does its own scaling maths. The heatmap composites on `<canvas>`
for pixel accuracy (per the SDS's Sprint 3 note preferring Canvas over CSS); the
focus nodes and gaze path sit on an absolutely-positioned SVG layer above it.
