# Installed CLI gateway acceptance

`packaged_cli_e2e.py` uses the installed **Test** gateway worker, not `desktop.py`, for configuration, start, stop, login, and every HTTP assertion. Source client transports seed two closed conversations through the native CLIs before gateway startup. The test sends only synthetic prompts to loopback Responses and Anthropic SSE servers with placeholder keys. It records no prompt bodies or credentials in `result.json`. It changes Codex and Claude models and permissions through authenticated HTTP, reads the effective state back, and confirms the next native model request uses the selected model.

Run as the normal desktop user after the Test application has been installed. Provide absolute paths to the installed bundled worker and the two native CLIs. `--gui` only checks that the worker is inside the distinct installed Test controller's resources. It does **not** launch or exercise the GUI; record a separate installed GUI launch smoke test for that claim. `--codex-package` should point to a complete installed daemon package root containing `bin/codex[.exe]` when one exists; without it, the harness stages just the supplied binary and reports native daemon startup failure if that distribution needs other package files. `--source-root` points to the matching repository checkout staged on the test host; source modules are used only to seed closed native sessions.

Ubuntu example with paths to the installed Test package and native CLIs supplied as environment variables:

```sh
python3 -B "$CMB_SOURCE/tests/acceptance/packaged_cli_e2e.py" \
  --source-root "$CMB_SOURCE" \
  --test-root "$HOME/.tmp/cmb-package-20261014/e2e" \
  --gui "$CMB_TEST_GUI" --gateway "$CMB_TEST_GATEWAY" \
  --codex-cli "$CMB_CODEX_CLI" --claude-cli "$CMB_CLAUDE_CLI"
```

Windows normal-user CMD example using the dedicated Python 3.11 build environment and the installed Test package paths:

```bat
"%CMB_PACKAGE_PYTHON%" -B "%CMB_SOURCE%\tests\acceptance\packaged_cli_e2e.py" ^
  --source-root "%CMB_SOURCE%" ^
  --test-root "%USERPROFILE%\.tmp\cmb-package-20261014\e2e" ^
  --gui "%CMB_TEST_GUI%" --gateway "%CMB_TEST_GATEWAY%" ^
  --codex-cli "%CMB_CODEX_CLI%" --claude-cli "%CMB_CLAUDE_CLI%"
```

The harness creates a short, new run directory below the test root to fit Windows AF_UNIX socket limits. It fails before touching native state if a supplied path or gateway version is wrong. Each run leaves a sanitized `result.json` in its own directory, requests cooperative shutdown of its isolated gateway and daemon, and verifies the isolated Claude profile has no live writer and the Codex daemon is stopped. If shutdown or native status cannot be confirmed, the result fails; inspect the task-owned processes before rerunning. HTTP mutations each get a fresh UUID and are never retried after an uncertain response; only reads are polled. A failure is evidence for the reported stage, not proof that later stages passed. No daily `.codex` or `.claude` profile is selected.

For installed builds with background client status refresh, the harness waits up to 45 seconds for `GET /api/clients` to return `pending: false`. Each GET must finish within the UI's 10-second status deadline. A failed refresh (`refreshError`) is rejected even if the response includes an older complete client list. `POST /api/clients` has the UI's 45-second lifecycle deadline and is issued once. The full method, route, duration, and status trace stays in the run's `result.json`; the console prints only a short summary.
