# 3D Viewer compatible OBJ export

## Goal

Allow the Windows 3D Viewer to show the colour texture of RTAB-Map OBJ exports without changing or discarding the original full-resolution bundle.

## Scope

After RTAB-Map produces a valid textured OBJ bundle, the application will create a second, viewer-compatible bundle. Its texture images will be JPEG files capped at 4096 pixels on their longest edge. The OBJ and MTL files will preserve the original mesh, UV coordinates, materials, and relative texture references.

The raw RTAB-Map bundle remains unchanged. Cropping continues to use that raw bundle for maximum source quality. Each crop result will also receive a viewer-compatible copy. The crop catalog and **Open cropped OBJ** action will refer to the compatible OBJ, so opening remains a single-file action for the operator.

## Design

Create a focused compatibility-bundle service that:

1. Copies the OBJ and MTL files into a sibling `viewer` output directory.
2. Reads each `map_Kd` reference from the copied MTL files.
3. Re-encodes referenced JPG, JPEG, or PNG textures to JPEG at at most 4096 pixels, preserving aspect ratio; images already within the limit are copied without enlargement.
4. Rewrites the copied MTL's `map_Kd` entries to the compatible texture filenames.
5. Fails the compatible-bundle step with a clear error while preserving the original raw or crop bundle.

Windows image APIs already available with the desktop runtime will perform the resize; no third-party Python package will be introduced.

## User-facing behavior

- The existing exported raw OBJ stays available as the high-resolution source.
- A compatible bundle is created automatically after export and after crop.
- The application reports the compatible OBJ path on success.
- **Open cropped OBJ** opens the compatible OBJ by default.
- Existing crop bundles remain readable; only newly created export/crop outputs gain the compatible copy.

## Verification

Automated tests will first prove that the compatibility service creates a separate bundle, caps an oversized texture at 4096 pixels, preserves the source artifacts, and leaves a valid OBJ-to-MTL-to-texture reference chain. Export and crop integration tests will verify that their default/opened path is the compatible OBJ.

Manual verification: create a new scan export, open the compatible OBJ in Windows 3D Viewer, and confirm that its material texture is shown.
