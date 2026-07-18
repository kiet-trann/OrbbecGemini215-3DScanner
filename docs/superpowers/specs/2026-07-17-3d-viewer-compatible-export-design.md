# 3D Viewer compatible GLB export

## Goal

Allow Windows 3D Viewer to show the colour texture of RTAB-Map scans without changing or discarding the original full-resolution OBJ bundle.

## Evidence and decision

The original and the 4096-pixel compatibility OBJ bundles contain valid `mtllib`, `usemtl`, UV coordinates, MTL `map_Kd`, and JPEG files. Windows 3D Viewer still renders them white. Therefore external OBJ/MTL textures are not a reliable interface for this application.

The compatible output will be a binary glTF (`.glb`) instead. A GLB embeds the mesh, UV coordinates, material, and JPEG texture in one file, avoiding the external-material import path that failed in Windows 3D Viewer.

## Scope

After RTAB-Map produces a valid textured OBJ bundle, the application will create `viewer/<mesh>.glb` beside the untouched raw bundle. The GLB uses a JPEG texture capped at 4096 pixels on its longest edge. Cropping continues to use the raw OBJ for full source quality and produces its own `viewer/<cropped-mesh>.glb` before publishing the crop.

The converter supports one textured material, which matches the current RTAB-Map exports. It must reject a source with zero or more than one textured material rather than emitting a visually incorrect GLB.

## Design

Create a focused GLB writer that:

1. Parses an OBJ's positions, UVs, normals, triangular faces, `mtllib`, `usemtl`, and its one `map_Kd` texture.
2. Creates render vertices from the unique `(position, UV, normal)` combinations used by face corners.
3. Resizes and encodes the diffuse texture to JPEG at a maximum 4096-pixel edge using existing OpenCV.
4. Writes a glTF 2.0 JSON chunk and binary chunk containing positions, normals, UVs, indices, and JPEG image bytes according to the GLB 2.0 container format.
5. Publishes the completed GLB atomically at `viewer/<source-stem>.glb`; on failure, keeps the raw export or crop untouched.

No new third-party dependency is introduced. Open3D can read the source texture but cannot write textured GLB files, so the narrow writer is intentionally local to this workflow.

## User-facing behavior

- The raw OBJ/MTL/full-resolution texture remains the source bundle for future MeshLab or Blender use.
- Each new export and crop gains a `viewer/*.glb` file for Windows 3D Viewer.
- The crop catalog prefers the viewer GLB when present; legacy raw OBJ crops remain discoverable.
- The action label becomes **Open cropped model** and opens the GLB by default.
- Compatibility errors report the source/material problem without deleting raw artifacts.

## Verification

Tests first prove that a GLB has the `glTF` header, embeds an image, defines a base-colour texture, caps the image at 4096 pixels, and leaves the source OBJ bundle unchanged. Integration tests verify export/crop path generation and catalog preference. Manual verification opens a generated GLB in Windows 3D Viewer and confirms texture colour appears.
