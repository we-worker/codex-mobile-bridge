# Agent Note: Direct foreground Claude Console submission

Status: implemented

## Problem

Foreground initialization visibly navigates a long Console draft to collect accessibility text before Enter. The source is already generated locally, but Chromium can expose only a viewport slice through AX/UIA. Full readback therefore puts repeated caret movement on the normal connection path and mistakes limited accessibility visibility for incomplete input.

## Decision

The explicit foreground initializer writes the prepared source once and dispatches Enter once without Home, Down, End or selection navigation. It retains selected application identity, window, prompt focus, cancellation and existing-draft guards. A bounded non-navigating read checks that the editor displays this input: macOS accepts an exact value or a stable matching slice of at least 32 UTF-16 units; Windows accepts an exact document immediately, or a compatible uniquely placed slice / virtualized gap after a short settling period. These checks establish observed input, not full-source proof. macOS keeps its one-second delayed-read tolerance; Windows waits at most 1.2 seconds with 250 ms settling for partial views.

After the Enter down/up pair, the foreground helper reports submission and lets the existing owner await the signed receipt for its generation. Mac does not interpret an immediate focus change or inaccessible empty prompt as failed dispatch. Windows removes the fixed 700 ms post-submit wait. Missing receipt does not become connected and does not automatically submit again. Trust, ownership handoff, active work and request replay rules remain unchanged. The unattended Windows background path retains its strict full-document check.

The Mac Unicode-input fallback retains focus checks for each event and performs the same readiness check once after all chunks, rather than demanding full AX readback every 128 units.

## Alternatives considered

The previous [Mac early readback](2026-10-16-claude-early-console-readback.md) and [Windows adaptive collector](2026-10-16-claude-adaptive-console-readback-windows.md) preserved full pre-submit text equality, but still visibly navigated Console. This decision replaces their foreground collection strategy. Their rejected selected-text and dynamic-loader experiments remain relevant: selected-text APIs also returned partial values, and a loader using eval was rejected by Claude CSP. No clipboard access, CSP change, new permission or dynamic loader is introduced.

Treating successful SetValue alone as connection success was rejected: the platform setter does not prove script execution. The existing signed connection handshake is the authoritative outcome. Merely shrinking navigation waits would retain the reported regression.

## Consequences

Normal foreground submission no longer scrolls through the draft. A partial visible read cannot establish that every byte is present, so successful execution must still be confirmed by the existing bridge protocol. An unreadable or unrelated input view stops before Enter; no heartbeat stops before connected. Native tests exercise sliced/empty/changing views, wrong content, pre-dispatch cancellation and focus changes, single Enter, and no replay. Real Test evidence and installed-package results are recorded under `.tmp/claude-direct-submit-20261016/acceptance.md`; no credentials or real chat content are committed.

## Decision audit

The two readback notes linked above are partially superseded and retain their measured limitations and rejected alternatives. The signed-ready-latency note still applies unchanged: UI cleanup is separate from a usable signed connection. No other active Console proposal was found.

## References

[Microsoft ValuePattern.SetValue documentation](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.valuepattern.setvalue) describes setting a control value; it does not promise script execution or a connected bridge. Native behavior is verified on the installed Claude applications.
