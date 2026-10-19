# Agent Note: SSH Claude Code CLI sessions

Status: implemented

## Problem

The Claude CLI adapter read only this computer's native history. A selected SSH host's Claude installation, account, configuration, history and project directory could not be used from mobile.

## Decision

Reuse the App's trusted SSH host aliases and strict noninteractive SSH transport. Run a standalone standard-library worker in the remote login shell. Passive list/detail read the host's own Claude profile and JSONL history without activating a session. The gateway ID binds host ID, profile origin and native session UUID. An explicit resume rechecks profile, history, authentication, cwd, model, permission mode and native session registry, then replaces the worker with Claude's stream-json process. Model, permission, Skill, approval and interrupt controls use that process. An SSH loss leaves an uncertain write unconfirmed; the bridge never replays it automatically.

Upload IDs stay scoped to the bridge ledger. For a remote send, verified bytes are transferred through the selected SSH alias to a private immutable file under that remote Claude profile. Only the resulting remote path enters the model message. The local gateway upload path is never sent as a remote file reference. The remote profile and SSH alias must remain unchanged for later operations. No local Claude settings or credentials are copied to the host.

## Native process identity

Read-only inspection of installed Claude Code 2.1.287 found registry `procStart` produced by `LC_ALL=C TZ=UTC ps -o lstart= -p <pid>`. On Linux its `pidDomain` is `darwin:<machine-id>:<pid namespace link>`; on macOS it is `darwin`. The worker checks PID, process start and domain before resuming, failing closed on missing or mismatched evidence. A read-only probe of the existing scoped Linux SSH host confirmed `/etc/machine-id`, `/proc/self/ns/pid` and UTC/C `ps` are available and have the expected shapes. This does not constitute a native Linux Claude turn test.

## Verification and limits

Targeted Python tests cover standalone profile/history, immutable uploads, host/profile IDs, PID reuse/domain mismatch, partial host failures, background list latency, account changes, and unknown SSH write without replay. The native acceptance fixture creates an original saved session with installed Claude Code 2.1.287 and a temporary profile, then uses disposable OpenSSH and a localhost API mock to verify resume, original cwd/model/permission/auth, native model and permission controls, Skill expansion, remote file bytes and path, approval, interrupt, and a severed SSH stream reported as unknown after one write. Native user-message replay UUID confirms sends before acceptance. The fixture injects its temporary `CLAUDE_CONFIG_DIR` because the local test sshd's `SetEnv` did not propagate it. Node tests cover the existing upload and session UI. No paid Claude request, production remote profile write or native Linux Claude execution was used. Direct SSH child lifetime follows the current gateway connection; after loss, the user must inspect history and explicitly resume, with no automatic retry.
