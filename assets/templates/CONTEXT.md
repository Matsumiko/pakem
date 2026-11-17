# CONTEXT - entry point

Read this file FIRST in every session, then follow the routing below. Do not load every file at once.

## Protocol

Below, `pakem` means `python3 .pakem/pakem.py` (on Windows replace `python3` with `python` or `py -3`).

<!-- pakem:protocol:begin -->
{{PROTOCOL}}
<!-- pakem:protocol:end -->

## Routing

| If you are about to... | Read first |
|---|---|
{{ROUTING}}

## Standing rules

- Ambiguous requirement: ask the user or record the assumption through `step`. Do not guess silently.
- Existing repo: follow the existing pattern; do not reshape the structure unless asked.
- Bypassing a rule (`skip`) requires a reason in `PROJECT.md` (`reason.<name>`).
- Do not edit gates or weaken rules so that `finish` passes. Fix the root cause.
- Do not create empty files/documents to make the structure look complete; defer with a reason.
- Follow the existing module pattern before inventing a new one.
