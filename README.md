# Spaling Audiobook v0.0.2

Ứng dụng Windows tạo audiobook tiếng Việt, ảnh minh họa và video từ nội dung truyện.

## Yêu cầu hệ thống

- Windows 10 hoặc Windows 11 64-bit.
- RAM tối thiểu 8 GB, khuyến nghị 16 GB.
- NVIDIA GPU tối thiểu 4 GB VRAM.
- Tối thiểu 35 GB dung lượng trống.
- Kết nối Internet trong lần cài đặt đầu tiên.
- Driver NVIDIA đang hoạt động.

## Cài đặt

1. Tải `Spaling-Audiobook-v0.0.2-setup.exe` tại trang **Releases**.
2. Chạy file cài đặt.
3. Chọn **Cài dependency và model AI** khi trình cài đặt yêu cầu.
4. Chờ quá trình tải và cấu hình hoàn tất.

Hoặc cài từ mã nguồn:

```cmd
git clone https://github.com/MaxxAlan/Spaling-AudioBook.git
cd Spaling-AudioBook
install.bat
```

Installer mac dinh chay qua `install.py` de de mo rong theo tung thiet bi:

```cmd
python install.py --profile core   :: dependency toi thieu
python install.py --profile audio  :: them TTS/ASR QA
python install.py --profile full   :: day du local AI, ComfyUI, Ollama, model
```

Tren Windows moi chua co Python, cu chay `install.bat`; file nay tu tai Python portable roi chuyen sang `install.py`.

## Chạy di động (USB)

Toàn bộ runtime (Python, Node, FFmpeg, Git, Ollama), dependency và model nằm ngay trong thư mục ứng dụng (`.runtime`, `.data`) — không ghi ra ổ C, không cần quyền Admin.

- **Clone vào thư mục nào thì dùng thư mục đó.** Có thể đổi vị trí thư mục bất kỳ lúc nào.
- Để dùng trên máy khác: copy toàn bộ thư mục sang USB, cắm vào máy mới, chạy lại:

```cmd
cd Spaling-AudioBook
install.bat
```

  install.bat sẽ bỏ qua các thành phần đã có (không tải lại từ mạng), chỉ đồng bộ lại liên kết pnpm và kiểm tra toàn bộ. Bản chất chạy lại là "sửa chữa/bổ sung" chứ không xóa dữ liệu.
- Không cần cài đặt bất kỳ chương trình nào trước trên máy mới.
- Ổ chứa cần tối thiểu 35 GB trống khi cài đầy đủ model AI.

## Bật ứng dụng

Mở **Spaling Audiobook** từ Desktop hoặc Start Menu.

Nếu chạy từ thư mục mã nguồn:

```cmd
audiobook web
```

Ứng dụng mở tại <http://127.0.0.1:8765>.

## Gỡ cài đặt

Gỡ **Spaling Audiobook** trong **Windows Settings → Apps → Installed apps**.

Nếu cài từ mã nguồn:

```cmd
uninstall.bat
```

Copyright (c) 2026 MaxxAlan. All Rights Reserved.
