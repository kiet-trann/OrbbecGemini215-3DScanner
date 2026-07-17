# Smooth 3D preview and flat crop-plane design

## Goal

Make rotation in the crop dialog responsive while retaining a flat 2D crop
surface that precisely matches the last selected 3D viewing angle.

## Interaction model

The left canvas remains the 3D model viewer. While the user right-drags, it
renders a low-detail preview at most once every 33 milliseconds. On right-button
release it redraws at normal detail, calculates the current camera projection,
and refreshes the right canvas.

The right canvas is a static flat 2D projection of the mesh from that final
camera angle. It does not redraw while the 3D view is rotating. The operator
draws the crop rectangle only on this right-hand canvas.

## Geometry and preview

Both canvases use the same `CameraProjection` after a rotation finishes. The
right crop surface draws sampled projected mesh vertices as a 2D point image.
The cropper receives that same projection with the rectangle, so its face
selection remains mathematically aligned with the displayed 2D crop.

After rectangle dragging ends, the left viewer draws a single highlighted
preview of faces that will be kept. It does not recompute highlighted faces for
every pointer movement.

## Performance and safety

The low-detail 3D pass has a fixed maximum face count; the full settled pass
has a larger fixed cap. Rendering uses Tk's scheduled callbacks so multiple
mouse events coalesce into one frame. Rotation clears an old rectangle because
it belongs to the prior projection. The crop service, raw OBJ, materials, and
textures are unchanged.

## Testing

Pure helpers expose the preview-detail cap and sampled 2D point list. Tests
verify that a settled projection maps the same vertex positions for the crop
plane, and that the moving detail cap is lower than the settled cap.
