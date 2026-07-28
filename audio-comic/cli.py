"""Command-line interface for the audiobook audio subsystem."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Callable

from core.cache_manager import CacheManager
from core.exceptions import AudioComicError
from core.pipeline import Pipeline
from core.project_manager import ProjectManager
from core.state_manager import StateManager
from models.export_settings import ExportSettings
from models.segment import Segment
from tts.mock_provider import MockTTSProvider
from utils.encoding import read_text_file
from utils.logging_config import get_logger, setup_logging
from utils.paths import (
    get_app_root, get_default_cache_dir, get_default_projects_dir,
    normalize_user_path,
)
from utils.system_check import run_system_check
from video.ffmpeg_manager import FFmpegManager

logger = get_logger("cli")


def _load_settings() -> dict:
    path = get_app_root() / "config" / "settings.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _prepare_generation_settings(settings: dict, ai_enabled: bool) -> dict:
    """Keep user TTS controls authoritative when AI guidance is enabled."""
    return deepcopy(settings)


def _create_tts_provider(name: str, settings: dict, device: str | None = None):
    if name == "vieneu":
        from tts.vieneu_provider import VieNeuTTSProvider

        tts = settings.get("tts", {})
        paths = settings.get("paths", {})
        return VieNeuTTSProvider(
            model_path=paths.get("vieneu_model", ""),
            checkpoint_path=paths.get("vieneu_checkpoint", ""),
            device=device or tts.get("device", "auto"),
            dtype=tts.get("dtype", "auto"),
            seed=tts.get("seed", 42),
            default_voice=tts.get("voice", "Thanh Bình"),
            style=tts.get("style", "doc_truyen"),
            temperature=tts.get("temperature", 0.6),
            top_k=tts.get("top_k", 20),
            top_p=tts.get("top_p", 0.88),
            repetition_penalty=tts.get("repetition_penalty", 1.15),
            max_chars=tts.get("model_max_chars", 256),
            pitch_ratio=tts.get("pitch_ratio", 0.936),
            tempo_ratio=tts.get("tempo_ratio", 1.019),
            voice_registry_path=str(
                get_app_root() / "config" / "custom_voices.json"
            ),
        )
    if name == "sapi5":
        from tts.sapi5_provider import WindowsSAPI5Provider

        return WindowsSAPI5Provider()
    return MockTTSProvider(
        generate_tone=True,
        max_duration_seconds=settings.get("tts", {}).get("mock_max_duration_seconds"),
    )


def _progress(stage: str, percent: float, message: str) -> None:
    print(f"\r{percent:6.1f}% | {stage}: {message}", end="", flush=True)
    if percent >= 100:
        print()


def _create_project(args: argparse.Namespace, source_text: str):
    manager = ProjectManager(Path(args.projects_dir or get_default_projects_dir()))
    project = manager.create_project(
        story_name=args.story or Path(args.input).stem,
        chapter_number=args.chapter,
        chapter_title=args.title or "",
        source_text=source_text,
        source_file=Path(args.input),
        output_dir=Path(args.output) if args.output else None,
    )
    project.export_settings = ExportSettings(
        export_mp3=args.mp3,
        export_subtitles=bool(getattr(args, "cc", False)),
        mp3_bitrate=args.mp3_bitrate,
    )
    return manager, project


def _run_generation(
    args: argparse.Namespace,
    settings_override: dict | None = None,
    progress_callback: Callable[[str, float, str], None] | None = None,
    segments_override: list[dict] | None = None,
    pipeline_callback: Callable[[Pipeline], None] | None = None,
) -> dict[str, str]:
    ai_enabled = bool(getattr(args, "ai", False) or segments_override)
    settings = _prepare_generation_settings(
        settings_override or _load_settings(), ai_enabled
    )
    tts_snapshot = {
        key: settings.get("tts", {}).get(key)
        for key in ("voice", "temperature", "top_k", "top_p", "repetition_penalty", "pitch_ratio", "tempo_ratio")
    }
    logger.info("TTS settings snapshot before AI analysis: %s", tts_snapshot)
    args.input = normalize_user_path(args.input)
    if args.output:
        args.output = normalize_user_path(args.output)
    if args.projects_dir:
        args.projects_dir = normalize_user_path(args.projects_dir)
    if args.max_segment_length is not None and args.max_segment_length < 50:
        raise ValueError("--max-segment-length phải từ 50 trở lên")
    selected_device = args.device or settings.get("tts", {}).get("device", "auto")
    max_segment_length = args.max_segment_length or settings.get("tts", {}).get(
        "max_segment_length", 500
    )
    print(f"Thiết bị TTS: {selected_device}")
    source_text = read_text_file(Path(args.input))
    manager, project = _create_project(args, source_text)
    if segments_override:
        project.segments = [Segment.from_dict(item) for item in segments_override]
    ai_helper = None
    if getattr(args, "ai", False) and not segments_override:
        from ai.ollama_helper import OllamaNarrationHelper
        from ai.parameter_policy import ParameterPolicy

        ai_helper = OllamaNarrationHelper(
            model=getattr(args, "ai_model", ""),
            timeout=getattr(args, "ai_timeout", 900),
            batch_size=getattr(args, "ai_batch_size", 12),
            retries=getattr(args, "ai_retries", 1),
            parameter_policy=ParameterPolicy.from_tts_settings(settings),
        )
        print(f"AI hỗ trợ: {ai_helper.model}")
    pipeline = Pipeline(
        tts_provider=_create_tts_provider(args.tts_provider, settings, args.device),
        ffmpeg_manager=FFmpegManager(settings.get("paths", {}).get("ffmpeg", "")),
        cache_manager=CacheManager(
            Path(getattr(args, "cache_dir", "") or get_default_cache_dir())
        ),
        progress_callback=progress_callback or _progress,
        max_segment_length=max_segment_length,
        ai_helper=ai_helper,
        semantic_qa={
            "enabled": bool(
                settings.get("tts", {}).get("semantic_qa", False)
                and args.tts_provider == "vieneu"
            ),
            "model": settings.get("tts", {}).get("semantic_qa_model", "small"),
            "device": settings.get("tts", {}).get("semantic_qa_device", "cpu"),
            "compute_type": settings.get("tts", {}).get(
                "semantic_qa_compute_type", "int8"
            ),
        },
    )
    if pipeline_callback:
        pipeline_callback(pipeline)
    state = StateManager(Path(project.project_dir) / "project_state.json")
    outputs = pipeline.run(project, state)
    manager.save_project(project)
    print("Hoàn thành:")
    for kind, path in outputs.items():
        print(f"  {kind}: {Path(path).resolve()}")
    return outputs


def cmd_generate_audio(args: argparse.Namespace) -> None:
    _run_generation(args)


def cmd_audio_to_srt(args: argparse.Namespace) -> None:
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
        progress_callback=lambda percent, message: _progress("ASR", percent, message),
    )
    print(f"Phụ đề: {result.srt_path}")
    print(
        f"Ngôn ngữ: {result.language} ({result.language_probability * 100:.1f}%) "
        f"| Đoạn: {result.segment_count} | Model: {result.model}"
    )


def cmd_system_check(args: argparse.Namespace) -> None:
    settings = _load_settings()
    paths = settings.get("paths", {})
    report = run_system_check(
        ffmpeg_path=paths.get("ffmpeg", ""),
        ffprobe_path=paths.get("ffprobe", ""),
        vieneu_model_path=paths.get("vieneu_model", ""),
    )
    for result in report.results:
        print(f"[{result.status.value.upper():7s}] {result.name}: {result.message}")
        if result.path:
            print(f"          path: {result.path}")


def cmd_model_info(args: argparse.Namespace) -> None:
    try:
        version = importlib.metadata.version("vieneu")
        import vieneu

        print(f"VieNeu package: {version}")
        print(f"Runtime: {Path(vieneu.__file__).resolve()}")
    except (ImportError, importlib.metadata.PackageNotFoundError):
        print("VieNeu chưa được cài đặt")
        return

    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    hub = hf_home / "hub"
    print(f"Hugging Face cache: {hub}")
    for model_dir in sorted(hub.glob("models--*")) if hub.is_dir() else []:
        if any(token in model_dir.name.lower() for token in ("vieneu", "moss-audio")):
            size = sum(path.stat().st_size for path in model_dir.rglob("*") if path.is_file())
            print(f"  {model_dir.name}: {size / (1024**2):.1f} MiB")
    settings = _load_settings().get("tts", {})
    device = settings.get("device", "auto")
    backend = "ONNX Runtime / CPU" if device in ("cpu", "auto") else "PyTorch / CUDA"
    print(f"Configured execution: {backend} (device={device})")


def cmd_clear_cache(args: argparse.Namespace) -> None:
    cache = CacheManager(get_default_cache_dir())
    print(f"Đã xóa {cache.clear_all()} cache entries")


def _add_input_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", "-input", "-i", required=True, help="Tệp TXT đầu vào")
    parser.add_argument("--story", "-s")
    parser.add_argument("--chapter", "-c", type=int, default=1)
    parser.add_argument("--title", "-t")
    parser.add_argument("--output", "-output", "-o", help="Thư mục output")
    parser.add_argument("--projects-dir")
    parser.add_argument("--tts-provider", choices=["vieneu", "sapi5", "mock"], default="vieneu")
    device = parser.add_mutually_exclusive_group()
    device.add_argument(
        "--cpu", "-cpu", dest="device", action="store_const", const="cpu",
        help="Chạy TTS bằng CPU (ONNX Runtime)",
    )
    device.add_argument(
        "--gpu", "-gpu", dest="device", action="store_const", const="cuda",
        help="Chạy TTS bằng GPU NVIDIA/CUDA",
    )
    parser.set_defaults(device=None)
    parser.add_argument(
        "--max-segment-length", type=int, default=None,
        help="Số ký tự tối đa mỗi đoạn TTS (mặc định theo config)",
    )
    parser.add_argument(
        "--ai", "-ai", action="store_true",
        help="Dùng Ollama để tạo hướng dẫn đọc và tinh chỉnh phân đoạn",
    )
    parser.add_argument(
        "--ai-model", default="",
        help="Model Ollama (mặc định tự chọn model nhẹ phù hợp)",
    )
    parser.add_argument("--mp3", action="store_true")
    parser.add_argument("-cc", "--cc", action="store_true", help="Xuất SRT tiếng Việt")
    parser.add_argument("--mp3-bitrate", choices=["192k", "320k"], default="192k")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="audio-comic", description="Chuyển TXT thành audio tiếng Việt")
    commands = parser.add_subparsers(dest="command")

    audio = commands.add_parser("generate-audio", help="TXT → WAV/MP3 (luồng chính)")
    _add_input_options(audio)
    audio.set_defaults(func=cmd_generate_audio)

    asr = commands.add_parser("audio-to-srt", help="WAV/MP3 → SRT bằng faster-whisper")
    asr.add_argument("--input", "-input", "-i", required=True)
    asr.add_argument("--output", "-output", "-o")
    asr.add_argument("--model", default="small")
    asr.add_argument("--language", default="vi")
    asr.add_argument("--device", choices=["auto", "cpu", "gpu"], default="auto")
    asr.add_argument(
        "--compute-type",
        choices=["auto", "default", "int8", "float16", "float32"],
        default="auto",
    )
    asr.add_argument("--beam-size", type=int, default=5)
    asr.add_argument("--vad", action=argparse.BooleanOptionalAction, default=True)
    asr.add_argument("--prompt", default="")
    asr.set_defaults(func=cmd_audio_to_srt)

    commands.add_parser("system-check").set_defaults(func=cmd_system_check)
    commands.add_parser("model-info").set_defaults(func=cmd_model_info)
    commands.add_parser("clear-cache").set_defaults(func=cmd_clear_cache)
    return parser


def _join_unquoted_path_values(argv: list[str]) -> list[str]:
    """Accept Windows paths containing spaces even when the shell split them.

    Values following -input/-output are joined until the next option. Quoting
    paths is still recommended, but the documented short command remains
    forgiving for users pasting it into PowerShell or cmd.exe.
    """
    path_options = {"-input", "--input", "-i", "-output", "--output", "-o"}
    normalized: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        normalized.append(token)
        index += 1
        if token not in path_options or index >= len(argv):
            continue
        value_parts: list[str] = []
        while index < len(argv) and not argv[index].startswith("-"):
            value_parts.append(argv[index])
            index += 1
        if value_parts:
            normalized.append(" ".join(value_parts))
    return normalized


def main(argv: list[str] | None = None) -> None:
    setup_logging(log_dir=get_app_root() / "logs")
    parser = build_parser()
    argv = _join_unquoted_path_values(list(sys.argv[1:] if argv is None else argv))
    command_names = {
        "generate-audio", "audio-to-srt", "system-check", "model-info", "clear-cache",
    }
    if argv and argv[0] not in command_names and argv[0] not in ("-h", "--help"):
        argv.insert(0, "generate-audio")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return
    try:
        args.func(args)
    except (AudioComicError, OSError, ValueError) as exc:
        logger.error("Command failed: %s", exc)
        print(f"Lỗi: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
