# Agent Note: Installed Claude Code CLI Skills

Status: implemented

## Decision

The resumed CLI retains its original configuration directory, working directory and user/project/local setting sources. The Skill picker uses the commands actually loaded by native initialization, excluding built-in commands. Native plugin enablement, project scope and user-invocable restrictions determine the available choices; the gateway does not maintain a second filesystem parser.

A selected CLI Skill is sent as its native `/name` invocation in the owned process. CLI messages allow one Skill selection, matching the native invocation form. The server validates the selection against that owned process catalog before sending. Closed history remains passive and offers no Skill selection.

## Verification

Fixture tests cover loaded user/project/plugin command filtering and native slash-command input. Root acceptance with installed Claude 2.1.287, an isolated config and a loopback mock API verified native Skill expansion; for image-bearing input the native Skill tool delivered the selected instructions, alongside exact image bytes and uploaded-file Read results. No paid API was used.
