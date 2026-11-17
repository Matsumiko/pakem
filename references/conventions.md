# Pakem conventions

Read only when needed. General principle: **proportional**. Structure follows the size and type of the project, not the other way around.

## Project artifacts

Do not create empty documents to make the repo look complete. Run `pakem audit` to sort REQUIRED / RECOMMENDED / NOT NEEDED; do the REQUIRED ones, defer the RECOMMENDED ones with a reason. Canonical choices and the list of files that must not be created automatically are in `references/artifacts.md`.

## Modularization (`app` and `library` projects)

- One module, one responsibility. If the name needs the word "and", split it.
- Thin entry points: they only wire modules together, with no business logic.
- One-way dependencies (e.g. handlers to services to repositories). No circular imports.
- Reasonable bounds: files above ~300 lines or functions above ~50 lines are a signal to split, not an absolute law.
- The structure of `tests/` mirrors the structure of the source.
- Small projects: do not force 10 folders. Three clear files are better than an empty layered structure.
- Every new module is recorded in `MODULE-MAP.md` with its path in backticks.

## When tests are mandatory

- Mandatory: there is logic, state, parsing, or integration (app, service, library).
- May be skipped with a reason: one-off scripts, simple conversions, research projects. For `oneoff`, `verify` must still prove something (run the script on a sample input, then check that the output exists and is not empty).
- Bug test: every bug that gets fixed should have a test that fails before the fix.
- New tests go into the existing test folder. Do not create both `test/` and `tests/`; pick one and stay consistent.

## When to write an ADR

Write an ADR when a decision (a) has real alternatives, (b) is expensive to reverse, or (c) will be questioned by others later. Examples: choosing a database, framework, auth pattern, state strategy. One decision, one file via `pakem adr "judul"`. Do not write an ADR for trivial choices (variable names, import order).

Accepted decisions are not re-debated without new information. If there is new information, write a new ADR that supersedes it and change its status.

## When to write research

`docs/research/` is used when exploration results will be used again, so they are not repeated. One topic per file: question, sources, findings, conclusion.

## BUG-HISTORY format

Add via `pakem bug "title" --symptom ... --cause ... --fix ... --prevent ...`. New entries go on top automatically, each entry:

```
## BUG-NNN - short title (date)
- Symptom:
- Root cause:
- Fix:
- Prevention / test:
```

Check this file before fixing a bug: if the symptom looks similar, read the old root cause first.

## Project hygiene

- README: how to set up, run, and test; sized proportionally.
- One command each for setup, run, and test (Makefile or `scripts/`), recorded in PROJECT.md. That test command is exactly the content of `verify`.
- Config: `.env.example` exists, `.env` is in `.gitignore`, no secrets in code.
- Dependencies: versions pinned (lockfile). Adding a large dependency is recorded with its reason in an ADR.
- Linter and formatter from the start so style stays consistent across sessions and across agents.
- Git: `.gitignore` matching the stack, small commits with clear messages.
- Errors and logging: one convention, recorded in PROJECT.md under the Conventions section.

## Security checklist (active when `sensitive: true` in PROJECT.md)

This is the only security checklist. `references/reviews.md` only points here; do not copy it.

For projects with auth, payments, or personal data:

- [ ] Input from outside is validated at the system boundary
- [ ] Queries use parameters, not string concat
- [ ] Passwords are hashed with a suitable algorithm; never logged
- [ ] Secrets come only from the environment or a secret manager
- [ ] Authorization is checked server-side on every action, not just in the UI
- [ ] Personal data does not appear in logs, errors, or analytics
- [ ] Dependencies are checked for vulnerabilities before release
- [ ] There are tests for failure paths (access denied, malicious input)

Put the relevant ticks into the Definition of done section in PROJECT.md.

## Ambiguous requirements

Order: (1) ask the user if the answer significantly changes direction, (2) if not, take the most reasonable assumption and record it via `pakem step "Asumsi: ..."`. Never choose silently.

## Resume after a disconnection

`pakem start` shows the active session along with `lastPosition` and `nextStep`. Briefly verify that the repo state matches the notes (e.g. `git status`), then continue from `nextStep`. If the notes no longer match, record the correction via `step` before continuing.
