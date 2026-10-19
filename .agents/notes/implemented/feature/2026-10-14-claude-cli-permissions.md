# Agent Note: Claude Code CLI native permission modes

Status: implemented

## Decision

An explicitly resumed CLI session offers the native default, acceptEdits, plan, dontAsk, auto and bypassPermissions choices. The launch permits bypassPermissions to be selected later but retains the saved mode at startup. Full Access requires an explicit option selection and a server-checked confirmation field; no startup path selects it automatically. The adapter reports a change only after the native control response names the requested mode and the owned process reports the effective mode in a status event. A mismatch or missing report leaves the action unconfirmed.

Closed history still has no permission choices, and unknown saved permissions still block resume. The original profile, cwd and settings sources are preserved.

## Verification

Fixture tests cover mode choices, Full Access confirmation and native control routing. `python -B -m unittest tests.test_claude_cli` and `node --test tests/desktop-sessions-ui.test.cjs` pass. Root acceptance with installed Claude 2.1.287 and an isolated mock API confirmed the control response and effective native status for all six modes. Organization-specific restrictions are still reported as unconfirmed if the native process refuses a change. No paid API was used.
