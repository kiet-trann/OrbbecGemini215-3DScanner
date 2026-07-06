# Orbbec Gemini 215 Real-Time 3D Scanner Prototype

Prototype Python cho bai toan scan 3D real-time bang camera Orbbec Gemini 215.

Muc tieu dau tien:

- Ket noi va lay RGB-D tu Orbbec Gemini 215.
- Hien thi RGB, depth va point cloud real-time.
- Tracking camera bang ArUco hoac AprilTag marker.
- Ghep nhieu frame depth/point cloud thanh mo hinh 3D.
- Xuat ket qua scan ra `.PLY`, chuan bi mo rong `.OBJ` va `.STL`.

## Tech Stack

- Python 3.10+
- pyorbbecsdk2
- OpenCV / opencv-contrib-python
- Open3D
- NumPy
- SciPy

## Project Layout

```text
docs/                  Tai lieu yeu cau, kien truc, setup, quy trinh scan
src/scanner_app/       Package chinh cua prototype
scripts/               Script chay theo tung moc phat trien
data/raw/              Du lieu RGB-D raw neu can luu tam
data/sessions/         Du lieu moi lan scan
data/calibration/      Intrinsic, marker config, calibration files
outputs/ply/           Ket qua .PLY
outputs/obj/           Ket qua .OBJ sau nay
outputs/stl/           Ket qua .STL sau nay
tests/                 Test cho module xu ly doc lap
```

## Development Milestones

1. `scripts/01_rgbd_viewer.py` - Mo camera va hien thi RGB/Depth.
2. `scripts/02_export_pointcloud.py` - Xuat `single_frame.ply`.
2b. `scripts/03_pointcloud_viewer.py` - Hien thi point cloud co mau real-time bang Open3D.
3. `scripts/03_marker_tracking.py` - Detect marker va ve truc XYZ.
4. `scripts/04_pose_estimation.py` - Tinh camera pose 4x4.
5. `scripts/05_merge_pointcloud.py` - Ghep point cloud nhieu frame.
6. `scripts/06_tsdf_fusion.py` - TSDF fusion bang Open3D.
7. `scripts/07_export_mesh.py` - Tao mesh va xuat `.PLY` / `.OBJ` / `.STL`.

## Quick Start

```powershell
cd C:\Users\TD-998\OrbbecGemini215-3DScanner
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Sau khi cai Orbbec SDK va cam camera qua USB 3.0:

```powershell
python scripts/01_rgbd_viewer.py
```

Xem point cloud co mau real-time:

```powershell
python scripts/03_pointcloud_viewer.py
```

Chay marker tracking voi ArUco `DICT_4X4_50`, marker vat ly 6 cm:

```powershell
python scripts/03_marker_tracking.py --marker-size-m 0.06
```

Smoke test khong mo cua so GUI:

```powershell
python scripts/03_marker_tracking.py --headless --max-frames 3
```

Luu camera pose 4x4 tu marker tracking vao `data/sessions/*.jsonl`:

```powershell
python scripts/04_pose_estimation.py --marker-size-m 0.06
```

Scan va ghep cac frame co marker thanh mot point cloud tong:

```powershell
python scripts/05_merge_pointcloud.py --marker-size-m 0.06 --max-frames 120
```

## Prototype Definition of Done

- Gemini 215 ket noi on dinh.
- RGB + Depth hien thi real-time.
- Point cloud single frame xuat duoc `.PLY`.
- Marker tracking hoat dong va co camera pose hop le.
- Nhieu frame duoc ghep thanh point cloud tong.
- File `.PLY` mo duoc bang CloudCompare, MeshLab, Blender hoac Open3D.
