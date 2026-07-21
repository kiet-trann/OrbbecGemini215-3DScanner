# Thông báo trạng thái khi mở kết quả quét

## Mục tiêu

Giữ nhãn trạng thái dễ đọc sau các thao tác mở mô hình hoặc thư mục kết quả. Nhãn không được hiển thị đường dẫn tuyệt đối của tệp.

## Phạm vi

- `OpenActionService` tiếp tục dùng đường dẫn đầy đủ để mở đúng tệp hoặc thư mục trong Windows.
- Khi mở OBJ thành công, dịch vụ trả về `Đã mở mô hình 3D`.
- Khi mở thư mục thành công, dịch vụ trả về `Đã mở thư mục kết quả`.
- Khi không thể mở, dịch vụ trả về thông báo lỗi ngắn theo loại thao tác, không kèm đường dẫn.
- Các nút hiện tại vẫn gán thông báo này lên nhãn trạng thái; không thêm popup hoặc thay đổi quy trình quét.

## Thiết kế

`OpenActionResult.message` là ranh giới hiển thị cho thao tác mở. `OpenActionService` tạo thông báo thân thiện với người dùng, trong khi `Scanner3DWindow` chỉ hiển thị thông báo đó và không cần biết đường dẫn.

Điều này áp dụng đồng nhất cho mở mô hình đã cắt, mô hình xuất gần nhất, thư mục của mô hình, và thư mục của phiên quét vì tất cả đều đi qua cùng dịch vụ.

## Kiểm thử

Các kiểm thử của `OpenActionService` sẽ xác nhận:

- Mở OBJ gọi launcher với đường dẫn chính xác nhưng trả về thông báo ngắn.
- Mở thư mục gọi launcher với thư mục cha nhưng trả về thông báo ngắn.
- Các lỗi thiếu tệp hoặc lỗi launcher không để lộ đường dẫn.
