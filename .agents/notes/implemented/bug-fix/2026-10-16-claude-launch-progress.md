# Agent Note: Claude launch progress before process discovery

Status: implemented

## Problem

Explicit initialization starts its native worker asynchronously. The first client status snapshot can observe `connecting` while Claude's process has not appeared yet. The manager converted that snapshot to `error`, so the UI showed a failed connection during normal launch. That false error also selected the 15-second status cache instead of the one-second pending cache, delaying a later signed connection.

## Decision

Keep this interval pending as `starting`; the worker remains responsible for reporting launch failure, cancellation or required user action. A stopped process after `needs-initialization` still reports unavailable. While a new enable request is pending, the shared UI does not apply error styling inherited from the previous attempt.

## Alternatives considered

Waiting synchronously for the process would block status reads. Treating process existence as connection success would skip the signed bridge receipt. Both are unnecessary: the existing pending state and short cache already provide the required behavior.

## Consequences

Regression tests reproduce the false failure on both platform branches and verify that a signed connection replaces it after two seconds rather than remaining behind the idle cache. Native launch failures and stopped, uninitialized clients still report errors. These source tests do not measure full native startup duration.

Installed Test acceptance on macOS and Windows observed `starting` → `connecting` → `connected` through normal quit and cold initialization, with no false failure in between. Single runs completed in 10.243 and 30.437 seconds respectively; these are full cold-start observations, not a controlled speed comparison. The original Test settings were retained and the macOS formal gateway and active Codex host remained unchanged.
