# Agent Note: Keep a joined CLI writer after a transient read timeout

Status: implemented

## Problem

The native Goal completion event can arrive while a background `thread/read` refresh is pending. The refresh worker treated every app-server read failure as proof that the joined writer was gone. A timed-out read therefore cleared the CLI join and made the phone history-only even when the proxy and daemon connection remained live.

## Decision

Preserve the joined session on `AppServerUnavailable` from a background refresh. Retry that replay-safe read in one worker with bounded backoff so the final turn can converge without another native event, including after more than one timeout. Each worker is tied to its original joined process and has a cancellation event. Closing or revoking that join wakes a sleeping worker and prevents it from reading a later connection. The proxy's actual disconnect callback still clears all joins; an explicit `notLoaded` or identity mismatch still invalidates the affected thread. No write is replayed.

## Evidence and limits

An isolated native Codex 0.162.1 loopback Goal turn and explicit `complete` transition stayed connected and editable. Completion alone did not reproduce the user's disconnect. A deterministic adapter test reproduced the reported history-only state when `thread/read` timed out after a completed Goal event; the change keeps the live writer and converges the completed turn after two timeouts without any later event.

The reported chat is CLI-origin but Desktop-owned in the latest read-only snapshot. A dual-process isolated fixture showed the Goal sidecar set and clear a Goal without stealing the owning process's writer. A service fixture reproduced a history-only window followed by automatic Desktop reattachment after an owner-disconnect event; it does not prove that such an event caused the user's incident. Connection-transition logs now record only the opaque thread ID and a fixed reason category, distinguishing Desktop client/IPC loss, snapshot validation, and native thread/proxy loss without logging chat text, prompts, credentials, or provider details.

## Alternatives considered

Invalidating on every refresh failure simplifies recovery but abandons a writer that remains alive. Retaining every failed connection would hide real disconnects; only read failures retry while the same joined process remains valid.

## Consequences

A stale read cannot overwrite a replacement connection or a newer turn event. Backoff bounds repeated read work. The original production trigger remains unproven; the fix covers reproduced timeout and ordering races.
