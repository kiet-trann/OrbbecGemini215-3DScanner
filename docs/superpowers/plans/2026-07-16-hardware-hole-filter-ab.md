# Hardware Hole-Filter A/B Implementation Plan

> Required execution skill: `superpowers:executing-plans`. Tasks use checkboxes.

**Goal:** Verify whether the Gemini 215 firmware hole filter materially improves valid depth at the known box-edge failure point, with safe rollback.

**Architecture:** This is a device-property A/B experiment, not a tracker change. Read and record the current property, enable only `OB_PROP_DEPTH_HOLEFILTER_BOOL`, then repeat the existing 3-by-3 raw-depth measurement. Restore the original value unless the central edge region improves without invalid geometry.

**Tech Stack:** Python 3, `pyorbbecsdk`, Gemini 215, NumPy, existing `OrbbecCapture` adapter.

## Global Constraints

- Keep Close_Up Precision Mode, stream profiles, 0.20-0.40 m range, and color alignment unchanged.
- Do not start RTAB-Map, export geometry, lower tracking thresholds, or alter fusion.
- Change only `OB_PROP_DEPTH_HOLEFILTER_BOOL`; restore its recorded value on failed A/B validation.
- Control grid: center-middle mean 39.39%, minimum 5.53%; center-bottom mean 50.44%, minimum 44.50% valid depth.

## Task 1: Apply one runtime property

**Files:** no repository file; Gemini runtime device property only.

**Interfaces:** consume `Device.is_property_supported()`, `Device.get_bool_property()`, and `Device.set_bool_property()` from `pyorbbecsdk`. Produce a before/after readback.

- [ ] Verify read and write support for `OB_PROP_DEPTH_HOLEFILTER_BOOL` before mutation. Expected control state: read=True, write=True, value=False.
- [ ] Enable `OB_PROP_DEPTH_HOLEFILTER_BOOL=True` and read it back. Continue only when the readback is True.
- [ ] Record the former value so it can be restored after a failed experiment.

## Task 2: Repeat the spatial depth measurement

**Files:** no repository file; existing capture adapter and in-memory measurement only.

**Interfaces:** consume `OrbbecCapture.read_packet()` with `depth_raw` and `depth_scale_mm`. Produce 8-second mean and minimum valid-depth ratios in a 3-by-3 image grid.

- [ ] Hold the same box edge fixed. Use Close_Up Precision Mode, color alignment, and 0.20-0.40 m range. Do not run a tracker or map.
- [ ] Record 8 seconds. A pixel is valid only if raw depth is nonzero and converts into the evaluation range.
- [ ] Candidate passes only if center-middle mean > 0.3939, center-middle minimum > 0.0553, center-bottom mean >= 0.5044, and center-bottom minimum >= 0.4450.
- [ ] Reject a candidate that fills background outside the object silhouette even if its global ratio rises.

## Task 3: Decide integration or rollback

**Files:**
- On pass: `src/scanner_app/camera/orbbec_capture.py` and `tests/test_orbbec_capture.py` in a separate TDD change.
- On failure: `docs/experiments/2026-07-16-custom-markerless-failure-record.md`.

**Interfaces:** consume Task 2 measurement; produce either an explicit scanner-camera configuration or a documented rejection.

- [ ] On pass, start a separate TDD change to expose a capture configuration field, enable this supported property, and test readback with the fake device.
- [ ] On failure, restore the former property value, document the A/B values, and do not add filter code or more tracker tuning.
