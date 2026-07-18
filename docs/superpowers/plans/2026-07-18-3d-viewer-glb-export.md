# 3D Viewer Compatible GLB Export Implementation Plan

**Goal:** Replace the unreliable external OBJ/MTL texture preview with a self-contained GLB that Windows 3D Viewer can render in colour.

**Architecture:** Parse the one-material RTAB-Map OBJ, de-index its position/UV/normal corner tuples into glTF render vertices, resize the diffuse texture to a maximum 4096-pixel JPEG, and write a standards-compliant GLB 2.0 container. Integrate the result as `viewer/<stem>.glb`; raw OBJ remains the crop source and fallback.

**Tech Stack:** Python 3.11, OpenCV, `struct`, `json`, pytest, Tkinter.

## Task 1: Write and test the textured GLB bundle writer

**Files:**
- Create: `src/scanner_app/rtabmap/glb_bundle.py`
- Create: `tests/test_rtabmap_glb_bundle.py`
- Delete: `src/scanner_app/rtabmap/viewer_bundle.py`
- Delete: `tests/test_rtabmap_viewer_bundle.py`

- [ ] Write a failing test that builds an 8192×4096 single-material OBJ fixture with positions, UVs, normals, and one triangle; call `create_3d_viewer_glb(source, output)`; then parse the resulting GLB header and JSON chunk.

```python
assert glb.read_bytes()[:4] == b"glTF"
assert document["asset"]["version"] == "2.0"
assert document["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] == {"index": 0}
assert document["images"][0]["mimeType"] == "image/jpeg"
assert image_dimensions(extract_image(glb, document)) == (4096, 2048)
assert source_texture_dimensions == (8192, 4096)
```

- [ ] Run `C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe -m pytest tests/test_rtabmap_glb_bundle.py -q` and confirm failure because `glb_bundle` is absent.
- [ ] Implement `create_3d_viewer_glb(source_obj: Path, output_path: Path, max_texture_dimension: int = 4096) -> Path` with these exact stages:

```python
positions, texcoords, normals, faces, material_name = _read_textured_obj(source_obj)
texture = _find_single_diffuse_texture(source_obj, material_name)
vertices, indices = _build_glb_vertices(positions, texcoords, normals, faces)
jpeg = _encode_capped_jpeg(texture, max_texture_dimension)
_write_glb(output_path, vertices, indices, jpeg)
```

`_write_glb` must write the 12-byte GLB header (`b"glTF"`, version `2`, total byte length), a 4-byte-aligned JSON chunk of type `0x4E4F534A`, and a 4-byte-aligned binary chunk of type `0x004E4942`. The document must contain one scene, node, mesh primitive, material, texture, image, sampler, buffer, five buffer views (positions, normals, UVs, indices, JPEG), and four accessors. It must set `mode: 4`, `componentType: 5126` for floats, `componentType: 5125` for indices, and `mimeType: image/jpeg`.
- [ ] Run the writer test and confirm pass.
- [ ] Commit with `feat: generate textured GLB viewer bundles`.

## Task 2: Replace OBJ viewer integration with GLB integration

**Files:**
- Modify: `src/scanner_app/rtabmap/exporter.py`
- Modify: `src/scanner_app/rtabmap/obj_crop.py`
- Modify: `tests/test_rtabmap_exporter.py`
- Modify: `tests/test_rtabmap_obj_crop.py`

- [ ] Write failing assertions that `ExportResult.viewer_model` and `CropResult.viewer_model` end in `.glb`, are published at `viewer/<source-stem>.glb`, and leave original JPEG dimensions unchanged.
- [ ] Run the targeted exporter and crop tests; confirm they fail on the absent `viewer_model` field.
- [ ] Change both result dataclasses to expose `viewer_model: Path | None` (export) or `viewer_model: Path` (crop). Call `create_3d_viewer_glb(raw_obj, raw_obj.parent.parent / "viewer" / f"{raw_obj.stem}.glb")` after export validation and `create_3d_viewer_glb(cropped_obj, temporary / "viewer" / f"{cropped_obj.stem}.glb")` before publishing a crop. On export compatibility failure return the valid raw paths plus `3D Viewer model failed: ...`; on crop compatibility failure remove its temporary directory.
- [ ] Run targeted tests and confirm pass.
- [ ] Commit with `feat: generate GLB models after export and crop`.

## Task 3: Prefer GLB in the application UI and crop catalog

**Files:**
- Modify: `src/scanner_app/visualization/crop_catalog.py`
- Modify: `src/scanner_app/visualization/scanner_3d_window.py`
- Modify: `tests/test_crop_catalog.py`
- Modify: `tests/test_scanner_3d_window.py`

- [ ] Write a failing catalog test with a raw `<crop>/model_cropped.obj` and compatible `<crop>/viewer/model_cropped.glb`; assert the catalog returns exactly the GLB. Update the crop-result selection test to expect `viewer_model`.
- [ ] Run catalog/UI tests and confirm they fail because the current catalog expects a compatible OBJ.
- [ ] Change compatible lookup to `path.parent / "viewer" / f"{path.stem}.glb"`; leave legacy raw OBJ entries as fallback. Update status messages and selection to `viewer_model`; change the button label to **Open cropped model**.
- [ ] Run catalog/UI tests and confirm pass.
- [ ] Commit with `feat: open compatible GLB models by default`.

## Task 4: Document and verify Windows 3D Viewer output

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `tests/test_project_docs.py`

- [ ] Change the documentation regression test to require `GLB`, `viewer`, `4096`, and `raw` in each README, then confirm it fails.
- [ ] Update Vietnamese and English workflow instructions: raw OBJ remains high-resolution source, `viewer/*.glb` embeds the capped JPEG, and **Open cropped model** uses it by default.
- [ ] Run the focused tests and the full suite: `C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe -m pytest -q`.
- [ ] Generate a GLB from the existing `lam_face_mesh.obj`, open it in Windows 3D Viewer, and confirm texture colour manually before offering branch integration options.
- [ ] Commit with `docs: explain GLB viewer exports`.
