# Agent Note: Local CLI model catalogs use the native daemon environment

Status: implemented

## Problem

A mobile gateway can join a Codex CLI daemon that was started in another terminal with different environment variables. Reading the gateway environment for an API model catalog can select the wrong endpoint or credentials. Treating that environment as unavailable also makes an ordinary environment-backed CLI account appear to require manual model IDs.

## Decision

The local catalog resolves only the variable names that the effective native provider configuration uses. A platform reader validates the same-user PID record, process generation, executable and native home, then reads selected launch variables from that process. The raw values are used only for the catalog request. The durable model identity includes a digest of those values and process generation, alongside the existing config and account identity; it never stores or returns raw credentials. A failed identity check gives an actionable catalog error and cannot reuse a catalog from a previously verified environment.

The upstream API model list determines availability. Native `model/list` is an optional, two-second metadata lookup after a successful upstream list and fills reasoning efforts only for matching model IDs. A configured native catalog continues to use the daemon's model list.

## Alternatives considered

Launching a new CLI command with the gateway environment is simpler but does not reveal the already-running daemon's environment. `command/exec` may filter environment variables and would perform a shell action for a passive model read. A gateway-managed environment snapshot excludes ordinary terminal-started daemons. Returning the full process environment would expose unrelated values, so the reader selects only requested names.

## Consequences

macOS uses a bounded `KERN_PROCARGS2` read, Linux uses bounded `/proc/PID/environ`, and Windows x64 reads a bounded UTF-16 block through the process API. Their generation checks use native PID metadata. If the operating system denies the read, the UI reports that the daemon launch environment cannot be verified. Existing saved-auth and configured-catalog paths do not require unused environment variables. Synthetic same-user child tests exercise value isolation and stale identity rejection; Windows x64 was checked on an isolated Windows 10 child.
