# Agent Note: Route CLI-origin chats to their existing execution owner

Status: implemented

The model, Skill, plan and local Goal restrictions are superseded by [CLI session controls](../feature/2026-10-14-cli-session-controls.md); permission restrictions are superseded by [CLI permission switching](../feature/2026-10-14-cli-permission-switching.md). Editing/forking, rename and side-chat restrictions remain.

## Problem

The CLI source marker describes where a chat began, not which process currently executes it. Blocking every Desktop snapshot for CLI origins sends App-adopted chats into a separate daemon resume, which fails with `already has an active writer`. The reported chat has a live matching Desktop owner while the daemon reports notLoaded. Previous isolated native warm/cold acceptance did not cover this case.

## Decision

Read saved history and passively discover the existing Desktop owner for CLI-origin chats. Follow only the selected owner after host/id/cwd/provider validation. Explicit continuation uses this existing connection when present; only a bounded lookup without a discovered owner allows the established native daemon path. A discovery timeout is not proof of absence: explicit native resume may still be attempted, while the native writer lock prevents competing ownership. Finding an owner but failing snapshot identity blocks that fallback. Neither pathway navigates Desktop to claim a CLI thread. Origin labels remain unchanged. Connected native sessions reject Desktop snapshots; selected Desktop sessions reject native callbacks. Disconnects invalidate only sessions using that runtime. Unknown writes are not replayed.

## Alternatives considered

Routing every CLI-origin chat to the daemon keeps source-specific behavior simple, but conflicts with actual App ownership. Removing writer locks or killing the owner would disrupt user work and is not an acceptable recovery. Always activating Desktop would change ownership of CLI-only chats and lose the existing terminal/daemon lifecycle; the native cold-resume path remains necessary.

## Existing-note audit

[CLI access](../feature/2026-10-14-codex-cli-access.md) and [cold resume](../feature/2026-10-14-codex-cli-resume.md) are partially superseded specifically on source-based routing. Discovery, diagnostics, native resume and no-replay rules still apply. Other file-reading and notification notes are unrelated.

## Verification

The reported chat connects read-only to its live Desktop owner in 0.11 seconds with saved history retained, native attach count zero and no message sent. An isolated native 0.162.1 two-process test reproduces active-writer rejection in the competing daemon and successful rejoin in the original owner; it makes no model calls. With real Desktop IPC available but no owner for the isolated CLI thread, discovery times out and explicit native cold resume succeeds. Service fixtures cover selected-owner send routing, identity rejection, native in-flight competition, stale events and disconnects. Full regression and packaged acceptance results are recorded in [VERIFICATION.md](../../../../VERIFICATION.md).

## Consequences

App IPC and native daemon protocols are separate and version-sensitive. Native Windows/Linux and arbitrary SSH hosts require their own acceptance; macOS and protocol fixtures do not establish those environments. A writer without a supported discoverable endpoint cannot safely be seized.
