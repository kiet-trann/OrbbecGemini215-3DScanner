# Toast dùng chung và trạng thái runtime tự cập nhật

## Mục tiêu

Tách phản hồi thao tác khỏi nhãn trạng thái runtime. Nhãn đầu trang chỉ hiển thị trạng thái thực của RTAB-Map, còn mọi phản hồi do người dùng thao tác sẽ hiển thị bằng toast tạm thời.

## Phạm vi

- Thêm một API dùng chung trên `Scanner3DWindow` để hiện toast: nội dung và mức độ `success`, `error`, hoặc `info`.
- Toast thay toast hiện có, hiển thị ở góc phải dưới cửa sổ, tự ẩn sau 4 giây; toast lỗi tự ẩn sau 6 giây.
- Các thao tác mở mô hình/thư mục, kiểm tra camera, chọn cấu hình, gửi lệnh pause/resume, xuất OBJ, cắt OBJ và các lỗi xác thực dùng toast thay vì ghi vào nhãn đầu trang.
- Nhãn đầu trang tiếp tục được `refresh()` cập nhật từ `RtabmapRuntime.status()`.
- Runtime poll mỗi 500 ms gọi `refresh()` khi trạng thái RTAB-Map thay đổi theo cả hai chiều chạy sang dừng và dừng sang chạy.

## Thiết kế

`Scanner3DWindow` sở hữu một widget toast và một bộ đếm sau-lệnh (`after`) để tránh một toast cũ tự ẩn toast mới. Phương thức `notify(message, tone="info")` cấu hình nội dung/màu, đặt toast nổi trên góc phải dưới, hủy lịch ẩn trước đó nếu có, rồi lên lịch ẩn theo mức độ.

Các handler giữ trách nhiệm hiện tại: thực hiện thao tác hoặc nhận kết quả nền. Thay vì gọi `self.status.set(...)`, chúng gọi `notify(...)`. Khi cần quyết định màu, handler dùng kết quả thành công/thất bại sẵn có; không thay đổi đường dẫn mở file hay luồng export/crop.

`refresh()` là đường duy nhất đặt `self.status` và cấu hình `status_chip`. `_poll_runtime()` so sánh runtime đang quan sát với `runtime_was_running`; khi khác nhau, nó gọi `refresh()` để đồng bộ nhãn, các điều khiển camera, hướng dẫn quét và dữ liệu dashboard.

## Xử lý lỗi

- Toast lỗi hiển thị 6 giây và có màu đỏ.
- Toast thành công hiển thị 4 giây và có màu xanh lá.
- Toast thông tin/đang xử lý hiển thị 4 giây và có màu xanh dương/trung tính.
- Một toast mới thay thế toast cũ; callback ẩn của toast cũ không được phép ẩn toast mới.

## Kiểm thử

- Poll runtime làm mới khi RTAB-Map chuyển từ dừng sang chạy và từ chạy sang dừng.
- `notify()` chọn đúng thời lượng, nội dung, màu và chỉ giữ một lịch ẩn hiệu lực.
- Các handler thao tác gọi toast thay vì sửa nhãn runtime.
- Các kiểm thử dashboard và thao tác mở file hiện có vẫn xanh.
