# Agent Note: Modal dialog backdrop dismissal

Status: implemented

## Problem

Web and desktop gateway modal dialogs require their explicit close control even when the user taps the surrounding backdrop. This is inconsistent on narrow screens, where the backdrop occupies most of the view.

## Decision

A shared listener closes a modal dialog only after a primary pointer gesture starts and ends on its backdrop without moving or scrolling. It waits for the resulting click before invoking that dialog's existing close or cancel control. The control's disabled state and close handler remain authoritative; dialogs without a close control receive a cancelable close request. Native system dialogs are outside this behavior.

The listener is delegated at the document level, so dialogs inserted after startup use the same rule. Web serves the script before `app.js` through the existing `/app.js` resource, and the desktop renderer loads the same file directly.

## Alternatives considered

Adding a click handler to each dialog would make the known dialogs explicit, but newly created dialogs and the two renderer entry points would drift. Closing directly on `pointerup` would also remove the modal before its click is dispatched, risking a click on the page underneath and bypassing button-specific disabled states.

## Consequences

Backdrop taps follow the existing close lifecycle, while internal blank space, drags, scrolling, and an inside-to-outside release leave the dialog open. The added listener and one shared script increase the renderer surface slightly. Automated event-flow tests cover the gesture and disabled cases; browser and native WebView delivery still need separate visual checks.
