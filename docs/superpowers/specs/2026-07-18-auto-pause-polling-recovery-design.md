# Auto-pause polling recovery design

## Goal

Ensure a failed Windows Pause key injection never leaves the auto-pause monitor stuck in the countdown state.

## Root cause

`ActivityMonitor.observe()` calls `WindowsRtabmapBridge.pause()` after verified inactivity. The bridge lets an `OSError` from foregrounding RTAB-Map or `SendInput` escape. That exception terminates the Tkinter polling callback before it schedules its next 250 ms run, leaving the last visible message as `Auto-pause countdown` and leaving RTAB-Map running.

## Design

Keep the existing guarded bridge, activity signal, and Space-key shortcut. At the bridge boundary, convert OS-level input failures into `BridgeResult(sent=False, message=...)`. `ActivityMonitor` already treats that result as `UNCERTAIN`; the existing UI then displays the unavailable reason and disables auto-pause while its scheduled polling loop remains alive.

No Stop, Close Database, or Save command will be introduced. Manual Pause and Resume use the same result path and will show the diagnostic message instead of raising into the UI.

## Verification

Add a regression test that simulates a one-window RTAB-Map match whose key sender raises `OSError`, asserting that `pause()` returns an unsent result. Extend the activity-monitor test to assert that an unsent Pause transitions to `UNCERTAIN`, then run the focused bridge/activity/UI test set.
