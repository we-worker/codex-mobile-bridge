# Agent Note: Attribute CLI replies to their recorded turn model

Status: implemented

## Problem

Native CLI `thread/read` exposes the current thread model but may omit per-turn model attribution. Historical replies could therefore show only `CODEX` after an explicit native connection. Assigning the current model to all turns would mislabel conversations where the model changed.

## Decision

The live-session view joins native turns by ID to its already loaded saved rollout `turn_context`. The saved context overrides only when it has an actual model. Native per-turn model fields, when provided, are retained. At the start of a new native turn, capture the then-current model for that turn; a subsequent settings change does not relabel it. Later native snapshots that omit per-turn model fields retain captured settings by matching turn ID; an explicit native turn model takes priority. Turns with no model evidence retain no model label. No added SSH or rollout read occurs in a native callback or refresh.

## Verification

A regression fixture with two recorded models and two later live turns passes. The current thread model differs from both historical models, changes between live turns, and changes again after the second starts. Repeated native snapshots without per-turn models retain both captured labels; an explicit native turn model supersedes the captured label.

## Alternatives considered

Using the current model for every reply is simple but invents historical attribution. Reading every rollout again during native callbacks provides more metadata at the cost of local/SSH latency. Reuse loaded history and native per-turn evidence instead.

## Consequences

Unknown Desktop historical labels remain unknown because Desktop hydration may substitute the current model. Only native CLI per-turn evidence can fill missing saved attribution. The existing timeline regression and native mixed-model fixture verify this distinction.
