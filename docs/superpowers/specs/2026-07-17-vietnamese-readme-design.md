# Thiết kế README tiếng Việt

## Mục tiêu

Thay README prototype cũ bằng hướng dẫn vận hành tiếng Việt cho 3D Scanner
và luồng RTAB-Map + Orbbec Gemini 215 đang được dùng.

## Đối tượng và phạm vi

README hướng đến người vận hành Windows. Tài liệu chỉ tập trung vào cách mở
app, quét bằng RTAB-Map, lưu database, xuất raw OBJ và crop nhiều OBJ. Các
script prototype marker/markerless cũ không được trình bày như luồng chính.

## Cấu trúc

1. Giới thiệu vai trò của 3D Scanner và RTAB-Map.
2. Yêu cầu: Windows, Python environment của dự án, Orbbec Gemini 215 và
   RTAB-Map runtime đã được đóng gói trong repository qua Git LFS.
3. Khởi chạy bằng shortcut Desktop hoặc lệnh Python.
4. Quy trình scan: mở RTAB-Map, quét, lưu `.db`, refresh/chọn session, export
   raw OBJ, crop và mở OBJ đã crop.
5. Giải thích ngắn về database và nhiều OBJ trong một session.
6. Auto-pause: experimental, chỉ Pause sau ba giây không có node mới; không
   tự lưu hay tự Stop.
7. Vị trí file session/output và lưu ý clone cần Git LFS.
8. Nêu rõ các hướng scanner tự phát triển vẫn là prototype, không phải luồng
   vận hành chính.

## Quy ước chính xác

- RTAB-Map là tiến trình duy nhất dùng camera và sở hữu session SLAM.
- Database mặc định tại `C:\Users\TD-998\Documents\RTAB-Map`.
- Runtime RTAB-Map có trong `third_party/rtabmap` và được quản lý bằng Git LFS.
- Raw/cropped OBJ được ghi dưới `outputs/scanner_3d` và không được commit.
