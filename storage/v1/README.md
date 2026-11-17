# Pakem Team Storage v1

The default backend remains `jsonl` for compatibility with older projects. Projects can explicitly migrate to the local SQLite backend:

```bash
pakem team storage info
pakem team storage migrate --to sqlite
```

SQLite stores a serialized team board and append-only protocol event records in `.pakem/team/team.sqlite3`. Each state mutation updates the board and inserts its corresponding event in one SQLite transaction. WAL mode, `synchronous=FULL`, and a busy timeout are enabled.

Migration runs under the existing project-local coordination lock. Original `board.json` and `events.jsonl` files are retained as backups; after migration, SQLite is authoritative and the old files are not updated. Back up the whole `.pakem/team/` directory before migration.

**Scope:** this backend is for a local project directory or a filesystem with reliable SQLite locking. It is not a distributed database, does not provide multi-host consensus, and should not be placed on filesystems that do not support SQLite locking/WAL semantics. For agents on separate hosts, deploy a future authenticated server-side coordination backend.
