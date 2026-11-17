---
# Pakem configuration (machine-read). Format: key: value, one key per line.
# rule.* values: required | skip | when-decision | when-needed. Every skip REQUIRES a reason.*
# exposure: private | public      (private repo or published)
# deploy: none | staging | production
# handover: true | false          (will be handed over to someone else)
type: {{TYPE}}
sensitive: false
exposure: private
deploy: none
handover: false
verify: {{VERIFY}}
reason.verify: {{REASON_VERIFY}}
rule.tests: {{R_TESTS}}
reason.tests: {{REASON_TESTS}}
rule.adr: {{R_ADR}}
reason.adr: {{REASON_ADR}}
rule.research: {{R_RESEARCH}}
reason.research: {{REASON_RESEARCH}}
rule.modular: {{R_MODULAR}}
reason.modular: {{REASON_MODULAR}}
---
# {{NAME}}

{{EXISTING_NOTE}}

## Summary
[FILL: one or two sentences: what this project is and who it is for]

## Stack
[FILL: language, framework, runtime version, database]

## Commands
- Setup: [FILL: one command to prepare the environment]
- Run: [FILL: one command to run it]
- Verify: see `verify` at the top (run automatically by `finish`)

## Conventions
[FILL: code style, naming, error handling, logging, how config and secrets are managed]

## Definition of done
{{DOD}}
