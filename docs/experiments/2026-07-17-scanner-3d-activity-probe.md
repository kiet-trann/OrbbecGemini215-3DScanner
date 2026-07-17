# 3D Scanner Activity Probe

Date: 2026-07-17

## Purpose

Validate that RTAB-Map's active temporary database provides a read-only signal
for the experimental three-second auto-pause monitor.

## Runtime inspected

- RTAB-Map working directory: `C:\Users\TD-998\Documents\RTAB-Map`
- Temporary database: `C:\Users\TD-998\Documents\RTAB-Map\rtabmap.tmp.db`
- Verified schema table: `Node`
- Probe command: `scripts\17_rtabmap_activity_probe.py --seconds 25 --interval 0.25`

## Hardware result

The operator moved the Gemini 215 while mapping, then held it on a non-scanned
area. The read-only probe returned:

```json
{
  "reliable": true,
  "mapping_observed": true,
  "stable_seconds": 6.2970000000000255,
  "failures": []
}
```

The signal therefore observed both required conditions: Node growth while
mapping and no new Node for more than three seconds. The monitor may be exposed
as opt-in experimental functionality in the 3D Scanner UI. It must still
send only the guarded Pause command, never Save, Stop, or Close Database.
