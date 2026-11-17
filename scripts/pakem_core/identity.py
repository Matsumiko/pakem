"""Ed25519 identities and signed Pakem attestations.

Private keys live outside the project in the user's config directory. The
project stores only public keys and revocation metadata. This module does not
provide transport authentication by itself; a trusted host must bind verified
identity claims to the actual caller.
"""
from __future__ import annotations

import base64
import contextlib
import functools
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

FORMAT = "pakem.signed-payload.v1"
ALGORITHM = "Ed25519"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _crypto():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Ed25519 requires the 'cryptography' package; install it with: python -m pip install cryptography") from exc
    return Ed25519PrivateKey, Ed25519PublicKey, serialization


def _safe_id(value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value) or value in {".", ".."}:
        raise ValueError("agent ID is not valid")
    return value


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    if not isinstance(value, str) or len(value) > 16384:
        raise ValueError("base64 value is not valid")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise ValueError("base64 value is not valid") from exc


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextlib.contextmanager
def _registry_lock(root: str | Path):
    directory = Path(root).resolve() / ".pakem" / "identity"
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".registry.lock"
    if lock_path.is_symlink():
        raise ValueError("identity registry lock must not be a symlink")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    stream = os.fdopen(fd, "r+b", buffering=0)
    try:
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            if stream.read(1) == b"":
                stream.seek(0)
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            while True:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def _locked_registry(function):
    @functools.wraps(function)
    def wrapped(root, *args, **kwargs):
        with _registry_lock(root):
            return function(root, *args, **kwargs)
    return wrapped


def registry_path(root: str | Path) -> Path:
    return Path(root).resolve() / ".pakem" / "identity" / "registry.json"


def _project_key_namespace(root: str | Path) -> str:
    canonical = str(Path(root).resolve()).encode("utf-8", errors="surrogatepass")
    return hashlib.sha256(canonical).hexdigest()[:24]


def private_key_path(root: str | Path, agent_id: str, key_id: str | None = None) -> Path:
    agent_id = _safe_id(agent_id)
    if key_id is not None and (not isinstance(key_id, str) or not re.fullmatch(r"[a-f0-9]{16}", key_id)):
        raise ValueError("key ID is not valid")
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")) / "Pakem"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "pakem"
    suffix = f".{key_id}" if key_id else ""
    return base / "identities" / _project_key_namespace(root) / f"{agent_id}{suffix}.ed25519"


def _atomic_write(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        try:
            os.fchmod(fd, mode)
        except OSError:
            pass
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _load_registry(root: str | Path, create: bool = False) -> dict:
    path = registry_path(root)
    if path.is_symlink():
        raise ValueError("identity registry must not be a symlink")
    if not path.exists():
        if not create:
            return {"schemaVersion": 1, "agents": {}}
        registry = {"schemaVersion": 1, "updatedAt": _stamp(), "agents": {}}
        _save_registry(root, registry)
        return registry
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"identity registry is invalid: {exc}") from exc
    if not isinstance(registry, dict) or registry.get("schemaVersion") != 1 or not isinstance(registry.get("agents"), dict):
        raise ValueError("identity registry does not match schema v1")
    for agent_id, item in registry["agents"].items():
        _safe_id(agent_id)
        if not isinstance(item, dict) or item.get("agentId") != agent_id or item.get("algorithm") != ALGORITHM:
            raise ValueError(f"registry entry {agent_id} is not valid")
        try:
            public_raw = _unb64(item.get("publicKey"))
        except ValueError as exc:
            raise ValueError(f"registry public key for {agent_id} is not valid") from exc
        if len(public_raw) != 32 or hashlib.sha256(public_raw).hexdigest() != item.get("fingerprint"):
            raise ValueError(f"registry public key/fingerprint for {agent_id} does not match")
        key_id = item.get("keyId")
        if key_id is not None and (not isinstance(key_id, str) or not re.fullmatch(r"[a-f0-9]{16}", key_id)
                                   or key_id != item.get("fingerprint", "")[:16]):
            raise ValueError(f"registry keyId for {agent_id} is not valid")
        if item.get("revokedAt") is not None and not isinstance(item.get("revokedAt"), str):
            raise ValueError(f"registry revokedAt for {agent_id} is not valid")
        previous = item.get("previousKeys", [])
        if not isinstance(previous, list):
            raise ValueError(f"registry previousKeys for {agent_id} must be an array")
        for retired in previous:
            if not isinstance(retired, dict):
                raise ValueError(f"registry previous key for {agent_id} is not valid")
            retired_public = _unb64(retired.get("publicKey"))
            if len(retired_public) != 32 or hashlib.sha256(retired_public).hexdigest() != retired.get("fingerprint"):
                raise ValueError(f"registry previous public key for {agent_id} does not match")
    return registry


def _save_registry(root: str | Path, registry: dict) -> None:
    registry["updatedAt"] = _stamp()
    path = registry_path(root)
    # Public keys/revocations are intentionally readable and may be committed
    # so peers can verify signed payloads. Private keys never live here.
    _atomic_write(path, (_canonical(registry) + b"\n"), 0o644)
    try:
        os.chmod(path.parent, 0o755)
        os.chmod(path, 0o644)
    except OSError:
        pass


@_locked_registry
def create(root: str | Path, agent_id: str, replace: bool = False,
           key_out: str | Path | None = None) -> dict:
    agent_id = _safe_id(agent_id)
    Private, _, serialization = _crypto()
    registry = _load_registry(root, create=True)
    existing = registry["agents"].get(agent_id)
    if existing and not replace:
        raise ValueError(f"identity for agent {agent_id} already exists")
    private = Private.generate()
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    fingerprint = hashlib.sha256(public_raw).hexdigest()
    key_id = fingerprint[:16]
    key_path = Path(key_out).expanduser() if key_out else private_key_path(root, agent_id, key_id)
    if key_path.exists() and not replace:
        raise ValueError(f"private key already exists: {key_path}; use a deliberate backup/rotate")
    private_raw = private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                        serialization.NoEncryption())
    _atomic_write(key_path, private_raw, 0o600)
    registry["agents"][agent_id] = {
        "agentId": agent_id, "algorithm": ALGORITHM, "publicKey": _b64(public_raw),
        "fingerprint": fingerprint, "keyId": key_id, "createdAt": _stamp(), "revokedAt": None,
        "previousKeys": [],
    }
    _save_registry(root, registry)
    return {"agentId": agent_id, "algorithm": ALGORITHM, "fingerprint": fingerprint,
            "publicKey": _b64(public_raw), "privateKeyPath": str(key_path),
            "privateKeyPermissions": "0600", "registryPath": str(registry_path(root)),
            "warning": "Store a backup of the private key securely. The private key is not stored in the project."}


@_locked_registry
def import_public(root: str | Path, agent_id: str, public_key: str,
                  replace: bool = False) -> dict:
    """Register a public key owned by another host (e.g. a seal key in CI).

    Private keys never enter the repo: the registry stores only public keys, so
    verification still works anywhere while signing is possible only for the
    holder of the original key.
    """
    agent_id = _safe_id(agent_id)
    _, Public, _ = _crypto()
    try:
        public_raw = _unb64(public_key.strip())
    except Exception as exc:
        raise ValueError("public key must be 32-byte Ed25519 base64") from exc
    if len(public_raw) != 32:
        raise ValueError("Ed25519 public key must be exactly 32 bytes")
    try:
        Public.from_public_bytes(public_raw)
    except Exception as exc:
        raise ValueError(f"public key is not valid: {exc}") from exc
    registry = _load_registry(root, create=True)
    if agent_id in registry["agents"] and not replace:
        raise ValueError(f"identity for agent {agent_id} already exists; use rotate or replace")
    fingerprint = hashlib.sha256(public_raw).hexdigest()
    registry["agents"][agent_id] = {
        "agentId": agent_id, "algorithm": ALGORITHM, "publicKey": _b64(public_raw),
        "fingerprint": fingerprint, "keyId": fingerprint[:16], "createdAt": _stamp(),
        "revokedAt": None, "previousKeys": [], "privateKeyOnThisHost": False,
    }
    _save_registry(root, registry)
    return {"agentId": agent_id, "fingerprint": fingerprint, "publicKey": _b64(public_raw),
            "registryPath": str(registry_path(root)),
            "note": "private key was not imported; signing must use --key on the host that owns the key"}


@_locked_registry
def rotate(root: str | Path, agent_id: str, reason: str = "") -> dict:
    """Rotate an agent's signing key while retaining retired public-key metadata."""
    agent_id = _safe_id(agent_id)
    Private, _, serialization = _crypto()
    registry = _load_registry(root)
    item = registry["agents"].get(agent_id)
    if not item:
        raise ValueError(f"identity for agent {agent_id} has not been created")
    if item.get("revokedAt"):
        raise ValueError(f"identity for agent {agent_id} is revoked; recreate it through the provisioning procedure")
    old_key_path = private_key_path(root, agent_id, item.get("keyId"))
    if not old_key_path.is_file():
        raise ValueError(f"active private key for agent {agent_id} is not available on this host")
    old_raw = old_key_path.read_bytes()
    if len(old_raw) != 32:
        raise ValueError("old Ed25519 private key is not valid")
    old_private = Private.from_private_bytes(old_raw)
    old_public = old_private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    old_fingerprint = hashlib.sha256(old_public).hexdigest()
    if old_fingerprint != item.get("fingerprint"):
        raise ValueError("active private key does not match the public registry; rotation aborted")

    new_private = Private.generate()
    new_private_raw = new_private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                                serialization.NoEncryption())
    new_public = new_private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    new_fingerprint = hashlib.sha256(new_public).hexdigest()
    new_key_id = new_fingerprint[:16]
    new_key_path = private_key_path(root, agent_id, new_key_id)
    if new_key_path.exists():
        raise ValueError("rotation target key file already exists; not overwritten")
    _atomic_write(new_key_path, new_private_raw, 0o600)
    retired = {"fingerprint": item["fingerprint"], "publicKey": item["publicKey"],
               "keyId": item.get("keyId"), "retiredAt": _stamp(), "reason": str(reason)[:300]}
    item.setdefault("previousKeys", []).append(retired)
    item.update({"publicKey": _b64(new_public), "fingerprint": new_fingerprint,
                 "keyId": new_key_id, "rotatedAt": _stamp()})
    _save_registry(root, registry)
    return {"agentId": agent_id, "oldFingerprint": old_fingerprint,
            "newFingerprint": new_fingerprint, "newPrivateKeyPath": str(new_key_path),
            "retiredPublicKeys": len(item["previousKeys"]),
            "warning": "The old private key was not deleted automatically; delete or archive it securely per organizational policy."}


@_locked_registry
def list_identities(root: str | Path) -> dict:
    registry = _load_registry(root)
    agents = []
    for agent_id, item in sorted(registry["agents"].items()):
        agents.append({"agentId": agent_id, "algorithm": item.get("algorithm"),
                       "fingerprint": item.get("fingerprint"), "createdAt": item.get("createdAt"),
                       "rotatedAt": item.get("rotatedAt"), "retiredKeyCount": len(item.get("previousKeys", [])),
                       "revokedAt": item.get("revokedAt"), "active": not bool(item.get("revokedAt"))})
    return {"schemaVersion": 1, "agents": agents, "count": len(agents)}


@_locked_registry
def revoke(root: str | Path, agent_id: str, reason: str = "") -> dict:
    agent_id = _safe_id(agent_id)
    registry = _load_registry(root)
    item = registry["agents"].get(agent_id)
    if not item:
        raise ValueError(f"identity for agent {agent_id} not found")
    if not item.get("revokedAt"):
        item["revokedAt"] = _stamp()
        item["revocationReason"] = str(reason)[:300]
        _save_registry(root, registry)
    return {"agentId": agent_id, "revokedAt": item["revokedAt"], "revoked": True}


def _load_private_key(path: Path, Private, serialization):
    """The key may be 32 raw bytes (Pakem format) or PEM PKCS8."""
    raw = path.read_bytes()
    if raw.lstrip().startswith(b"-----BEGIN"):
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        try:
            key = load_pem_private_key(raw, password=None)
        except Exception as exc:
            raise ValueError(f"PEM private key cannot be read: {exc}") from exc
        if not hasattr(key, "public_key") or key.public_key().__class__.__name__ != "Ed25519PublicKey":
            raise ValueError("PEM private key is not Ed25519")
        return key
    if len(raw) != 32:
        raise ValueError("Ed25519 private key must be exactly 32 bytes (raw) or PEM PKCS8")
    return Private.from_private_bytes(raw)


@_locked_registry
def sign(root: str | Path, agent_id: str, payload: Any,
         key_path: str | Path | None = None) -> dict:
    """Sign a payload as agent_id.

    `key_path` lets the private key live outside the host config directory (e.g. a
    mounted CI secret): the registry still holds the public key, so the signature
    can still be verified elsewhere without carrying the private key.
    """
    agent_id = _safe_id(agent_id)
    Private, _, serialization = _crypto()
    registry = _load_registry(root)
    item = registry["agents"].get(agent_id)
    if not item:
        raise ValueError(f"identity for agent {agent_id} has not been created")
    if item.get("revokedAt"):
        raise ValueError(f"identity for agent {agent_id} is revoked")
    source = Path(key_path).expanduser() if key_path else private_key_path(root, agent_id, item.get("keyId"))
    if not source.is_file():
        raise ValueError(f"private key for agent {agent_id} is not available: {source}")
    private = _load_private_key(source, Private, serialization)
    public_raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    fingerprint = hashlib.sha256(public_raw).hexdigest()
    if fingerprint != item.get("fingerprint") or _b64(public_raw) != item.get("publicKey"):
        raise ValueError("private key does not match the public key in the registry")
    payload_bytes = _canonical(payload)
    unsigned = {"format": FORMAT, "algorithm": ALGORITHM, "agentId": agent_id,
                "fingerprint": fingerprint, "payload": payload,
                "payloadSha256": hashlib.sha256(payload_bytes).hexdigest()}
    signature = private.sign(_canonical(unsigned))
    return {**unsigned, "signature": _b64(signature)}


@_locked_registry
def verify(root: str | Path, envelope: dict, audience: str | None = None,
           action: str | None = None, check_expiry: bool = True) -> dict:
    _, Public, _ = _crypto()
    if not isinstance(envelope, dict) or envelope.get("format") != FORMAT or envelope.get("algorithm") != ALGORITHM:
        raise ValueError("unknown signed envelope format/algorithm")
    agent_id = _safe_id(envelope.get("agentId"))
    registry = _load_registry(root)
    item = registry["agents"].get(agent_id)
    if not item:
        raise ValueError(f"public identity for {agent_id} is not known")
    if item.get("revokedAt"):
        raise ValueError(f"identity {agent_id} is revoked")
    if envelope.get("fingerprint") != item.get("fingerprint"):
        raise ValueError("signed envelope fingerprint does not match the registry")
    payload = envelope.get("payload")
    payload_hash = hashlib.sha256(_canonical(payload)).hexdigest()
    if payload_hash != envelope.get("payloadSha256"):
        raise ValueError("payload digest does not match")
    unsigned = {key: envelope.get(key) for key in
                ("format", "algorithm", "agentId", "fingerprint", "payload", "payloadSha256")}
    try:
        public = Public.from_public_bytes(_unb64(item["publicKey"]))
        public.verify(_unb64(envelope.get("signature")), _canonical(unsigned))
    except Exception as exc:
        raise ValueError("invalid Ed25519 signature") from exc

    # Token claims are optional for ordinary attestations. If present, enforce
    # expiry and optional audience/action constraints after signature checks.
    claims = payload if isinstance(payload, dict) else {}
    if claims.get("type") == "pakem.delegation.v1":
        if claims.get("subject") != agent_id:
            raise ValueError("delegation subject differs from the signing identity")
        if not isinstance(claims.get("actions"), list) or not claims["actions"] or any(not isinstance(x, str) for x in claims["actions"]):
            raise ValueError("delegation actions are not valid")
        try:
            issued_at = datetime.fromisoformat(str(claims["issuedAt"]).replace("Z", "+00:00"))
            expires_at = datetime.fromisoformat(str(claims["expiresAt"]).replace("Z", "+00:00"))
            if issued_at.tzinfo is None:
                issued_at = issued_at.replace(tzinfo=timezone.utc)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError) as exc:
            raise ValueError("delegation timestamps are not valid") from exc
        if expires_at <= issued_at or expires_at - issued_at > timedelta(days=1):
            raise ValueError("delegation lifetime is not valid (maximum 24 hours)")
        if issued_at > datetime.now(timezone.utc) + timedelta(minutes=2):
            raise ValueError("delegation is not yet valid (issuedAt is in the future)")
    if check_expiry and claims.get("expiresAt"):
        try:
            expiry = datetime.fromisoformat(str(claims["expiresAt"]).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError("token expiresAt is not valid") from exc
        if expiry <= datetime.now(timezone.utc):
            raise ValueError("signed token has expired")
    if audience is not None and claims.get("audience") != audience:
        raise ValueError("token audience does not match")
    if action is not None and action not in claims.get("actions", []):
        raise ValueError("token does not allow the requested action")
    return {"valid": True, "agentId": agent_id, "fingerprint": item["fingerprint"],
            "payload": payload, "token": bool(claims.get("expiresAt"))}


def issue_token(root: str | Path, agent_id: str, audience: str,
                actions: list[str], ttl_seconds: int = 900) -> dict:
    if not isinstance(audience, str) or not audience.strip() or len(audience) > 200:
        raise ValueError("audience must be a non-empty string of at most 200 characters")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or not 30 <= ttl_seconds <= 86400:
        raise ValueError("ttl_seconds must be 30-86400")
    clean_actions = []
    if not isinstance(actions, list) or not actions or len(actions) > 50:
        raise ValueError("actions must be an array of 1-50 items")
    for value in actions:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
            raise ValueError("each action must be non-empty text of at most 100 characters")
        if value.strip() not in clean_actions:
            clean_actions.append(value.strip())
    issued = datetime.now(timezone.utc)
    payload = {"type": "pakem.delegation.v1", "subject": _safe_id(agent_id),
               "audience": audience.strip(), "actions": clean_actions,
               "issuedAt": issued.isoformat(timespec="seconds"),
               "expiresAt": (issued + timedelta(seconds=ttl_seconds)).isoformat(timespec="seconds"),
               "tokenId": str(uuid.uuid4())}
    return sign(root, agent_id, payload)
