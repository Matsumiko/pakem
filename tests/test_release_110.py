"""Pakem 1.1.0 conformance and production-hardening regression profile."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "pakem.py"
sys.path.insert(0, str(ROOT / "scripts"))

from pakem_core import coordination, identity, protocol  # noqa: E402

SOURCE_VERSION = re.search(r'(?m)^VERSION = "([^"]+)"',
                           (ROOT / "scripts" / "pakem.py").read_text(encoding="utf-8")).group(1)

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: F401
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import jsonschema  # noqa: F401
    # Test resolusi URN memakai Registry/Resource dari `referencing`. jsonschema
    # lama tidak menariknya sebagai dependency, jadi tanpa guard ini suite error
    # (bukan skip) di mesin yang jsonschema-nya di bawah 4.18.
    from referencing import Registry, Resource  # noqa: F401
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

NEEDS_CRYPTO = unittest.skipUnless(
    HAS_CRYPTO, "cryptography tidak terpasang: pip install cryptography (lihat requirements-dev.txt)")
NEEDS_JSONSCHEMA = unittest.skipUnless(
    HAS_JSONSCHEMA, "jsonschema/referencing tidak terpasang: pip install -r requirements-dev.txt")


def run(cwd: Path, *args: str, env=None, timeout=30):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd,
                          env=merged, text=True, capture_output=True, timeout=timeout, check=False)


class Release110Tests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name) / "project"
        self.root.mkdir()
        self.config_home = Path(self._td.name) / "config"
        self.env = {"XDG_CONFIG_HOME": str(self.config_home)}
        self._env_patcher = patch.dict(os.environ, self.env)
        self._env_patcher.start()
        result = run(self.root, "init", "--type", "oneoff", "--adapter", "none", env=self.env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def tearDown(self):
        self._env_patcher.stop()
        self._td.cleanup()

    def test_cli_version_and_capability_catalog(self):
        result = run(self.root, "--version", env=self.env)
        self.assertEqual(result.stdout.strip(), f"pakem {SOURCE_VERSION}")
        info = protocol.negotiate("1.0", ["identity.ed25519.v1", "coordination.sqlite.v1", "conformance.v1"])
        self.assertTrue(info["compatible"])
        self.assertEqual(len(info["common_capabilities"]), 3)

    @NEEDS_CRYPTO
    def test_identity_creation_keeps_private_key_outside_project(self):
        result = run(self.root, "identity", "create", "worker-a", "--json", env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        private_path = Path(data["privateKeyPath"])
        self.assertTrue(private_path.is_file())
        self.assertFalse(private_path.is_relative_to(self.root))
        registry = json.loads((self.root / ".pakem/identity/registry.json").read_text())
        self.assertEqual(registry["agents"]["worker-a"]["fingerprint"], data["fingerprint"])
        self.assertNotIn("privateKey", json.dumps(registry))

    @NEEDS_CRYPTO
    def test_signed_payload_round_trip_and_tamper_detection(self):
        identity.create(self.root, "worker-a")
        envelope = identity.sign(self.root, "worker-a", {"task": "T1", "result": "passed"})
        verified = identity.verify(self.root, envelope)
        self.assertTrue(verified["valid"])
        modified = json.loads(json.dumps(envelope))
        modified["payload"]["result"] = "forged"
        with self.assertRaisesRegex(ValueError, "digest"):
            identity.verify(self.root, modified)

    @NEEDS_CRYPTO
    def test_signed_envelope_signature_tamper_is_rejected(self):
        identity.create(self.root, "worker-a")
        envelope = identity.sign(self.root, "worker-a", {"hello": "world"})
        envelope["signature"] = "A" * 86
        with self.assertRaisesRegex(ValueError, "signature"):
            identity.verify(self.root, envelope)

    @NEEDS_CRYPTO
    def test_delegation_token_enforces_audience_and_action(self):
        identity.create(self.root, "worker-a")
        token = identity.issue_token(self.root, "worker-a", "pakem-host://worker-01", ["team.claim", "team.submit"], 300)
        self.assertTrue(identity.verify(self.root, token, "pakem-host://worker-01", "team.claim")["valid"])
        with self.assertRaisesRegex(ValueError, "audience"):
            identity.verify(self.root, token, "pakem-host://worker-02", "team.claim")
        with self.assertRaisesRegex(ValueError, "action"):
            identity.verify(self.root, token, "pakem-host://worker-01", "team.review")

    @NEEDS_CRYPTO
    def test_delegation_subject_must_match_signing_identity(self):
        identity.create(self.root, "worker-a")
        token = identity.issue_token(self.root, "worker-a", "host", ["read"], 300)
        token["payload"]["subject"] = "worker-b"
        # Keep the old signature/digest to ensure tampering is rejected before claims are trusted.
        with self.assertRaises(ValueError):
            identity.verify(self.root, token)

    @NEEDS_CRYPTO
    def test_revoked_identity_cannot_verify_old_envelopes(self):
        identity.create(self.root, "worker-a")
        envelope = identity.sign(self.root, "worker-a", {"proof": 1})
        identity.revoke(self.root, "worker-a", "retired")
        with self.assertRaisesRegex(ValueError, "revoked"):
            identity.verify(self.root, envelope)

    @NEEDS_CRYPTO
    def test_rotation_requires_explicit_operator_action(self):
        identity.create(self.root, "worker-a")
        with self.assertRaisesRegex(ValueError, "already exists"):
            identity.create(self.root, "worker-a")

    def test_json_to_sqlite_migration_preserves_state_and_event_history(self):
        coordination.initialize(self.root)
        coordination.register_agent(self.root, "lead", "lead")
        coordination.register_agent(self.root, "worker", "worker")
        coordination.add_task(self.root, "T1", "first task")
        before = coordination.read_events(self.root, limit=0)
        migrated = coordination.migrate_storage(self.root)
        self.assertTrue(migrated["migrated"])
        self.assertEqual(migrated["events"], before["total"])
        self.assertTrue((self.root / ".pakem/team/board.json").is_file())
        self.assertTrue((self.root / ".pakem/team/events.jsonl").is_file())
        after_status = coordination.status(self.root)
        self.assertEqual(after_status["tasks"][0]["taskId"], "T1")
        coordination.assign_task(self.root, "T1", "worker", "lead")
        after_events = coordination.read_events(self.root, limit=0)
        self.assertEqual(after_events["total"], before["total"] + 1)
        self.assertEqual(after_events["backend"], "sqlite")
        self.assertTrue(coordination.storage_info(self.root)["transactional_state_and_events"])

    def test_sqlite_migration_is_idempotent_and_does_not_overwrite_json_backups(self):
        coordination.initialize(self.root)
        board_before = (self.root / ".pakem/team/board.json").read_bytes()
        first = coordination.migrate_storage(self.root)
        second = coordination.migrate_storage(self.root)
        self.assertTrue(first["migrated"])
        self.assertFalse(second["migrated"])
        self.assertEqual((self.root / ".pakem/team/board.json").read_bytes(), board_before)

    def test_sqlite_cli_info_migrate_and_doctor(self):
        run(self.root, "team", "init", env=self.env)
        info = run(self.root, "team", "storage", "info", "--json", env=self.env)
        self.assertEqual(info.returncode, 0, info.stderr)
        self.assertEqual(json.loads(info.stdout)["backend"], "jsonl")
        migrate = run(self.root, "team", "storage", "migrate", "--to", "sqlite", "--json", env=self.env)
        self.assertEqual(migrate.returncode, 0, migrate.stderr)
        self.assertTrue(json.loads(migrate.stdout)["migrated"])
        doctor = run(self.root, "doctor", "--json", env=self.env)
        self.assertIn(doctor.returncode, (0, 1))
        report = json.loads(doctor.stdout)
        messages = "\n".join(x["message"] for x in report["issues"])
        self.assertIn("team storage backend: sqlite", messages)
        self.assertIn("Pakem Ed25519 identity schemas installed", messages)

    def test_competing_agents_cannot_claim_same_sqlite_task(self):
        coordination.initialize(self.root)
        coordination.register_agent(self.root, "worker-a", "worker")
        coordination.register_agent(self.root, "worker-b", "worker")
        coordination.add_task(self.root, "T1", "contended task")
        coordination.migrate_storage(self.root)
        commands = [
            [sys.executable, str(self.root / ".pakem/pakem.py"), "team", "claim", "T1", "--agent", "worker-a", "--json"],
            [sys.executable, str(self.root / ".pakem/pakem.py"), "team", "claim", "T1", "--agent", "worker-b", "--json"],
        ]
        procs = [subprocess.Popen(cmd, cwd=self.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env={**os.environ, **self.env}) for cmd in commands]
        results = [proc.communicate(timeout=20) + (proc.returncode,) for proc in procs]
        self.assertEqual(sum(1 for _, _, code in results if code == 0), 1, results)
        self.assertEqual(coordination.status(self.root)["summary"]["claimed"], 1)


    def test_sqlite_online_backup_is_valid_and_refuses_overwrite(self):
        coordination.initialize(self.root)
        coordination.register_agent(self.root, "worker", "worker")
        coordination.migrate_storage(self.root)
        output = Path(self._td.name) / "team-backup.sqlite3"
        result = coordination.backup_sqlite(self.root, output)
        self.assertTrue(result["created"])
        self.assertTrue(result["consistent_snapshot"])
        import sqlite3
        connection = sqlite3.connect(output)
        try:
            count = connection.execute("SELECT COUNT(*) FROM pakem_events").fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, "already exists"):
            coordination.backup_sqlite(self.root, output)

    def test_sqlite_backend_missing_database_is_reported_not_recreated(self):
        coordination.initialize(self.root)
        coordination.migrate_storage(self.root)
        database = self.root / ".pakem/team/team.sqlite3"
        database.unlink()
        with self.assertRaisesRegex(ValueError, "database is missing"):
            coordination.status(self.root)
        self.assertFalse(database.exists())

    def test_migration_reports_corrupt_jsonl_rows(self):
        coordination.initialize(self.root)
        coordination.register_agent(self.root, "worker", "worker")
        ledger = self.root / ".pakem/team/events.jsonl"
        with ledger.open("a", encoding="utf-8") as stream:
            stream.write("{not-json}\n")
        result = coordination.migrate_storage(self.root)
        self.assertEqual(result["corrupt_events_skipped"], 1)
        self.assertEqual(coordination.read_events(self.root, limit=0)["total"], 1)

    @NEEDS_CRYPTO
    def test_identity_cli_sign_issue_and_verify(self):
        created = run(self.root, "identity", "create", "worker-a", "--json", env=self.env)
        self.assertEqual(created.returncode, 0, created.stderr)
        payload = self.root / "payload.json"
        payload.write_text(json.dumps({"task": "T1", "status": "verified"}), encoding="utf-8")
        signed_path = self.root / "payload.signed.json"
        signed = run(self.root, "identity", "sign", "worker-a", "--file", str(payload),
                     "--output", str(signed_path), env=self.env)
        self.assertEqual(signed.returncode, 0, signed.stderr)
        verified = run(self.root, "identity", "verify", str(signed_path), "--json", env=self.env)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertTrue(json.loads(verified.stdout)["valid"])
        issue = run(self.root, "identity", "issue", "worker-a", "--audience", "pakem-host://test",
                    "--action", "team.claim", "--ttl-seconds", "300", env=self.env)
        self.assertEqual(issue.returncode, 0, issue.stderr)
        token = self.root / "token.json"
        token.write_text(issue.stdout, encoding="utf-8")
        token_verify = run(self.root, "identity", "verify", str(token), "--audience", "pakem-host://test",
                           "--action", "team.claim", "--json", env=self.env)
        self.assertEqual(token_verify.returncode, 0, token_verify.stdout + token_verify.stderr)



    @NEEDS_CRYPTO
    def test_concurrent_identity_creates_do_not_lose_registry_entries(self):
        commands = [
            [sys.executable, str(self.root / ".pakem/pakem.py"), "identity", "create", agent, "--json"]
            for agent in ("agent-a", "agent-b")
        ]
        processes = [subprocess.Popen(command, cwd=self.root, text=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, env={**os.environ, **self.env})
                     for command in commands]
        results = [process.communicate(timeout=20) + (process.returncode,) for process in processes]
        self.assertEqual([item[2] for item in results], [0, 0], results)
        registry = json.loads((self.root / ".pakem/identity/registry.json").read_text())
        self.assertEqual(set(registry["agents"]), {"agent-a", "agent-b"})

    @NEEDS_CRYPTO
    def test_identity_rotation_switches_fingerprint_and_retires_old_key(self):
        first = identity.create(self.root, "worker-a")
        old_envelope = identity.sign(self.root, "worker-a", {"generation": 1})
        rotation = identity.rotate(self.root, "worker-a", "routine rotation")
        self.assertNotEqual(first["fingerprint"], rotation["newFingerprint"])
        new_envelope = identity.sign(self.root, "worker-a", {"generation": 2})
        self.assertTrue(identity.verify(self.root, new_envelope)["valid"])
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            identity.verify(self.root, old_envelope)
        current = identity.list_identities(self.root)["agents"][0]
        self.assertEqual(current["retiredKeyCount"], 1)
        # The retired key file is retained for operator-managed cleanup, not active signing.
        self.assertTrue(Path(first["privateKeyPath"]).is_file())

    def test_sqlite_board_and_event_write_roll_back_together(self):
        from unittest.mock import patch
        coordination.initialize(self.root)
        coordination.register_agent(self.root, "lead", "lead")
        coordination.add_task(self.root, "T1", "existing")
        coordination.migrate_storage(self.root)
        before_status = coordination.status(self.root)
        before_events = coordination.read_events(self.root, limit=0)["total"]
        # Force a duplicate event_id to violate SQLite's unique constraint after the
        # board UPDATE has been attempted; the transaction must roll both back.
        existing_event = coordination.read_events(self.root, limit=1)["events"][-1]
        record = dict(existing_event)
        record["event"] = "team.task.created"
        with patch.object(coordination, "_make_coordination_event", return_value=record):
            with self.assertRaises(Exception):
                coordination.add_task(self.root, "T2", "must rollback")
        after_status = coordination.status(self.root)
        self.assertEqual(after_status["revision"], before_status["revision"])
        self.assertNotIn("T2", {task["taskId"] for task in after_status["tasks"]})
        self.assertEqual(coordination.read_events(self.root, limit=0)["total"], before_events)


    @NEEDS_CRYPTO
    def test_registry_rejects_public_key_fingerprint_mismatch(self):
        identity.create(self.root, "worker-a")
        path = self.root / ".pakem/identity/registry.json"
        registry = json.loads(path.read_text())
        registry["agents"]["worker-a"]["fingerprint"] = "0" * 64
        path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            identity.list_identities(self.root)

    @NEEDS_JSONSCHEMA
    def test_approval_store_matches_its_schema(self):
        import jsonschema
        from referencing import Registry, Resource

        run(self.root, "team", "init", "--json", env=self.env)
        run(self.root, "runtime", "init", "rilis", "--json", env=self.env)
        granted = run(self.root, "policy", "approve", "--category", "deploy", "--risk", "high",
                      "--target", "prod", "--reason", "rilis terjadwal", "--json", env=self.env)
        self.assertEqual(granted.returncode, 0, granted.stderr + granted.stdout)

        docs = {}
        for path in ROOT.rglob("*.schema.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            docs[doc["$id"]] = doc
        registry = Registry()
        for schema_id, doc in docs.items():
            registry = registry.with_resource(schema_id, Resource.from_contents(doc))

        store = json.loads((self.root / ".pakem/runtime/approvals.json").read_text(encoding="utf-8"))
        schema = docs["urn:pakem:runtime:v1:approval"]
        jsonschema.validators.validator_for(schema)(schema, registry=registry).validate(store)

        # format date-time bersifat anotasi di JSON Schema; yang ditegakkan enum/const/required.
        store["approvals"][0]["category"] = "bogus"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validators.validator_for(schema)(schema, registry=registry).validate(store)

    @NEEDS_JSONSCHEMA
    def test_schemas_resolve_offline_from_urn_ids(self):
        import jsonschema
        from referencing import Registry, Resource

        docs = {}
        for path in ROOT.rglob("*.schema.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            docs[doc["$id"]] = doc
        registry = Registry()
        for schema_id, doc in docs.items():
            registry = registry.with_resource(schema_id, Resource.from_contents(doc))

        record = {
            "schemaVersion": 1,
            "updatedAt": "2026-11-09T00:00:00+00:00",
            "agents": {
                "worker-a": {
                    "agentId": "worker-a", "algorithm": "Ed25519",
                    "publicKey": "A" * 43, "fingerprint": "a" * 64, "keyId": "b" * 16,
                    "createdAt": "2026-11-09T00:00:00+00:00", "revokedAt": None,
                    "previousKeys": [],
                }
            },
        }
        schema = docs["urn:pakem:identity:v1:identity-registry"]
        jsonschema.validators.validator_for(schema)(schema, registry=registry).validate(record)

        record["agents"]["worker-a"]["fingerprint"] = "bukan-hex"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validators.validator_for(schema)(schema, registry=registry).validate(record)

    @NEEDS_JSONSCHEMA
    def test_identity_and_storage_json_schemas_are_valid(self):
        schemas = [
            ROOT / "identity/v1/agent-identity.schema.json",
            ROOT / "identity/v1/identity-registry.schema.json",
            ROOT / "identity/v1/signed-payload.schema.json",
            ROOT / "storage/v1/team-storage.schema.json",
        ]
        for path in schemas:
            schema = json.loads(path.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator.check_schema(schema)


    def test_actual_upgrade_installs_110_modules_and_preserves_user_state(self):
        run(self.root, "team", "init", env=self.env)
        run(self.root, "team", "register", "lead", "--role", "lead", env=self.env)
        run(self.root, "team", "add", "T1", "--title", "existing task", env=self.env)
        policy_path = self.root / ".pakem/POLICY.json"
        policy = json.loads(policy_path.read_text())
        policy["autonomy"] = "manual"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        board_before = coordination.status(self.root)
        policy_before = policy_path.read_bytes()
        # Simulate an older vendored CLI with 1.0.0 and missing 1.1.0 modules.
        vendored = self.root / ".pakem/pakem.py"
        vendored.write_text(vendored.read_text().replace(f'VERSION = "{SOURCE_VERSION}"', 'VERSION = "1.0.0"', 1),
                            encoding="utf-8")
        (self.root / ".pakem/pakem_core/identity.py").unlink()
        for rel in ("identity/v1", "storage/v1", "adapters/identity", "adapters/storage-sqlite"):
            target = self.root / ".pakem" / rel
            if target.is_dir():
                import shutil
                shutil.rmtree(target)
        upgraded = run(self.root, "upgrade", "--from", str(SCRIPT), env=self.env)
        self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
        self.assertEqual(coordination.status(self.root)["boardId"], board_before["boardId"])
        self.assertEqual(policy_path.read_bytes(), policy_before)
        self.assertTrue((self.root / ".pakem/pakem_core/identity.py").is_file())
        self.assertTrue((self.root / ".pakem/identity/v1/identity-registry.schema.json").is_file())
        self.assertTrue((self.root / ".pakem/storage/v1/team-storage.schema.json").is_file())
        self.assertTrue((self.root / ".pakem/adapters/identity/v1/README.md").is_file())
        self.assertTrue((self.root / ".pakem/adapters/storage-sqlite/v1/README.md").is_file())

    def test_storage_backup_cli(self):
        coordination.initialize(self.root)
        coordination.migrate_storage(self.root)
        output = Path(self._td.name) / "cli-backup.sqlite3"
        result = run(self.root, "team", "storage", "backup", "--output", str(output), "--json", env=self.env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["consistent_snapshot"])

    def test_upgrade_installs_identity_and_storage_schemas(self):
        # A fresh init already installs them; verify the stable upgrade path too.
        result = run(self.root, "upgrade", "--dry-run", env=self.env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("identity", result.stdout)
        self.assertIn("storage", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
