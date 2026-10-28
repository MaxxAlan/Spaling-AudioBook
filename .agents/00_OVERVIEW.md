# Spaling Audiobook – AI Agent Guide (Overview)

**Version:** 0.0.2  
**Purpose:** Hướng dẫn cho AI agents làm việc với repo này một cách nhẹ nhàng, chính xác, không phá vỡ cấu trúc.

## Mục tiêu dự án
Ứng dụng Windows (portable) tạo audiobook tiếng Việt từ truyện: TTS, phân tích script, tạo ảnh minh họa (storyboard/poster), video + phụ đề. Hỗ trợ local AI (Ollama, ComfyUI), voice clone, QA semantic.

## Quy tắc vàng cho AI Agents
1. **Tìm kiếm nhẹ (light search)**: Luôn đọc file này và các file trong `.agents/` trước khi `grep`/`find` toàn repo.
2. **Không đụng runtime data**: Không commit `.runtime/`, `.data/`, `.audiobook-*`, `output/`, `models/`, voice assets.
3. **Giữ portable**: Mọi path phải relative từ ROOT = thư mục chứa `audiobook.py`.
4. **Import style**:
   - Root scripts: `from backend_bootstrap import ...`, `from overnight.presets import ...`
   - audio-comic: sau khi `sys.path.insert(0, str(ROOT / "audio-comic"))` thì import top-level `from ai.xxx`, `from core.xxx`, `from tts.xxx`...
5. **Không rename folder đang chạy**: `audio-comic` và `poster-generator` được hard-code ở nhiều nơi.
6. **Khi sửa code**: Ưu tiên sửa nhỏ, có test path rõ ràng. Cập nhật lại file tương ứng trong `.agents/` nếu thay đổi API công khai.

## Cấu trúc thư mục chính (khoa học)

```
Spaling-AudioBook/                 # ROOT
├── .agents/                       # ← Hướng dẫn AI agents (bạn đang ở đây)
├── .github/workflows/             # CI release Windows
├── audio-comic/                   # Python package lõi TTS + pipeline audio
│   ├── ai/                        # Ollama, context, parameter policy
│   ├── audio/                     # process, normalize, silence, quality
│   ├── core/                      # Pipeline, CacheManager, ProjectManager, State
│   ├── models/                    # Character, Segment, VoiceProfile, Project
│   ├── text_processing/           # Dialogue parser, sentence splitter, analyzer
│   ├── tts/                       # Providers (SAPI5, VieNeu, mock, local_wave)
│   ├── utils/                     # paths, logging, hashing, system_check
│   ├── video/                     # FFmpeg, storyboard video, subtitles
│   ├── config/                    # settings.json, default_voice_profiles.json
│   ├── app.py, cli.py
│   └── requirements*.txt
├── poster-generator/              # Node/TS – storyboard + thumbnail + image gen
│   ├── src/
│   │   ├── analysis/              # chapter/chunk analyzer, scene ranker
│   │   ├── characters/            # character bible, visual resolver
│   │   ├── prompts/               # prompt templates
│   │   ├── providers/             # text (Ollama) + image (ComfyUI)
│   │   ├── sources/               # loader, chunker, cache
│   │   ├── storyboard/            # prompt-builder, vision-reviewer
│   │   ├── thumbnail/             # brief, concept, platform composer
│   │   ├── schemas/               # Zod schemas
│   │   ├── cli.ts, storyboard-gen.ts, poster-gen.ts ...
│   ├── workflows/                 # ComfyUI workflow JSON
│   └── package.json
├── web/                           # Static frontend (index.html, app.js, style.css)
├── overnight/                     # Presets cho overnight generation
├── tools/                         # release scripts, model download
├── installer/                     # Inno Setup script
├── audiobook.py                   # CLI entry chính (unified)
├── web_app.py                     # Local web server (port 8765)
├── backend_bootstrap.py           # Ollama + ComfyUI bootstrap
├── install.py / install.bat / install.sh
├── pyproject.toml
└── requirements*.txt
```

## Entry points quan trọng
| Lệnh / File              | Mục đích                          |
|--------------------------|-----------------------------------|
| `audiobook.py` / `audiobook` | CLI chính (generate, web, story...) |
| `web_app.py`             | HTTP server + job queue           |
| `backend_bootstrap.py`   | Khởi động Ollama/ComfyUI          |
| `audio-comic/cli.py`     | CLI audio subsystem               |
| `poster-generator` (pnpm)| storyboard-gen, poster-gen        |
| `install.py`             | Cài runtime + models (profiles)   |

## Khi nào dùng file nào trong .agents/
- **00_OVERVIEW.md** (file này): cấu trúc tổng quan + quy tắc.
- **01_PYTHON_MAP.md**: map modules Python + hàm/class chính.
- **02_TYPESCRIPT_MAP.md**: map TS + export chính.
- **03_WORKFLOWS.md**: luồng chạy phổ biến (generate audiobook, storyboard...).
- **04_CONVENTIONS.md**: style code, logging, path handling, error handling.
