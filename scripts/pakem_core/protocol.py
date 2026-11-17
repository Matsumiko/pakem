"""Stable Pakem Protocol contracts and peer capability negotiation.

Pakem protocol versioning is independent from external transports such as MCP.
The v1.0 event/session wire contract is frozen; new features are negotiated as
capabilities rather than silently changing existing event envelopes.
"""
from __future__ import annotations

from typing import Iterable

PROTOCOL_NAME = "pakem"
PROTOCOL_VERSION = "1.0"
SUPPORTED_VERSIONS = ("1.0",)
CAPABILITIES = {
    "events.v1": "Append-only JSONL event envelope v1",
    "events.integrity.v1": "Hash-chained ledger events with optional Ed25519 seals",
    "sessions.v1": "Persistent session metadata v1",
    "context.snapshot.v1": "Read-only structured project and workflow context snapshot",
    "runtime.v1": "Workflow state machine, checkpoints, and policy decisions",
    "intelligence.graph.v1": "Static local dependency graph",
    "intelligence.impact.v1": "Change impact analysis",
    "coordination.v1": "Shared multi-agent task board and leases",
    "coordination.review.v1": "Independent review before task completion",
    "git.worktree.v1": "Isolated Git worktree lifecycle adapter",
    "mcp.stdio.2026-07-28": "MCP modern stateless stdio adapter",
    "identity.ed25519.v1": "Agent public-key identity and signed Pakem attestations",
    "identity.delegation.v1": "Audience/action-scoped Ed25519 delegation tokens with expiry",
    "coordination.sqlite.v1": "Transactional local SQLite coordination backend",
    "conformance.v1": "Protocol and runtime conformance test profile v1",
}


def negotiate(peer_version: str, peer_capabilities: Iterable[str] | None = None) -> dict:
    """Negotiate a Pakem protocol version and feature intersection."""
    if not isinstance(peer_version, str) or not peer_version.strip():
        raise ValueError("peer_version must be a non-empty string")
    peer_version = peer_version.strip()
    peer = []
    for item in peer_capabilities or []:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("peer_capabilities must contain non-empty strings")
        if item.strip() not in peer:
            peer.append(item.strip())
    compatible = peer_version in SUPPORTED_VERSIONS
    common = sorted(set(peer) & set(CAPABILITIES))
    unsupported = sorted(set(peer) - set(CAPABILITIES))
    return {
        "protocol": PROTOCOL_NAME,
        "local_version": PROTOCOL_VERSION,
        "peer_version": peer_version,
        "compatible": compatible,
        "selected_version": PROTOCOL_VERSION if compatible else None,
        "supported_versions": list(SUPPORTED_VERSIONS),
        "common_capabilities": common,
        "unsupported_peer_capabilities": unsupported,
        "local_capabilities": sorted(CAPABILITIES),
        "notes": [
            "Event envelope v1.0 stays stable; new extensions are negotiated through capabilities.",
            "A capability only declares contract support, not authorization to perform side effects.",
        ],
    }
