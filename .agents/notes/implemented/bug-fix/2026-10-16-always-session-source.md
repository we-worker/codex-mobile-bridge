# Agent Note: Always identify a session source

Status: implemented

## Problem

A list containing only CLI chats looked like Desktop chats because the source label disappeared when only one source was available. Users could not tell which runtime would continue the chat.

## Decision

Always show the source above the date on every session row: Codex APP/CLI/IDE, Claude Code/Cowork/CLI, and DeepSeek Harness APP. Unknown sources use the existing localized Other source label. The source selector remains conditional on multiple available types; its visibility is independent of row identity.

This supersedes only the single-type row-label rule in [Unified Claude chat list](../optimization/2026-10-14-claude-unified-chat-list.md). Chronological ordering, filtering, selection and project grouping stay as documented there.

## Alternatives considered

Keeping labels only in mixed lists saves a small amount of visual space but leaves single-source users unable to identify the runtime. Requiring a selector in every list adds a control without a filtering choice.

## Consequences and verification

All sources use the existing two-column row layout and the existing swipe-stability rules. DOM regressions cover single-source Codex/Claude/DSH, legacy desktop rows, and unknown sources. Source selectors still hide when there is no filtering choice.
