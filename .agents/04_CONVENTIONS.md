# Coding Conventions & Agent Rules

## Path & Portable
- Luôn dùng `pathlib.Path`
- ROOT = `Path(__file__).resolve().parent` ở root scripts
- Không hard-code ổ C: hoặc absolute path người dùng
- Runtime nằm trong `.runtime/`, data trong `.data/` (gitignored)

## Python style
- `from __future__ import annotations`
- Type hints đầy đủ
- Logging qua `utils.logging_config` (namespace `audio_comic`)
- Exception hierarchy từ `core.exceptions`
- Atomic JSON write khi persist state

## TypeScript style
- ESM only
- Zod schema cho mọi input/output quan trọng
- pino logger
- Atomic write + content hash cache
- Provider interface (dễ mock)

## Khi AI agent sửa code
1. Đọc `.agents/00_OVERVIEW.md` + map tương ứng trước.
2. Chỉ sửa file liên quan, không refactor lớn trừ khi được yêu cầu rõ.
3. Sau khi thêm/sửa public function/class → cập nhật file map trong `.agents/`.
4. Không thêm dependency mới nếu không thật cần (giữ install nhẹ).
5. Test path: ưu tiên chạy `python -c "import ..."` hoặc dry-run CLI.
6. Commit message ngắn, rõ (tiếng Việt hoặc Anh đều được).

## Những thứ tuyệt đối không làm
- Commit file trong `.runtime/`, `.data/`, `models/`, voice custom, output media
- Đổi tên `audio-comic` hoặc `poster-generator` mà không update toàn bộ hard-code
- Thêm `from audio_comic.xxx` (sai import style)
- Xóa `.agents/` hoặc bỏ qua guide này

## Harness / Scaffold
Dự án dùng cấu trúc monorepo nhẹ:
- Python core: `audio-comic/`
- Node image pipeline: `poster-generator/`
- Unified CLI + Web: root
- Agent knowledge base: `.agents/`

Khi cần mở rộng, ưu tiên thêm module vào đúng package thay vì tạo file rời ở root.
