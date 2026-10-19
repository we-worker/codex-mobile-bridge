# Agent Note: Create Codex CLI chats from known project folders

Status: implemented

## Problem

The New chat dialog only creates Codex App chats from saved App projects. A folder used only by Codex CLI, such as an existing terminal project, cannot be selected for a new phone chat.

## Decision

Expose Codex App and Codex CLI as explicit chat types. CLI folder choices come from saved CLI-origin chat metadata on the selected local or SSH host; listing choices only reads metadata. The CLI creation request is keyed by type, host, folder and request ID. It connects to the existing native CLI daemon only after the user submits the form, creates a persistent thread with the selected cwd and CLI source, then names and reads that thread. It does not start a turn or open the desktop App. The native CLI connection identifies distinctly as `codex-mobile-bridge-cli`; this exact originator is classified as CLI after a gateway restart. The installed 0.162.1 daemon accepts `threadSource: cli` but persists `source: vscode`, so the originator is needed for discovery. Existing `codex-mobile-bridge` rows are not classified as CLI. The runtime chooses the provider and authentication for the selected cwd.

## Verification

Source tests cover the explicit `thread/start` call, known-folder selection, duplicate requests and unchanged App creation. An isolated Codex CLI 0.162.1 loopback fixture created a CLI chat through the authenticated HTTP API; a fresh store read confirmed CLI origin and the selected cwd/provider, and a send completed through the native daemon. The saved rollout contained a user message and an assistant message after the fixture emitted output item events. The native live `thread/read` fixture returned an empty item list, so the connected live view did not display the assistant item; that fixture limitation does not affect saved-history discovery.

## Alternatives considered

Opening the App for every new chat reuses the existing path but cannot create a CLI-owned chat. A free-form arbitrary directory field broadens project selection beyond known configuration. Explicit chat type and discovered CLI folders preserve the user-selected execution context.

## Consequences

The old desktop create API remains compatible when kind is omitted. An unknown CLI create outcome keeps its receipt rather than creating another thread. Actual 390px English UI acceptance creates a CLI chat, sends a message, displays the reply, and has no horizontal overflow.
