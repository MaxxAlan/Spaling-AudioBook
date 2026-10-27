# Common Workflows (for Agents)

## 1. Generate full audiobook (CLI)
```
python audiobook.py generate <canon.md> <chapter.txt> [options]
```
Hoặc qua web UI: `audiobook web` → mở http://127.0.0.1:8765

Flow nội bộ:
1. `backend_bootstrap.configure_local_paths` + `bootstrap_backends`
2. Classify inputs → load context
3. Gọi poster-generator (storyboard-gen) nếu cần ảnh
4. audio-comic Pipeline: text_processing → TTS → audio process → export
5. Optional: video + subtitles

## 2. Chỉ tạo storyboard / ảnh
```
cd poster-generator
pnpm build
node dist/storyboard-gen.js ...
```
Hoặc từ root qua audiobook.py (nó tự build nếu cần).

## 3. Chỉ audio từ TXT
```
python -m audio-comic ...   # sau khi path đúng
# hoặc
python audio-comic/cli.py ...
```

## 4. Install / Update runtime
```
install.bat
# hoặc
python install.py --profile core|audio|full
```
Profiles:
- core: tối thiểu
- audio: + TTS/ASR
- full: + ComfyUI + Ollama + models

## 5. Overnight / batch
Dùng `overnight/presets.py` + profile ranges để chọn số ảnh / scene.

## 6. Context optimization
```
python optimize_context.py ...
```
Trích summary, character, timeline, glossary cho chapter.

## Khi debug
- Xem log trong console (streamed) hoặc `audio_comic.log`
- Job web lưu dưới `.audiobook-web/`
- Cache audio: do CacheManager quản lý (thường trong project dir hoặc .data)
