# Phiên quét và kết quả dạng danh sách card

## Mục tiêu

Thay hai bảng kỹ thuật trong trang `Phiên & kết quả` bằng danh sách card sáng, dễ quét bằng mắt. Mỗi card biểu diễn một phiên quét hoặc một mô hình đã cắt; khi chọn, vùng chi tiết xuất hiện ngay bên dưới danh sách tương ứng. Mọi thao tác hiện có vẫn được giữ.

## Bố cục

- Tiêu đề `Phiên quét & kết quả`, nút `Làm mới`, và hai bộ đếm nhỏ: phiên quét và kết quả.
- Khối `Phiên quét`: các card xếp dọc. Card hiển thị tên cơ sở dữ liệu, thời gian cập nhật và dung lượng.
- Khi chọn một phiên, vùng `Đang chọn` hiển thị tên, dung lượng, thời điểm, trạng thái và hai thao tác `Xuất OBJ gốc` và `Mở thư mục`.
- Khối `Mô hình đã cắt`: các card xếp dọc theo cùng ngôn ngữ thiết kế, có tên OBJ, thư mục đầu ra, thời gian và dung lượng.
- Khi chọn một mô hình, vùng chi tiết hiển thị thông tin đó cùng `Mở mô hình` và `Mở thư mục`.
- Nếu danh sách trống, mỗi khối hiển thị trạng thái rỗng ngắn, rõ và không có hành động bị hiểu nhầm là khả dụng.

## Hành vi và dữ liệu

- Danh sách phiên tiếp tục lấy từ `DashboardState.sessions`; danh sách mô hình tiếp tục lấy từ `CropCatalog`.
- `refresh()` tái tạo card, cập nhật bộ đếm và giữ lựa chọn nếu đường dẫn của mục đó vẫn còn tồn tại.
- Chọn card cập nhật phần chi tiết và trạng thái khả dụng của các nút. Không tự mở tệp.
- `Xuất OBJ gốc`, mở mô hình và mở thư mục tiếp tục gọi nguyên các hành vi hiện hữu.
- Các chuỗi hiển thị sẽ dùng tiếng Việt; tên tệp, đuôi tệp, tên định dạng và thuật ngữ SDK giữ nguyên tiếng Anh.

## Cấu trúc mã

- Tách các hàm thuần để tạo metadata card và trạng thái lựa chọn, giúp kiểm thử không cần Tk.
- Thay `Treeview` trong phần kết quả bằng `CTkScrollableFrame`, `CTkFrame` và các card có nút/callback riêng.
- Lưu đường dẫn đang chọn thay cho `Treeview.selection()`; các hành động hiện hữu đọc trạng thái này.
- Không thay đổi controller, catalog, định dạng tệp hay luồng xuất.

## Kiểm thử

- Kiểm thử metadata cho card phiên và card mô hình, bao gồm dung lượng, ngày giờ và trạng thái rỗng.
- Kiểm thử lựa chọn được giữ sau làm mới khi mục còn tồn tại và được xoá khi mục đã biến mất.
- Kiểm thử trạng thái nút mở/xuất theo mục được chọn.
- Chạy đầy đủ bộ kiểm thử và kiểm tra lint trên các tệp đã đổi.
