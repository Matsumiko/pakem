# SQLite Coordination Adapter v1

Use `pakem team storage info` to inspect the current backend. Migrate explicitly with `pakem team storage migrate --to sqlite`.

The migration is one-way in this release. JSON board/event files are retained unchanged for manual backup or inspection; once `storage.json` selects SQLite, subsequent team operations use SQLite as the authoritative source. Back up `.pakem/team/` before migration. SQLite coordination is local-only and is not a multi-host lock service.
