# Project artifacts: choose, don't collect

> **The decision source is `pakem audit` output.** This file explains the reasoning, canonical choices, and catalog; it is not a second audit list. If they differ, `audit` wins.

Read it when `pakem audit` shows gaps, when you are about to hand over, or when the user asks "which files should exist". Do not load it for ordinary coding tasks.

Principle: **an empty file is worse than a missing file.** Artifacts exist because there is a real risk to prevent, not because they are on a list.

## How to choose

Three questions, in order:

1. Without this, would the next session/agent have to guess? → **REQUIRED**
2. Without this, can the "finished" claim not be proven again? → **REQUIRED**
3. If absent, is the risk greater than the cost of creating and maintaining it? → **RECOMMENDED**

Everything else is **NOT NEEDED**. For the RECOMMENDED ones, defer with an honest reason (in `pakem step` or `PROJECT.md`), not with an empty file.

## Map by failure mode

### Power outage, terminal closed, model stops mid-run

| Need | Artifact/action |
|---|---|
| Last position | `pakem step "<selesai>" --next "<berikutnya>"` as often as possible |
| History | `.pakem/sessions/*.json` (atomic, do not commit) |
| Context | `.pakem/CONTEXT.md` + `PROJECT.md` |
| Decisions | `docs/adr/` when the decision is expensive to reverse |
| Repo check | small git commits; `pakem start` compares HEAD + changed files |

Rule: record a `step` every time you stop for more than a few minutes, before a risky operation, and before handing off a task. A session without steps = a resume without granularity.

### New person joins / handover

| Need | Artifact |
|---|---|
| Start | `README.md` (setup, run, test) + `.env.example` |
| Code map | `.pakem/MODULE-MAP.md`, `ARCHITECTURE.md` if the system is large |
| Rationale | `docs/adr/` |
| Status & remaining work | **one** `HANDOVER.md` (status, access, contacts, what is unfinished, risks) |
| Access | a section in `HANDOVER.md`; `docs/ACCESS.md` only if the access is complex |
| Honest condition | `KNOWN_ISSUES` and `TECH_DEBT` sections in `HANDOVER.md`, not two separate files |
| Terminology | `GLOSSARY.md` only if the domain really is unfamiliar |

### Incident / system down

`RUNBOOK.md` (symptom → check → action → escalation), `docs/MONITORING.md` (dashboards, alerts, who gets paged), `INCIDENTS.md` or `docs/postmortems/` after the first incident. Do not create them before there is a production system.

### Release / deploy

The same `verify` as CI, lockfile, `.env.example`, `.gitattributes`, `CHANGELOG.md`, `DEPLOYMENT.md` (including rollback), `RUNBOOK.md`. Pick one CI system. `.github/workflows/` is only needed once there is a deploy target or a team; `pakem ci` generates a workflow that runs `pakem check` (verify stays the single source).

### Public / community repo

`LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, PR/issue templates. `SUPPORT.md`, `GOVERNANCE.md`, `MAINTAINERS.md`, `FUNDING.yml` only once the community actually exists.

### Sensitive data / compliance

`SECURITY.md`, `docs/THREAT_MODEL.md` or `docs/SECURITY_CHECKLIST.md`, secret/dependency scans, `PRIVACY.md`/`docs/COMPLIANCE.md` if there is personal data. Set `sensitive: true` in `PROJECT.md` so the security checklist in `conventions.md` is active.

### Library / API

`examples/`, `openapi.yaml` or `docs/api/`, `CITATION.cff` only for research/academic projects.

## Canonical choices (never both)

| Concern | Use | Don't also create |
|---|---|---|
| ADR | `docs/adr/` | `docs/decisions/` |
| New ESLint | `eslint.config.js` (flat) | `.eslintrc` |
| Dependency updates | `.github/dependabot.yml` | `renovate.json` (pick one) |
| Env | `.env.example` | `.env.*.example` without a real difference |
| Lockfile | one, matching the package manager | a second lockfile / ignoring it for an app |
| CI | one system | GitHub Actions + GitLab CI at the same time |
| Handover | one `HANDOVER.md` with sections | separate `ACCESS` + `KNOWN_ISSUES` + `TECH_DEBT` + `HANDOVER` |
| Runtime version | `.nvmrc` or `.node-version` | both |
| Container | `Dockerfile` + `docker-compose.yml` | dev/prod variants before you need them |
| API docs | `openapi.yaml` for HTTP | a `docs/api/` that copies the same content |

## Never create automatically

`FUNDING.yml`, `GOVERNANCE.md`, `MAINTAINERS.md`, `CITATION.cff`, `CODEOWNERS`, `labeler.yml`, `release.yml`, `sonar-project.properties`, `codeclimate.yml`, `devbox.json`/`flake.nix`, `k8s/`, `helm/`, `terraform/`, `ansible/`, `docs/postmortems/`, `docs/PRD.md`, `docs/SRS.md`, `docs/SLA.md`, `docs/STAKEHOLDERS.md`, `THIRD_PARTY_LICENSES.md`, `CLA.md`, `PRIVACY.md`, `docs/COMPLIANCE.md`, `docs/BACKUP_RESTORE.md`.

Create them only when the trigger appears: the first deploy, the first public release, the first incident, the first external contributor, the first handover, or the first personal data.

## Related Pakem commands

- `pakem audit` — sorts REQUIRED/RECOMMENDED/NOT NEEDED by `type`, `exposure`, `deploy`, `handover`, `sensitive`, and repo contents. Read-only; creates no files.
- `pakem doctor` — checks the setup (config, placeholder, git, hooks, adapters, sessions) before blaming the code.
- `pakem ci` — generates a CI workflow that runs `pakem check`, so `verify` is not duplicated.
- `pakem audit --json` — for agents that want to process the results.
- `pakem spec` / `pakem spec --approve` — spec container + approval; `finish` rejects drafts.
- `pakem plan add/done/drop` — small tasks with files+verify; `finish` rejects open tasks.
- `pakem adr "judul"` — one decision, one ADR.
- `pakem bug ...` — one bug, one entry; do not rewrite it in `KNOWN_ISSUES` without a reason.
- `pakem finish` — continuity/verification gate; prints `[WARN] risk:` for gaps matching the flags, without failing the session. It does not judge documentation completeness.
