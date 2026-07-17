# RTAB-Map preview coordinate design

## Goal

Make the crop preview use the RTAB-Map mesh coordinate convention so its named
views show the intended directions.

## Coordinate convention

RTAB-Map exported OBJ data is treated as X-forward, Y-left and Z-up. The crop
preview converts this basis to its internal Y-up renderer without changing the
source OBJ:

```
preview_x = rtabmap_x
preview_y = rtabmap_z
preview_z = -rtabmap_y
```

The conversion is included in the projection matrix used for both drawing and
crop hit testing. Cropped OBJ vertices are therefore still written in their
original RTAB-Map coordinates.

## Named views

- Front: camera looks at the +X face.
- Back: camera looks at the -X face.
- Top: camera looks down onto the +Z face.
- Bottom: camera looks up at the -Z face.

## Verification

Projection tests use points on the RTAB-Map axes to prove that each named view
makes its corresponding face nearest to the camera. Existing crop and full
test suites must remain green.
