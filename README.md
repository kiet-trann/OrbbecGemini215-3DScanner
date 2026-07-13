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

Chay hardware qualification gate truoc khi tiep tuc markerless tracking:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe scripts\12_hardware_qualification.py
```

Dung mot tam phang matte, khong bong, mau dong nhat, dat vuong goc voi camera va lap day nua giua
khung depth. Chuan bi moc 0.20 m, 0.30 m va 0.40 m tu camera den mat phang. Giu camera, day USB 3.0
va target co dinh trong warm-up 10 giay va tung lan capture. Script se ghi
`data/sessions/qualification_<timestamp>.json`, in PASS/FAIL, va chi dat khi RGB-D >= 24 fps,
IMU trong 190-210 Hz, central object valid ratio >= 0.70, median noise <= 1.0 mm va p90 noise <= 2.0 mm.
Khong tiep tuc markerless tracking neu gate nay FAIL.

Chay markerless RGB-D tracking o Close-Up Precision Mode cho vat nho 5-30 cm, giu depth trong
khoang 0.20-0.30 m va in moi ket qua tracking thanh mot dong JSON:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe scripts\13_markerless_tracking.py --min-depth-m 0.20 --max-depth-m 0.30
```

Che do nhanh de tracking live vat nho o 25 cm, uu tien dat >=15 accepted updates/s:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe scripts\13_markerless_tracking.py --backend opencv --tracking-width 240 --tracking-height 150 --min-depth-m 0.20 --max-depth-m 0.30 --print-every 0
```

Chay scan 3D markerless live cho vat nho nhu hop sua dat tren ban. Giu camera khoang 25 cm,
di chuyen cham quanh vat; cua so RGB nam ben trai, model TSDF nam ben phai. Nhan `Q` hoac `ESC`
de dung va ghi mesh PLY vao `outputs/ply`:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe scripts\14_markerless_scanner.py --backend opencv --tracking-width 240 --tracking-height 150 --min-depth-m 0.20 --max-depth-m 0.30
```

`--min-depth-m/--max-depth-m` la vung object/fusion de cat model hop sua. Tracking live mac dinh
dung depth rong hon `0.20-0.50 m` de co du diem bam tren vat va mat ban gan. Neu RGB thay ro nhung
status van `LOST` voi `reason=fitness_below_minimum` va `depth` thap, thu tang tracking range:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe scripts\14_markerless_scanner.py --backend opencv --tracking-width 240 --tracking-height 150 --min-depth-m 0.20 --max-depth-m 0.30 --tracking-max-depth-m 0.50 --print-every 10
```

Neu van mat tracking khi cua so model dang cap nhat, giam tai preview de uu tien tracking:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe scripts\14_markerless_scanner.py --backend opencv --tracking-width 240 --tracking-height 150 --min-depth-m 0.20 --max-depth-m 0.30 --live-integrate-interval-s 1.0 --preview-interval-s 1.0 --print-every 10
```

Smoke test khong mo cua so va khong export mesh:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe scripts\14_markerless_scanner.py --headless --no-export --max-frames 120 --backend opencv --tracking-width 240 --tracking-height 150 --min-depth-m 0.20 --max-depth-m 0.30
```

Chay lai tracking tu session da record thi can truyen depth intrinsics cua session:

```powershell
C:\Users\TD-998\OrbbecGemini215-3DScanner\.venv\Scripts\python.exe scripts\13_markerless_tracking.py --replay data\sessions\scan_demo --max-frames 120 --intrinsics-fx 500 --intrinsics-fy 500 --intrinsics-cx 320 --intrinsics-cy 200 --intrinsics-width 640 --intrinsics-height 400
```

Xem point cloud co mau real-time:

```powershell
python scripts/03_pointcloud_viewer.py
```

Chay marker tracking voi ArUco `DICT_4X4_50`, marker vat ly 6 cm:

```powershell
python scripts/03_marker_tracking.py --marker-size-m 0.06
```

Tao marker PNG dung dictionary dang dung trong prototype:

```powershell
python scripts/00_generate_aruco_marker.py --dictionary DICT_4X4_50 --id 0 --marker-size-px 800 --border-px 160
```

File mac dinh duoc tao tai `data/calibration/aruco_DICT_4X4_50_id0_800px.png`.
Khi test, neu log `markers=0 | rejected=0` thi camera chua thay candidate marker ro rang;
neu `rejected` tang nhung `markers=0` thi thu tang kich thuoc marker, giu phang, tang anh sang,
hoac kiem tra dung dictionary `DICT_4X4_50`.

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

Khi marker de mat khoi khung hinh, co the dung theo so frame track duoc thay vi tong so frame camera:

```powershell
python scripts/05_merge_pointcloud.py --marker-size-m 0.06 --target-tracked-frames 50 --max-frames 1000
```

Giam dung luong PLY bang voxel downsample truoc khi ghi file:

```powershell
python scripts/05_merge_pointcloud.py --marker-size-m 0.06 --target-tracked-frames 50 --max-frames 1000 --voxel-size-m 0.003
```

Scan theo thoi gian that va chi lay moi N frame tracked de co du thoi gian di quanh vat:

```powershell
python scripts/05_merge_pointcloud.py --marker-size-m 0.06 --capture-seconds 30 --tracked-frame-stride 3 --min-depth-m 0.15 --max-depth-m 0.80 --voxel-size-m 0.002
```

Mo preview RGB trong luc merge de biet marker va vat co nam trong khung hinh khong:

```powershell
python scripts/05_merge_pointcloud.py --marker-size-m 0.06 --capture-seconds 30 --tracked-frame-stride 3 --preview --min-depth-m 0.15 --max-depth-m 0.80 --voxel-size-m 0.002
```

Voi vat nho nhu vo tai nghe, nen scan trong mot ROI theo he toa do marker de tranh ghep ca mat ban.
Dat marker co dinh canh vat, mo preview, roi chinh cac moc `roi-*` sao cho hop 3D bao quanh vat:

```powershell
python scripts/05_merge_pointcloud.py --marker-size-m 0.06 --capture-seconds 35 --tracked-frame-stride 4 --preview --min-depth-m 0.15 --max-depth-m 0.70 --voxel-size-m 0.0015 --roi-min-x -0.20 --roi-max-x 0.04 --roi-min-y -0.15 --roi-max-y 0.12 --roi-min-z 0.01 --roi-max-z 0.16
```

Neu point cloud bi tach lop, dung TSDF fusion de tao mesh lien be mat hon thay vi chong cac point cloud tho:

```powershell
python scripts/06_tsdf_fusion.py --marker-size-m 0.06 --capture-seconds 45 --tracked-frame-stride 5 --preview --min-depth-m 0.15 --max-depth-m 0.70 --voxel-length-m 0.002 --sdf-trunc-m 0.010 --roi-min-x -0.28 --roi-max-x 0.08 --roi-min-y -0.18 --roi-max-y 0.16 --roi-min-z 0.015 --roi-max-z 0.14
```

Mo lai file PLY da scan bang Open3D, thay cho Windows 3D Viewer:

```powershell
python scripts/08_view_ply.py outputs/ply/merged_cloud_20260707_081312.ply
```

Chi in thong tin file, khong mo cua so GUI:

```powershell
python scripts/08_view_ply.py outputs/ply/merged_cloud_20260707_081312.ply --info-only
```

Cat bot mat ban/nen. Voi vat nho, mac dinh khong giu cum lon nhat de tranh lam mat vat:

```powershell
python scripts/09_crop_ply.py outputs/ply/merged_cloud_20260707_091637.ply
python scripts/08_view_ply.py outputs/ply/merged_cloud_20260707_091637_cropped.ply
```

Dung point cloud da crop de thu dung mesh va xuat OBJ/STL/PLY:

```powershell
python scripts/10_reconstruct_mesh.py outputs/ply/earbud_case_tight_crop.ply --output outputs/obj/earbud_case.obj
python scripts/10_reconstruct_mesh.py outputs/ply/earbud_case_tight_crop.ply --output outputs/stl/earbud_case.stl
```

## Prototype Definition of Done

- Gemini 215 ket noi on dinh.
- RGB + Depth hien thi real-time.
- Point cloud single frame xuat duoc `.PLY`.
- Marker tracking hoat dong va co camera pose hop le.
- Nhieu frame duoc ghep thanh point cloud tong.
- File `.PLY` mo duoc bang CloudCompare, MeshLab, Blender hoac Open3D.
