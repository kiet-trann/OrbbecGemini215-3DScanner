# Markerless Scanner Delivery Roadmap

The approved design is implemented through four independently reviewable plans.
Execute them in order; do not start a later phase until the prior gate passes.

1. `2026-07-10-capture-hardware-foundation.md`
   - Explicit synchronized RGB-D profiles, IMU collection, depth processing,
     deterministic recording/replay, and the hardware qualification gate.
2. `2026-07-10-markerless-tracking.md`
   - IMU prediction, RGB-D odometry, ICP, quality gating, keyframes,
     relocalization, and pose graph optimization.
3. `2026-07-10-live-scanner-ui-fusion.md`
   - Live TSDF, scan-session concurrency, side-by-side Open3D GUI, and the
     runnable single-pass markerless scanner.
4. `2026-07-10-two-pass-finalization.md`
   - Real bottom-surface capture, automatic/manual pass registration, final
     TSDF rebuild, cleanup, and PLY/OBJ/STL export.

The Gemini 215 is declared insufficient only if Phase 1 fails the controlled
hardware gate after all corrective checks in the approved design spec have been
performed. Algorithmic tracking or reconstruction failures are not hardware
failure evidence.
