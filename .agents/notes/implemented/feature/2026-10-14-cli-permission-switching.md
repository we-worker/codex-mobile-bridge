# Agent Note: Permission switching for joined CLI chats

Status: implemented

## Problem

[CLI session controls](2026-10-14-cli-session-controls.md) leave permissions unavailable for CLI-origin chats. A joined native CLI daemon accepts per-thread permission updates, while the existing UI gate uses the broader Desktop configuration capability. Opening that capability would also expose rename and unrelated operations. On SSH, desktop settings on the gateway computer do not describe the selected CLI runtime.

## Decision

Expose an independent `canChangePermissions` capability after a CLI chat has an active owner. App-owned chats use the existing owner IPC. Joined native CLI chats read config requirements, profiles and feature availability from their selected daemon, including the selected SSH host. Unknown or restricted options remain disabled. Full access still requires the existing explicit confirmation flag.

The native adapter sends only the selected profile, approval policy and reviewer through `thread/settings/update`. It never changes provider, authentication, cwd or global config. The requested setting does not become displayed state. The effective `thread/settings/updated` notification updates the state, and the bridge confirms the requested mode only after a later state sequence reports it. Attach projects the effective permission state from `thread/resume`; disconnect and invalidation clear adapter state before reconnect. Unsupported older daemons cannot pass capability discovery, and unknown writes are not replayed. Native CLI messages name the CLI runtime; Desktop-owned permission messages retain their existing wording.

The main permission dialog binds its options and save request to the runtime active when it opens. A chat or runtime change and a disconnect close the dialog. The optional `expectedRuntime` request field is checked under the session action lock before a setting write, so a delayed native dialog cannot write to a newly attached Desktop owner. Older clients that omit the field retain their existing request behavior.

## Alternatives considered

Enabling `canConfigure` would be a small gate change, but would expose unsupported CLI rename and other Desktop controls. Reusing local Desktop preference files for native and SSH CLI could offer a mode forbidden by the selected runtime. Projecting requested settings immediately would make a successful RPC look like proof of effective permission, even when a later policy decision differs.

## Existing-note audit

[CLI session controls](2026-10-14-cli-session-controls.md) is partially superseded only on its permission restriction; its model, Skill, plan, Goal and owner boundaries remain. Earlier [CLI access](2026-10-14-codex-cli-access.md), [cold resume](2026-10-14-codex-cli-resume.md), and [existing owner](../bug-fix/2026-10-14-cli-existing-owner.md) retain their discovery, lifecycle and ownership decisions; their permission restriction is superseded here. No proposed or rejected note covered native CLI permission switching.

## Consequences

Local and SSH native CLI chats can change ask, auto-review and full-access when their selected runtime and policy permit each choice. App-owned CLI chats keep Desktop owner validation. A native update may remain unconfirmed until the effective settings event arrives; the panel reports that state without claiming success. Targeted adapter, service, capability and UI tests pass. Socket-based HTTP fixture tests cannot bind in this sandbox; real daemon and SSH behavior require separate acceptance.

## Verification

`python -B -m unittest tests.test_codex_cli_session.CliSessionTests tests.test_cli_bridge_integration.CliBridgeTests` passes 61 tests, including reconnect state and a permission event. `PYTHONPATH=tests:. python -B -m unittest test_linux_permissions.CapabilityTests test_linux_permissions.LinuxReviewerCompatibilityTests` passes 7 policy tests. `node --test tests/cli-access-ui.test.cjs tests/linux-permissions-ui.test.cjs` passes 15 UI checks, including native and Desktop wording. Note tree, format and archived-note validators pass. HTTP fixtures that bind sockets cannot run in this sandbox. Real runtime and SSH acceptance remains separate from these fixture checks.
