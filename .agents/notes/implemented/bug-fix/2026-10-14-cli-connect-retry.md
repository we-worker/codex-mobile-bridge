# Agent Note: Reuse in-flight owner discovery during explicit continuation

Status: implemented

## Problem

An explicit continuation on a CLI-origin chat first requests a background owner lookup, then synchronously runs the same lookup again. If the background lookup has already reached a slow `IPC.owner`, the second call adds a second wait before native continuation or a Desktop-owner error. Separately, a failed native proxy connection repeated the same attempt before starting the daemon.

## Decision

Explicit continuation waits for the current background owner lookup to finish and consumes that result once. If no lookup is in flight, it still performs a fresh one. A later independent explicit action also probes again. Background saved-history reading proceeds independently. The native adapter additionally remembers the daemon-start generation before its first connect; after taking the lock, it retries the proxy only if another adapter call started the daemon meanwhile. Existing timeouts, identity checks, and no-write-replay rules remain intact.

## Verification and limit

The real `Bridge.activate` chain with a delayed fake `IPC.owner` called owner discovery twice before the change, both when no owner existed and when an owner had no snapshot yet. After the change it calls once; a later separate activation probes again. A controlled unavailable-proxy fixture required two attempts instead of three. Isolated native 0.162.1 cold attach remained about 0.25 seconds before and after because that fixture has no stalled proxy. The measured fixture demonstrates the duplicate wait, while the reported production delay has not been timed at its actual IPC boundary.

## Alternatives considered

Always probing again guarantees freshness but duplicates the same in-flight observation. Reusing only the current lookup removes that delay while a later user action still asks for fresh owner evidence.

## Consequences

Continuation still waits for an actual owner lookup; the change does not weaken owner identity checks or introduce a timeout-based takeover.
