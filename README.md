# 3D Scanner

🇻🇳 [Tiếng Việt](README.md) · 🇬🇧 [English](README.en.md)

Ứng dụng Windows hỗ trợ quy trình scan 3D với **Orbbec Gemini 215** và
**RTAB-Map**. RTAB-Map đảm nhiệm camera, SLAM và tạo model 3D; 3D Scanner
giúp mở RTAB-Map, quản lý session đã lưu, xuất OBJ và crop từng vật thể.

> RTAB-Map là tiến trình duy nhất được dùng camera và sở hữu session scan.
> 3D Scanner không thay thế RTAB-Map, không tự Stop và không tự lưu database.

## Quy trình chính

```text
Mở 3D Scanner
        ↓
Chọn profile camera → Apply & Open RTAB-Map → quét vật thể → lưu database (.db)
        ↓
Refresh sessions → chọn database → Export raw OBJ
        ↓
Crop raw OBJ → khoanh vùng vật thể → Create cropped OBJ
```

Một database có thể chứa toàn bộ không gian đã quét. Bạn có thể xuất một raw
OBJ của cả session, sau đó crop nhiều OBJ riêng cho từng vật thể. App không tự
nhận diện số lượng vật thể trong database.

## Yêu cầu

- Windows 10/11.
- Orbbec Gemini 215 và driver/SDK hoạt động.
- Python environment `.venv` của dự án.
- Git LFS khi clone repository: RTAB-Map runtime được lưu trong Git LFS.

Nếu clone dự án trên máy khác, lấy runtime trước khi chạy app:

```powershell
git lfs pull
```

Sau đó cần có các file sau:

```text
third_party\rtabmap\RTABMap-0.23.1-win64\bin\RTABMap.exe
third_party\rtabmap\RTABMap-0.23.1-win64\bin\rtabmap-export.exe
```

Nếu chưa có environment Python:

```powershell
$ProjectRoot = (Get-Location).Path
python -m venv .venv
& "$ProjectRoot\.venv\Scripts\Activate.ps1"
python -m pip install -e .[dev]
```

## Mở ứng dụng

Nếu đã tạo shortcut Desktop, mở **3D Scanner** từ shortcut đó.

Hoặc chạy trực tiếp tại thư mục dự án:

```powershell
.\.venv\Scripts\pythonw.exe scripts\17_3d_scanner.py
```

Khi cần thấy lỗi trong terminal, dùng `python.exe` thay cho `pythonw.exe`:

```powershell
.\.venv\Scripts\python.exe scripts\17_3d_scanner.py
```

## Scan và lưu session

1. Mở 3D Scanner.
2. Trong **Camera setup**, chọn **Near — Close-up Precision** (0,15--0,32 m)
   hoặc **Far — Long-distance** (0,20--0,70 m).
3. Có thể bấm **Refresh camera settings** để xem mode, serial, firmware,
   profile stream, dải depth, alignment, IMU và depth filters mà camera trả về.
4. Bấm **Apply & Open RTAB-Map**. App thiết lập và xác nhận mode trước khi
   RTAB-Map mở camera.
5. Trong RTAB-Map, chọn nguồn Orbbec Gemini 215 rồi quét chậm quanh vật thể.
   Cố gắng giữ camera thấy các bề mặt cần lấy và tránh chuyển động quá nhanh.
6. Khi quét xong, Pause nếu cần kiểm tra model.
7. Lưu session từ RTAB-Map: **File → Close database**, sau đó xác nhận lưu
   database `.db`.
8. Quay lại 3D Scanner và bấm **Refresh sessions**.

Khi RTAB-Map đang chạy, app khóa profile và các nút preflight: **không thể đổi
chế độ** giữa phiên scan. Hãy đóng RTAB-Map, chọn profile mới, rồi bấm
**Apply & Open RTAB-Map** cho phiên tiếp theo.

Database RTAB-Map mặc định nằm tại:

```text
%USERPROFILE%\Documents\RTAB-Map
```

File `.db` không chỉ là một model OBJ. Nó lưu dữ liệu session/map của RTAB-Map
(ảnh, depth, pose camera và dữ liệu SLAM) để có thể xuất lại hoặc xử lý tiếp.

## Xuất raw OBJ

1. Trong bảng **Saved RTAB-Map sessions**, chọn database cần dùng.
2. Bấm **Export raw OBJ**.
3. Chờ RTAB-Map xuất raw OBJ, MTL và texture.

Raw OBJ là toàn bộ hình học của session: có thể gồm vật thể, mặt bàn, nền hoặc
nhiều vật thể. Nó luôn được giữ nguyên để bạn có thể crop lại nhiều lần.

Sau mỗi lần export hoặc crop, app tạo thêm file GLB trong thư mục `viewer` cho Windows
3D Viewer. GLB tự chứa mesh, UV, material và JPEG có cạnh dài tối đa 4096 px để nạp
màu ổn định. Raw OBJ, MTL và texture gốc độ phân giải cao vẫn được giữ nguyên để xử lý
về sau. Khi mở bằng 3D Viewer, chỉ cần mở một file `.glb` trong thư mục `viewer`.

## Crop OBJ

1. Bấm **Crop raw OBJ** và chọn raw OBJ vừa xuất.
2. Ở khung trái, dùng **chuột phải kéo** để xoay model và **con lăn** để zoom.
   Các nút Front, Back, Top, Bottom đưa model về các góc chuẩn RTAB-Map.
3. Ở khung phải, dùng **chuột trái kéo** một hình chữ nhật quanh phần muốn giữ.
4. Bấm **Create cropped OBJ**.

Kết quả crop là một bundle OBJ riêng gồm `.obj`, `.mtl` và texture. Chọn một
hàng trong **Cropped OBJ outputs** rồi bấm **Open cropped OBJ** hoặc
**Open output folder** để mở lại kết quả sau khi khởi động app.

## Auto-pause (thử nghiệm)

Auto-pause là tính năng opt-in. Khi RTAB-Map đang scan và không có node map mới
trong khoảng 3 giây, app chỉ gửi lệnh **Pause** để bạn kiểm tra model.

- Không tự Stop RTAB-Map.
- Không tự Close database.
- Không tự lưu session.
- Nếu hiện `Auto-pause unavailable`, app không có tín hiệu activity đủ tin cậy
  từ session đang chạy; hãy Pause thủ công khi cần.

## Vị trí file

| Nội dung | Vị trí |
| --- | --- |
| Database RTAB-Map đã lưu | `%USERPROFILE%\Documents\RTAB-Map` |
| Runtime RTAB-Map | `third_party\rtabmap\RTABMap-0.23.1-win64` |
| Raw OBJ và cropped OBJ | `outputs\scanner_3d` |

`third_party/rtabmap` được quản lý bằng Git LFS. Các file scan, raw OBJ và crop
OBJ trong `outputs/scanner_3d` là dữ liệu sinh ra khi vận hành, không nên
commit lên Git.

## Ghi chú về prototype cũ

Repository vẫn chứa các script marker, markerless và fusion tự phát triển để
tham khảo/đánh giá kỹ thuật. Chúng không phải luồng vận hành chính hiện tại.
Để scan 3D với Gemini 215, dùng 3D Scanner + RTAB-Map theo hướng dẫn trên.
