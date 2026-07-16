# Nonblocking Live Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep markerless pose tracking responsive while a worker builds the temporary 3D preview.

**Architecture:** A preview worker owns a preview-only TSDF fusion instance and latest-only queues for keyframes and completed meshes. The scanner submits keyframes without waiting, updates Open3D only on the main thread, and rebuilds the saved mesh from every accepted keyframe after stopping.

**Tech Stack:** Python, `threading`, `queue`, Open3D, pytest.

## Global Constraints

- Preview work may drop stale frames; final export must retain every accepted keyframe.
- The tracking thread must never call `extract_preview()`.
- The stateful quality gate must run once per packet.

---

### Task 1: Preview worker

**Files:** Create `src/scanner_app/fusion/preview_worker.py`; create `tests/test_preview_worker.py`.

- [ ] Write a failing test that starts `LivePreviewWorker`, submits a keyframe, and waits for `drain_latest_mesh()` to return the mesh produced by a fake fusion.
- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_preview_worker.py`; expect import failure for `LivePreviewWorker`.
- [ ] Implement `start()`, `submit(keyframe)`, `drain_latest_mesh()`, and `close()`. Use `Queue(maxsize=1)` plus `put_latest()` for input and output. The worker owns `fusion_factory(**fusion_kwargs)`, calls `integrate(keyframe)`, then publishes `extract_preview()`.
- [ ] Re-run the worker tests; expect pass.
- [ ] Commit `feat: add nonblocking live preview worker`.

### Task 2: Single gate evaluation

**Files:** Modify `src/scanner_app/tracking/markerless.py`; modify `tests/test_markerless_tracker.py`.

- [ ] Write a failing test with a direct bad estimate and a good relocalized estimate. Assert the recording quality gate receives exactly one evaluation timestamp for that packet.
- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_markerless_tracker.py`; expect the new assertion to fail.
- [ ] Select direct/relocalized estimates using `metrics_rejection_reason()` only. After selecting the final candidate, call `quality_gate.evaluate(metrics, packet.tracking_timestamp_us)` once.
- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_markerless_tracker.py tests/test_tracking_quality.py`; expect pass.
- [ ] Commit `fix: evaluate markerless timestamps once per frame`.

### Task 3: Scanner wiring

**Files:** Modify `scripts/14_markerless_scanner.py`; modify `tests/test_markerless_scanner_script.py`.

- [ ] Write failing tests asserting accepted keyframes are submitted to a worker, a completed mesh is passed to `preview.update_mesh()`, and the tracking loop never calls `fusion.extract_preview()`.
- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_markerless_scanner_script.py`; expect failures against the synchronous preview implementation.
- [ ] Create the worker only when `preview.wants_mesh_preview`; submit accepted keyframes and drain meshes each loop. Close the worker before closing the preview. Leave final export as a fresh full rebuild from `final_keyframes`.
- [ ] Run `python -m pytest -q -p no:cacheprovider`; expect all tests to pass.
- [ ] Commit `feat: keep tracking responsive during live mesh preview`.
