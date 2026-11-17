# Pakem Policy v1

`POLICY.json` controls what a compatible host runtime may allow automatically.

- `autonomy`: `manual`, `assisted`, or `guarded_autonomous`.
- `maxAutonomousRisk`: highest risk level that may proceed without an approval when no category-specific rule requires one.
- `approvalRequiredFor`: categories that always require explicit approval.
- `deniedCategories`: categories the runtime must deny.
- `approvalTtlSeconds`: lifetime for a one-use, workflow-bound approval (30–86400 seconds).

Categories: `read`, `write`, `command`, `destructive`, `deploy`, `security`, `policy_change`, `gate_change`.

Approval is an auditable local record, not cryptographic identity or a secure human-authentication mechanism. A host agent/runtime MUST mediate `policy approve` through a genuine user-confirmation channel and MUST NOT let the agent self-approve. The CLI cannot prove who invoked it. Approval is one-use, bound to workflow ID, category, risk, and target, and expires.

The policy engine does not execute commands, edit source code, deploy, or start agents. It returns `allow`, `require_approval`, or `deny`; the host runtime remains responsible for enforcing the decision.
