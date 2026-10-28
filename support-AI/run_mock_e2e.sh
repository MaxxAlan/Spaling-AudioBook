#!/usr/bin/env bash
# Mock e2e runner – không cần Ollama/ComfyUI/GPU
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CHAPTER="${1:-testing/chapter1.txt}"
IMAGES="${2:-4}"
OUT="${3:-artifacts/e2e-mock}"

if [[ ! -f testing/master.md || ! -f testing/request.md ]]; then
  echo "Thiếu testing/master.md hoặc testing/request.md"
  exit 1
fi

if [[ ! -f "$CHAPTER" ]]; then
  echo "Thiếu chapter: $CHAPTER"
  exit 1
fi

# Ensure mock storyboard binary exists (fallback when TS not built)
mkdir -p poster-generator/dist
if [[ ! -f poster-generator/dist/storyboard-gen.js ]]; then
  echo "Cần mock storyboard-gen.js – xem support-AI/E2E_TEST_REPORT.md"
  exit 1
fi
touch -d "2026-10-28" poster-generator/dist/storyboard-gen.js 2>/dev/null || true

echo "==> Mock e2e: chapter=$CHAPTER images=$IMAGES out=$OUT"
python3 audiobook.py build \
  --input testing/master.md testing/request.md "$CHAPTER" \
  --output "$OUT" \
  --images "$IMAGES" \
  --mock \
  --force \
  --no-video

echo "==> Done. Manifest: $OUT/audiobook-manifest.json"
