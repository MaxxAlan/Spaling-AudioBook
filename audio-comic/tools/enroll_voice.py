"""Compile an authorized reference WAV into a reusable VieNeu v3 voice bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cpu")
    parser.add_argument("--style", default="doc_truyen")
    parser.add_argument("--gender", default="neutral")
    parser.add_argument("--description", default="")
    parser.add_argument("--consent-confirmed", action="store_true", required=True)
    parser.add_argument("--already-denoised", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    reference = Path(args.reference).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if not reference.is_file():
        raise FileNotFoundError(reference)
    if not args.consent_confirmed:
        raise ValueError("Chỉ enroll giọng khi chủ giọng đã đồng ý.")

    from vieneu import Vieneu

    tts = Vieneu(mode="v3turbo", device=args.device)
    tts.add_voice(
        args.id,
        reference,
        denoise=not args.already_denoised,
        use_ref_codes=True,
        description=args.description or args.name,
        gender=args.gender,
        style=args.style,
    )
    with tempfile.TemporaryDirectory(prefix="spaling-voice-") as folder:
        snapshot = Path(folder) / "voices.json"
        tts.save_voices(snapshot)
        preset = json.loads(snapshot.read_text(encoding="utf-8"))["presets"][args.id]

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model": "VieNeu-TTS-v3-Turbo",
                "voices": {args.id: preset},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
