# Pakem MCP Adapter v1

Pakem 1.0.0 ships a dependency-free MCP server over stdio, targeting the modern
stateless MCP specification `2026-07-28`.

## Start

Read-only (default):

```bash
python3 .pakem/pakem.py mcp serve
```

Bound multi-agent worker (host must launch this process for the authenticated
agent identity):

```bash
python3 .pakem/pakem.py mcp serve --agent-id backend --allow-write
```

The modern MCP client must put these fields inside `params._meta` on **every
request**:

- `io.modelcontextprotocol/protocolVersion`: `2026-07-28`
- `io.modelcontextprotocol/clientCapabilities`: object
- `io.modelcontextprotocol/clientInfo`: recommended object

The server implements `server/discover`, `tools/list`, and `tools/call`.
Messages are newline-delimited JSON-RPC 2.0 on stdin/stdout. Stdout is reserved
for protocol messages; diagnostics go to stderr.

## Tools

Read-only tools: `pakem.context`, `pakem.protocol.info`, `pakem.team.status`,
`pakem.team.events`, `pakem.graph`, `pakem.impact`, and `pakem.policy.check`.

With both `--agent-id` and `--allow-write`: `pakem.session.start`,
`pakem.session.step`, `pakem.session.finish`, `pakem.team.claim`,
`pakem.team.heartbeat`, `pakem.team.submit`, `pakem.team.review`, and
`pakem.team.assign`. The session tools call the project's own CLI (`start`/`step`/`finish`), so
they record events, run task verify, and return gate output — a failed `finish` is a normal result
(`ok: false`, `exit: 1`, gate lines), not a protocol error. Mutation tools bind the acting agent to the server's fixed
`--agent-id`; callers cannot pass an alternate agent ID as a tool argument.

## Trust boundary

MCP `clientInfo` is self-reported and is not authentication. `--agent-id` is
also only a process configuration value. It is trustworthy only when a trusted
host/supervisor launches the server with the correct identity and protects its
process environment and project access. Do not expose this stdio server as a
network service without a separate authenticated transport and authorization
layer.

The adapter does not expose arbitrary shell execution, deployment, raw file
writes, merge, push, or policy modification. Policy decisions are advisory
records; the host still enforces permissions and human approvals.
