# Agent Note: Claude context readings

Status: implemented

## Decision

For Claude Code CLI, SSH CLI, and Claude Desktop transcript fallback, show the latest main-loop assistant request's `input_tokens + cache_creation_input_tokens + cache_read_input_tokens`. These per-request counts describe the last observed model input; result-level `usage` and `modelUsage` are cumulative and cannot be used as the current context reading. Assistant `output_tokens` may be a placeholder, so it is excluded. A native `compact_boundary` invalidates the prior reading until a later request supplies usage. Zero is a valid measurement; absent or malformed usage is unknown.

The 32-pixel ring shows a blue percentage fill only when the native record supplies a positive context-window capacity. A model name alone does not prove a limit, particularly for API-compatible providers. Native `result.modelUsage[latestAssistantModel].contextWindow` supplies capacity but its cumulative token counts are ignored. The Desktop connector passes only model identifiers and their context-window capacities from results; its existing context summary remains preferred when available. The injected connector revision changes so an older renderer closure cannot silently omit the new fields.

## Verification

Fixture tests cover latest versus cumulative usage, cache tokens, sidechains, compaction, unknown capacity and zero, plus local and SSH detail paths, Desktop transcript fallback and sanitized connector fields. Browser UI tests cover measured tokens without a capacity. No real chat or paid model request was used.
