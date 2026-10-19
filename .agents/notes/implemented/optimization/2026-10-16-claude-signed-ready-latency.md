# Agent Note: Claude signed connection readiness

Status: implemented

## Problem

During explicit Claude Desktop initialization, a signed renderer receipt could make `status()` report connected while the native DevTools cleanup still held `reconnecting`. An authenticated list request in that interval failed with “Claude 正在重新连接”.

## Decision

After the current connector's signed receipt is accepted, and after the existing read probe succeeds when an earlier probe failed, mark the mailbox ready for normal calls before closing DevTools. Keep native cleanup running and report `consoleCleanupPending` until its result is known. A cleanup failure retains the existing manual-close message. The existing generation, owner, cancellation, whole-source injection, and unconfirmed-write checks stay in place.

On an explicit first Windows foreground initialization with no existing owner and no persisted connection token, skip the pre-Console wait for an earlier renderer to follow the newly created generation. No renderer can sign that new token until this initialization injects its source. Keep the handoff wait for persisted tokens, existing owners, reconnects, and restarts.

## Consequences

The first list request can use the established file bridge while native cleanup is pending. A source fixture holds cleanup open on simulated Windows and macOS paths and verifies a signed list response in that interval. A separate Windows fixture verifies the first-owner wait is skipped only without a persisted token. These fixtures do not measure live startup time or replace platform acceptance and packaged validation.
