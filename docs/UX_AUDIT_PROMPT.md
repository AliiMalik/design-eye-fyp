# UX audit prompt — DesignEye

A self-directed brief for auditing every user-facing surface. Written to be
re-runnable: re-read it after any significant UI change.

## Framing

DesignEye tells designers where people will look and how clear their work is.
A tool that critiques interfaces is held to its own standard — every flaw here
undermines the product's central claim. Audit it the way the product audits a
mockup.

Judge against what a **real person** hits, not what the happy path shows. The
happy path is already known to work; the value is in everything either side of it.

## Surfaces

Marketing and auth
- `/` landing, `/login`, `/register`, `/forgot-password`, `/reset-password`

Signed-in app
- `/dashboard`, `/projects`, `/projects/[id]`, `/upload`,
  `/results/[assetId]`, `/batches/[id]`, `/compare`, `/settings`

Framework-level
- Route error boundaries, 404, route loading states, the app shell and nav

## What counts as a gap

**1. States other than success.** For every screen that loads data, check all four:
empty (a brand-new account with zero projects, results and comparisons),
loading, error (API down, 500, network failure), and partial (some data missing).
A screen that only renders the success case is incomplete.

**2. Dead ends.** Any screen a user can reach with nothing to do next, and no
obvious way forward. Empty states must offer the action that fills them.

**3. Destructive and irreversible actions.** Deleting a project, asset or batch.
Is there confirmation? Is it recoverable? Does the user understand the blast
radius (deleting a project takes its assets with it)?

**4. Feedback.** After every action: did the user learn what happened? Silent
success is a bug. So is a spinner with no end and no cancel.

**5. Copy.** The standing instruction is plain language. Flag internal
vocabulary leaking to users, unexplained numbers, and false precision. Also flag
**overclaiming** — this product makes predictions with known limits, and the UI
must not imply certainty it does not have.

**6. Waiting.** Inference takes seconds; LLM review can take a minute. Is
progress legible? Can the user leave and come back? What happens on timeout?

**7. Responsive.** 375px, 768px, 1280px. Designers work on laptops but examiners
click on anything. Horizontal scroll on the body is a defect.

**8. Accessibility.** Full pass:
   - keyboard: every action reachable and operable, in a sensible order
   - visible focus on every interactive element
   - contrast: text and essential UI against their backgrounds
   - forms: real labels, errors tied to inputs and announced
   - images: meaningful alt text; decorative images marked as such
   - semantics: landmarks, headings in order, buttons that are buttons
   - motion: respects reduced motion
   - anything conveyed by colour alone also conveyed another way

**9. Consistency.** The same idea should look and behave the same everywhere:
score presentation, empty states, destructive actions, error tone.

**10. First-run.** Sign up with a fresh account and walk through. A new user with
no data is the harshest reviewer of an app built and demoed with seeded data.

## Method

1. Read each surface's source before judging it.
2. Exercise the real running app — the app shell renders client-side, so read the
   live DOM rather than reasoning from JSX alone.
3. Test the states that are hard to reach on purpose: empty, error, slow, tiny
   viewport, keyboard-only.
4. For each finding record: **what** the user experiences, **why** it is a
   problem, and **the fix**.

## Standards to hold

- Every fix keeps `npx tsc --noEmit` and `npx next lint` clean.
- Reuse the existing design system (`Bezel`, `Button`, the motion easing, Lucide
  at `strokeWidth={1.5}`); do not introduce a second visual language.
- Never branch rendered structure on `useReducedMotion()` — a documented trap.
- Prefer the smallest change that removes the problem.

## Out of scope

Backend behaviour, model accuracy, and score calibration. Those are tracked
separately. This audit is strictly about what the user experiences.

---

# Findings — first run, 2026-08-19

Method: read every surface's source, then exercised the running app as a
**brand-new account with zero data**, plus keyboard-only and 375px passes.

## Fixed

**1. Every form in the app was unlabelled.** `Field` rendered a bare `<label>`
with no `htmlFor`, and the control arrived as `children`, so the label was
visually present but programmatically disconnected. A screen reader announced
"edit text, blank" on login, register, settings and both password flows.
*Fix:* `Field` generates one id via `useId` and shares it through context —
context rather than `cloneElement` because the password fields nest the input
beside a show/hide button, so cloning would have put the id on the wrapper div.
The error message is now wired with `aria-describedby`, `aria-invalid` and
`role="alert"` so validation failures are announced rather than only shown.
Twelve unlabelled inputs across the app went to zero from one component change.

**2. A brand-new user was told their work scored 0.0 — "Needs work".** With no
analyses at all, the dashboard rendered `avg_clarity_score.toFixed(1)` as `0.0`
and ran it through `clarityBand()`, producing a failing grade for work that did
not exist. *Fix:* an em dash and "no analyses yet". The projects page already did
this correctly, so the two surfaces now agree — this was an inconsistency where
one side was plainly wrong.

**3. "Welcome back" greeted people who had never visited**, under a subtitle
promising insights that were "synchronised and ready for review" when there were
none. *Fix:* first-run copy that says what to do next instead.

**4. The 404 was Next's unstyled default** — no branding, no navigation, no way
back. A dead end is the one thing a 404 must not be. *Fix:* `app/not-found.tsx`
in the product's own language with two exits.

**5. There was no route error boundary at all.** An unhandled render error showed
a stack trace in development and a blank grey page in production. *Fix:*
`app/error.tsx` with a retry, a route home, and a generic message — the same
rule the API follows, since a thrown error can carry internals.

**6. Keyboard users tabbed through the entire sidebar on every navigation**
before reaching content. *Fix:* a skip link, visually hidden until focused, and
`#main` made focusable.

**7. The results page scrolled sideways on a phone.** Five view-mode tabs are
wider than 375px and were unconstrained, pushing the body to 397px. *Fix:* the
strip scrolls within itself; body overflow measured 22px before, 0 after.

**8. Implementation vocabulary on user-facing screens.** The sign-in screen sold
"bcrypt + JWT sessions", "Tenant-isolated storage" and "Sub-second inference" to
designers deciding whether to trust the product; settings explained bcrypt cost
factors and a "Redis broker". *Fix:* plain equivalents — "Your designs stay
private", "Results in seconds", "Secure sign-in", "Job queue".

**9. Destructive confirmations were inconsistent.** Deleting a project stated its
blast radius and irreversibility; deleting an asset said only `Delete "file"?`.
*Fix:* all four now state both.

## Checked and sound

- Empty states on projects, compare and the results list — clear, each with the
  action that fills them
- A missing or deleted result renders a proper explanation with retry
- Destructive actions all confirm before acting
- Batch progress is legible while screens analyse
- `html lang`, heading order, no positive `tabindex`, images carry alt text,
  buttons have accessible names
- `Button` and the input primitives already had `focus-visible` rings
- Dashboard at 375px: no overflow

## Not addressed, deliberately

- **Colour contrast was not measured programmatically.** Doing it properly needs
  a WCAG contrast pass over computed foreground/background pairs across both
  themes; worth a dedicated pass rather than a guess.
- **The settings system panel still shows model build, device and API version.**
  Arguably diagnostic rather than jargon, and useful when something breaks. Left
  as a judgement call to revisit.
