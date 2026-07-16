# Custom Markerless Tracking Failure Record

Date: 2026-07-16

## Hardware result

Command/backend: `scripts/14_markerless_scanner.py --backend background-assisted` with RGB PnP fallback enabled.

```
frames=1053 accepted=732 keyframes=399 integrated=194 lost=270 tracking_fps=5.47
rejected_reasons=fitness_below_minimum:172,timestamp_gap_above_maximum:145,translation_above_maximum:4
```

The prior run without the PnP fallback was materially better: 1092 frames, 932 accepted, and 104 lost. The fallback therefore increased rather than reduced loss.

## Decision

Do not spend more iterations tuning ORB matching, PnP, thresholds, or preview cadence in the custom live tracker. The limiting input is Gemini stereo depth at object edges/oblique surfaces plus an architecture without robust relocalization/loop closure. Keep this backend as a diagnostic baseline only and validate the RTAB-Map native Orbbec path next.

## RTAB-Map direct Gemini validation

After Microsoft Kinect Runtime 2.0 was installed, the RTAB-Map GUI launched and its native Orbbec SDK v2 driver reconstructed the first three box faces correctly. However, every long run later reached raw depth loss at an oblique edge:

- `fromImageEmpty=1`, `Missing correspondences`, and `Cloud with only NaN values created!`;
- visual odometry and loop closure then rejected insufficient inliers;
- setting `Odom/ResetCountdown=3` prevented long drift but created repeated empty maps when the camera left the object, so it was removed.

Running Gemini in `Close_Up Precision Mode` improved capture throughput but did not remove the raw depth holes. RTAB-Map direct is therefore useful as a visualization/reference path, not a production markerless object-scanner solution for this camera and scene.

The standalone `rtabmap-rgbd_camera.exe` remains blocked by the missing `opencv_highgui470.dll` in the official ZIP. No DLL was copied from an unverified source.

## Raw depth edge measurement and hardware hole-filter A/B

At the user-held problematic box edge, a raw 8-second RGB-D measurement (color-aligned, 0.20-0.40 m) captured 234 frames at 26.32 FPS. Valid depth was concentrated in the center column:

| Grid region | Mean valid depth | Minimum valid depth |
| --- | ---: | ---: |
| center-middle | 39.39% | 5.53% |
| center-bottom | 50.44% | 44.50% |
| all left/right cells | at most 0.04% | 0.00% |

Every nonzero depth pixel was already in the test range, so the loss was not caused by 0.20-0.40 m clipping. This proves the failure enters before SLAM/tracking.

Gemini exposes a writable `OB_PROP_DEPTH_HOLEFILTER_BOOL` firmware property and it was initially `false`. The property was enabled for an A/B test, but the next pipeline returned no RGB-D frames and emitted a Color timestamp anomaly. The test was immediately rolled back; readback confirmed `false`. A short post-rollback startup check returned one RGB-D frame but was not a valid replacement measurement because pipeline startup consumed the three-second capture window.

## Operating decision (approved by user)

Use the RTAB-Map GUI as the primary scanner for the current Gemini 215 workflow. It has already reconstructed three faces of the box correctly, provides a live markerless 3D preview, and requires no custom scanner implementation.

Operational workflow:

1. Start RTAB-Map with the Gemini Orbbec SDK v2 source.
2. Scan the required visible faces while keeping the object in view.
3. Pause RTAB-Map while the camera is still aimed at the object; do not stop by turning the camera away.
4. Save the session, crop table/background geometry, then export the object mesh/OBJ.

Freeze further work on custom scanner branches, RTAB-Map odometry tuning, and Gemini hardware hole filtering. Revisit custom code only if RTAB-Map is blocked by a concrete requirement that cannot be addressed through its configuration or post-processing.
