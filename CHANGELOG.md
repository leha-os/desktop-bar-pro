# Changelog

Mọi thay đổi đáng chú ý của LEHA Desktop Bar PRO được ghi tại đây.
Định dạng ngày: dd/mm/yyyy.

## [1.0.0] - 21/11/2026

Bản phát hành đầu tiên.

- Dọn code trước phát hành (không đổi tính năng, giao diện hay cấu hình mặc định): bỏ hẳn cụm System Tray đã tắt vốn tham chiếu thư viện không còn dùng, gộp các dòng import bị trùng, bỏ import thừa trong hàm menu chuột phải, thêm docstring mô tả ở đầu file và hằng số `__version__`.

- Thanh điều hướng Virtual Desktop ở mép trên màn hình, chuyển desktop bằng một cú bấm.
- Kết xuất Win32 Layered Window (`UpdateLayeredWindow`) với alpha premultiplied, nền trong suốt 100% tùy chọn.
- Đăng ký Windows AppBar để giữ vùng hiển thị riêng, tùy chọn tự ẩn khi ứng dụng toàn màn hình.
- Khóa đơn tiến trình bằng Windows Mutex; không dùng biểu tượng System Tray.
- Pro Studio: bảng tùy chỉnh mở tại máy (`127.0.0.1`) với 6 mẫu phối màu, màu riêng từng desktop, kiểu thẻ, chữ, bố cục và kích thước.
- Đổi tên Virtual Desktop, tùy chọn tự khởi động cùng Windows, cấu hình lưu tự động vào `config.json`.
- Phím tắt toàn cục `Ctrl+Alt+H` để ẩn hoặc hiện thanh bar.
