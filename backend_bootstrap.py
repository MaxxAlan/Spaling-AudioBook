"""Health-check and start local services required by the unified web app."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import IO
from urllib import error, request
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent


@dataclass
class BackendStatus:
    name: str
    ready: bool
    message: str
    started: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ready": self.ready,
            "message": self.message,
            "started": self.started,
        }


@dataclass
class BackendSession:
    statuses: list[BackendStatus] = field(default_factory=list)
    processes: list[subprocess.Popen[bytes]] = field(default_factory=list)
    log_handles: list[IO[bytes]] = field(default_factory=list)

    def close(self) -> None:
        """Stop only backend processes started by this web session."""
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
        for handle in self.log_handles:
            handle.close()

    def as_dicts(self) -> list[dict[str, object]]:
        return [status.as_dict() for status in self.statuses]


def _read_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _http_ready(url: str, timeout: float = 1.5) -> bool:
    try:
        with request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (OSError, error.URLError, ValueError):
        return False


def _wait_http(
    url: str, process: subprocess.Popen[bytes], timeout: int
) -> tuple[bool, str]:
    deadline = time.monotonic() + max(1, timeout)
    while time.monotonic() < deadline:
        if _http_ready(url):
            return True, ""
        code = process.poll()
        if code is not None:
            return False, f"tiến trình thoát với mã {code}"
        time.sleep(1)
    return False, f"quá thời gian chờ {timeout} giây"


def _tool_status(name: str, *, required: bool = True) -> BackendStatus:
    executable = shutil.which(f"{name}.cmd") or shutil.which(name)
    if executable:
        return BackendStatus(name, True, executable)
    if name == "pnpm":
        corepack = shutil.which("corepack.cmd") or shutil.which("corepack")
        if corepack:
            return BackendStatus(
                name, True, f"{corepack} pnpm (dự phòng qua Corepack)"
            )
    level = "bắt buộc" if required else "tùy chọn"
    return BackendStatus(name, False, f"Không tìm thấy trong PATH ({level})")


def _ensure_ollama(timeout: int) -> BackendStatus:
    audio_tool = str(ROOT / "audio-comic")
    if audio_tool not in sys.path:
        sys.path.insert(0, audio_tool)
    try:
        from ai.ollama_helper import OllamaNarrationHelper

        helper = OllamaNarrationHelper()
        was_ready = helper.server_ready()
        ready, message = helper.ensure_server(startup_timeout=min(timeout, 300))
        if ready:
            models = helper.list_models()
            suffix = f"; {len(models)} model sẵn sàng" if models else "; chưa có model"
            return BackendStatus("Ollama", True, message + suffix, not was_ready)
        return BackendStatus("Ollama", False, message)
    except Exception as exc:
        return BackendStatus("Ollama", False, f"Không kiểm tra được Ollama: {exc}")


def _ensure_comfyui(timeout: int, session: BackendSession) -> BackendStatus:
    env = _read_env(ROOT / "poster-generator" / ".env")
    if env.get("IMAGE_AI_PROVIDER", "").lower() != "comfyui":
        return BackendStatus(
            "ComfyUI", True, "Không cần khởi động (IMAGE_AI_PROVIDER không phải comfyui)"
        )
    base_url = env.get("COMFYUI_BASE_URL", "http://127.0.0.1:8188").rstrip("/")
    health_url = f"{base_url}/system_stats"
    if _http_ready(health_url):
        return BackendStatus("ComfyUI", True, f"Đang chạy tại {base_url}")

    comfy_path = Path(env.get("COMFYUI_PATH", "")).expanduser()
    main_script = comfy_path / "main.py"
    workflow = Path(env.get("COMFYUI_WORKFLOW", "")).expanduser()
    if not main_script.is_file():
        return BackendStatus("ComfyUI", False, f"Không tìm thấy {main_script}")
    if not workflow.is_file():
        return BackendStatus("ComfyUI", False, f"Không tìm thấy workflow {workflow}")

    parsed = urlparse(base_url)
    python_command = env.get("COMFYUI_PYTHON", "python")
    executable = shutil.which(python_command) or python_command
    command = [
        executable,
        "main.py",
        "--listen",
        parsed.hostname or "127.0.0.1",
        "--port",
        str(parsed.port or 8188),
        "--disable-auto-launch",
        "--lowvram",
    ]
    log_dir = ROOT / ".audiobook-web" / "backends"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_handle = (log_dir / "comfyui.log").open("ab")
    process_kwargs: dict[str, object] = {
        "cwd": comfy_path,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        process_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        process_kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **process_kwargs)
    except OSError as exc:
        log_handle.close()
        return BackendStatus("ComfyUI", False, f"Không thể khởi động: {exc}")
    session.processes.append(process)
    session.log_handles.append(log_handle)
    ready, reason = _wait_http(health_url, process, timeout)
    if ready:
        return BackendStatus(
            "ComfyUI", True, f"Đã tự khởi động tại {base_url} (low VRAM)", True
        )
    return BackendStatus(
        "ComfyUI",
        False,
        f"Khởi động thất bại: {reason}. Xem {log_dir / 'comfyui.log'}",
        True,
    )


def bootstrap_backends(timeout: int = 3000) -> BackendSession:
    session = BackendSession()
    session.statuses.extend(
        [
            _tool_status("ffmpeg"),
            _tool_status("ffprobe"),
            _tool_status("node"),
            _tool_status("pnpm"),
        ]
    )
    session.statuses.append(_ensure_ollama(timeout))
    session.statuses.append(_ensure_comfyui(timeout, session))
    return session


def print_backend_report(session: BackendSession) -> None:
    print("\nKiểm tra backend trước khi mở giao diện:")
    for status in session.statuses:
        marker = "OK" if status.ready else "CẢNH BÁO"
        print(f"- [{marker}] {status.name}: {status.message}")
    print()
