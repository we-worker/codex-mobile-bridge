# Agent Note: Native CLI Goal on SSH hosts

Status: implemented

## Problem

The joined CLI adapter already sends Goal RPCs through its existing app-server proxy, but Bridge and Web rejected Goal on every SSH host. This hid a compatible runtime capability and prevented Goal lifecycle controls even when the remote CLI was the verified writer.

## Decision

Offer Goal on an SSH chat only when its verified execution runtime is a connected native CLI and that same daemon confirms Goal support. Passive reads do not join the runtime. Goal reads, writes and activation turns use the joined CLI path; the host-specific Bridge data directory retains the operation ledger. An SSH chat owned by the desktop App remains without Goal controls because its follower IPC has no Goal write method. A remote Goal read never falls back to the gateway's local Goal database or a sidecar writer. The Web requires explicit remote capability fields while preserving local legacy-view behavior.

The common Goal command flow still checks expected state, records intent before writes, confirms native state, and leaves uncertain delivery unknown without replay. Create and resume activation use the existing send path and retain the thread's provider, authentication, working directory and permission settings.

## Alternatives considered

Keeping the blanket SSH restriction avoids remote version differences but blocks the already joined native daemon's supported Goal API. Reusing the gateway's local Goal sidecar for SSH would target the wrong home and risk a second writer. Exposing Goal for SSH desktop owners would promise a follower write operation that does not exist.

## Consequences

Compatible SSH native CLI sessions can create, pause, edit, resume and clear Goals. Unsupported or disconnected native runtimes and App-owned SSH sessions stay unavailable. Fixture tests cover the lifecycle, explicit capability, passive reads, unsupported runtime, ownership boundary and durable unknown-result handling. These fixtures do not establish behavior on every SSH host or Codex version; native acceptance and build results belong in [verification](../../../../VERIFICATION.md).

This extends [CLI session controls](2026-10-14-cli-session-controls.md) only for SSH native Goal. Its rules for local App owners, other controls and no-replay behavior remain in effect.
