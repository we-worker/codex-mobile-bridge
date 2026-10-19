# Agent Note: Follow CLI rollout updates during passive viewing

Status: implemented

## Problem

The first passive read stores a CLI rollout snapshot in the live session. Later terminal turns append to the same rollout, but subsequent timeline polls skipped the saved-history read once the session had state. The phone therefore remained on the initial exchange until an explicit continuation changed the runtime path.

## Decision

While a CLI-origin session is disconnected, periodic background reads refresh its saved rollout. Local saved history has a two-second read cadence independent of the 15-second owner retry; SSH keeps the existing owner retry cadence to avoid extra remote reads. An unchanged normalized snapshot does not advance the timeline sequence. This only reads saved data; it does not resume a thread, start a daemon, or claim its writer. A connected runtime remains responsible for its own events.

## Verification

An integration fixture appends a second terminal turn after the first passive read and checks that timeline changes contain the new reply without advancing the owner retry, native attach or call. An unchanged repeat read yields no new rows. The test failed before the change and passes after it.

## Alternatives considered

Requiring Continue provides fresh live events but claims a writer just to read history. Refreshing on every poll increases filesystem and SSH work; a bounded local history cadence fixes visibility while keeping passive access read-only.

## Consequences

Real isolated native-writer acceptance displayed a subsequent reply through GET-only gateway polling in 2.354 seconds with the correct model and connected=false. SSH keeps its existing cadence; no two-second SSH guarantee is made.
