# Hardware hole-filter A/B validation

## Goal

Determine whether Gemini 215's firmware depth-hole filter improves valid depth at a box edge before changing tracking or fusion.

## Evidence

- The direct RGB-D measurement at the problematic edge showed depth only in the center image column; the center-middle region varied from 5.53% to 39.39% valid depth in the 0.20–0.40 m range.
- The device exposes `OB_PROP_DEPTH_HOLEFILTER_BOOL` with read and write permission and reports it disabled.
- No device-recommended software filters are exposed. Creating SDK software filter objects exits the native Python binding without a usable error.

## A/B procedure

1. Retain the already recorded baseline grid measurement with the hole filter disabled.
2. Enable only `OB_PROP_DEPTH_HOLEFILTER_BOOL`; do not alter work mode, range, stream profile, registration, or tracking.
3. Repeat the same 8-second 3-by-3 depth-grid measurement at the same edge.
4. Keep the property only if the center-edge region has materially higher and less variable valid depth without filling the background across the object silhouette. Otherwise restore its former value.

## Scope and safety

The test operates at camera-property and diagnostic levels only. It does not start RTAB-Map, create a map, export geometry, or modify tracker thresholds. The property value is read first and will be restored if the A/B test fails.

## Acceptance

The candidate passes only if the repeated measurement shows a sustained improvement in the problematic central region. A higher global ratio alone is insufficient.
