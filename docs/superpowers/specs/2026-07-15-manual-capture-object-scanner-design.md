# Manual Capture Object Scanner Design

## Goal

Produce a usable markerless 3D mesh of a small object with the Orbbec Gemini 215 by replacing continuous live fusion with a manual, capture-first workflow. The operator moves the camera to a stable viewpoint, presses Space to capture that view, then finalizes after collecting coverage around the object.

## Scope

- Target objects are 5--30 cm wide and positioned about 0.20--0.45 m from the camera.
- The operator captures 12--20 views around the object, plus higher viewpoints as needed.
- Each accepted view is a burst of 40 RGB-D frames. The median valid depth becomes the view's depth image; the latest color image is retained.
- The session persists raw RGB-D view data, calibrated intrinsics, capture metadata, and accepted-view diagnostics so reconstruction can be replayed offline.
- Finalization performs object ROI/background filtering, pairwise registration, loop-closure candidates, pose-graph optimization, TSDF fusion, mesh cleanup, and PLY export.

The first release does not attempt continuous handheld tracking, real-time mesh fusion, automatic capture, texture baking, or closed-bottom reconstruction from a single upright pass.

## Operator Workflow

1. Start the scanner with the object away from direct sunlight, on a matte table, with a matte backdrop behind it.
2. Center the object at 0.20--0.45 m and press Space when the camera is stable.
3. The scanner validates central depth coverage, captures and saves one burst, and displays a view count and quality result.
4. Move approximately 15--20 degrees around the object and repeat until the front, sides, rear, and high-angle surfaces are covered.
5. Press F to finalize. The scanner reconstructs from saved views and exports a PLY mesh only if registration and mesh quality checks pass.
6. To obtain the bottom, reposition or flip the object and capture a second session; joining separate sessions is outside this release.

## Components and Data Flow

```text
manual scanner CLI
  -> static burst capture
  -> session writer (raw color/depth + metadata)
  -> foreground/ROI filter
  -> pairwise registration + loop closures
  -> pose graph optimization
  -> TSDF integration using optimized poses
  -> mesh quality gate + PLY export
```

`capture.static_view` owns median burst fusion. `recording.session` owns the portable on-disk format. `processing.object_roi` or a replacement foreground module owns conservative object/background exclusion. `registration` owns point-cloud preprocessing, pairwise registration, and pose-graph construction. Reconstruction never depends on the old continuous `MarkerlessTracker` pose chain.

## Registration and Edge Handling

No depth interpolation will be applied to silhouette holes. Registration uses only valid, non-boundary depth samples after erosion of the validity mask. The color/depth object cloud is downsampled before feature matching and ICP. Pairwise registration must meet configured fitness and RMSE limits before an edge is added to the graph. Adjacent views create certain edges; geometrically plausible non-adjacent overlaps create uncertain loop-closure edges. Global pose-graph optimization runs before every final TSDF rebuild.

The initial object ROI is detected from valid foreground depth around the first selected depth cluster, with operator-configurable depth bounds of 0.20--0.45 m. The depth bounds are intentionally wider than the measured object depth so no rear face is clipped at 0.30 m. The final ROI remains bounded to a 0.35 m object envelope and rejects table/background points.

## Error Handling and Quality Gates

- Reject a capture when valid object depth is below the configured minimum or the burst is unstable.
- Preserve a rejected-capture reason and leave the current session unchanged.
- Reject pairwise edges below registration fitness or above RMSE limits; continue testing eligible loop closures.
- Refuse export for an empty mesh, a mesh outside the object envelope, or excessive disconnected components.
- Always preserve the captured session when finalization fails so it can be replayed after configuration changes.

## Validation

Unit tests cover burst median depth, session persistence, ROI filtering, pairwise quality decisions, pose graph construction, and reconstruction failures. Script tests cover Space/F command handling with fake input and deterministic output paths. A hardware smoke test uses the Panasonic box: raw single-frame point cloud must contain valid depth, the capture session must contain at least 12 accepted views, finalization must create a non-empty mesh, and the mesh must remain inside the configured object envelope.

## Acceptance Criteria

- A manually captured session can be replayed without the camera connected.
- No fusion stage hard-codes a 0.30 m maximum depth.
- Rejected views do not enter registration or fusion.
- Final fusion uses optimized pose-graph poses rather than sequential live poses.
- The workflow exports a non-empty PLY mesh for the test box when its visible surfaces have sufficient coverage.
