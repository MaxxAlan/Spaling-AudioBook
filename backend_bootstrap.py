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


def configure_local_paths(root: Path | None = None) -> Path:
    """Keep models and caches on the app drive instead of the C: user profile.

    Forces process-wide env vars so Ollama models, HuggingFace downloads and
    pip caches land inside ``<root>/.data`` no matter where the user has
    pointed HF_HOME/PIP_CACHE_DIR globally (e.g. another project on drive D).
    Also prepends the portable runtimes from ``<root>/.runtime`` to PATH so
    the app uses its own Python/Node/FFmpeg/Git/Ollama instead of any system
    installs. Values are relative to the app root, so they follow the app if
    the folder is moved. Only affects this process and its children.
    """
    app_root = (root or ROOT).resolve()
    data_dir = app_root / ".data"
    runtime_dir = app_root / ".runtime"
    os.environ["OLLAMA_MODELS"] = str(data_dir / "ollama" / "models")
    os.environ["HF_HOME"] = str(data_dir / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(data_dir / "huggingface" / "hub")
    os.environ["PIP_CACHE_DIR"] = str(data_dir / "pip")
    os.environ["PNPM_CONFIG_STORE_DIR"] = str(data_dir / "pnpm-store")
    os.environ["NPM_CONFIG_CACHE"] = str(data_dir / "npm-cache")
    # Run the bundled Ollama on its own port so it never collides with an
    # Ollama the user already installed (default port 11434 auto-starts on login).
    os.environ["OLLAMA_HOST"] = "127.0.0.1:11435"
    os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11435"
    runtime_paths = [
        str(runtime_dir / "python"),
        str(runtime_dir / "python" / "Scripts"),
        str(runtime_dir / "node"),
        str(runtime_dir / "ffmpeg" / "bin"),
        str(runtime_dir / "git" / "cmd"),
        str(runtime_dir / "ollama"),
        str(runtime_dir / "pnpm"),
    ]
    os.environ["PATH"] = os.pathsep.join(runtime_paths + [os.environ.get("PATH", "")])
    _normalize_poster_env(app_root)
    return data_dir


def _normalize_poster_env(app_root: Path) -> None:
    """Rebind absolute paths in ``poster-generator/.env`` to the current app root.

    install.bat writes COMFYUI_PATH/COMFYUI_WORKFLOW/COMFYUI_PYTHON with the
    drive letter present at install time. If the app is moved to another drive
    (e.g. the USB is mounted as F: on another PC), those stale E:\\ paths would
    break the poster generator. Rewrite them so they follow the app. Values
    that already point at the current root are left untouched, so user tweaks
    to other keys survive.
    """
    env_path = app_root / "poster-generator" / ".env"
    if not env_path.is_file():
        return
    replacements = {
        "COMFYUI_PATH": str(app_root / "ComfyUI"),
        "COMFYUI_WORKFLOW": str(app_root / "poster-generator" / "workflows" / "sd15_basic.json"),
        "COMFYUI_PYTHON": str(app_root / ".runtime" / "python" / "python.exe"),
    }
    lines = env_path.read_text(encoding="utf-8-sig").splitlines()
    changed = False
    for i, line in enumerate(lines):
        key, sep, value = line.partition("=")
        if not sep or not key.strip() or key.strip() not in replacements:
            continue
        try:
            current = str(Path(value.strip().strip('"')).resolve())
        except OSError:
            current = ""
        target = replacements[key.strip()]
        if current and current == str(Path(target).resolve()):
            continue
        lines[i] = f"{key.strip()}={target}"
        changed = True
    if changed:
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


configure_local_paths()


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
