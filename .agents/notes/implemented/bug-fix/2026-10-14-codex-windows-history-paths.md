# Agent Note: Read native Windows Codex history by directory identity

Status: implemented

## Problem

Native Codex on Windows can store a rollout path such as `\\?\C:\...\sessions\...jsonl` in SQLite while the gateway receives the same `CODEX_HOME` as an ordinary `C:\...` path. `Path.resolve()` preserves those different representations. A lexical parent check then labels an existing rollout outside the Codex home: the chat remains in the list, but its saved history is unavailable after gateway restart. The isolated installed-gateway run had the expected reply in its JSONL; the read was rejected before parsing it.

## Decision

`SessionStore` uses one rollout containment check for discovery diagnostics and history reads. Ordinary resolved paths keep the existing parent check. When that check does not match on Windows, the store compares the actual identity of each existing rollout ancestor with the resolved `sessions` or `archived_sessions` directory using `Path.samefile()`. Inaccessible ancestors do not grant access. The rollout itself is resolved before this check, so a child symlink that leads outside the home remains outside. CLI and Desktop origins, providers, and runtime ownership rules are unchanged.

## Alternatives considered

Waiting longer for the HTTP detail response cannot make this path pass the permanent containment check. Removing the extended-path prefix or accepting a string prefix would treat path spelling as authority and risks confusing nearby directories or other Windows path forms. Running identity checks for every ordinary path would add unnecessary filesystem work, including to SSH history reads; the fallback is limited to Windows paths whose normal parent check fails.

## Consequences

The original isolated Windows rollout becomes readable after restart without activating a native writer. Regression fixtures retain rejection for an outside directory, a prefix-similar sibling, and a symlink that escapes the home; ordinary paths do not use the identity fallback. Windows fallback reads a bounded number of directory identities, and an inaccessible directory still fails closed. The original isolated SQLite, WAL, and JSONL hashes stayed unchanged during the successful read.
