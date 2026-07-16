# Nonblocking Live Preview Design

## Problem

The live scanner performs TSDF integration and `extract_preview()` on the same
thread that reads camera frames and estimates pose. Hardware telemetry shows
tracking at 6.13 FPS while the preview is only 1.8 FPS. The expensive mesh
extraction therefore pauses capture for more than the 500 ms timestamp limit,
creating false `timestamp_gap_above_maximum` rejections. A relocalization
attempt can also call the timestamp gate twice for one packet, producing a
false `timestamp_not_increasing` rejection.

## Decision

Move live TSDF integration and mesh extraction to a background preview worker.
The tracking loop owns capture, RGB-D odometry, pose acceptance, and UI event
polling. It submits accepted keyframes to a bounded latest-only queue and never
waits for fusion. The worker owns its preview fusion instance, integrates the
newest submitted keyframe at the configured interval, extracts a mesh, and
publishes only the newest completed mesh. The UI thread drains that result and
updates Open3D.

The final export remains deterministic: after scanning stops, a separate
fusion instance rebuilds from every accepted keyframe. Dropping queued preview
keyframes can only reduce temporary preview detail; it cannot alter the saved
mesh.

## Timestamp Gate

For each packet, select the best direct or relocalized pose using metric-only
checks first. Call the stateful quality gate exactly once after that choice,
using the host monotonic tracking clock. This removes duplicate timestamps
within one packet while retaining gap, motion, fitness, RMSE, and depth checks
for the final accepted/rejected pose.

## Acceptance Criteria

1. A deliberately slow preview extraction does not delay tracking packet
   processing or cause a timestamp-gap rejection.
2. Relocalization evaluates the stateful timestamp gate once per packet.
3. The preview worker shows the newest completed mesh and closes cleanly.
4. Final export still rebuilds from all accepted keyframes.
5. Existing headless mode performs no preview extraction.
