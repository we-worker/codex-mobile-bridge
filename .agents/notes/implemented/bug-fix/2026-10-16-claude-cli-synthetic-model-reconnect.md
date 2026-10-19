# Agent Note: Ignore Claude CLI synthetic model when resuming

Status: implemented

## Problem and decision

Claude Code can save an assistant event whose `message.model` is `<synthetic>`. It is not a selectable model. The local CLI adapter previously selected the last assistant model without excluding that sentinel. On Windows, the installed npm `claude.cmd` forwards arguments through raw `%*`; `--model <synthetic>` is interpreted as CMD redirection and the native CLI exits before acknowledging `initialize`.

Saved-history model selection now skips `<synthetic>`. If an earlier real assistant model exists, resume retains that model. If the history contains only synthetic assistant events, resume omits `--model` and lets the original Claude profile and project settings choose their native default. The original profile, cwd, permission mode, settings sources and writer guard are unchanged. An uncertain resume receipt is not replayed automatically.

## Verification

The original closed Windows session had one assistant model event, `<synthetic>`, with no earlier real model. With the original `.cmd` launch path, a no-turn resume previously waited 30.000 seconds for `initialize`, received no control response, and found the launcher exited with code 1; isolated stderr matched the Windows CMD syntax-error category. With this change, the same session returned an `initialize` success in 1.219 seconds and resume was ready in 3.641 seconds. The probe sent no user or model message and closed its owned process; a fresh native registry check confirmed no live writer. The saved account, cwd and permission preflight checks passed. No existing unknown receipt was replayed.

Unit regressions cover real-then-synthetic history and synthetic-only history with no forced `--model`. `python -B -m unittest tests.test_claude_cli tests.test_claude_reconnect` passed 59 tests; `git diff --check` passed.

The isolated Windows metadata-only probe is `F:/cmb-package-20261014/.tmp/claude-reconnect-probe/probe.py`, with source ZIP `current-bridge.zip` in the same directory. It imports the ZIP rather than an installed Test gateway runtime, so it does not by itself verify a newly installed package. The existing installed Test gateway entry is `F:/cmb-package-20261014/windows_test_http.py` (`TestHTTP`, `base`, `data`) for HTTP acceptance after installation; a no-turn native resume through that gateway still needs a fresh, explicit test request and a closed-writer check.

The subsequently installed `a175fac` Windows Test package passed that HTTP acceptance: one explicit resume returned ready in 3.828 seconds, the detail endpoint confirmed ready, and the original cwd, permission mode and gateway settings were retained. No model message was sent. The resumed idle connection was left available for the user's manual test.
