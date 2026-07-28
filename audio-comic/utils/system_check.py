"""System dependency checker for Audio-Comic Offline System.

Checks for Python version, FFmpeg, CUDA/GPU, VieNeu-TTS model,
ComfyUI, fonts, disk space, and other requirements at startup.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from utils.logging_config import get_logger

logger = get_logger("utils.system_check")


class CheckStatus(Enum):
    """Status levels for dependency checks."""
    READY = "ready"
    WARNING = "warning"
    MISSING = "missing"
    ERROR = "error"


@dataclass
class CheckResult:
    """Result of a single dependency check.

    Attributes:
        name: Human-readable name of the dependency.
        status: Check status.
        message: Status description.
        fix_instructions: How to fix if not ready.
        version: Detected version string, if applicable.
        path: Detected path, if applicable.
    """
    name: str
    status: CheckStatus = CheckStatus.MISSING
    message: str = ""
    fix_instructions: str = ""
    version: str = ""
    path: str = ""


@dataclass
class SystemCheckReport:
    """Complete system check report.

    Attributes:
        results: List of individual check results.
        overall_ready: Whether the system is ready for basic operation.
    """
    results: List[CheckResult] = field(default_factory=list)

    @property
    def overall_ready(self) -> bool:
        """System is ready if no checks have ERROR status."""
        return all(r.status != CheckStatus.ERROR for r in self.results)

    @property
    def has_warnings(self) -> bool:
        """Check if any warnings exist."""
        return any(r.status == CheckStatus.WARNING for r in self.results)

    def get_by_name(self, name: str) -> Optional[CheckResult]:
        """Get a specific check result by name."""
        for r in self.results:
            if r.name == name:
                return r
        return None


def check_python_version() -> CheckResult:
    """Check Python version (requires 3.10+)."""
    result = CheckResult(name="Python")
    version = sys.version_info
    result.version = f"{version.major}.{version.minor}.{version.micro}"

    if version >= (3, 10):
        result.status = CheckStatus.READY
        result.message = f"Python {result.version}"
    elif version >= (3, 9):
        result.status = CheckStatus.WARNING
        result.message = f"Python {result.version} (khuyến nghị 3.10+)"
    else:
        result.status = CheckStatus.ERROR
        result.message = f"Python {result.version} quá cũ"
        result.fix_instructions = "Cài đặt Python 3.10 trở lên từ python.org"

    return result


def check_ffmpeg(custom_path: str = "") -> CheckResult:
    """Check if FFmpeg is available.

    Args:
        custom_path: Custom path to FFmpeg binary.
    """
    result = CheckResult(name="FFmpeg")

    ffmpeg_path = custom_path or shutil.which("ffmpeg")

    if ffmpeg_path is None:
        result.status = CheckStatus.MISSING
        result.message = "FFmpeg không được tìm thấy"
        result.fix_instructions = (
            "1. Tải FFmpeg từ https://ffmpeg.org/download.html\n"
            "2. Giải nén và thêm thư mục bin vào PATH\n"
            "3. Hoặc chỉ định đường dẫn trong Settings"
        )
        return result

    try:
        proc = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            # Extract version from first line
            first_line = proc.stdout.split("\n")[0]
            result.status = CheckStatus.READY
            result.message = first_line.strip()
            result.path = ffmpeg_path
            result.version = first_line.strip()
        else:
            result.status = CheckStatus.ERROR
            result.message = "FFmpeg không hoạt động đúng"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        result.status = CheckStatus.ERROR
        result.message = f"Lỗi khi kiểm tra FFmpeg: {e}"

    return result


def check_ffprobe(custom_path: str = "") -> CheckResult:
    """Check if FFprobe is available."""
    result = CheckResult(name="FFprobe")

    ffprobe_path = custom_path or shutil.which("ffprobe")

    if ffprobe_path is None:
        result.status = CheckStatus.WARNING
        result.message = "FFprobe không được tìm thấy (thường đi kèm FFmpeg)"
        result.fix_instructions = "FFprobe thường nằm cùng thư mục với FFmpeg"
        return result

    try:
        proc = subprocess.run(
            [ffprobe_path, "-version"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0:
            result.status = CheckStatus.READY
            result.path = ffprobe_path
            result.message = "FFprobe sẵn sàng"
        else:
            result.status = CheckStatus.ERROR
            result.message = "FFprobe không hoạt động đúng"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        result.status = CheckStatus.ERROR
        result.message = "Không thể chạy FFprobe"

    return result


def check_cuda() -> CheckResult:
    """Check CUDA and GPU availability."""
    result = CheckResult(name="CUDA / GPU")

    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            properties = torch.cuda.get_device_properties(0)
            total_memory = getattr(properties, "total_memory", getattr(properties, "total_mem", 0))
            vram = total_memory / (1024 ** 3)
            result.status = CheckStatus.READY
            result.message = f"{gpu_name} ({vram:.1f} GB VRAM)"
            result.version = torch.version.cuda or ""
        else:
            result.status = CheckStatus.WARNING
            result.message = "CUDA không khả dụng, sẽ sử dụng CPU"
            result.fix_instructions = (
                "Cài đặt NVIDIA driver và PyTorch với CUDA support\n"
                "TTS vẫn hoạt động trên CPU nhưng chậm hơn"
            )
    except ImportError:
        result.status = CheckStatus.WARNING
        result.message = "PyTorch chưa được cài đặt"
        result.fix_instructions = "pip install torch (tùy chọn, cần cho VieNeu-TTS với GPU)"

    return result


def check_vieneu_model(model_path: str = "") -> CheckResult:
    """Check if VieNeu-TTS model is available."""
    result = CheckResult(name="VieNeu-TTS")

    try:
        import vieneu
        result.status = CheckStatus.READY
        result.message = "VieNeu-TTS library đã cài đặt"
        try:
            from importlib.metadata import version
            result.version = version("vieneu")
        except Exception:
            result.version = "unknown"
        result.path = str(Path(vieneu.__file__).resolve())
        result.message = f"VieNeu-TTS {result.version} đã cài; model chạy local"
    except ImportError:
        result.status = CheckStatus.WARNING
        result.message = "VieNeu-TTS chưa được cài đặt"
        result.fix_instructions = (
            "pip install vieneu\n"
            "Hệ thống vẫn hoạt động với MockTTS hoặc SAPI5"
        )

    if model_path and not Path(model_path).exists():
        result.status = CheckStatus.WARNING
        result.message += f"\nModel path không tồn tại: {model_path}"

    return result


def check_comfyui(url: str = "http://127.0.0.1:8188") -> CheckResult:
    """Check if ComfyUI is running locally."""
    result = CheckResult(name="ComfyUI")

    try:
        import urllib.request
        req = urllib.request.Request(f"{url}/system_stats", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                result.status = CheckStatus.READY
                result.message = f"ComfyUI đang chạy tại {url}"
                result.path = url
            else:
                result.status = CheckStatus.MISSING
                result.message = "ComfyUI không phản hồi"
    except Exception:
        result.status = CheckStatus.WARNING
        result.message = "ComfyUI không hoạt động (sẽ dùng Template Poster)"
        result.fix_instructions = (
            "1. Cài đặt ComfyUI từ https://github.com/comfyanonymous/ComfyUI\n"
            "2. Khởi động ComfyUI: python main.py\n"
            "3. Kiểm tra http://127.0.0.1:8188\n"
            "Hoặc dùng Template Poster thay thế"
        )

    return result


def check_disk_space(path: str = ".", min_gb: float = 1.0) -> CheckResult:
    """Check available disk space.

    Args:
        path: Path to check disk space for.
        min_gb: Minimum required space in GB.
    """
    result = CheckResult(name="Dung lượng đĩa")

    try:
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
        total_gb = usage.total / (1024 ** 3)

        if free_gb >= min_gb:
            result.status = CheckStatus.READY
            result.message = f"{free_gb:.1f} GB trống / {total_gb:.1f} GB tổng"
        else:
            result.status = CheckStatus.WARNING
            result.message = f"Chỉ còn {free_gb:.1f} GB trống"
            result.fix_instructions = f"Cần ít nhất {min_gb} GB trống"
    except OSError as e:
        result.status = CheckStatus.ERROR
        result.message = f"Không thể kiểm tra dung lượng: {e}"

    return result


def check_fonts(font_path: str = "") -> CheckResult:
    """Check if Vietnamese-compatible fonts are available."""
    result = CheckResult(name="Fonts")

    if font_path and Path(font_path).exists():
        result.status = CheckStatus.READY
        result.message = f"Font tùy chỉnh: {Path(font_path).name}"
        result.path = font_path
        return result

    # Check for common system fonts on Windows
    if platform.system() == "Windows":
        fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        # Look for fonts that support Vietnamese
        vn_fonts = [
            "arial.ttf", "arialbd.ttf", "times.ttf", "timesbd.ttf",
            "segoeui.ttf", "segoeuib.ttf", "calibri.ttf", "calibrib.ttf",
            "tahoma.ttf", "tahomabd.ttf",
        ]
        found = [f for f in vn_fonts if (fonts_dir / f).exists()]
        if found:
            result.status = CheckStatus.READY
            result.message = f"Tìm thấy {len(found)} font hệ thống hỗ trợ tiếng Việt"
            result.path = str(fonts_dir / found[0])
        else:
            result.status = CheckStatus.WARNING
            result.message = "Không tìm thấy font hệ thống phù hợp"
    else:
        result.status = CheckStatus.WARNING
        result.message = "Kiểm tra font trên hệ thống này chưa được hỗ trợ"
        result.fix_instructions = "Chỉ định đường dẫn font trong Settings"

    return result


def run_system_check(
    ffmpeg_path: str = "",
    ffprobe_path: str = "",
    vieneu_model_path: str = "",
    comfyui_url: str = "http://127.0.0.1:8188",
    output_path: str = ".",
    font_path: str = "",
) -> SystemCheckReport:
    """Run all system dependency checks.

    Args:
        ffmpeg_path: Custom FFmpeg path.
        ffprobe_path: Custom FFprobe path.
        vieneu_model_path: Path to VieNeu model.
        comfyui_url: ComfyUI URL.
        output_path: Output directory to check disk space.
        font_path: Custom font path.

    Returns:
        Complete system check report.
    """
    logger.info("Running system dependency check...")
    report = SystemCheckReport()

    checks = [
        check_python_version(),
        check_ffmpeg(ffmpeg_path),
        check_ffprobe(ffprobe_path),
        check_cuda(),
        check_vieneu_model(vieneu_model_path),
        check_comfyui(comfyui_url),
        check_disk_space(output_path),
        check_fonts(font_path),
    ]

    for check in checks:
        report.results.append(check)
        status_str = check.status.value.upper()
        logger.info("  [%s] %s: %s", status_str, check.name, check.message)

    if report.overall_ready:
        logger.info("System check: READY (có thể có cảnh báo)")
    else:
        logger.warning("System check: CÓ LỖI - một số thành phần cần cài đặt")

    return report
