#!/usr/bin/env python3
"""Portable installer for Spaling Audiobook.

Stdlib-only on purpose: this file is the installer, so it must run before any
project dependency exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / ".runtime"
DATA = ROOT / ".data"
DOWNLOADS = DATA / "downloads"
POSTER_DIR = ROOT / "poster-generator"
COMFYUI_DIR = ROOT / "ComfyUI"

OLLAMA_HOST = "127.0.0.1:11435"
COMFYUI_COMMIT = "806e092ed42772e4ce7abf44c97c50021cc4bd10"
IPADAPTER_COMMIT = "a0f451a5113cf9becb0847b92884cb10cbdec0ef"
DREAMSHAPER_SHA256 = "879DB523C30D3B9017143D56705015E15A2CB5628762C11D086FED9538ABD7FD"
REALISTIC_VISION_SHA256 = "C48BFD159CD7A6507B128685E963C398FA72399CEFAFAF603781DF50CE836CC7"

INSTALL_STEPS = [
    "Kiem tra thiet bi",
    "Cai portable runtime",
    "Cai Python dependencies",
    "Cai pnpm",
    "Cai ComfyUI va image models",
    "Cai Ollama text models",
    "Cai Node dependencies va build",
    "Doctor check",
    "Ghi manifest",
]


@dataclass(frozen=True)
class RuntimeZip:
    name: str
    url: str
    target: Path
    marker: Path
    strip_single_dir: bool = False


class InstallerUI:
    def __init__(self, steps: list[str]) -> None:
        self.steps = steps
        self.status = ["todo"] * len(steps)
        self.current = 0
        self.logs: list[str] = []
        self.download_label = ""
        self.download_current = 0
        self.download_total = 0
        self.interactive = sys.stdout.isatty()

    def step(self, index: int) -> None:
        self.current = index
        for i in range(index):
            if self.status[i] == "todo":
                self.status[i] = "done"
        if 0 <= index < len(self.status):
            self.status[index] = "running"
        self.render()

    def done(self, index: int) -> None:
        if 0 <= index < len(self.status):
            self.status[index] = "done"
        self.render()

    def skip(self, index: int) -> None:
        if 0 <= index < len(self.status):
            self.status[index] = "skip"
        self.render()

    def fail(self) -> None:
        if 0 <= self.current < len(self.status):
            self.status[self.current] = "fail"
        self.render()

    def log(self, message: str) -> None:
        self.logs.append(message)
        self.logs = self.logs[-9:]
        self.render()

    def download(self, label: str, current: int, total: int) -> None:
        self.download_label = label
        self.download_current = current
        self.download_total = total
        self.render()

    def clear_download(self) -> None:
        self.download_label = ""
        self.download_current = 0
        self.download_total = 0
        self.render()

    def render(self) -> None:
        if not self.interactive:
            return
        print("\x1b[2J\x1b[H", end="")
        print("SPALING AUDIOBOOK INSTALLER")
        print("=" * 72)
        print("LOGS")
        if self.logs:
            for line in self.logs:
                print(f"  {line[:120]}")
        else:
            print("  Dang chuan bi...")
        print()
        print("TIEN DO")
        for i, step in enumerate(self.steps):
            marker = {
                "todo": ".",
                "running": ">",
                "done": "x",
                "skip": "-",
                "fail": "!",
            }[self.status[i]]
            print(f"  [{marker}] {step}")
        print()
        print("DOWNLOAD")
        print("  " + self.progress_line())
        sys.stdout.flush()

    def progress_line(self) -> str:
        if not self.download_label:
            return "[chua co file dang tai]"
        width = 70
        total = max(self.download_total, 0)
        current = max(self.download_current, 0)
        percent = 0 if total <= 0 else min(100, int(current * 100 / total))
        filled = 0 if total <= 0 else min(width, int(width * current / total))
        if filled <= 0:
            bar = ">" + (" " * (width - 1))
        elif filled >= width:
            bar = "=" * width
        else:
            bar = ("=" * (filled - 1)) + ">" + (" " * (width - filled))
        size = format_bytes(total) if total else "unknown"
        return f"{self.download_label} ({size}) [{bar}] {percent:3d}%"


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(value)
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    if unit == "B":
        return f"{int(size)} {unit}"
    return f"{size:.1f} {unit}"


UI = InstallerUI(INSTALL_STEPS)


WINDOWS_X64_RUNTIMES = [
    RuntimeZip("Node.js", "https://nodejs.org/dist/v22.14.0/node-v22.14.0-win-x64.zip", RUNTIME / "node", RUNTIME / "node" / "node.exe", True),
    RuntimeZip("FFmpeg", "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", RUNTIME / "ffmpeg", RUNTIME / "ffmpeg" / "bin" / "ffmpeg.exe", True),
    RuntimeZip("Git", "https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.3/MinGit-2.55.0.3-64-bit.zip", RUNTIME / "git", RUNTIME / "git" / "cmd" / "git.exe"),
    RuntimeZip("Ollama", "https://github.com/ollama/ollama/releases/download/v0.6.6/ollama-windows-amd64.zip", RUNTIME / "ollama", RUNTIME / "ollama" / "ollama.exe"),
]


def log(message: str) -> None:
    UI.log(message)
    if not UI.interactive:
        print(message, flush=True)


def fail(message: str) -> None:
    UI.fail()
    raise SystemExit(f"[LOI] {message}")


def run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    log("+ " + " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, env=env or os.environ.copy(), check=True)


def output(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()


def which(name: str) -> str | None:
    candidates = [name]
    if os.name == "nt" and not name.lower().endswith((".exe", ".cmd", ".bat")):
        candidates = [f"{name}.cmd", f"{name}.exe", name]
    for candidate in candidates:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def configure_env() -> None:
    DATA.mkdir(exist_ok=True)
    runtime_paths = [
        RUNTIME / "python",
        RUNTIME / "python" / "Scripts",
        RUNTIME / "node",
        RUNTIME / "ffmpeg" / "bin",
        RUNTIME / "git" / "cmd",
        RUNTIME / "ollama",
        RUNTIME / "pnpm",
    ]
    os.environ["PATH"] = os.pathsep.join(str(p) for p in runtime_paths) + os.pathsep + os.environ.get("PATH", "")
    os.environ["OLLAMA_MODELS"] = str(DATA / "ollama" / "models")
    os.environ["HF_HOME"] = str(DATA / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(DATA / "huggingface" / "hub")
    os.environ["PIP_CACHE_DIR"] = str(DATA / "pip")
    os.environ["PNPM_CONFIG_STORE_DIR"] = str(DATA / "pnpm-store")
    os.environ["NPM_CONFIG_CACHE"] = str(DATA / "npm-cache")
    os.environ["OLLAMA_HOST"] = OLLAMA_HOST
    os.environ["OLLAMA_BASE_URL"] = f"http://{OLLAMA_HOST}"


def check_device(profile: str) -> None:
    system = platform.system()
    machine = platform.machine().lower()
    free_gb = shutil.disk_usage(ROOT).free // (1024**3)
    need_gb = 35 if profile == "full" else 8 if profile == "audio" else 3
    log(f"[DEVICE] {system} {machine}, Python {platform.python_version()}, free {free_gb} GB")
    if free_gb < need_gb:
        fail(f"Can toi thieu {need_gb} GB trong cho profile {profile}. Hien con {free_gb} GB.")
    if system != "Windows":
        log("[CANH BAO] Auto-download runtime hien moi dong goi cho Windows x64; may nay se dung tool co san trong PATH.")
    elif "64" not in machine and "amd64" not in machine and "x86_64" not in machine:
        fail("Installer portable hien chi co goi Windows x64. Hay cai Python/Node/FFmpeg/Git/Ollama thu cong roi chay lai --profile core.")
    if not which("nvidia-smi"):
        log("[CANH BAO] Khong thay NVIDIA GPU. Full image/video van cai duoc nhung se cham hoac fallback CPU.")


def download(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        UI.download(destination.name, destination.stat().st_size, destination.stat().st_size)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    log(f"[TAI] {url}")
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or "0")
        read = 0
        last_render = 0.0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            read += len(chunk)
            now = time.monotonic()
            if now - last_render >= 0.2 or (total and read >= total):
                UI.download(destination.name, read, total)
                last_render = now
    UI.download(destination.name, destination.stat().st_size, destination.stat().st_size)


def extract_zip(zip_path: Path, target: Path, *, strip_single_dir: bool = False) -> None:
    staging = target.with_name(target.name + "-staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(staging)
    if target.exists():
        shutil.rmtree(target)
    if strip_single_dir:
        children = [p for p in staging.iterdir()]
        if len(children) == 1 and children[0].is_dir():
            shutil.move(str(children[0]), target)
            shutil.rmtree(staging)
            return
    shutil.move(str(staging), target)


def ensure_windows_runtime(item: RuntimeZip) -> None:
    if item.marker.exists():
        log(f"[OK] {item.name}: {item.target}")
        return
    zip_path = DOWNLOADS / f"{item.name.lower().replace('.', '').replace(' ', '-')}.zip"
    download(item.url, zip_path)
    extract_zip(zip_path, item.target, strip_single_dir=item.strip_single_dir)
    if not item.marker.exists():
        fail(f"Khong tim thay marker sau khi cai {item.name}: {item.marker}")
    log(f"[OK] {item.name}: {item.target}")


def ensure_portable_python() -> None:
    if platform.system() != "Windows":
        return
    portable = RUNTIME / "python" / "python.exe"
    if not portable.exists():
        zip_path = DOWNLOADS / "python.zip"
        download("https://www.nuget.org/api/v2/package/python/3.11.9", zip_path)
        staging = DOWNLOADS / "python-nuget"
        if staging.exists():
            shutil.rmtree(staging)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging)
        target = RUNTIME / "python"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(staging / "tools", target)
    if Path(sys.executable).resolve() != portable.resolve():
        log("[BOOTSTRAP] Chuyen sang Python portable trong .runtime...")
        os.execv(str(portable), [str(portable), str(__file__), *sys.argv[1:]])


def ensure_runtimes(profile: str) -> None:
    if platform.system() == "Windows":
        for item in WINDOWS_X64_RUNTIMES:
            if profile in {"core", "audio"} and item.name in {"Node.js", "Git", "Ollama"}:
                continue
            ensure_windows_runtime(item)
    required = ["ffmpeg", "ffprobe"]
    if profile in {"full", "dev"}:
        required += ["node", "git", "ollama"]
    missing = [tool for tool in required if not which(tool)]
    if missing:
        fail("Thieu tool: " + ", ".join(missing))


def python_cmd() -> list[str]:
    portable = RUNTIME / "python" / "python.exe"
    if portable.exists():
        return [str(portable)]
    return [sys.executable]


def pip_install(args: list[str]) -> None:
    run(python_cmd() + ["-m", "pip", "install"] + args)


def install_python_deps(profile: str) -> None:
    UI.step(2)
    pip_install(["--upgrade", "pip", "setuptools", "wheel"])
    pip_install(["-r", str(ROOT / "requirements.txt"), "pytest", "huggingface_hub"])
    if profile in {"audio", "full", "dev"}:
        run(python_cmd() + ["-c", "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('[OK] faster-whisper small ready')"])
    UI.done(2)


def ensure_pnpm(profile: str) -> None:
    UI.step(3)
    if profile not in {"full", "dev"}:
        UI.skip(3)
        return
    if not (RUNTIME / "pnpm" / "pnpm.cmd").exists():
        npm = which("npm")
        if not npm:
            fail("Khong tim thay npm de cai pnpm.")
        run([npm, "install", "--global", "--prefix", str(RUNTIME / "pnpm"), "pnpm@11.9.0"])
    if not which("pnpm"):
        fail("pnpm chua nam trong PATH.")
    UI.done(3)


def git_checkout(repo: str, target: Path, commit: str) -> None:
    git = which("git")
    if not git:
        fail("Khong tim thay git.")
    if not (target / ".git").exists():
        run([git, "clone", repo, str(target)])
    run([git, "-C", str(target), "fetch", "--depth", "1", "origin", commit])
    run([git, "-C", str(target), "checkout", "--detach", commit])


def install_comfyui(skip_models: bool) -> None:
    UI.step(4)
    git_checkout("https://github.com/comfyanonymous/ComfyUI.git", COMFYUI_DIR, COMFYUI_COMMIT)
    try:
        run(python_cmd() + ["-c", "import torch"])
    except subprocess.CalledProcessError:
        log("[THIEU] Dang cai PyTorch CUDA build; CPU van chay duoc neu khong co NVIDIA.")
        pip_install(["torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu128"])
    pip_install(["-r", str(COMFYUI_DIR / "requirements.txt"), "-q"])

    ipadapter = COMFYUI_DIR / "custom_nodes" / "ComfyUI_IPAdapter_plus"
    git_checkout("https://github.com/cubiq/ComfyUI_IPAdapter_plus.git", ipadapter, IPADAPTER_COMMIT)
    req = ipadapter / "requirements.txt"
    if req.exists():
        pip_install(["-r", str(req), "-q"])
    if not skip_models:
        run(python_cmd() + [str(ROOT / "tools" / "download_image_models.py"), "--identity"])
        download_hf_model("Lykon/DreamShaper", "DreamShaper_8_pruned.safetensors", COMFYUI_DIR / "models" / "checkpoints", DREAMSHAPER_SHA256)
        download_hf_model("SG161222/Realistic_Vision_V6.0_B1_noVAE", "Realistic_Vision_V6.0_NV_B1_fp16.safetensors", COMFYUI_DIR / "models" / "checkpoints", REALISTIC_VISION_SHA256)
    UI.done(4)


def download_hf_model(repo_id: str, filename: str, target: Path, sha256: str) -> None:
    target.mkdir(parents=True, exist_ok=True)
    code = (
        "from huggingface_hub import hf_hub_download; "
        f"hf_hub_download(repo_id={repo_id!r}, filename={filename!r}, local_dir={str(target)!r})"
    )
    run(python_cmd() + ["-c", code])
    path = target / filename
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    if digest != sha256:
        fail(f"Checksum khong khop cho {filename}")


def write_poster_env() -> None:
    env_path = POSTER_DIR / ".env"
    existing = env_path.read_text(encoding="utf-8-sig") if env_path.exists() else ""
    values = {
        "TEXT_AI_PROVIDER": "ollama",
        "TEXT_AI_MODEL": "qwen2.5:7b",
        "OLLAMA_BASE_URL": f"http://{OLLAMA_HOST}",
        "VISION_QA_MODEL": "moondream",
        "VISION_QA_JUDGE_MODEL": "qwen2.5:1.5b",
        "IMAGE_AI_PROVIDER": "comfyui",
        "COMFYUI_BASE_URL": "http://127.0.0.1:8188",
        "COMFYUI_PATH": str(COMFYUI_DIR),
        "COMFYUI_WORKFLOW": str(POSTER_DIR / "workflows" / "sd15_basic.json"),
        "COMFYUI_PYTHON": str((RUNTIME / "python" / "python.exe") if platform.system() == "Windows" else Path(sys.executable)),
    }
    lines = existing.splitlines()
    seen: set[str] = set()
    for index, line in enumerate(lines):
        key, sep, _ = line.partition("=")
        if sep and key.strip() in values:
            lines[index] = f"{key.strip()}={values[key.strip()]}"
            seen.add(key.strip())
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def ensure_ollama_models(skip_models: bool) -> None:
    UI.step(5)
    if skip_models:
        UI.skip(5)
        return
    ollama = which("ollama")
    if not ollama:
        fail("Khong tim thay ollama.")
    if subprocess.run([ollama, "list"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        log("[*] Dang khoi dong Ollama server...")
        log_path = DATA / "ollama.log"
        with log_path.open("ab") as log_file:
            subprocess.Popen([ollama, "serve"], stdout=log_file, stderr=subprocess.STDOUT)
        for _ in range(45):
            time.sleep(1)
            if subprocess.run([ollama, "list"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                break
        else:
            fail(f"Ollama khong san sang. Log: {log_path}")
    for model in ["qwen2.5:1.5b", "qwen2.5:7b", "moondream"]:
        run([ollama, "pull", model])
    UI.done(5)


def install_node_deps(profile: str) -> None:
    UI.step(6)
    if profile not in {"full", "dev"}:
        UI.skip(6)
        return
    pnpm = which("pnpm")
    if not pnpm:
        fail("Khong tim thay pnpm.")
    node_modules = POSTER_DIR / "node_modules"
    if node_modules.exists():
        shutil.rmtree(node_modules)
    run([pnpm, "--dir", str(POSTER_DIR), "install", "--frozen-lockfile", "--store-dir", str(DATA / "pnpm-store")])
    run([pnpm, "--dir", str(POSTER_DIR), "build"])
    UI.done(6)


def doctor(profile: str, skip_doctor: bool) -> None:
    UI.step(7)
    if skip_doctor:
        UI.skip(7)
        return
    if profile not in {"full", "dev"}:
        log("[SKIP] Doctor full-stack chi chay mac dinh cho profile full/dev.")
        UI.skip(7)
        return
    run(python_cmd() + [str(ROOT / "audiobook.py"), "doctor"])
    UI.done(7)


def write_manifest(profile: str) -> None:
    UI.step(8)
    manifest = {
        "schema_version": 3,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "profile": profile,
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": output(python_cmd() + ["--version"]),
        },
        "paths": {
            "root": str(ROOT),
            "runtime": str(RUNTIME),
            "data": str(DATA),
        },
    }
    (ROOT / ".install-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    UI.done(8)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Spaling Audiobook on this device.")
    parser.add_argument("--profile", choices=["core", "audio", "full", "dev"], default="full", help="core=min deps, audio=audio QA, full=all local AI, dev=full plus source build")
    parser.add_argument("--skip-models", action="store_true", help="Install code/deps but do not download AI model weights.")
    parser.add_argument("--skip-comfyui", action="store_true", help="Skip ComfyUI and image model setup.")
    parser.add_argument("--skip-doctor", action="store_true", help="Skip final audiobook doctor check.")
    parser.add_argument("--keep-downloads", action="store_true", help="Keep downloaded zip files in .data/downloads.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_env()
    ensure_portable_python()
    configure_env()
    UI.step(0)
    check_device(args.profile)
    UI.done(0)
    UI.step(1)
    ensure_runtimes(args.profile)
    UI.done(1)
    install_python_deps(args.profile)
    ensure_pnpm(args.profile)
    if args.profile in {"full", "dev"}:
        write_poster_env()
        if not args.skip_comfyui:
            install_comfyui(args.skip_models)
        else:
            UI.step(4)
            UI.skip(4)
        ensure_ollama_models(args.skip_models)
        install_node_deps(args.profile)
    else:
        UI.step(4)
        UI.skip(4)
        UI.step(5)
        UI.skip(5)
        UI.step(6)
        UI.skip(6)
    doctor(args.profile, args.skip_doctor)
    write_manifest(args.profile)
    if DOWNLOADS.exists() and not args.keep_downloads:
        shutil.rmtree(DOWNLOADS)
    UI.clear_download()
    log("[OK] Cai dat hoan tat.")
    log("Chay ung dung: .\\audiobook.bat web")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        fail(f"Lenh that bai ({exc.returncode}): {' '.join(exc.cmd)}")
