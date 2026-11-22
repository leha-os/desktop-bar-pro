# LEHA Desktop Bar PRO

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![License](https://img.shields.io/badge/license-MIT-green)

**A lightweight Virtual Desktop navigation bar for Windows 10 and 11.**

Thanh điều hướng Virtual Desktop gọn nhẹ đặt ở mép trên màn hình: bấm là chuyển desktop ngay, tùy biến sâu bằng bảng Pro Studio, và chạy nền nhẹ nhàng như một thành phần của hệ thống.

---

## Tính năng chính

- **Chuyển Virtual Desktop tức thì:** bấm vào thẻ màn hình để chuyển ngay, trạng thái desktop đang dùng được làm nổi bật và cập nhật theo thời gian thực.
- **Kết xuất Layered Window trực tiếp:** vẽ bằng Win32 `CreateDIBSection` và `UpdateLayeredWindow` với alpha premultiplied, không nhấp nháy, hỗ trợ nền thanh bar trong suốt 100% hòa vào hình nền desktop.
- **Phản hồi mượt khi tương tác:** chu kỳ vẽ rút xuống khoảng 8 ms khi di chuột hoặc đang chuyển động, và giãn ra khoảng 50 ms khi đứng yên để giữ mức tải nền thấp.
- **Giữ chỗ trên màn hình bằng Windows AppBar:** thanh bar đăng ký vùng riêng ở mép trên (`SHAppBarMessage`, `ABE_TOP`) để cửa sổ phóng to không che khuất, kèm tùy chọn tự ẩn khi có ứng dụng chạy toàn màn hình.
- **Chỉ chạy một bản duy nhất:** khóa đơn tiến trình bằng Windows Mutex, mở lại nhiều lần vẫn chỉ có một thanh bar trên hệ thống.
- **Không chiếm khay hệ thống:** không có biểu tượng System Tray; chuột phải lên thanh bar để mở Pro Studio hoặc thoát ứng dụng.
- **Pro Studio, bảng tùy chỉnh trực quan:** mở trong trình duyệt nhưng chỉ phục vụ nội bộ trên máy (`127.0.0.1`, cổng ngẫu nhiên), gồm:
  - 6 mẫu phối màu sẵn: Viên nổi Đa màu, Viên nổi Tối giản, Obsidian, Catppuccin, Cyber Mint, Apple Light.
  - Màu riêng cho từng Virtual Desktop (nền, chữ, điểm sáng), chế độ đa màu hoặc đơn màu.
  - Kiểu thẻ Filled, Outline hoặc Minimal; cỡ chữ, độ đậm, in nghiêng, viết hoa hoặc thường.
  - Căn trái, giữa hoặc chia đều; độ rộng, khoảng cách, bo góc, chiều cao và độ mờ của thanh bar.
  - Đổi tên từng Virtual Desktop và tùy chọn tự khởi động cùng Windows.
- **Lưu cấu hình tự động:** mọi thay đổi được ghi vào `config.json` cạnh file chạy và áp dụng ngay, không cần khởi động lại.
- **Phím tắt toàn cục:** `Ctrl+Alt+H` để ẩn hoặc hiện nhanh thanh bar.

---

## Cài đặt và sử dụng

### Cách 1: Bản chạy ngay (khuyên dùng)

1. Vào mục [Releases](https://github.com/leha-os/desktop-bar-pro/releases) và tải file `LEHA-Desktop-Bar-PRO-v1.0.0-Win64.zip`.
2. Giải nén vào một thư mục cố định, ví dụ `C:\Tools\LEHA Desktop Bar PRO\`.
3. Chạy file `LEHA Desktop Bar PRO.exe`.
4. Tùy chọn: chuột phải lên thanh bar, mở Pro Studio, vào mục Tên Màn và Hệ Thống, bật Tự động khởi động cùng Windows.

> **Lưu ý:** bản `.exe` hiện chưa có chữ ký số, nên lần chạy đầu Windows SmartScreen có thể hiện cảnh báo. Chọn **More info**, sau đó **Run anyway** để tiếp tục. Mã nguồn đầy đủ có trong repo này để bạn tự kiểm tra hoặc tự đóng gói lại.

### Cách 2: Chạy từ mã nguồn

Yêu cầu: Windows 10 (build 1903 trở lên) hoặc Windows 11, Python 3.10 trở lên.

```powershell
pip install -r requirements.txt
python desktop_bar.py
```

### Đóng gói lại thành file .exe

```powershell
build.bat
```

File kết quả nằm trong thư mục `dist`. Kịch bản `build.bat` đóng gói bằng PyInstaller ở chế độ one-file, không cửa sổ console, kèm thông tin phiên bản từ `version_info.txt`.

---

## Điều khiển nhanh

| Thao tác | Chức năng |
| --- | --- |
| Chuột trái vào thẻ màn hình | Chuyển sang Virtual Desktop tương ứng |
| Chuột phải lên thanh bar | Mở Pro Studio hoặc thoát ứng dụng |
| `Ctrl+Alt+H` | Ẩn hoặc hiện nhanh thanh bar |

---

## Cấu trúc dự án

```text
LEHA Desktop Bar PRO/
├── desktop_bar.py      # Mã nguồn chính (Tkinter, Pillow, pyvda, Win32 API qua ctypes)
├── config.json         # Cấu hình giao diện mặc định, tự cập nhật khi dùng
├── requirements.txt    # Thư viện cần cài để chạy từ mã nguồn
├── build.bat           # Đóng gói lại thành file .exe bằng PyInstaller
├── version_info.txt    # Thông tin phiên bản gắn vào file .exe
├── CHANGELOG.md        # Nhật ký thay đổi theo phiên bản
└── LICENSE             # Giấy phép MIT
```

## Công nghệ

- Python 3.10+, Tkinter cho cửa sổ nền
- Win32 API qua `ctypes`: Layered Window, AppBar, Mutex, Global Hotkey, Registry autostart
- [pyvda](https://pypi.org/project/pyvda/) để đọc, chuyển và đổi tên Virtual Desktop
- Pillow để kết xuất hình ảnh của thanh bar
- Máy chủ Pro Studio nội bộ bằng `http.server`, chỉ nghe trên `127.0.0.1`

## Giấy phép

Phát hành theo giấy phép [MIT](LICENSE). Tác giả: **Le Ha**.
