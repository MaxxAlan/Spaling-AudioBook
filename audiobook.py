"""Unified v0.0.2 CLI: canon + chapter -> narrated multi-image audiobook."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unicodedata
from collections import deque
from copy import deepcopy
from pathlib import Path
from typing import Sequence

from overnight.presets import AUDIOBOOK_PROFILE_RANGES, choose_image_count, estimate_scene_hints

from backend_bootstrap import configure_local_paths

ROOT = Path(__file__).resolve().parent
AUDIO_TOOL = ROOT / "audio-comic"
POSTER_TOOL = ROOT / "poster-generator"
TESTING = ROOT / "testing"

configure_local_paths(ROOT)


def _pnpm_command() -> list[str] | None:
    """Resolve pnpm on Windows, falling back to the Corepack bundled with Node."""
    pnpm = shutil.which("pnpm.cmd") or shutil.which("pnpm")
    if pnpm:
        return [pnpm]
    corepack = shutil.which("corepack.cmd") or shutil.which("corepack")
    if corepack:
        return [corepack, "pnpm"]
    return None


def _build_poster_tool() -> None:
    command = _pnpm_command()
    if command is None:
        raise RuntimeError(
            "Không tìm thấy pnpm hoặc Corepack. Hãy cài Node.js kèm Corepack "
            "rồi chạy lại install.cmd."
        )
    subprocess.run([*command, "build"], cwd=POSTER_TOOL, check=True)


def _run_streamed(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    """Stream child logs while preserving a useful error for the web UI."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    tail: deque[str] = deque(maxlen=20)
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.rstrip()
        if line:
            tail.append(line)
            print(line, flush=True)
    return_code = process.wait()
    if return_code:
        detail = tail[-1] if tail else "Tiến trình không trả về thông báo lỗi."
        raise RuntimeError(
            f"Storyboard thất bại (mã {return_code}): {detail}"
        )


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def classify_inputs(values: Sequence[str]) -> tuple[Path, Path, Path]:
    """Return (master, rules, chapter) regardless of the three-file order."""
    paths = [Path(value).expanduser().resolve() for value in values]
    if len(paths) != 3:
        raise ValueError("--input cần đúng 3 file: master.md, request.md và chapter.txt")
    for path in paths:
        if not path.is_file():
            raise ValueError(f"Không tìm thấy file: {path}")
    chapters = [path for path in paths if path.suffix.lower() == ".txt"]
    markdown = [path for path in paths if path.suffix.lower() == ".md"]
    if len(chapters) != 1 or len(markdown) != 2:
        raise ValueError("Đầu vào phải gồm đúng hai file .md và một file .txt")
    master = next((path for path in markdown if "master" in path.name.lower()), None)
    rules = next((path for path in markdown if any(token in path.name.lower() for token in ("request", "rule", "canon", "yêu"))), None)
    if master is None:
        master = next((path for path in markdown if "master" in path.read_text(encoding="utf-8-sig", errors="ignore")[:8000].lower()), None)
    if rules is None:
        rules = next((path for path in markdown if path != master), None)
    if master is None or rules is None or master == rules:
        raise ValueError("Không phân biệt được master.md và request.md")
    return master, rules, chapters[0]


def _slug(value: str) -> str:
    value = unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    result = "-".join("".join(char.lower() if char.isalnum() else " " for char in value).split())
    return result or "audiobook"


def _audio_modules():
    location = str(AUDIO_TOOL)
    if location not in sys.path:
        sys.path.insert(0, location)
    import cli as audio_cli
    from video.ffmpeg_manager import FFmpegManager
    from video.storyboard_video import create_storyboard_video
    return audio_cli, FFmpegManager, create_storyboard_video


_LAST_PROGRESS: tuple[str, int] = ("", -1)


def _progress(stage: str, percent: float, message: str) -> None:
    global _LAST_PROGRESS
    bucket = min(100, int(percent) // 5 * 5)
    marker = (stage, bucket)
    if marker != _LAST_PROGRESS or percent >= 100:
        print(f"[audio {percent:5.1f}%] {stage}: {message}", flush=True)
        _progress_event("audio", percent, message)
        _LAST_PROGRESS = marker


def _progress_event(stage: str, percent: float, message: str, **values: object) -> None:
    payload = {"stage": stage, "percent": round(percent, 1), "message": message, **values}
    print(f"@@progress {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}", flush=True)


def _atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _build_signature(paths: Sequence[Path], args: argparse.Namespace) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    digest.update(json.dumps({
        "chapter": args.chapter_number,
        "story": args.story,
        "audiobook": args.audiobook,
        "images": args.images,
        "platform": args.platform,
        "image_output": args.image_output,
        "voice": args.voice,
        "tts_provider": args.tts_provider,
        "ai": args.ai,
        "ai_model": args.ai_model,
        "model_profile": args.model_profile,
        "subtitle_mode": args.subtitle_mode,
        "video": args.video,
        "mp3": args.mp3,
    }, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return digest.hexdigest()


def _paths_exist(values: dict[str, str]) -> bool:
    paths = [Path(value) for value in values.values() if value]
    return bool(paths) and all(path.is_file() and path.stat().st_size > 0 for path in paths)


def _storyboard_exists(payload: dict) -> bool:
    scenes = payload.get("scenes", [])
    if not scenes:
        return bool(payload.get("covers")) and _paths_exist(payload["covers"])
    return all(
        scene.get("images") and _paths_exist(scene["images"])
        for scene in scenes
    )


def _final_audit(output: Path, audio_outputs: dict[str, str], storyboard: dict) -> dict:
    audio_report_path = Path(audio_outputs.get("audio_quality_report", ""))
    if not audio_report_path.is_file():
        raise ValueError("Thiếu audio-quality-report.json; không xuất bản kết quả chưa kiểm duyệt.")
    audio_report = json.loads(audio_report_path.read_text(encoding="utf-8"))
    rejected_audio = [
        item.get("segment_id")
        for item in audio_report.get("segments", [])
        if not item.get("approved", False)
    ]
    if rejected_audio:
        raise ValueError(f"Audio QA còn segment bị từ chối: {rejected_audio[:10]}")

    visual_report_path = output / "images" / "storyboard-qa.json"
    visual_approved = 0
    if storyboard.get("scenes"):
        if not visual_report_path.is_file():
            raise ValueError("Thiếu storyboard-qa.json; không xuất bản ảnh chưa kiểm duyệt.")
        visual_report = json.loads(visual_report_path.read_text(encoding="utf-8"))
        approved_pairs = {
            (item.get("sceneId"), item.get("platform"))
            for item in visual_report if item.get("approved")
        }
        expected_pairs = {
            (scene.get("scene_id"), platform)
            for scene in storyboard["scenes"]
            for platform in scene.get("images", {})
        }
        missing = expected_pairs - approved_pairs
        if missing:
            raise ValueError(f"Visual QA chưa duyệt đủ cảnh: {sorted(missing)[:10]}")
        visual_approved = len(approved_pairs)
    return {
        "approved": True,
        "audio_segments": len(audio_report.get("segments", [])),
        "visual_scene_platforms": visual_approved,
        "audio_report": str(audio_report_path),
        "visual_report": str(visual_report_path) if visual_report_path.is_file() else None,
    }


def generate_audio(args: argparse.Namespace, chapter: Path, output: Path) -> dict[str, str]:
    audio_cli, _, _ = _audio_modules()
    settings = deepcopy(audio_cli._load_settings())
    tts_settings = settings.setdefault("tts", {})
    for argument, key in (
        ("voice", "voice"),
        ("temperature", "temperature"),
        ("top_k", "top_k"),
        ("top_p", "top_p"),
        ("repetition_penalty", "repetition_penalty"),
        ("pitch_ratio", "pitch_ratio"),
        ("tempo_ratio", "tempo_ratio"),
    ):
        value = getattr(args, argument, None)
        if value is not None:
            tts_settings[key] = value
    if args.mock:
        tts_settings["mock_max_duration_seconds"] = 0.12
    namespace = argparse.Namespace(
        input=str(chapter), output=str(output / "audio"),
        projects_dir=str(output / ".audiobook-work" / "projects"),
        cache_dir=str(output / ".audiobook-work" / "cache"),
        story=args.story or chapter.stem, chapter=args.chapter_number,
        title=args.title or "", tts_provider="mock" if args.mock else args.tts_provider,
        device=None if args.device == "auto" else ("cuda" if args.device == "gpu" else "cpu"),
        max_segment_length=args.max_segment_length, ai=args.ai,
        ai_model=args.ai_model, ai_timeout=None if args.overnight else 900,
        ai_batch_size=24 if args.overnight else 12,
        ai_retries=10 if args.overnight else 1,
        mp3=args.mp3, mp3_bitrate=args.mp3_bitrate,
        cc=args.subtitle_mode != "none",
    )
    print("\n[1/3] Tạo giọng đọc", flush=True)
    if args.ai:
        print(
            f"[models] TTS guidance={args.ai_model or 'qwen2.5:1.5b'}; "
            "storyboard director=qwen2.5:7b; extraction worker=qwen2.5:1.5b",
            flush=True,
        )
    previous_overnight = os.environ.get("AUDIOBOOK_OVERNIGHT")
    if args.overnight:
        os.environ["AUDIOBOOK_OVERNIGHT"] = "1"
    try:
        return audio_cli._run_generation(
            namespace, settings_override=settings,
            progress_callback=_progress,
        )
    finally:
        if previous_overnight is None:
            os.environ.pop("AUDIOBOOK_OVERNIGHT", None)
        else:
            os.environ["AUDIOBOOK_OVERNIGHT"] = previous_overnight


def _poster_needs_build() -> bool:
    target = POSTER_TOOL / "dist" / "storyboard-gen.js"
    if not target.is_file():
        return True
    return any(path.stat().st_mtime > target.stat().st_mtime for path in (POSTER_TOOL / "src").rglob("*.ts"))


def generate_storyboard(
    args: argparse.Namespace, master: Path, rules: Path, chapter: Path, output: Path,
) -> dict:
    if _poster_needs_build():
        print("[setup] Build poster-generator...", flush=True)
        _build_poster_tool()
    images_dir = output / "images"
    command = [
        "node", str(POSTER_TOOL / "dist" / "storyboard-gen.js"),
        "--master", str(master), "--rules", str(rules), "--chapter", str(chapter),
        "--output", str(images_dir), "--images", str(args.images),
        "--platform", args.platform, "--format", args.image_format,
        "--quality", "standard", "--device", args.device,
        "--render-mode", args.render_mode,
        "--parallel-workers", str(args.parallel_workers),
        "--model-profile", args.model_profile,
    ]
    provider = "mock" if args.mock else args.image_provider
    if provider:
        command.extend(["--image-provider", provider])
    if args.seed is not None:
        command.extend(["--seed", str(args.seed)])
    if args.scene_weights:
        command.extend(["--scene-weights", args.scene_weights])
    # Feed the compact context generated for this job; keep ROOT/.md as CLI fallback.
    ctx_dir = chapter.parent
    context_names = ("characters.md", "glossary.md", "timeline.md", "chapter_summaries.md")
    if not any((ctx_dir / name).is_file() for name in context_names):
        ctx_dir = ROOT / ".md"
    if ctx_dir.is_dir():
        command.extend(["--context-dir", str(ctx_dir)])
    state_root = Path(args.character_state_dir).expanduser().resolve() if args.character_state_dir else output
    command.extend(["--project-root", str(state_root)])
    if args.force:
        command.append("--force")
    print("\n[2/3] Tạo ảnh bìa và storyboard", flush=True)
    environment = os.environ.copy()
    if args.mock:
        environment["TEXT_AI_PROVIDER"] = "mock"
    if args.overnight:
        environment["AUDIOBOOK_OVERNIGHT"] = "1"
    _run_streamed(command, cwd=POSTER_TOOL, env=environment)
    return json.loads((images_dir / "storyboard.json").read_text(encoding="utf-8"))


def generate_cover(
    args: argparse.Namespace, master: Path, rules: Path, chapter: Path, output: Path,
) -> dict:
    if _poster_needs_build():
        print("[setup] Build poster-generator...", flush=True)
        _build_poster_tool()
    images_dir = output / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    platforms = ("youtube", "tiktok") if args.platform == "both" else (args.platform,)
    extension = "jpg" if args.image_format == "jpeg" else "png"
    covers: dict[str, str] = {}
    environment = os.environ.copy()
    provider = "mock" if args.mock else args.image_provider
    if args.mock:
        environment["TEXT_AI_PROVIDER"] = "mock"
    if provider:
        environment["IMAGE_AI_PROVIDER"] = provider
    if args.overnight:
        environment["AUDIOBOOK_OVERNIGHT"] = "1"
    print("\n[2/3] Tạo ảnh bìa", flush=True)
    for platform in platforms:
        target = images_dir / f"cover-{platform}.{extension}"
        command = [
            "node", str(POSTER_TOOL / "dist" / "poster-gen.js"),
            "--input", str(master), str(rules), str(chapter),
            "--output", str(target),
            "--platform", platform,
            "--format", args.image_format,
            "--quality", "standard",
            "--variants", "1",
            f"--{args.device}",
        ]
        if args.seed is not None:
            command.extend(["--seed", str(args.seed)])
        if args.force:
            command.append("--force")
        subprocess.run(command, cwd=POSTER_TOOL, check=True, env=environment)
        covers[platform] = str(target.resolve())
    return {"covers": covers, "scenes": []}


def storyboard_durations(storyboard: dict, audio_duration: float) -> list[float]:
    scenes = storyboard.get("scenes", [])
    if not scenes or audio_duration <= 0:
        raise ValueError("Không đủ dữ liệu để tính timeline storyboard")
    if len(scenes) == 1:
        return [audio_duration]
    line_count = max(2, int(storyboard.get("chapter_line_count", 2)))
    positions = [max(0.0, min(1.0, (int(scene["start_line"]) - 1) / (line_count - 1))) for scene in scenes]
    if any(right <= left for left, right in zip(positions, positions[1:])):
        positions = [index / max(1, len(scenes) - 1) for index in range(len(scenes))]
    boundaries = [0.0]
    boundaries.extend((left + right) / 2 for left, right in zip(positions, positions[1:]))
    boundaries.append(1.0)
    return [max(0.05, (boundaries[index + 1] - boundaries[index]) * audio_duration) for index in range(len(scenes))]


def apply_storyboard_overrides(storyboard: dict, output: Path) -> dict:
    override_path = output / "images" / "storyboard.overrides.json"
    if not override_path.is_file():
        return storyboard
    try:
        overrides = json.loads(override_path.read_text(encoding="utf-8")).get("scenes", {})
    except (OSError, json.JSONDecodeError):
        return storyboard
    merged = []
    for scene in storyboard.get("scenes", []):
        current = overrides.get(str(scene.get("scene_id", "")), {})
        if current.get("enabled", True) is False:
            continue
        next_scene = dict(scene)
        for key in ("location", "action"):
            if key in current:
                next_scene[key] = current[key]
        next_scene["_editor_order"] = int(current.get("order", scene.get("index", 0)))
        merged.append(next_scene)
    if not merged:
        raise ValueError("Scene editor đã tắt toàn bộ cảnh; không thể ghép video")
    result = dict(storyboard)
    result["scenes"] = sorted(merged, key=lambda scene: (scene["_editor_order"], scene.get("index", 0)))
    return result


def create_video(args: argparse.Namespace, audio_outputs: dict[str, str], storyboard: dict, output: Path) -> str | None:
    if not args.video:
        return None
    storyboard = apply_storyboard_overrides(storyboard, output)
    _, FFmpegManager, create_storyboard_video = _audio_modules()
    platform = "youtube" if args.platform == "both" else args.platform
    images = [scene.get("images", {}).get(platform, "") for scene in storyboard["scenes"]]
    if not all(images):
        raise ValueError(f"Storyboard thiếu ảnh cho platform {platform}")
    audio = audio_outputs.get("audio_mp3") or audio_outputs["audio"]
    manager = FFmpegManager()
    duration = manager.get_duration(audio)
    durations = storyboard_durations(storyboard, duration)
    width, height = ((1080, 1920) if platform == "tiktok" else (1920, 1080))
    video_dir = output / "video"; video_dir.mkdir(parents=True, exist_ok=True)
    video = video_dir / f"{_slug(args.story or 'audiobook')}-chapter-{args.chapter_number:03d}.mp4"
    print("\n[3/3] Ghép storyboard với audio", flush=True)
    nvenc_ready = args.device == "gpu" and manager.supports_encoder("h264_nvenc")
    video_encoder = "h264_nvenc" if nvenc_ready else "libx264"
    if args.device == "gpu" and not nvenc_ready:
        reason = next(
            (
                line for line in manager.last_encoder_error.splitlines()
                if "driver" in line.lower() or "nvenc api" in line.lower()
            ),
            "NVENC không khởi tạo được trên driver/FFmpeg hiện tại.",
        )
        print(f"[render] NVENC không khả dụng: {reason}", flush=True)
        print("[render] Tự chuyển sang CPU để job vẫn hoàn thành.", flush=True)
    print(
        f"[render] Video encoder: {video_encoder} "
        f"({'GPU NVENC' if video_encoder == 'h264_nvenc' else 'CPU fallback'})",
        flush=True,
    )
    last_video_percent = -1

    def video_progress(position: float, total: float) -> None:
        nonlocal last_video_percent
        percent = min(100, int(position / total * 100)) if total > 0 else 0
        if percent >= last_video_percent + 1 or percent >= 100:
            last_video_percent = percent
            print(
                f"[video {percent:5.1f}%] Ghép video: {position:.1f}/{total:.1f} giây",
                flush=True,
            )

    return create_storyboard_video(
        images, audio, str(video), durations=durations,
        subtitle_path=(
            audio_outputs.get("subtitles")
            if args.subtitle_mode in ("soft", "burn") else None
        ),
        subtitle_mode=args.subtitle_mode,
        ffmpeg_manager=manager, width=width, height=height,
        video_encoder=video_encoder,
        unlimited=args.overnight,
        progress_callback=video_progress,
    )


def resolve_build_image_count(
    args: argparse.Namespace, chapter: Path, audio_outputs: dict[str, str]
) -> tuple[str, int]:
    if args.overnight:
        profile = "max"
    elif args.images is not None:
        count = int(args.images)
        if count < 2:
            raise ValueError("Số ảnh cảnh phải từ 2 trở lên.")
        return "custom", count
    else:
        profile = args.audiobook or "medium"
    _, FFmpegManager, _ = _audio_modules()
    audio = audio_outputs.get("audio_mp3") or audio_outputs["audio"]
    duration = FFmpegManager().get_duration(audio)
    chapter_text = chapter.read_text(encoding="utf-8-sig", errors="ignore")
    count = choose_image_count(
        profile, duration, scene_hints=estimate_scene_hints(chapter_text)
    )
    return profile, count


def run_build(args: argparse.Namespace) -> int:
    master, rules, chapter = classify_inputs(args.input)
    if not args.story:
        args.story = chapter.stem
    output = Path(args.output).expanduser().resolve()
    final_manifest = output / "audiobook-manifest.json"
    if final_manifest.exists() and not args.force:
        raise ValueError(f"Output đã tồn tại: {final_manifest}. Dùng --force để chạy lại.")
    output.mkdir(parents=True, exist_ok=True)
    if args.cc and args.subtitle_mode == "none":
        args.subtitle_mode = "soft"
        args.keep_srt = True
    if args.video:
        args.image_output = "scenes"
    if args.overnight:
        args.audiobook = "max"
        args.model_profile = "max"
        print(
            "[overnight] Không giới hạn thời gian; giữ lựa chọn AI narration của user và audiobook max."
            if not args.mock else
            "[overnight/mock] Kiểm thử không model; giữ audiobook max.",
            flush=True,
        )
    if args.render_mode == "parallel":
        print(
            f"[render] Song song với {args.parallel_workers} worker; cần đủ VRAM hoặc backend hỗ trợ hàng đợi.",
            flush=True,
        )
    progress_manifest = output / "audiobook-progress.json"
    signature = _build_signature((master, rules, chapter), args)
    checkpoint: dict = {}
    if progress_manifest.is_file() and not args.force:
        try:
            loaded = json.loads(progress_manifest.read_text(encoding="utf-8"))
            if loaded.get("signature") == signature:
                checkpoint = loaded
        except (OSError, json.JSONDecodeError):
            checkpoint = {}
    checkpoint = {
        "version": 1,
        "signature": signature,
        "status": "running",
        "stages": checkpoint.get("stages", {}),
    }
    _atomic_json(progress_manifest, checkpoint)

    audio_stage = checkpoint["stages"].get("audio", {})
    if audio_stage.get("status") == "completed" and _paths_exist(audio_stage.get("outputs", {})):
        audio_outputs = audio_stage["outputs"]
        print("[resume] Audio hợp lệ, bỏ qua bước TTS.", flush=True)
        _progress_event("audio", 100, "Khôi phục audio từ checkpoint")
    else:
        audio_outputs = generate_audio(args, chapter, output)
        checkpoint["stages"]["audio"] = {"status": "completed", "outputs": audio_outputs}
        _atomic_json(progress_manifest, checkpoint)
    if args.image_output == "scenes":
        profile, image_count = resolve_build_image_count(args, chapter, audio_outputs)
        args.audiobook = profile
        args.images = image_count
        lower, upper = AUDIOBOOK_PROFILE_RANGES.get(profile, (image_count, image_count))
        range_text = "không giới hạn" if upper == float("inf") else f"khung {lower}–{upper}"
        print(
            f"[audiobook] preset={profile}, ảnh AI chính={image_count} ({range_text})",
            flush=True,
        )
        storyboard_stage = checkpoint["stages"].get("storyboard", {})
        if storyboard_stage.get("status") == "completed" and _storyboard_exists(storyboard_stage.get("outputs", {})):
            storyboard = storyboard_stage["outputs"]
            print("[resume] Storyboard hợp lệ, bỏ qua bước sinh ảnh.", flush=True)
            _progress_event("storyboard", 100, "Khôi phục storyboard từ checkpoint")
        else:
            storyboard = generate_storyboard(args, master, rules, chapter, output)
            checkpoint["stages"]["storyboard"] = {"status": "completed", "outputs": storyboard}
            _atomic_json(progress_manifest, checkpoint)
    elif args.image_output == "poster":
        storyboard_stage = checkpoint["stages"].get("storyboard", {})
        if storyboard_stage.get("status") == "completed" and _storyboard_exists(storyboard_stage.get("outputs", {})):
            storyboard = storyboard_stage["outputs"]
            print("[resume] Ảnh bìa hợp lệ, bỏ qua bước sinh ảnh.", flush=True)
            _progress_event("storyboard", 100, "Khôi phục ảnh bìa từ checkpoint")
        else:
            storyboard = generate_cover(args, master, rules, chapter, output)
            checkpoint["stages"]["storyboard"] = {"status": "completed", "outputs": storyboard}
            _atomic_json(progress_manifest, checkpoint)
    else:
        storyboard = {"covers": {}, "scenes": []}
    video_stage = checkpoint["stages"].get("video", {})
    saved_video = str(video_stage.get("output", "") or "")
    if args.video and video_stage.get("status") == "completed" and saved_video and Path(saved_video).is_file():
        video = saved_video
        print("[resume] Video hợp lệ, bỏ qua bước FFmpeg.", flush=True)
        _progress_event("video", 100, "Khôi phục video từ checkpoint")
    else:
        video = create_video(args, audio_outputs, storyboard, output)
        checkpoint["stages"]["video"] = {"status": "completed", "output": video}
        _atomic_json(progress_manifest, checkpoint)
    subtitle_file = audio_outputs.get("subtitles")
    if subtitle_file and not args.keep_srt:
        Path(subtitle_file).unlink(missing_ok=True)
        audio_outputs.pop("subtitles", None)
    audit = _final_audit(output, audio_outputs, storyboard)
    manifest = {
        "schema_version": 1, "version": "0.0.2", "story": args.story or chapter.stem,
        "audiobook_profile": args.audiobook,
        "overnight_unlimited": bool(args.overnight),
        "render_mode": args.render_mode,
        "parallel_workers": args.parallel_workers if args.render_mode == "parallel" else 1,
        "chapter_number": args.chapter_number,
        "inputs": {"master": str(master), "rules": str(rules), "chapter": str(chapter)},
        "audio": audio_outputs, "cover": storyboard.get("covers", {}),
        "subtitle_mode": args.subtitle_mode,
        "subtitles": audio_outputs.get("subtitles"),
        "image_output": args.image_output,
        "storyboard": (
            str(output / "images" / "storyboard.json")
            if args.image_output == "scenes" else None
        ),
        "visual_qa": (
            str(output / "images" / "storyboard-qa.json")
            if (output / "images" / "storyboard-qa.json").is_file() else None
        ),
        "character_cast": (
            str(output / "images" / "characters-used.json")
            if (output / "images" / "characters-used.json").is_file() else None
        ),
        "audit": audit,
        "scene_count": len(storyboard.get("scenes", [])), "video": video,
    }
    _atomic_json(final_manifest, manifest)
    checkpoint["status"] = "completed"
    checkpoint["final_manifest"] = str(final_manifest)
    _atomic_json(progress_manifest, checkpoint)
    print(f"\nHoàn tất v0.0.2: {output}")
    print(f"- Audio: {audio_outputs.get('audio_mp3') or audio_outputs['audio']}")
    if args.image_output == "scenes":
        print(f"- Ảnh truyện: {manifest['scene_count']} cảnh + ảnh bìa")
    elif args.image_output == "poster":
        print("- Ảnh truyện: chỉ ảnh bìa")
    if video:
        print(f"- Video: {video}")
    if audio_outputs.get("subtitles"):
        suffix = (
            " (đã ghi cứng vào MP4)" if video and args.subtitle_mode == "burn"
            else " (đã nhúng track vào MP4)" if video and args.subtitle_mode == "soft"
            else ""
        )
        print(f"- Phụ đề: {audio_outputs['subtitles']}{suffix}")
    print(f"- Manifest: {final_manifest}")
    return 0


def run_doctor() -> int:
    ollama = shutil.which("ollama")
    required_models = ("qwen2.5:1.5b", "qwen2.5:7b", "moondream")
    model_checks = {
        f"Ollama model {model}": bool(ollama) and subprocess.run(
            [ollama, "show", model], capture_output=True, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        ).returncode == 0
        for model in required_models
    }
    checkpoints = ROOT / "ComfyUI" / "models" / "checkpoints"
    checks = {
        "Python >= 3.10": sys.version_info >= (3, 10),
        "Node.js": shutil.which("node") is not None,
        "pnpm/Corepack": _pnpm_command() is not None,
        "FFmpeg": shutil.which("ffmpeg") is not None,
        "FFprobe": shutil.which("ffprobe") is not None,
        "audio-comic": (AUDIO_TOOL / "app.py").is_file(),
        "poster-generator build": (POSTER_TOOL / "dist" / "storyboard-gen.js").is_file(),
        "faster-whisper semantic QA": importlib.util.find_spec("faster_whisper") is not None,
        "DreamShaper 8": (checkpoints / "DreamShaper_8_pruned.safetensors").is_file(),
        "Realistic Vision 6": (checkpoints / "Realistic_Vision_V6.0_NV_B1_fp16.safetensors").is_file(),
        **model_checks,
    }
    for name, ready in checks.items():
        print(f"[{'OK' if ready else 'THIẾU'}] {name}")
    return 0 if all(checks.values()) else 1


def _asr_progress(percent: float, message: str) -> None:
    print(f"\r[ASR {percent:5.1f}%] {message:<90}", end="", flush=True)
    if percent >= 100:
        print()


def run_audio_to_srt(args: argparse.Namespace) -> int:
    location = str(AUDIO_TOOL)
    if location not in sys.path:
        sys.path.insert(0, location)
    from ai.audio_transcriber import transcribe_audio_to_srt

    result = transcribe_audio_to_srt(
        args.input,
        args.output,
        model_name=args.model,
        language=args.language,
        device=args.device,
        compute_type=args.compute_type,
        beam_size=args.beam_size,
        vad_filter=args.vad,
        initial_prompt=args.prompt,
        progress_callback=_asr_progress,
    )
    print(f"Hoàn tất phụ đề AI: {result.srt_path}")
    print(
        f"- Ngôn ngữ nhận dạng: {result.language} "
        f"({result.language_probability * 100:.1f}%)"
    )
    print(f"- Số đoạn ASR: {result.segment_count} | Model: {result.model}")
    return 0


def run_web(args: argparse.Namespace) -> int:
    from backend_bootstrap import (
        BackendSession,
        bootstrap_backends,
        print_backend_report,
    )
    from web_app import run_server, set_backend_status

    session = (
        BackendSession()
        if args.skip_backends
        else bootstrap_backends(timeout=args.backend_timeout)
    )
    print_backend_report(session)
    set_backend_status(session.as_dicts())
    try:
        run_server(args.host, args.port, open_browser=not args.no_browser)
        return 0
    finally:
        session.close()


def run_generate_story(args: argparse.Namespace) -> int:
    from audio_comic.ai.context.loader import load_context_files, build_context_prompt
    from audio_comic.ai.ollama_helper import OllamaNarrationHelper
    chapter_path = Path(args.chapter).expanduser().resolve()
    if not chapter_path.is_file():
        print(f"Loi: Khong tim thay chapter: {chapter_path}", file=sys.stderr)
        return 1
    chapter_text = chapter_path.read_text(encoding="utf-8-sig", errors="ignore")
    ctx_dir = Path(args.context_dir) if args.context_dir else ROOT / ".md"
    ctx = load_context_files(ctx_dir)
    context_str = build_context_prompt(ctx, for_image=True)
    helper = OllamaNarrationHelper(model=args.model or "")
    print(f"Story model: {helper.story_model}", flush=True)
    print(f"Context loaded: {ctx.loaded_files}", flush=True)
    result = helper.generate_story_prompt(chapter_text, context_str)
    output_path = Path(args.output) if args.output else chapter_path.parent / f"{chapter_path.stem}_scenes.json"
    output_path.write_text(result, encoding="utf-8")
    print(f"Da tao: {output_path}", flush=True)
    return 0


def run_setup() -> int:
    print("=== Spaling Audiobook Setup ===\n")
    print("[1/4] Python dependencies...")
    req = ROOT / "requirements.txt"
    if req.is_file():
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req), "-q"], check=True)
        print("  OK")
    print("[2/4] poster-generator...")
    cmd = _pnpm_command()
    if cmd:
        subprocess.run([*cmd, "install", "--frozen-lockfile"], cwd=POSTER_TOOL, check=True)
        subprocess.run([*cmd, "build"], cwd=POSTER_TOOL, check=True)
        print("  OK")
    print("[3/4] Ollama models...")
    ollama = shutil.which("ollama")
    if ollama:
        for m in ["qwen2.5:1.5b", "qwen2.5:7b", "moondream"]:
            print(f"  Pulling {m}...")
            subprocess.run([ollama, "pull", m], check=True)
        print("  OK")
    else:
        print("  WARN: Ollama not found")
    print("[4/4] Doctor check...")
    result = run_doctor()
    print("\n=== Done ===")
    return result


def run_status() -> int:
    print("=== Spaling Audiobook Status ===\n")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Node.js: {'found' if shutil.which('node') else 'MISSING'}")
    print(f"FFmpeg: {'found' if shutil.which('ffmpeg') else 'MISSING'}")
    ollama = shutil.which("ollama")
    if ollama:
        print("Ollama: found")
        r = subprocess.run([ollama, "list"], capture_output=True, text=True, check=False)
        lines = [l.strip() for l in r.stdout.strip().split("\n")[1:] if l.strip()]
        if lines:
            print("  Models:")
            for l in lines:
                print(f"    {l}")
        else:
            print("  No models")
    else:
        print("Ollama: MISSING")
    ctx_dir = ROOT / ".md"
    print(f"\nContext .md/: {'found' if ctx_dir.is_dir() else 'NOT FOUND'}")
    if ctx_dir.is_dir():
        for f in ["master.md","request.md","characters.md","glossary.md","timeline.md","chapter_summaries.md"]:
            print(f"  {f}: {'OK' if (ctx_dir/f).is_file() else 'missing'}")
    return 0


def run_models(action: str, model_name: str) -> int:
    ollama = shutil.which("ollama")
    if not ollama:
        print("Loi: Ollama not found.", file=sys.stderr)
        return 1
    if action == "list":
        return subprocess.run([ollama, "list"], check=False).returncode
    if action == "pull":
        if not model_name:
            result = 0
            for m in ["qwen2.5:1.5b", "qwen2.5:7b", "moondream"]:
                print(f"Pulling {m}...")
                result |= subprocess.run([ollama, "pull", m], check=False).returncode
            return result
        return subprocess.run([ollama, "pull", model_name], check=False).returncode
    if action == "remove":
        if not model_name:
            print("Loi: model name required.", file=sys.stderr)
            return 1
        return subprocess.run([ollama, "rm", model_name], check=False).returncode
    return 1


def run_wizard() -> int:
    """Small interactive UI for users who prefer not to compose flags."""
    def ask(label: str, default: str) -> str:
        value = input(f"{label} [{default}]: ").strip()
        return value or default

    print("AudioBook v0.0.2 release — trình hướng dẫn tạo truyện audio nhiều ảnh\n")
    master = ask("Master", str(TESTING / "master.md"))
    rules = ask("Request/canon", str(TESTING / "request.md"))
    chapter = ask("Chapter TXT", str(TESTING / "chapter1.txt"))
    output = ask("Thư mục output", str(ROOT / "output"))
    profile = ask("Mức audiobook (low/medium/high/max)", "medium").lower()
    device = ask("Thiết bị (auto/cpu/gpu)", "auto").lower()
    quality = ask("Chất lượng ảnh (draft/standard/high)", "standard").lower()
    return main(["build", "--input", master, rules, chapter, "--output", output, "--audiobook", profile, "--device", device, "--quality", quality])


def _add_audiobook_profile_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--audiobook", nargs="?", const="medium", default="medium",
        choices=["auto", "low", "medium", "high", "max"],
        help="Mật độ ảnh AI: low 6–60, medium 60–200, high 100–400, max/auto do AI chia theo cảnh",
    )
    profile = parser.add_mutually_exclusive_group()
    profile.add_argument("-low", dest="audiobook", action="store_const", const="low")
    profile.add_argument("-medium", dest="audiobook", action="store_const", const="medium")
    profile.add_argument("-high", dest="audiobook", action="store_const", const="high")
    profile.add_argument("-max", dest="audiobook", action="store_const", const="max")


def _add_build_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", "-i", nargs=3, required=True, metavar=("MASTER", "REQUEST", "CHAPTER"))
    parser.add_argument("--output", "-o", default=str(ROOT / "output"))
    parser.add_argument("--story", default="")
    parser.add_argument("--chapter-number", type=int, default=1)
    parser.add_argument("--title", default="")
    parser.add_argument("--images", type=int, default=None, metavar="N>=2")
    _add_audiobook_profile_options(parser)
    parser.add_argument("--platform", choices=["youtube", "tiktok", "both"], default="youtube")
    parser.add_argument("--image-format", choices=["jpeg", "png"], default="jpeg")
    parser.add_argument("--image-provider", choices=["comfyui", "mock"])
    parser.add_argument("--tts-provider", choices=["vieneu", "sapi5", "mock"], default="vieneu")
    parser.add_argument("--voice", default="")
    parser.add_argument("--device", choices=["auto", "cpu", "gpu"], default="auto")
    parser.add_argument("--render-mode", choices=["sequential", "parallel"], default="sequential")
    render = parser.add_mutually_exclusive_group()
    render.add_argument("--sequential", dest="render_mode", action="store_const", const="sequential")
    render.add_argument("--parallel", dest="render_mode", action="store_const", const="parallel")
    parser.add_argument("--parallel-workers", type=int, choices=range(1, 9), default=2, metavar="1..8")
    parser.add_argument("--max-segment-length", type=int, default=500)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--top-p", type=float)
    parser.add_argument("--repetition-penalty", type=float)
    parser.add_argument("--pitch-ratio", type=float)
    parser.add_argument("--tempo-ratio", type=float)
    parser.add_argument("--scene-weights", default="", help="JSON trọng số chọn cảnh")
    parser.add_argument(
        "--character-state-dir", default="",
        help="Thư mục lưu character continuity riêng của bộ truyện.",
    )
    parser.add_argument("--ai", action="store_true", help="Dùng Ollama hỗ trợ nhịp đọc")
    parser.add_argument("--ai-model", default="")
    parser.add_argument("--model-profile", choices=["low", "medium", "high", "max"], default="medium", help="Chất lượng ảnh: low=Nhanh, medium=Cân bằng, high=Cao cấp, max=Tốt nhất")
    parser.add_argument("--mp3", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--mp3-bitrate", choices=["192k", "320k"], default="192k")
    parser.add_argument("--video", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("-cc", "--cc", action="store_true", help="Xuất SRT tiếng Việt và nhúng subtitle track vào MP4")
    parser.add_argument(
        "--subtitle-mode", choices=["none", "file", "soft", "burn"], default="none",
        help="Phụ đề: không dùng, chỉ SRT, nhúng track hoặc ghi cứng vào video",
    )
    parser.add_argument(
        "--keep-srt", action=argparse.BooleanOptionalAction, default=True,
        help="Giữ file SRT riêng sau khi ghép video",
    )
    parser.add_argument(
        "--image-output", choices=["none", "poster", "scenes"], default="scenes",
        help="Không xuất ảnh, chỉ ảnh bìa hoặc toàn bộ ảnh cảnh",
    )
    parser.add_argument("--seed", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "-overnight", "--overnight", action="store_true",
        help="Không giới hạn thời gian; ép audiobook max, AI narration và chất lượng high",
    )
    parser.add_argument("--mock", action="store_true", help="Smoke test nhanh, không tải model AI")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="audiobook", description="Tạo audiobook nhiều ảnh từ master.md + request.md + chapter.txt")
    commands = parser.add_subparsers(dest="command")
    build = commands.add_parser("build", help="Chạy toàn bộ TTS → storyboard → video")
    _add_build_options(build)
    smoke = commands.add_parser("smoke-test", help="Test end-to-end bằng 3 file trong testing và provider mock")
    smoke.add_argument("--output", "-o", default=str(ROOT / "artifacts" / "smoke-test"))
    smoke.add_argument("--images", type=int, choices=range(2, 21), default=6)
    smoke.add_argument("--force", action="store_true")
    smoke.add_argument("-cc", "--cc", action="store_true")
    commands.add_parser("doctor", help="Kiểm tra dependency hệ thống")
    commands.add_parser("wizard", help="Mở giao diện hỏi-đáp trong terminal")
    web = commands.add_parser("web", help="Mở giao diện web local")
    web.add_argument(
        "--host", choices=["127.0.0.1", "localhost"], default="127.0.0.1",
        help="Chỉ bind loopback; Web API có quyền đọc file local nên không mở trực tiếp ra LAN.",
    )
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--no-browser", action="store_true")
    web.add_argument(
        "--backend-timeout", type=int, default=3000,
        help="Số giây tối đa chờ ComfyUI/Ollama sẵn sàng trước khi mở UI",
    )
    web.add_argument(
        "--skip-backends", action="store_true",
        help="Không tự kiểm tra/khởi động backend (chỉ dùng khi debug)",
    )
    asr = commands.add_parser(
        "audio-to-srt", help="Dùng AI dựng lại phụ đề SRT từ WAV/MP3 cũ"
    )
    asr.add_argument("--input", "-i", required=True, help="File audio WAV/MP3/M4A...")
    asr.add_argument("--output", "-o", help="File .srt (mặc định: <audio>.vi.srt)")
    asr.add_argument("--model", default="small", help="Model Whisper hoặc đường dẫn model")
    asr.add_argument("--language", default="vi", help="Mã ngôn ngữ; dùng auto để tự nhận diện")
    asr.add_argument("--device", choices=["auto", "cpu", "gpu"], default="auto")
    asr.add_argument(
        "--compute-type",
        choices=["auto", "default", "int8", "float16", "float32"],
        default="auto",
    )
    asr.add_argument("--beam-size", type=int, default=5)
    asr.add_argument(
        "--vad", action=argparse.BooleanOptionalAction, default=True,
        help="Lọc khoảng lặng để giảm câu nhận nhầm",
    )
    asr.add_argument(
        "--prompt", default="",
        help="Gợi ý tên riêng/thuật ngữ giúp AI chép chính xác hơn",
    )
    gen_story = commands.add_parser("generate-story", help="Tạo scene descriptions từ .md context")
    gen_story.add_argument("--chapter", "-c", required=True, help="File chapter TXT")
    gen_story.add_argument("--context-dir", "-d", help="Thư mục chứa .md files (characters, glossary...)")
    gen_story.add_argument("--output", "-o", help="File JSON output")
    gen_story.add_argument("--model", default="", help="Ollama model (mặc định: qwen2.5:7b)")

    commands.add_parser("setup", help="Cài đặt dependencies + pull AI models")
    commands.add_parser("status", help="Kiểm tra trạng thái models + dependencies")

    models = commands.add_parser("models", help="Quản lý Ollama models")
    models.add_argument("action", choices=["list", "pull", "remove"], help="Hành động")
    models.add_argument("model_name", nargs="?", default="", help="Tên model (cho pull/remove)")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_console(); values = list(sys.argv[1:] if argv is None else argv)
    command_names = {"build", "smoke-test", "doctor", "wizard", "web", "audio-to-srt", "generate-story", "setup", "status", "models"}
    if values and values[0] not in command_names and values[0] not in ("-h", "--help"):
        values.insert(0, "build")
    parser = build_parser(); args = parser.parse_args(values)
    try:
        if args.command == "build":
            return run_build(args)
        if args.command == "doctor":
            return run_doctor()
        if args.command == "wizard":
            return run_wizard()
        if args.command == "web":
            return run_web(args)
        if args.command == "audio-to-srt":
            return run_audio_to_srt(args)
        if args.command == "generate-story":
            return run_generate_story(args)
        if args.command == "setup":
            return run_setup()
        if args.command == "status":
            return run_status()
        if args.command == "models":
            return run_models(args.action, args.model_name)
        if args.command == "smoke-test":
            nested = ["build", "--input", str(TESTING / "master.md"), str(TESTING / "request.md"), str(TESTING / "chapter1.txt"), "--output", args.output, "--images", str(args.images), "--mock"]
            if args.force:
                nested.append("--force")
            if args.cc:
                nested.append("-cc")
            return main(nested)
        parser.print_help(); return 0
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
