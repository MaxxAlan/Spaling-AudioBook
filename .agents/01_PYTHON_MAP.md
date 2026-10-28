# Python Module & Function Map

Agents nên đọc file này thay vì scan toàn bộ `.py` khi cần tìm hàm.

## Root level

### `audiobook.py` (CLI chính ~46KB)
- `classify_inputs(values)` → phân loại input paths
- `generate_audio(...)` → pipeline TTS chính
- `run_generate_story(args)` → sinh scene JSON từ chapter + context
- `_build_poster_tool()`, `_run_streamed()`, `_progress*`, `_atomic_json`
- Import: `overnight.presets`, `backend_bootstrap`, dynamic load `audio-comic`

### `web_app.py` (Web UI server)
- `run_server(...)` (entry)
- Job management: `JOBS`, `PROCESSES`, GPU lock
- Backend status: `set_backend_status`, `_ollama_base_url`
- Serve static từ `web/`, API endpoints cho generate/job status

### `backend_bootstrap.py`
- `configure_local_paths(root)` → set PATH cho portable runtime
- `bootstrap_backends()` → đảm bảo Ollama + ComfyUI sẵn sàng
- `BackendSession`, `BackendStatus`
- `_ensure_ollama`, `_ensure_comfyui`, `_wait_http`

### `install.py`
- Profiles: `core`, `audio`, `full`
- `ensure_windows_runtime`, `ensure_portable_python`, `ensure_runtimes`
- `InstallerUI`, download + extract zip, winget helpers

### `optimize_context.py`
- `optimize_context(...)`, `extract_chapter_summary`
- `search_character`, `search_characters_for_chapter`
- `search_timeline_for_chapter`, `search_master_for_chapter`, `search_glossary_for_chapter`

### `overnight/presets.py`
- `AUDIOBOOK_PROFILE_RANGES`
- `choose_image_count`, `estimate_scene_hints`

## audio-comic/ (sau sys.path.insert)

### core/
- `Pipeline` (core/pipeline.py) – orchestration chính
- `CacheManager` – key-based cache cho segment audio
- `ProjectManager`, `StateManager`
- Exceptions: `AudioComicError`, `ProjectError`, `TTSGenerationError`...

### ai/
- `OllamaNarrationHelper` (ollama_helper.py) – story + narration prompts
- `ParameterPolicy`, `propose_retry` (parameter_optimizer)
- `load_context_files`, `build_context_prompt`, `build_narration_context` (context/loader.py)
- `transcribe_audio_to_srt` (audio_transcriber.py)

### text_processing/
- `dialogue_parser`, `sentence_splitter`, `script_analyzer`
- `character_detector`, `critical_words`, `normalizer`

### tts/
- Base: `base.py`
- Providers: `sapi5_provider`, `vieneu_provider`, `local_wave_provider`, `mock_provider`
- `voice_registry.py`

### audio/
- `processor.py` (read/write wav, sample rate, mono/stereo)
- `normalizer.py` (loudness, trim silence)
- `silence.py` (generate silence, fade, crossfade)
- `concatenator.py`, `exporter.py` (wav/mp3)
- `quality.py`, `semantic_quality.py` (LocalSpeechVerifier, text_integrity_score)

### video/
- `FFmpegManager`
- `create_storyboard_video`, subtitles, validator

### models/
- `Character`, `Segment`, `VoiceProfile`, `Project`, `ExportSettings`

### utils/
- `paths.py` (get_app_root, normalize_user_path...)
- `logging_config.py` (setup_logging, get_logger – namespace "audio_comic")
- `system_check.py`, `hashing.py`, `encoding.py`

### cli.py / app.py
- CLI entry cho subsystem audio (`audio-comic` command)

## Ghi chú quan trọng
- Sau `sys.path.insert(0, str(ROOT/"audio-comic"))` thì **không** dùng `from audio_comic.xxx`. Chỉ dùng `from ai.xxx`, `from core.xxx`...
- Có 1 chỗ cũ dùng `from audio_comic.ai...` đã được sửa thành `from ai...`.
- Logging namespace: `audio_comic` và `audio_comic.<module>`.
