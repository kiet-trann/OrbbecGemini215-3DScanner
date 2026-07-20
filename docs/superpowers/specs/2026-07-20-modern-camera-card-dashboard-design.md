# Camera card dashboard hiện đại

## Mục tiêu

Đồng bộ trang Camera với dashboard card sáng đã áp dụng cho phần Phiên quét & Kết quả. Giao diện mới phải giống bố cục bản xem trước: cấu hình dễ thao tác ở trên, thiết bị đang kết nối cạnh bên, thông số kỹ thuật chia nhóm card rõ ràng ở dưới.

## Bố cục

- Tiêu đề `Camera` kèm chip trạng thái camera theo kết quả runtime/preflight.
- Hàng đầu gồm hai card:
  - `Cấu hình quét`: ba profile dạng card ngang (Gần, Tiêu chuẩn, Xa); profile đang chọn có nền xanh nhạt và viền xanh.
  - `Thiết bị đang kết nối`: tên thiết bị, serial, firmware, mode đã xác nhận và trạng thái kiểm tra.
- Hai nút trong card cấu hình: `Kiểm tra thiết bị` là thao tác phụ; `Áp dụng & mở RTAB-Map` là thao tác chính.
- Nhóm `Thông số luồng`: depth stream, color stream, IMU.
- Nhóm `Khoảng cách & bộ lọc`: depth range, normal scan range, enabled depth filters, alignment target.
- Các nhóm chuyên sâu trình bày dạng card với fact tile; không dùng Treeview hoặc bảng lưới kỹ thuật.

## Hành vi

- Các card profile gọi luồng chọn profile hiện có và phản ánh profile đã chọn ngay sau refresh.
- Khóa toàn bộ card profile và hai nút thao tác khi RTAB-Map đang chạy, giữ nguyên quy tắc controller hiện tại.
- `Kiểm tra thiết bị` và `Áp dụng & mở RTAB-Map` tiếp tục gọi nguyên các handler hiện có.
- Card thiết bị hiển thị trạng thái trống dễ hiểu trước khi kiểm tra: `Chưa kiểm tra thiết bị` thay cho các chuỗi nội bộ dài.
- Thông số kỹ thuật từ `camera_settings_rows` vẫn đầy đủ, nhưng được phân loại vào nhóm hiển thị; tên định dạng, mode, thiết bị và bộ lọc theo Orbbec SDK giữ tiếng Anh.

## Cấu trúc mã

- Thêm hàm thuần tạo view model cho profile card, camera device card và các nhóm fact tile từ `CameraProfile` cùng `CameraSettingsSnapshot`.
- Thay `_build_camera_page` và `_refresh_camera_settings` bằng CustomTkinter card/list presentation; loại bỏ `camera_profile_combo` và `camera_settings_tree`.
- Không thay đổi `Scanner3DController`, preflight service, camera models hoặc quy ước profile.

## Kiểm thử

- Kiểm thử view model cho profile đang chọn, thiết bị chưa kiểm tra và thiết bị đã kiểm tra.
- Kiểm thử phân nhóm stream và quality có các thông số đúng, bao gồm thuật ngữ Orbbec SDK.
- Kiểm thử trạng thái khóa card/nút khi RTAB-Map chạy.
- Chạy đầy đủ pytest, Ruff cho tệp thay đổi và mở cửa sổ kiểm tra trực quan.
