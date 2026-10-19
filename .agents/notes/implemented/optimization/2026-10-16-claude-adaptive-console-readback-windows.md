# Agent Note: Earlier complete Claude Console readback on Windows

Status: implemented

The foreground collection strategy below is superseded by [direct submission](2026-10-16-claude-direct-console-submit.md). Historical measurements and rejected alternatives remain relevant.

## Problem

The Windows helper verifies a roughly 25 KiB multiline Claude Console script through UI Automation before pressing Enter. Its collector waits a fixed 200 ms after each viewport move and its focus check, even though the renderer begins settling when the navigation key is sent. In a harmless Test workspace diagnostic, source slices at 50, 100, 150 and 200 ms were identical at each of seven navigation steps. Prompt checks took 24–43 ms and text reads took 2–9 ms in that run.

## Decision

Start the settle clock immediately after each navigation key returns. An exact full-source readback may succeed after 50 ms. A partial view always waits until at least 200 ms after that key before it contributes to source coverage or causes rejection. The focus check immediately before each navigation key remains; a redundant check inside the adjacent key callback is removed. Focus and timeout checks still run after navigation and before every read. The 18-step cap, six-second deadline, coverage rules and single-submit rule remain unchanged.

## Alternatives considered

Advancing to the next viewport after a unique, contiguous partial read at 50 ms was tried in a Test build, but independent review found a renderer could expose a short valid prefix at 50 ms and a longer one at 200 ms. Early navigation could then skip part of the source. This path was removed before release. A selected-text fast path was also rejected after a real Test probe exposed only 7,577 of 24,954 UTF-16 units. A dynamic short loader was rejected after harmless Mac Console probes hit `EvalError` under the app's CSP.

## Consequences

Full-source proof can finish on an early exact read. All partial reads still use the original minimum 200 ms settle period measured from navigation, while focus checks can overlap that period. Native self-check covers a 32-character early prefix growing to 1,500 characters by the full settle point, later contiguous viewports, and early exact full readback, alongside existing full-coverage and no-submit cases. The final collector compiled, passed native self-checks and produced a full-source receipt for a 24,954-character Windows Test source in 4.407 seconds. This single run is not a controlled speedup measurement. The final Test package recompiled the growing-prefix fixture and passed packaged native self-checks. After installation, explicit initialization with Claude already running reached connected state in about 8.1 seconds and returned the real session list.
