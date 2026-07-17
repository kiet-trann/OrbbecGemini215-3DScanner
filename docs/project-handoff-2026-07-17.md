# Project handoff - 2026-07-17

## Current source of truth

- `main` is the active, pushed 3D Scanner 3D Scanner implementation.
- Current main commit at handoff: `c316f33` (`fix: hide occluded points in crop preview`).
- GitHub has `main` plus two retained recovery branches:
  - `backup/aruco-marker-20260717`: the original ArUco-marker direction before the RTAB-Map merge.
  - `backup/nonmarker-rtabmap-20260717`: the non-marker RTAB-Map / 3D Scanner 3D Scanner direction.
- All `codex/*` branches and their related worktrees were intentionally removed after backup branches were created.
- Do not run `git gc` or force-prune unreachable Git objects without a separate recovery decision.

## Validated scanner workflow

1. Run 3D Scanner 3D Scanner with `scripts/17_scanner_3d.py`.
2. Use RTAB-Map as the only process that owns the Orbbec Gemini 215 camera and SLAM session.
3. Save the RTAB-Map database manually from RTAB-Map. Known saved-session directory:
   `C:\Users\TD-998\Documents\RTAB-Map`.
4. In 3D Scanner 3D Scanner, refresh saved sessions, select a `.db`, then export a textured raw OBJ.
5. Crop from the raw OBJ. The application writes a separate crop bundle containing OBJ, MTL, and texture files.
6. Reopen prior crop results through the `Cropped OBJ outputs` list; select one row, then use `Open cropped OBJ` or `Open output folder`.

## Crop-dialog behavior

- Left pane: 3D model preview; right-drag rotates and mouse wheel zooms.
- Right pane: flat 2D crop plane from the final left-pane camera angle; left-drag creates the crop rectangle.
- Rotation is throttled and uses a lower-detail moving preview. The crop plane updates after right-button release.
- The 2D crop plane filters overlapping points by depth, retaining the nearest visible point per screen cell to reduce rear/background clutter.
- Crop geometry still uses the final 3D camera projection; crop output does not modify the raw OBJ or RTAB-Map database.

## Auto-pause

- Auto-pause is experimental, opt-in, and only pauses RTAB-Map after three seconds without new map nodes.
- It must never stop RTAB-Map, close a database, or save on the operator's behalf.
- The real activity-probe hardware experiment was recorded in
  `docs/experiments/2026-07-17-scanner_3d-activity-probe.md`.

## Verification status

- Before the final merge, `main` passed `222 tests, 6 subtests`.
- The RTAB-Map + Gemini workflow was manually exercised, including saved database discovery, native textured OBJ export, and crop output.

## Local items intentionally not committed

- `third_party/` contains the local RTAB-Map runtime and is intentionally untracked.
- `outputs/scanner_3d/` contains generated scan/export/crop artifacts and is intentionally untracked.
- At handoff, these pre-existing draft plans remain untracked and were not pushed:
  - `docs/superpowers/plans/2026-07-15-imu-orientation-viewer.md`
  - `docs/superpowers/plans/2026-07-15-manual-capture-object-scanner.md`
