# Agent Note: Unified Claude chat list

Status: implemented

## Problem

Separate Code, Cowork and CLI groups interrupt chronological scanning. Users also need a quick way to narrow a mixed list without losing chronological order.

## Decision

Show all Claude chat types in the same recent list by default. When the full readable inventory contains at least two types, show an All/Code/Cowork/CLI selector with only observed types and put a compact type label beside each title, above the existing date. The selector filters within the chronological list; search, archive visibility, project grouping, activity indicators and selection behavior remain available. A single-type inventory hides the selector. The create dialog owns its own chat-type selection.

Sort and display dates through the same seconds-to-milliseconds conversion in the shared session list. Desktop activity timestamps can arrive in milliseconds while local and SSH CLI history uses Unix seconds; comparing their raw numbers places CLI sessions below older Desktop sessions. The conversion belongs to the list presentation so the existing backend timestamps and consumers keep their current contract.

## Alternatives considered

Collapsible type groups make scanning chronological activity harder. The optional selector narrows a mixed list without grouping it by type. Project grouping remains an explicit display choice and groups by project across types.

## Consequences

The selected type is kept per provider and resets to All if that type disappears from the full inventory. Search and archive visibility do not determine whether the selector appears. Existing project collapse preferences still apply to project groups. DOM tests cover chronological mixing, adaptive type filtering, archive/search, project grouping and provider switching; responsive appearance is verified during integration.

A mixed-unit DOM regression checks global order, the visible CLI date, and ordering after type, search and project filters. It does not claim a live Claude Desktop or SSH integration run.
