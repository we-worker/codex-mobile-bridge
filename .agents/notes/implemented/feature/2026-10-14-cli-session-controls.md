# Agent Note: Model, Skills, plan and Goal on CLI-origin chats

Status: implemented

The permission restriction below is superseded by [CLI permission switching](2026-10-14-cli-permission-switching.md). Model, Skill, plan, Goal and owner boundaries remain.

## Problem

The previous owner-routing fix makes CLI-origin chats writable but leaves all configuration behind an origin-based desktop-only guard. App-adopted chats lose controls already supported by their owner; native CLI exposes only basic conversation operations. A connected label is not sufficient acceptance for the requested CLI workflow.

## Decision

Separate model and Skill access from broader Desktop configuration privileges. CLI-origin chats with a verified Desktop owner reuse existing model, Skill, plan and local Goal operations. Joined native CLI chats use the same daemon for model/Skill catalogs, selected settings, collaboration mode, Skill input and supported Goal RPC. Origin remains display metadata, while runtime and verified capability determine controls. Do not open unrelated permissions, rename, editing/forking or side-chat features by enabling a broad flag.

The native path retains provider, authentication and cwd. Only the requested per-thread settings change. Passive catalog inspection does not activate a session. Goal operations retain the existing persistent intent ledger, expected-state checks and unknown-result behavior; model turns run only on explicit user operations or their explicitly created/resumed goal workflow. Goal create/resume activation explicitly uses default collaboration mode so a preceding plan does not prevent execution. Optional Goal policy errors do not prevent baseline CLI attachment. No writes are replayed after uncertainty. UI switches from unavailable to ready when the actual connection/capability arrives and preserves pending selections across transient disconnects.

## Alternatives considered

Leaving all CLI controls disabled limits adapter work but does not meet the user's workflow. Flipping canConfigure for every CLI-origin chat would also enable unrelated operations with no adapter implementation. Reading native catalogs through a separate desktop/default account could offer mismatched models and skills; the joined CLI runtime is authoritative for its own capabilities.

## Existing-note audit

[CLI access](2026-10-14-codex-cli-access.md), [cold resume](2026-10-14-codex-cli-resume.md) and [existing owner](../bug-fix/2026-10-14-cli-existing-owner.md) are partially superseded on the controls restriction only. Their ownership, source discovery, lifecycle and no-replay rules remain applicable. File-reading and notification decisions are unrelated.

## Verification

Service tests cover App-owned CLI capability propagation and same-owner operations, native routing, passive non-activation, unrelated-control rejection and unknown-write handling. Real isolated CLI 0.162.1 and a local Responses fixture verify model/effort, Skill input, plan/default turns and Goal state changes. Browser actions verify model changes, Skill selection, plan send and Goal create/pause/edit/resume/clear; a 390 px English viewport has no horizontal overflow. Native checks confirm Goal activation switches out of plan mode and edited goals reach execution with provider/cwd/model/effort retained. Goal resume can already be executing natively while a supplementary activation is queued; verification checks actual state rather than requiring an active goal to become idle. Full source and packaged acceptance are recorded in [VERIFICATION.md](../../../../VERIFICATION.md).

## Consequences

Native methods and feature availability differ by runtime version and policy. Unsupported capability must remain unavailable with a useful explanation rather than bypassing checks. Local mock inference verifies transport and native state, not external-model quality; each platform and arbitrary SSH environment needs separate native acceptance. [SSH native CLI Goal](2026-10-14-ssh-native-cli-goal.md) extends Goal controls to verified joined SSH runtimes without opening them for remote App owners.
