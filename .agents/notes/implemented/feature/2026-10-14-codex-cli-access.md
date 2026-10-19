# Agent Note: Codex CLI discovery and explicit native access

Status: implemented

The model, Skill, plan and local Goal restrictions are superseded by [CLI session controls](2026-10-14-cli-session-controls.md); permission restrictions are superseded by [CLI permission switching](2026-10-14-cli-permission-switching.md). Editing/forking, rename and side-chat restrictions remain.

The source-based Desktop exclusion below is partially superseded by [existing-owner routing](../bug-fix/2026-10-14-cli-existing-owner.md): CLI origin is provenance, and an already active Desktop owner is reused without creating a replacement runtime.

The loaded-only connection decision below is superseded by [explicit CLI resume](2026-10-14-codex-cli-resume.md). Discovery and write-isolation decisions remain in effect.

## Problem

Session discovery accepted desktop originators only. A user-visible terminal chat with `originator=codex-tui` and `source=vscode` was excluded. SSH discovery also omitted saved managed hosts not referenced by specific project membership fields. Broadening discovery alone would send CLI-origin chats through Desktop activation and risk switching their execution owner.

## Decision

Keep saved history discovery separate from execution. SessionStore admits known CLI originators and legacy source metadata, still excluding internal subagents. List/get/notification discovery use the same source rule. AppHosts lists configured managed SSH hosts; Desktop shutdown checks retain their separate Desktop-only host set. Remote history and CLI proxy use the target user's login shell so CODEX_HOME selection follows that environment.

CLI-origin reads do not follow Desktop or resume native tasks. Explicit connection uses the official `codex app-server proxy` as a byte transport and performs WebSocket initialization against the existing control socket. It never starts a replacement daemon. Loaded-thread checks precede join and actions; provider/cwd are checked again before writes. The original runtime keeps its auth/config. Desktop snapshots for the same ID cannot take over CLI-origin writes. A restored queued submission must load authoritative source metadata before attaching.

The adapter projects native turns and requests into existing UI contracts. Supported actions are send, queue, steer, interrupt, command/file/permissions approval, input questions and supported MCP elicitation. Desktop-only configuration, goals, editing/forking, rename, Skills and side chats are rejected by the service as well as gated in the UI. The old wire format without `access` retains Desktop presentation compatibility.

Write failures with unknown outcomes are not replayed. Approval IDs are claimed before writing and quarantined on unknown outcomes until disconnect; another click cannot resend the response. Closing a viewer or gateway only closes the proxy, not the daemon or native task. The authenticated diagnostics route exports aggregate source/read status, omitting content, titles, paths, host aliases, thread IDs and credentials.

## Alternatives considered

The local approved roadmap also covers Claude Code and IDE-specific access. This implementation covers Codex CLI and SSH discovery only; the wider roadmap is not marked completed. Loading all CLI histories into a new app-server or using Desktop as a fallback was rejected because it changes execution ownership. Running only history discovery was insufficient for the accepted CLI interaction scope.

## Consequences

Official reference: https://learn.chatgpt.com/docs/app-server. Context7 was unavailable due to quota, so current official documentation and installed 0.162.1 help/protocol were used. `proxy` is raw WebSocket transport, not newline JSON. `thread/read` is passive; joining uses `thread/resume` only after explicit connection and loaded checks.

The upstream API has no atomic loaded-only resume. If the thread unloads between validation and resume, the same existing daemon may cold-load it. The code and user documentation disclose this; it is not described as a strict fail-closed owner guarantee. Pending approvals created before subscription are subject to upstream replay behavior; unsupported requests remain for the original CLI. Windows/Linux and arbitrary remote environments require native testing beyond this macOS run.

Targeted tests cover source/schema fallback, strict SSH flags, WebSocket framing/disconnect, native mapping and response identity, passive service/API access, restored queue source, capability enforcement, sanitized diagnostics and no replay. A real isolated CLI 0.162.1 TUI verified send/stream/idempotence with unchanged provider/model/cwd. Real browser actions verified explicit connect, send, interrupt and diagnostic download. User-provided existing thread was read only. Test project trust was explicitly authorized in an isolated CODEX_HOME; daily CLI trust configuration was not edited. See VERIFICATION.md for final regression/build scope.
