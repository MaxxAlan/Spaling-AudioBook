r"""Download image generation models for ComfyUI.

Models:
  - DreamShaper 8 (SD 1.5) — default
  - Hyper-SD15 LoRA — draft/fast
  - Realistic Vision 6.0 — realistic photos
  - ReV Animated — anime/manhwa
  - FLUX.1-dev GGUF Q4 — high quality cover

Usage:
    python tools\download_image_models.py                    # Download all
    python tools\download_image_models.py --profile default  # Download specific
    python tools\download_image_models.py --list             # List available
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
COMFYUI_MODELS = ROOT / "ComfyUI" / "models" / "checkpoints"
COMFYUI_LORAS = ROOT / "ComfyUI" / "models" / "loras"

MODEL_PROFILES = {
    "default": {
        "name": "DreamShaper 8",
        "filename": "dreamshaper_8_pruned.safetensors",
        "url": "https://huggingface.co/Lykon/DreamShaper/resolve/main/dreamshaper_8_pruned.safetensors",
        "size_mb": 2100,
        "target_dir": "checkpoints",
    },
    "draft": {
        "name": "Hyper-SD15 LoRA",
        "filename": "Hyper-SD15-8step-lora-v1.safetensors",
        "url": "https://huggingface.co/ByteDance/Hyper-FLUX-8Step-LoRA/resolve/main/Hyper-SD15-8step-lora-v1.safetensors",
        "size_mb": 24,
        "target_dir": "loras",
    },
    "realistic": {
        "name": "Realistic Vision 6.0",
        "filename": "Realistic_Vision_V6.0_B1_noVAE.safetensors",
        "url": "https://huggingface.co/SG161222/Realistic_Vision_V6.0_B1_noVAE/resolve/main/Realistic_Vision_V6.0_B1_noVAE.safetensors",
        "size_mb": 2100,
        "target_dir": "checkpoints",
    },
    "anime": {
        "name": "ReV Animated",
        "filename": "revAnimated_v122.safetensors",
        "url": "https://civitai.com/api/download/models/87153",
        "size_mb": 2100,
        "target_dir": "checkpoints",
    },
    "hq-cover": {
        "name": "FLUX.1-dev GGUF Q4",
        "filename": "flux1-dev-Q4_K_S.gguf",
        "url": "https://huggingface.co/city96/FLUX.1-dev-gguf/resolve/main/flux1-dev-Q4_K_S.gguf",
        "size_mb": 4900,
        "target_dir": "checkpoints",
    },
    "ipadapter-sd15": {
        "name": "IP-Adapter SD1.5",
        "filename": "ip-adapter_sd15.safetensors",
        "url": "https://huggingface.co/h94/IP-Adapter/resolve/main/models/ip-adapter_sd15.safetensors",
        "size_mb": 45,
        "target_dir": "ipadapter",
    },
    "clip-vision": {
        "name": "CLIP Vision ViT-H",
        "filename": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
        "url": "https://huggingface.co/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors",
        "size_mb": 2400,
        "target_dir": "clip_vision",
    },
}


def get_target_dir(profile: dict) -> Path:
    """Resolve target directory for ComfyUI."""
    comfyui_base = os.environ.get("COMFYUI_PATH", "")
    if comfyui_base and Path(comfyui_base).is_dir():
        return Path(comfyui_base) / "models" / profile["target_dir"]
    if COMFYUI_MODELS.is_dir():
        return COMFYUI_MODELS.parent / profile["target_dir"]
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    return MODELS_DIR


def download_with_progress(url: str, dest: Path, expected_size_mb: int) -> bool:
    """Download file with progress display."""
    try:
        import urllib.request
    except ImportError:
        print("  Loi: khong co urllib")
        return False

    print(f"  Tai tu: {url}")
    print(f"  Dich den: {dest}")
    print(f"  Kich thuoc: ~{expected_size_mb} MB")

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Spaling-Audiobook/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            total = response.headers.get("Content-Length")
            total = int(total) if total else None

            with open(dest, "wb") as f:
                downloaded = 0
                start_time = time.time()
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    elapsed = time.time() - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0
                    if total:
                        pct = (downloaded / total) * 100
                        print(f"\r  {pct:5.1f}% ({downloaded/(1024*1024):.1f} MB / {total/(1024*1024):.1f} MB) {speed/(1024*1024):.1f} MB/s", end="", flush=True)
                    else:
                        print(f"\r  {downloaded/(1024*1024):.1f} MB ({speed/(1024*1024):.1f} MB/s)", end="", flush=True)
            print()
            return True
    except Exception as e:
        print(f"\n  Loi tai: {e}")
        if dest.exists():
            dest.unlink()
        return False


def download_profile(profile_id: str, profile: dict) -> bool:
    """Download a single model profile."""
    print(f"\n{'='*60}")
    print(f"  [{profile_id.upper()}] {profile['name']}")
    print(f"{'='*60}")

    target_dir = get_target_dir(profile)
    dest = target_dir / profile["filename"]

    if dest.exists():
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  Da tai truoc do: {dest} ({size_mb:.0f} MB)")
        return True

    target_dir.mkdir(parents=True, exist_ok=True)

    if download_with_progress(profile["url"], dest, profile["size_mb"]):
        print(f"  THANH CONG: {dest}")
        return True
    else:
        print(f"  THAT BAI: {profile['name']}")
        return False


def list_profiles() -> None:
    """List all available model profiles."""
    print("\n  ID          | Ten                    | Kich thuoc | Dich den")
    print("  " + "-" * 70)
    for pid, p in MODEL_PROFILES.items():
        target_dir = get_target_dir(p)
        dest = target_dir / p["filename"]
        status = "DA TAI" if dest.exists() else "chua tai"
        print(f"  {pid:12s}| {p['name']:22s}| ~{p['size_mb']:>4d} MB   | {status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Tai image models cho ComfyUI")
    parser.add_argument("--profile", "-p", choices=list(MODEL_PROFILES.keys()), help="Tai model profile cu the")
    parser.add_argument("--list", "-l", action="store_true", help="Hien thi danh sach models")
    parser.add_argument("--all", "-a", action="store_true", help="Tai tat ca models")
    parser.add_argument("--identity", action="store_true", help="Tai IP-Adapter SD1.5 va CLIP Vision")
    args = parser.parse_args()

    if args.list:
        list_profiles()
        return 0

    if args.profile:
        p = MODEL_PROFILES[args.profile]
        return 0 if download_profile(args.profile, p) else 1

    if args.identity:
        selected = ("ipadapter-sd15", "clip-vision")
        return 0 if all(download_profile(pid, MODEL_PROFILES[pid]) for pid in selected) else 1

    # Download all
    print("=== Tai tat ca Image Models ===")
    results = {}
    for pid, p in MODEL_PROFILES.items():
        results[pid] = download_profile(pid, p)

    print(f"\n{'='*60}")
    print("KET QUA:")
    for pid, ok in results.items():
        print(f"  {pid}: {'OK' if ok else 'THAT BAI'}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
