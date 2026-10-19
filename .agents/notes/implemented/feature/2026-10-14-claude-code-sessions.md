# Agent Note: Continue closed local Claude Code sessions

Status: implemented

## Problem

Claude Desktop discovery does not expose terminal Claude Code chats. Reusing Desktop initialization for those chats changes their runtime and does not preserve the CLI profile, project configuration or permission mode.

## Decision

Read saved chats from the explicit CLAUDE_CONFIG_DIR, the selected Cockpit CLI instance, or the default Claude profile. A gateway ID binds the native UUID to its profile and settings fingerprint. Passive list/detail never launches a session. Existing native settings sources remain user, project and local; credentials stay in the native profile/environment.

An explicit resume validates the saved cwd and known prior permission mode, refreshes authentication evidence, and checks the native sessions registry immediately before spawning the same native UUID. The initialize control request starts no model turn. Only the resulting owned process receives send, model, permission, approval and interrupt controls. Its first system/init frame must match the UUID and cwd; mismatch terminates that owned process. Native initialize alone has no UUID field, so it is not claimed as independent identity evidence.

Writes use the existing UUID receipt ledger. Known pre-spawn rejections return blocked and allow a later explicit request; unknown outcomes are never automatically replayed. Approval IDs are claimed before sending, cancellation removes pending requests, and native terminal results feed completion evidence. A second message cannot be sent during a running turn or pending approval. Claude CLI readiness is independent of Desktop connectivity.

Display status resolves CLI availability immediately and refreshes its cached authentication result in the background. Desktop initialization and its ready check use only Desktop connection and session evidence, so CLI authentication and saved-history scans cannot delay them. Explicit CLI creation and resume still perform fresh authentication checks; the display cache never authorizes a write.

In Web and phone app management, CLI availability does not hide the Desktop launch control. The gateway reports `canStartDesktop` only for an installed, native-console-capable Claude Desktop whose process is confirmed stopped. A confirmed single running main process reports `canInitializeDesktop` so an idle setup still exposes initialization unless reconnect is available. Unknown process state offers neither action. Both initialization controls use the existing confirmation and `initializeDesktop` request; enabling CLI access alone never sends that intent.

## Alternatives considered

The native print-mode CLI accepts concurrent writers for one UUID, so relying on an upstream lock is insufficient. Opening an existing live terminal chat in another process is rejected. Registry evidence can verify a currently running writer, but cannot create an atomic lock against an independently started terminal.

Using the combined Desktop and CLI list to verify Desktop readiness exposes every saved CLI history file on the Desktop setup path. Keeping that list for user browsing while reading Desktop sessions directly for readiness preserves both views.

Routing the user's credentials through a new SDK service adds a second configuration owner. Spawning the installed CLI with the original profile/cwd keeps native configuration and authentication behavior. SSH Claude Code is excluded until equivalent source/profile and process checks exist.

Using the app enable switch as the Desktop launch trigger would also start Desktop for CLI-only selections. The explicit launch control keeps the two choices independent.

## Consequences

Closed local sessions can resume and expose native controls in the existing mobile/Web interface. Unknown original permissions, unavailable original configuration or uncertain writer evidence remain non-writable. The registry guard compares each writer's process start identity, and Linux additionally binds the machine ID and PID namespace. A terminal opened between the final registry check and spawn remains a narrow upstream concurrency limitation.

An installed, stopped Desktop remains launchable from app management even when Claude Code is available. Unknown process state, unsupported automatic connection, absent installation or stopped gateway hides that control. A renderer test verifies the button and its existing request payload; backend lifecycle fixtures cover those capability boundaries. The control has not been exercised against a real Desktop in this check.

For a selected managed API profile, authentication checks and CLI launch omit ambient `ANTHROPIC_*` values and the documented Claude provider-routing variables. The native profile's settings remain the source of the selected credentials and provider.

Windows Claude Code 2.1.168 was inspected on a native Windows host. Its registry may store `procStart` as CIM `CreationDate.Ticks`, but a native `sdk-cli` record can omit it. For a valid 2.1.168 record without `procStart`, only a native query that confirms the PID is absent permits a closed-session resume; a live PID or uncertain query remains blocked. Records with a valid start identity still block a live matching writer and admit an exited or reused PID. Malformed start identities and other Windows registry versions remain fail closed. The guard neither deletes the record nor relaxes active-writer protection, and Python never uses POSIX `os.kill` on Windows. A read-only check against the retained isolated 2.1.168 record confirmed the original guard blocked its absent PID and the corrected guard admitted it; the record hash was unchanged. Native Linux 2.1.287 uses a `linux:<machine-id>:<pid-namespace>` domain and the decimal start token from `/proc/<pid>/stat` field 22. The local guard and standalone SSH worker compare those fields, not macOS UTC `ps` output. Native Ubuntu tests blocked live writers, allowed exited/reused identities and rejected malformed records. Real SSH acceptance additionally passed resume, new chat, send, model/permission changes, Skill, upload, approval refusal, interrupt and a second closed resume against a loopback API.

An actual synthetic API request verified the selected existing authentication; an isolated capture verified project CLAUDE.md inheritance. Claude Code 2.1.287 with a loopback model service verified model selection, effective permission mode, allow/deny tool effects, interrupt of a running turn, and active-writer rejection followed by closed-session admission. Browser 390px English fixtures verified history-only, Continue, model/permissions, approvals and Stop presentation. These are macOS/native and browser checks, not Windows/Linux or physical-phone execution claims.

Decision search found [Codex CLI access](2026-10-14-codex-cli-access.md), which shares passive discovery and explicit ownership principles but concerns a different runtime. Its constraints remain valid; this note adds the local Claude implementation without superseding it.

## Explicit new CLI sessions

The new-chat picker offers Claude Code CLI beside Desktop Code and Cowork when the selected local or SSH profile is authenticated and a known project cwd exists. CLI creation requires a first message; the native CLI assigns the title. The selected project key binds its host, profile origin and cwd, and the adapter checks those inputs again before starting `claude -p --session-id` with stream-json controls. No bridge-written JSONL or empty placeholder chat is created. The native saved user event must contain the exact sent UUID before the operation reports ready; the older Windows CLI does not emit a replay-user event before its API retries. An uncertain write stays unknown under the existing receipt ledger and is never replayed automatically.

An isolated Claude Code 2.1.287 mock API run created one local and one loopback SSH session. Each retained the selected profile's synthetic credential, cwd, model and plan mode, sent its first message once, and produced native saved history. The SSH check validates the transport and protocol on macOS; it is not a paid Linux model run.

An isolated native Windows 2.1.168 run used the installed npm `.cmd` shim, UTF-8 stream JSON, a fake key, and a loopback-only unavailable API. Product-level new-session creation, native saved first-message evidence and immediate closed-session resume succeeded with the selected profile and cwd. Product permission-mode change, model selection and interrupt controls returned success. This version accepts `--permission-prompt-tool stdio` but rejects the newer `--permission-prompts host`; `set_permission_mode` confirms its mode in the control response rather than a separate status event. That initial unavailable-endpoint run did not exercise a second send or tool approval. A subsequent [native Windows fixture](../../../../tests/acceptance/windows_claude_cli_full.py) completed first and second replies, closed-session resume and another reply using a loopback Anthropic SSE service. Tool approval was checked before responding: denial created no file and produced the exact rejected tool result; acceptance created only the requested marker and produced the exact successful tool result and final reply. A repeated approval was rejected without a second file change. All seven model requests used the isolated endpoint, synthetic key and selected model. Product detail and native JSONL retained final replies; configuration, product and registry cwd matched the isolated project. The fixture closed its writers and listener, independently rechecked from the host. No paid credentials or physical phone were used.

The Windows npm shim has a distinct native `claude.exe` child PID. Terminating only the shim left that exact registered child running beyond five seconds. Local CLI ownership now checks the live shim-child parent relation and process creation identity at initialize, then checks creation FILETIME again on the same Windows handle before terminating that child during close. An isolated native run confirmed the child exited by the time close returned and stayed absent over five seconds. UTF-8 is explicit for CLI/SSH stream JSON and saved Claude history, registry and Cockpit profile JSON; native Windows CP936 verified Chinese history remained intact.
