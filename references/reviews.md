# Review lens: frontend & backend

Read before `finish` or before opening a PR, **only if** the project has a UI or `sensitive: true` in `PROJECT.md`. These are thinking lenses, not gates and not a replacement for human review.

Base rule: do not claim "already reviewed" without evidence that can be run. Write in `finish --summary` what was checked and which commands were run.

## Frontend: consistency

What is checked, as relevant:

- **Visual source of truth** — color/spacing/typography tokens and existing components. Do not create new patterns when existing components can be used.
- **Complete states** — loading, empty, error, disabled, and retry. Many UI bugs are born from states that were never designed.
- **Responsive** — layout at small, medium, and large widths; not just desktop.
- **Accessibility** — form labels, keyboard focus, tab order, contrast, `alt`, ARIA only when needed.
- **Visible performance** — images, bundle, and layout shift; measure, do not guess.
- **Text consistency** — terminology, capitalization, date/number format follow `STYLEGUIDE.md` or the conventions in `PROJECT.md`.

How to prove it:

- `verify` must include lint + typecheck; add e2e/visual tests if they already exist.
- For visual changes, run the app and look at the surface; screenshot/URL in the summary.
- Do not add a large UI/animation library without an ADR.

What is **not** Pakem's job: judging design taste. Pakem only ensures that consistency can be checked and is not forgotten.

## Backend: security

Do not duplicate the checklist. The single source is `conventions.md` section **Security checklist** (active when `sensitive: true`) — server-side authorization, boundary validation, parameterized queries, secrets, PII, password hashing, fail closed, resource limits, secret/dependency scans, and failure-path tests.

During review, focus on evidence, not on repeating the list:

- Name the commands that were run (tests, scans, curl) in the summary.
- For endpoints, test at minimum: success, invalid input, no auth, wrong auth.
- Do not write an empty `SECURITY.md`; better to have none than a false claim.

## When to stop

Fix only findings relevant to the current change. Do not expand the scope into a full security audit without user approval. Findings outside scope are recorded as `KNOWN_ISSUES`/`TECH_DEBT` (optionally as a section of `HANDOVER.md`), not fixed silently.

## Relation to Pakem

- `sensitive: true` → the security checklist in `conventions.md` is active, and `finish` warns about a missing `SECURITY.md`/threat model/scan.
- `audit` shows artifact gaps; `reviews.md` shows what is checked when those artifacts are used.
- `finish` remains evidence-based: `verify` commands and the summary, not claims.
