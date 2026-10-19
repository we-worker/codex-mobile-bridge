# Agent Note: Earlier Claude Console readback on macOS

Status: implemented

The foreground collection strategy below is superseded by [direct submission](2026-10-16-claude-direct-console-submit.md). Historical measurements and rejected alternatives remain relevant.

## Problem

The macOS helper enters roughly 25 KiB of connector source into Claude DevTools Console and requires one complete accessibility readback before Enter. A long CodeMirror line may expose only a virtualized slice. The helper waits for forty 25 ms reads before attempting its bounded caret navigation. In a real Test workspace probe, both the fourth and fortieth reads exposed the same 10,077 of 25,020 UTF-16 units, so that wait did not reveal more text in that case.

## Decision

For source longer than 3,500 UTF-16 units, four identical, nonempty AXValue reads that are an exact substring of the expected source permit one early use of the existing caret-reveal step. Only a complete exact readback succeeds. If the early step does not verify the source, the helper continues the original forty-read period and retains the original three caret-reveal attempts. If a later read succeeds after an early caret move, the helper moves the caret to the end before submission. Focus, selected application and Console checks run before each key action. The source format, owner handoff and signed connection receipt are unchanged.

## Alternatives considered

A short loader that reads the full gateway-owned script, verifies a pinned SHA-256 and dynamically evaluates it would avoid entering a long source. Two harmless nonce probes on the installed Mac Claude Desktop both returned `EvalError`: one evaluated after the asynchronous file read, and the other staged the verified nonce for a separate synchronous Console submission. A selected-text check returned zero selected characters in a real long-source probe and disturbed the fallback, so it was removed. Windows UI Automation selected only 7,577 of 24,954 units in a separate probe, so that fast path was also removed. Copying the full editor into the system clipboard would require preserving all existing clipboard formats and is outside this narrow change.

## Consequences

The early step can avoid the otherwise fixed wait when it obtains a complete readback; a still-settling editor receives the previous full wait and fallback, with at most one additional caret attempt. The actual 25,020-character Mac Test probe obtained a full execution receipt with the early helper in 2.429 seconds. An earlier old-helper run took 2.108 seconds under different conditions. In one later paired warm Test trial using the same 25,020-character source, the old helper took 2.094 seconds and the new helper took 0.931 seconds; both produced full-source receipts. One pair does not establish an all-machine or full-connection speedup. Swift fixtures cover early success, a later settled read, the original navigation and failure paths.
