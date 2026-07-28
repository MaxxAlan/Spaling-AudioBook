"""Lightweight local web UI for the unified audiobook command."""

from __future__ import annotations

import json
import mimetypes
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "web"
JOB_ROOT = ROOT / ".audiobook-web"

def _venv_python() -> str:
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
PERSIST_LOCK = threading.Lock()
GPU_LOCK = threading.Lock()
PROCESSES: dict[str, subprocess.Popen[str]] = {}
BACKEND_STATUS: list[dict[str, object]] = []


def set_backend_status(statuses: list[dict[str, object]]) -> None:
    global BACKEND_STATUS
    BACKEND_STATUS = list(statuses)


def _ollama_models() -> list[str]:
    try:
        with request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, error.URLError, json.JSONDecodeError):
        return []
    return [
        str(item.get("name", ""))
        for item in payload.get("models", [])
        if item.get("name") and not any(token in str(item["name"]).lower() for token in ("embed", "moondream"))
    ]


def _default_tts_settings() -> dict:
    path = ROOT / "audio-comic" / "config" / "settings.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("tts", {})
    except (OSError, json.JSONDecodeError):
        return {}


def _custom_voices() -> list[dict[str, str]]:
    path = ROOT / "audio-comic" / "config" / "custom_voices.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        {"id": str(item["id"]), "name": str(item["name"])}
        for item in payload.get("voices", [])
        if item.get("id") and item.get("name") and item.get("consent_confirmed")
    ]


def _vieneu_voices() -> list[dict[str, str]]:
    voices: list[dict[str, str]] = []
    try:
        import vieneu

        path = Path(vieneu.__file__).resolve().parent / "assets" / "voices_v3_turbo.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        voices.extend(
            {"id": str(voice_id), "name": str(voice_id)}
            for voice_id in payload.get("presets", {})
        )
    except (ImportError, OSError, json.JSONDecodeError):
        pass
    known = {item["id"].casefold() for item in voices}
    voices.extend(item for item in _custom_voices() if item["id"].casefold() not in known)
    return voices


def _hardware_snapshot() -> dict[str, object]:
    snapshot: dict[str, object] = {
        "os": platform.system(),
        "cpu_threads": os.cpu_count() or 1,
        "gpu": "",
        "vram_total_mb": 0,
        "vram_free_mb": 0,
    }
    nvidia_smi = shutil.which("nvidia-smi")
    if nvidia_smi:
        result = subprocess.run(
            [
                nvidia_smi,
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=5, check=False,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0 and result.stdout.strip():
            name, total, free = [item.strip() for item in result.stdout.splitlines()[0].split(",")]
            snapshot.update(
                gpu=name, vram_total_mb=int(total), vram_free_mb=int(free)
            )
    return snapshot


def _recommend_parallel_workers(payload: dict) -> dict[str, object]:
    hardware = _hardware_snapshot()
    # Image rendering is always ComfyUI GPU in the web app.  Keep accepting
    # legacy payload fields, but do not let their absence accidentally force
    # the recommendation path into CPU mode.
    device = str(payload.get("device", "gpu"))
    provider = str(payload.get("image_provider", "comfyui") or "comfyui")
    vram = int(hardware["vram_total_mb"])
    if device == "cpu":
        safe_cap = 1
    elif vram < 6000:
        safe_cap = 1
    elif vram < 12000:
        safe_cap = 2
    elif vram < 20000:
        safe_cap = 4
    else:
        safe_cap = 6
    fallback_reason = (
        f"Giới hạn an toàn: {hardware['gpu'] or 'CPU'}, "
        f"VRAM {vram or 0} MB, backend {provider}."
    )
    models = _ollama_models()
    model = str(payload.get("ai_model", "") or (models[0] if models else ""))
    if not model:
        return {
            "workers": safe_cap, "source": "hardware",
            "reason": fallback_reason, "hardware": hardware,
        }
    prompt = (
        "Bạn là bộ lập lịch tài nguyên cho pipeline sinh ảnh audiobook. "
        "Chọn số worker song song an toàn từ 1 đến 8. Không được vượt quá "
        f"safe_cap={safe_cap}. Cấu hình: {json.dumps(hardware, ensure_ascii=False)}, "
        f"device={device}, provider={provider}. Chỉ trả JSON "
        '{"workers":1,"reason":"một câu tiếng Việt ngắn"}.'
    )
    try:
        body = json.dumps({
            "model": model, "prompt": prompt, "stream": False, "format": "json",
            "options": {"temperature": 0},
        }).encode("utf-8")
        req = request.Request(
            "http://127.0.0.1:11434/api/generate", data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with request.urlopen(req, timeout=120) as response:
            outer = json.loads(response.read().decode("utf-8"))
        answer = json.loads(str(outer.get("response", "{}")))
        proposed = max(1, min(8, int(answer.get("workers", safe_cap))))
        workers = min(safe_cap, proposed)
        reason = str(answer.get("reason", fallback_reason))
        if proposed != workers:
            reason = (
                f"AI đề xuất {proposed} luồng, ứng dụng giới hạn còn {workers} "
                f"để tránh thiếu VRAM ({vram or 0} MB)."
            )
        return {
            "workers": workers, "source": f"Ollama · {model}",
            "reason": reason,
            "hardware": hardware,
        }
    except (OSError, ValueError, TypeError, error.URLError, json.JSONDecodeError):
        return {
            "workers": safe_cap, "source": "hardware",
            "reason": fallback_reason, "hardware": hardware,
        }


def _select_output_directory(initial: str = "") -> str:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(
            parent=root,
            title="Chọn thư mục xuất audiobook",
            initialdir=initial if initial and Path(initial).is_dir() else str(ROOT),
            mustexist=False,
        )
        return str(Path(selected).resolve()) if selected else ""
    finally:
        root.destroy()


def _job_snapshot(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        snap = dict(job)
    now = time.time()
    started = snap.get("started_at", 0)
    if started:
        elapsed = now - started
        snap["elapsed"] = elapsed
        eta = float(snap.get("eta_seconds", 0) or 0)
        measured_at = float(snap.get("eta_measured_at", now) or now)
        if eta > 0:
            eta = max(0.0, eta - (now - measured_at))
        snap["eta"] = eta
    else:
        snap["elapsed"] = 0
        snap["eta"] = 0
    return snap


def _update_job(job_id: str, **values: object) -> None:
    values["updated_at"] = time.time()
    if "eta_seconds" in values:
        values["eta_measured_at"] = time.time()
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(values)
        else:
            return
    _persist_job(job_id)


def _persist_job(job_id: str) -> None:
    with JOBS_LOCK:
        job = dict(JOBS.get(job_id, {}))
    if not job:
        return
    job_dir = JOB_ROOT / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    target = job_dir / "config.json"
    temporary = job_dir / "config.json.tmp"
    with PERSIST_LOCK:
        temporary.write_text(
            json.dumps(job, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, target)


def _load_persisted_jobs() -> list[tuple[str, dict]]:
    jobs_dir = JOB_ROOT / "jobs"
    if not jobs_dir.is_dir():
        return []
    restored: dict[str, dict] = {}
    resumable: list[tuple[str, dict]] = []
    for config_path in jobs_dir.glob("*/config.json"):
        try:
            job = json.loads(config_path.read_text(encoding="utf-8"))
            job.setdefault("schema_version", 1)
            job_id = str(job.get("id", ""))
            if not re.fullmatch(r"[a-f0-9]{12}", job_id):
                continue
            if job.get("status") in {"queued", "running"}:
                job.update({
                    "status": "queued",
                    "stage": "Khôi phục",
                    "message": "Đang tiếp tục từ checkpoint sau khi Web app khởi động lại.",
                    "cancel_requested": False,
                })
                resumable.append((job_id, dict(job.get("request", {}))))
            restored[job_id] = job
        except (OSError, json.JSONDecodeError):
            continue
    with JOBS_LOCK:
        JOBS.update(restored)
    for job_id in restored:
        _persist_job(job_id)
    return resumable


def _active_job_snapshot() -> dict | None:
    with JOBS_LOCK:
        active = [
            dict(job) for job in JOBS.values()
            if job.get("status") in {"queued", "running"}
        ]
    active.sort(key=lambda job: float(job.get("started_at", 0) or 0), reverse=True)
    return active[0] if active else None


def _parse_progress(line: str, current: float) -> float:
    if line.startswith("@@progress "):
        try:
            event = json.loads(line.removeprefix("@@progress "))
            percent = max(0.0, min(100.0, float(event.get("percent", 0))))
            stage = str(event.get("stage", ""))
            if stage == "audio":
                return max(current, percent * 0.6)
            if stage == "storyboard":
                return max(current, 62.0 + percent * 0.3)
            if stage == "video":
                return max(current, 93.0 + percent * 0.06)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    audio = re.search(r"\[audio\s+([\d.]+)%\]", line)
    if audio:
        return min(60.0, float(audio.group(1)) * 0.6)
    if "[2/3]" in line:
        return max(current, 62.0)
    analysis_marks = (
        ("Structural segmentation", 63.0),
        ("Narrative Director", 66.0),
        ("Guided worker", 72.0),
        ("Scene Director", 77.0),
        ("H\u1ee3p l\u1ec7 sau", 80.0),
    )
    for marker, percent in analysis_marks:
        if marker in line:
            return max(current, percent)
    scene = re.search(r"\u0110\u00e3 sinh c\u1ea3nh\s+(\d+)/(\d+)", line, re.IGNORECASE)
    if scene and int(scene.group(2)):
        return max(current, 80.0 + 12.0 * int(scene.group(1)) / int(scene.group(2)))
    if "[3/3]" in line:
        return max(current, 93.0)
    video = re.search(r"\[video\s+([\d.]+)%\]", line)
    if video:
        return max(current, 93.0 + 6.0 * min(100.0, float(video.group(1))) / 100.0)
    return current


def _remaining_eta(started_at: float, completed: int, total: int, now: float) -> float:
    if not started_at or completed <= 0 or total <= completed:
        return 0.0
    return (now - started_at) / completed * (total - completed)


def _manifest_outputs(output: Path) -> dict[str, str]:
    manifest_path = output / "audiobook-manifest.json"
    if not manifest_path.is_file():
        return {}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    audio = payload.get("audio", {})
    outputs = {
        "wav": str(audio.get("audio", "")),
        "mp3": str(audio.get("audio_mp3", "")),
        "srt": str(payload.get("subtitles", "") or audio.get("subtitles", "")),
        "video": str(payload.get("video", "") or ""),
        "manifest": str(manifest_path),
        "storyboard": str(payload.get("storyboard", "") or ""),
        "visual_qa": str(payload.get("visual_qa", "") or ""),
        "character_cast": str(payload.get("character_cast", "") or ""),
    }
    return {key: value for key, value in outputs.items() if value}


def _storyboard_files(job_id: str) -> tuple[Path, Path]:
    job = _job_snapshot(job_id)
    storyboard = Path(str((job or {}).get("outputs", {}).get("storyboard", ""))).resolve()
    output = Path(str((job or {}).get("output_dir", ""))).resolve()
    if not job or not storyboard.is_file() or not storyboard.is_relative_to(output):
        raise ValueError("Phiên này chưa có storyboard hợp lệ")
    return storyboard, storyboard.parent / "storyboard.overrides.json"


def _read_storyboard_editor(job_id: str) -> dict:
    storyboard_path, overrides_path = _storyboard_files(job_id)
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    try:
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        overrides = {"version": 1, "scenes": {}}
    scene_overrides = overrides.get("scenes", {})
    try:
        candidates = json.loads((storyboard_path.parent / "scene-candidates.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        candidates = []
    candidate_map = {
        str(item.get("scene", {}).get("sceneId", "")): item.get("scene", {})
        for item in candidates if isinstance(item, dict)
    }
    scenes = []
    for scene in storyboard.get("scenes", []):
        merged = dict(scene)
        source_scene = candidate_map.get(str(scene.get("scene_id", "")), {})
        merged["evidence"] = source_scene.get("evidence", [])
        merged["characters"] = source_scene.get("characters", [])
        merged["narrative_meaning"] = [
            source_scene.get("authorialIntent", ""),
            *(source_scene.get("narrativeSubtext", []) or []),
        ]
        current = scene_overrides.get(str(scene.get("scene_id", "")), {})
        for key in ("location", "action", "prompts", "enabled", "locked", "tone", "camera", "order", "reference_images", "render_status", "render_error"):
            if key in current:
                merged[key] = current[key]
        index = int(scene.get("index", 0) or 0)
        merged["image_urls"] = {
            platform: f"/api/jobs/{job_id}/scenes/{index}/image/{platform}?v={int(time.time())}"
            for platform in scene.get("images", {})
        }
        scenes.append(merged)
    scenes.sort(key=lambda item: (int(item.get("order", item.get("index", 0))), int(item.get("index", 0))))
    return {
        "version": 1,
        "job_id": job_id,
        "storyboard": str(storyboard_path),
        "platform": storyboard.get("platform"),
        "quality": storyboard.get("quality"),
        "scenes": scenes,
    }


def _write_scene_override(job_id: str, payload: dict) -> dict:
    storyboard_path, overrides_path = _storyboard_files(job_id)
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    scene_id = str(payload.get("scene_id", "")).strip()
    if scene_id not in {str(item.get("scene_id", "")) for item in storyboard.get("scenes", [])}:
        raise ValueError("Scene không tồn tại trong storyboard gốc")
    try:
        document = json.loads(overrides_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        document = {"version": 1, "scenes": {}}
    current = dict(document.setdefault("scenes", {}).get(scene_id, {}))
    for key in ("location", "action", "tone", "camera", "render_status", "render_error"):
        if key in payload:
            value = str(payload[key]).strip()
            if len(value) > 2000:
                raise ValueError(f"{key} vượt giới hạn")
            current[key] = value
    if "prompts" in payload:
        prompts = payload["prompts"]
        if not isinstance(prompts, dict):
            raise ValueError("prompts phải là object")
        merged_prompts = dict(current.get("prompts", {}))
        merged_prompts.update({
            key: str(value).strip()
            for key, value in prompts.items()
            if key in {"youtube", "tiktok"} and 20 <= len(str(value).strip()) <= 12000
        })
        current["prompts"] = merged_prompts
    for key in ("enabled", "locked"):
        if key in payload:
            current[key] = bool(payload[key])
    if "order" in payload:
        current["order"] = max(1, int(payload["order"]))
    if "reference_images" in payload:
        references = payload["reference_images"]
        if not isinstance(references, list) or len(references) > 3:
            raise ValueError("Tối đa 3 ảnh reference")
        checked = []
        for item in references:
            reference = Path(str(item)).resolve()
            if not reference.is_file() or reference.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".webp"}:
                raise ValueError(f"Reference không hợp lệ: {reference}")
            checked.append(str(reference))
        current["reference_images"] = checked
    current["updated_at"] = time.time()
    document["scenes"][scene_id] = current
    document["updated_at"] = time.time()
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = overrides_path.with_suffix(".json.tmp")
    with PERSIST_LOCK:
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, overrides_path)
    return current


def _rerender_scene(job_id: str, scene_id: str, platform_name: str) -> None:
    try:
        storyboard_path, overrides_path = _storyboard_files(job_id)
        _write_scene_override(job_id, {"scene_id": scene_id, "render_status": "running"})
        command = [
            shutil.which("node") or "node",
            str(ROOT / "poster-generator" / "dist" / "scene-rerender.js"),
            "--storyboard", str(storyboard_path),
            "--overrides", str(overrides_path),
            "--scene", scene_id,
            "--platform", platform_name,
        ]
        result = subprocess.run(
            command, cwd=ROOT / "poster-generator", capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=None,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout or "Render thất bại").strip()[-2000:])
        _write_scene_override(job_id, {"scene_id": scene_id, "render_status": "completed", "render_error": ""})
    except Exception as exc:
        try:
            _write_scene_override(job_id, {"scene_id": scene_id, "render_status": "failed", "render_error": str(exc)})
        except Exception:
            pass


def _build_command(job_id: str, payload: dict) -> tuple[list[str], Path]:
    job_dir = JOB_ROOT / "jobs" / job_id
    inputs = job_dir / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)

    context_dir = str(payload.get("context_dir", "")).strip()
    chapter_text = str(payload.get("chapter_text", ""))
    chapter_number = max(1, int(payload.get("chapter_number", 1)))

    print(f"[web] job={job_id} context_dir={context_dir!r} chapter_text_len={len(chapter_text)}")

    if not context_dir:
        raise ValueError("Thiếu thư mục .md (context_dir). Hãy chọn thư mục .md trên UI.")

    context_path = Path(context_dir)
    if not context_path.is_dir():
        raise ValueError(f"Thư mục .md không tồn tại: {context_dir}")
    if context_path.name.casefold() != ".md":
        raise ValueError(f"Phải chọn đúng thư mục .md: {context_dir}")
    if not chapter_text.strip():
        raise ValueError("File chương (.txt) đang rỗng")

    from optimize_context import optimize_context
    optimized = optimize_context(context_dir, chapter_number, chapter_text)

    master = inputs / "master.md"
    rules = inputs / "request.md"
    chapter = inputs / "chapter.txt"

    master.write_text(optimized.get("master", ""), encoding="utf-8")
    rules.write_text(optimized.get("request", ""), encoding="utf-8")
    chapter.write_text(chapter_text, encoding="utf-8")

    if not all(path.stat().st_size for path in (master, rules, chapter)):
        missing = [p.name for p in (master, rules, chapter) if not p.stat().st_size]
        raise ValueError(f"File rỗng sau optimize: {', '.join(missing)}. Kiểm tra thư mục .md có đủ master.md/request.md chưa.")

    for key in ["characters", "glossary", "timeline", "chapter_summaries"]:
        if optimized.get(key):
            (inputs / f"{key}.md").write_text(optimized[key], encoding="utf-8")

    (inputs / "raw_context").mkdir(exist_ok=True)
    for md_file in context_path.iterdir():
        if not md_file.is_file() or md_file.suffix.casefold() != ".md":
            continue
        (inputs / "raw_context" / md_file.name).write_text(
            md_file.read_text(encoding="utf-8"), encoding="utf-8"
        )

    raw_output = str(payload.get("output", "")).strip()
    output = Path(raw_output).expanduser().resolve() if raw_output else (ROOT / "output" / f"web-{job_id}")
    product_type = str(
        payload.get(
            "product_type",
            "video" if payload.get("video", True) else "audio",
        )
    )
    if product_type not in ("audio", "video"):
        raise ValueError("Loại sản phẩm phải là audio hoặc video")
    if product_type == "audio":
        video = False
        mp3 = True
        audio_srt = bool(payload.get("audio_srt", payload.get("cc", False)))
        image_output = (
            str(payload.get("audio_image_scope", "poster"))
            if payload.get("audio_images") else "none"
        )
        subtitle_mode = "file" if audio_srt else "none"
        keep_srt = audio_srt
    else:
        video = True
        mp3 = bool(payload.get("video_mp3", payload.get("mp3", True)))
        image_output = "scenes"
        requested_video_mode = str(
            payload.get("video_subtitle_mode")
            or ("soft" if payload.get("cc") else "none")
        )
        keep_srt = bool(payload.get("video_srt", payload.get("cc", False)))
        subtitle_mode = (
            "file" if requested_video_mode == "none" and keep_srt
            else requested_video_mode
        )
    if image_output not in ("none", "poster", "scenes"):
        raise ValueError("Tuỳ chọn xuất ảnh không hợp lệ")
    if subtitle_mode not in ("none", "file", "soft", "burn"):
        raise ValueError("Tuỳ chọn phụ đề không hợp lệ")

    # Parallelism is an automatic decision, not a dead UI knob.  The safety
    # cap is computed from VRAM and Ollama may lower it further; a 4 GB GTX
    # 1650 correctly resolves to one worker, while larger cards can use 2–6.
    auto_parallel = bool(payload.get("auto_parallel", False))
    parallel_workers = 1
    render_mode = "sequential"
    if auto_parallel:
        recommendation = _recommend_parallel_workers({
            "device": "gpu",
            "image_provider": "comfyui",
            "ai_model": payload.get("ai_model", ""),
        })
        parallel_workers = int(recommendation["workers"])
        render_mode = "parallel" if parallel_workers > 1 else "sequential"
        payload["parallel_recommendation"] = recommendation

    command = [
        _venv_python(), "-u", str(ROOT / "audiobook.py"), "build",
        "--input", str(master), str(rules), str(chapter),
        "--output", str(output),
        "--story", str(payload.get("story", "") or "audiobook"),
        "--chapter-number", str(max(1, int(payload.get("chapter_number", 1)))),
        "--audiobook", str(payload.get("audiobook", "medium")),
        "--platform", str(payload.get("platform", "youtube")),
        "--device", "gpu",
        "--render-mode", render_mode,
        "--parallel-workers", str(parallel_workers),
        "--tts-provider", str(payload.get("tts_provider", "vieneu")),
        "--max-segment-length", str(int(payload.get("max_segment_length", 500))),
        "--character-state-dir", str(context_path.parent),
        "--image-output", image_output,
        "--subtitle-mode", subtitle_mode,
        "--keep-srt" if keep_srt else "--no-keep-srt",
    ]
    optional_values = (
        ("title", "--title"),
        ("ai_model", "--ai-model"),
        # ComfyUI GPU low-VRAM is the supported local image backend.
        ("voice", "--voice"),
        ("temperature", "--temperature"),
        ("top_k", "--top-k"),
        ("top_p", "--top-p"),
        ("repetition_penalty", "--repetition-penalty"),
        ("pitch_ratio", "--pitch-ratio"),
        ("tempo_ratio", "--tempo-ratio"),
        ("model_profile", "--model-profile"),
    )
    for key, flag in optional_values:
        value = payload.get(key)
        if value not in (None, ""):
            command.extend([flag, str(value)])
    exact_images = payload.get("images")
    if exact_images not in (None, ""):
        profile = str(payload.get("model_profile", "medium"))
        limits = {"low": (3, 60), "medium": (60, 200), "high": (100, 400)}
        if profile == "max":
            raise ValueError("Profile max yêu cầu AI tự tính số cảnh")
        if profile not in limits:
            raise ValueError(f"Profile ảnh không hợp lệ: {profile}")
        count = int(exact_images)
        lower, upper = limits[profile]
        if count < lower or count > upper:
            raise ValueError(f"Số cảnh profile {profile} phải trong khoảng {lower}-{upper}")
        command.extend(["--images", str(count)])
    weights = payload.get("scene_weights")
    if isinstance(weights, dict):
        command.extend(["--scene-weights", json.dumps(weights, separators=(",", ":"))])
    if payload.get("ai"):
        command.append("--ai")
    if payload.get("overnight"):
        command.append("-overnight")
    if not video:
        command.append("--no-video")
    if not mp3:
        command.append("--no-mp3")
    if payload.get("force"):
        command.append("--force")
    return command, output


def _run_job(job_id: str, payload: dict) -> None:
    try:
        command, output = _build_command(job_id, payload)
        _update_job(job_id, output_dir=str(output), command=command)
        completed_outputs = _manifest_outputs(output)
        if completed_outputs:
            _update_job(
                job_id, status="completed", stage="Hoàn thành",
                message="Đã phục hồi kết quả hoàn chỉnh từ đĩa.",
                percent=100, outputs=completed_outputs,
            )
            return
        with GPU_LOCK:
            if _job_snapshot(job_id).get("cancel_requested"):
                _update_job(job_id, status="cancelled", stage="Đã hủy", message="Job đã bị hủy")
                return
            _update_job(job_id, status="running", stage="Khởi tạo", message="Đang bắt đầu pipeline", percent=1, started_at=time.time())
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
            with JOBS_LOCK:
                PROCESSES[job_id] = process
            progress = 1.0
            logs: list[str] = []
            scene_started_at = 0.0
            scene_completed = 0
            scene_total = 0
            tts_started_at = 0.0
            video_started_at = 0.0
            eta = 0.0
            assert process.stdout is not None
            for raw_line in process.stdout:
                line = raw_line.rstrip()
                if not line:
                    continue
                logs.append(line)
                logs = logs[-500:]
                progress = _parse_progress(line, progress)
                now = time.time()
                if line.startswith("@@progress "):
                    try:
                        event = json.loads(line.removeprefix("@@progress "))
                        display_line = str(event.get("message", line))
                        event_completed = int(event.get("completed", 0) or 0)
                        event_total = int(event.get("total", 0) or 0)
                        event_elapsed = float(event.get("elapsed", 0) or 0)
                        if event_completed and event_total and event_elapsed:
                            eta = event_elapsed / event_completed * (event_total - event_completed)
                        line = display_line
                    except (TypeError, ValueError, json.JSONDecodeError):
                        pass
                tts = re.search(r"Segment\s+(\d+)/(\d+)", line)
                if tts:
                    current, total = map(int, tts.groups())
                    if not tts_started_at:
                        tts_started_at = now
                    completed = max(0, current - 1)
                    eta = _remaining_eta(tts_started_at, completed, total, now)
                scene = re.search(r"\u0110ang sinh c\u1ea3nh\s+(\d+)/(\d+)", line, re.IGNORECASE)
                if scene:
                    _, scene_total = map(int, scene.groups())
                    if not scene_started_at:
                        scene_started_at = now
                scene_done = re.search(r"\u0110\u00e3 sinh c\u1ea3nh\s+(\d+)/(\d+)", line, re.IGNORECASE)
                if scene_done:
                    scene_completed, scene_total = map(int, scene_done.groups())
                    eta = _remaining_eta(
                        scene_started_at, scene_completed, scene_total, now
                    )
                if "[2/3]" in line:
                    eta = 0
                if "[3/3]" in line:
                    eta = 0
                    video_started_at = now
                video = re.search(r"\[video\s+([\d.]+)%\]", line)
                if video:
                    video_percent = float(video.group(1))
                    if not video_started_at:
                        video_started_at = now
                    eta = _remaining_eta(
                        video_started_at, video_percent, 100.0, now
                    )
                _update_job(
                    job_id, percent=round(progress, 1), stage="\u0110ang ch\u1ea1y",
                    message=line, logs=logs, eta_seconds=eta,
                )
            return_code = process.wait()
            cancelled = bool(_job_snapshot(job_id).get("cancel_requested"))
            if cancelled:
                _update_job(job_id, status="cancelled", stage="Đã hủy", message="Đã dừng theo yêu cầu")
            elif return_code != 0:
                _update_job(
                    job_id, status="failed", stage="Lỗi",
                    message=logs[-1] if logs else f"Process kết thúc với mã {return_code}",
                )
            else:
                outputs = _manifest_outputs(output)
                _update_job(
                    job_id, status="completed", stage="Hoàn thành", message="Audiobook đã sẵn sàng",
                    percent=100, outputs=outputs,
                )
    except Exception as exc:
        _update_job(job_id, status="failed", stage="Lỗi", message=str(exc))
    finally:
        with JOBS_LOCK:
            PROCESSES.pop(job_id, None)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "SpalingAudiobook/0.0.2"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/config":
            ctx_dir = ROOT / ".md"
            context_files = {}
            if ctx_dir.is_dir():
                for f in ["master.md", "request.md", "characters.md", "glossary.md", "timeline.md", "chapter_summaries.md"]:
                    context_files[f] = (ctx_dir / f).is_file()
            self._json({
                "models": _ollama_models(),
                "tts": _default_tts_settings(),
                "voices": _vieneu_voices(),
                "backends": list(BACKEND_STATUS),
                "default_output": str((ROOT / "output").resolve()),
                "context_files": context_files,
                "system": {
                    "ffmpeg": bool(shutil.which("ffmpeg")),
                    "node": bool(shutil.which("node")),
                    "gpu": bool(shutil.which("nvidia-smi")),
                },
            })
            return
        if path == "/api/jobs/active":
            self._json({"job": _active_job_snapshot()})
            return
        if path == "/api/jobs":
            with JOBS_LOCK:
                jobs = [
                    {
                        key: job.get(key)
                        for key in (
                            "id", "status", "stage", "message", "percent",
                            "created_at", "updated_at", "output_dir",
                        )
                    }
                    for job in JOBS.values()
                ]
            jobs.sort(key=lambda job: float(job.get("created_at", 0) or 0), reverse=True)
            self._json({"jobs": jobs})
            return
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})", path)
        if match:
            job = _job_snapshot(match.group(1))
            self._json(job or {"error": "Không tìm thấy job"}, HTTPStatus.OK if job else HTTPStatus.NOT_FOUND)
            return
        file_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/files/([a-z0-9_]+)", path)
        if file_match:
            self._serve_output(file_match.group(1), file_match.group(2))
            return
        storyboard_match = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/storyboard", path)
        if storyboard_match:
            try:
                self._json(_read_storyboard_editor(storyboard_match.group(1)))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        scene_image = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/scenes/(\d+)/image/(youtube|tiktok)", path)
        if scene_image:
            try:
                data = _read_storyboard_editor(scene_image.group(1))
                scene = next(item for item in data["scenes"] if int(item.get("index", 0)) == int(scene_image.group(2)))
                storyboard_path, _ = _storyboard_files(scene_image.group(1))
                image_path = Path(str(scene.get("images", {}).get(scene_image.group(3), ""))).resolve()
                if not image_path.is_file() or not image_path.is_relative_to(storyboard_path.parent):
                    raise ValueError("Ảnh scene không hợp lệ")
                self._serve_path(image_path)
            except (OSError, ValueError, StopIteration) as exc:
                self._json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
            return
        self._static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        cancel = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/cancel", path)
        if cancel:
            self._cancel(cancel.group(1))
            return
        resume = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/resume", path)
        if resume:
            self._resume(resume.group(1))
            return
        storyboard = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/storyboard", path)
        if storyboard:
            try:
                payload = self._read_json()
                current = _write_scene_override(storyboard.group(1), payload)
                self._json({"ok": True, "override": current})
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        rerender = re.fullmatch(r"/api/jobs/([a-f0-9]{12})/storyboard/rerender", path)
        if rerender:
            try:
                payload = self._read_json()
                scene_id = str(payload.get("scene_id", "")).strip()
                platform_name = str(payload.get("platform", "youtube")).strip()
                if platform_name not in {"youtube", "tiktok"}:
                    raise ValueError("Platform không hợp lệ")
                _write_scene_override(rerender.group(1), {"scene_id": scene_id, "render_status": "queued", "render_error": ""})
                threading.Thread(
                    target=_rerender_scene,
                    args=(rerender.group(1), scene_id, platform_name),
                    daemon=True,
                ).start()
                self._json({"ok": True, "status": "queued"}, HTTPStatus.ACCEPTED)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/select-output":
            try:
                payload = self._read_json()
                self._json({
                    "path": _select_output_directory(str(payload.get("initial", "")))
                })
            except (OSError, RuntimeError, ValueError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if path == "/api/read-context-dir":
            try:
                payload = self._read_json()
                dir_path = Path(payload.get("dir", ""))
                if not dir_path.is_dir():
                    raise ValueError(f"Thư mục không tồn tại: {dir_path}")
                files = {}
                for f in dir_path.glob("*.md"):
                    files[f.name] = f.read_text(encoding="utf-8")
                self._json({"files": files, "count": len(files)})
            except (OSError, ValueError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/recommend-workers":
            try:
                self._json(_recommend_parallel_workers(self._read_json()))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/jobs":
            try:
                payload = self._read_json()
                job_id = uuid.uuid4().hex[:12]
                with JOBS_LOCK:
                    JOBS[job_id] = {
                        "schema_version": 1, "id": job_id, "status": "queued", "stage": "Hàng đợi", "message": "Đang chờ tài nguyên",
                        "percent": 0, "logs": [], "outputs": {}, "cancel_requested": False, "output_dir": "",
                        "started_at": 0, "created_at": time.time(), "updated_at": time.time(), "request": payload,
                    }
                _persist_job(job_id)
                threading.Thread(target=_run_job, args=(job_id, payload), daemon=True).start()
                self._json({"job_id": job_id}, HTTPStatus.ACCEPTED)
            except (ValueError, OSError, json.JSONDecodeError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._json({"error": "Không tìm thấy endpoint"}, HTTPStatus.NOT_FOUND)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[web] {self.address_string()} - {fmt % args}")

    def _cancel(self, job_id: str) -> None:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            process = PROCESSES.get(job_id)
            if job:
                job["cancel_requested"] = True
                job["message"] = "Đang dừng sau tác vụ hiện tại"
        if not job:
            self._json({"error": "Không tìm thấy job"}, HTTPStatus.NOT_FOUND)
            return
        if process and process.poll() is None:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                process.terminate()
        self._json({"ok": True})

    def _resume(self, job_id: str) -> None:
        job = _job_snapshot(job_id)
        if not job:
            self._json({"error": "Không tìm thấy job"}, HTTPStatus.NOT_FOUND)
            return
        if job.get("status") in {"queued", "running"}:
            self._json({"ok": True, "job_id": job_id})
            return
        payload = dict(job.get("request", {}))
        if not payload:
            self._json({"error": "Phiên không còn cấu hình để tiếp tục"}, HTTPStatus.BAD_REQUEST)
            return
        _update_job(
            job_id, status="queued", stage="Khôi phục",
            message="Đang tiếp tục từ checkpoint", cancel_requested=False,
        )
        threading.Thread(target=_run_job, args=(job_id, payload), daemon=True).start()
        self._json({"ok": True, "job_id": job_id}, HTTPStatus.ACCEPTED)

    def _serve_output(self, job_id: str, key: str) -> None:
        job = _job_snapshot(job_id)
        if not job or key not in job.get("outputs", {}):
            self._json({"error": "Không tìm thấy output"}, HTTPStatus.NOT_FOUND)
            return
        path = Path(job["outputs"][key]).resolve()
        output_dir = Path(job["output_dir"]).resolve()
        if not path.is_file() or not path.is_relative_to(output_dir):
            self._json({"error": "Output không hợp lệ"}, HTTPStatus.NOT_FOUND)
            return
        self._serve_path(path)

    def _serve_path(self, path: Path) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.end_headers()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                self.wfile.write(chunk)

    def _static(self, url_path: str) -> None:
        relative = "index.html" if url_path in ("", "/") else unquote(url_path.lstrip("/"))
        target = (STATIC_DIR / relative).resolve()
        if not target.is_relative_to(STATIC_DIR.resolve()) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 80 * 1024 * 1024:
            raise ValueError("Dữ liệu rỗng hoặc vượt 80 MB")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = True) -> None:
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    resumable = _load_persisted_jobs()
    server = ThreadingHTTPServer((host, port), AppHandler)
    url = f"http://{host}:{port}"
    print(f"Spaling Audiobook: {url}")
    print("Nhấn Ctrl+C để dừng.")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    for job_id, payload in resumable:
        threading.Thread(target=_run_job, args=(job_id, payload), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng web app.")
    finally:
        server.server_close()
