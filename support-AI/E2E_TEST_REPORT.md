# E2E Test Report – Spaling Audiobook v0.0.2

**Date:** 2026-10-27  
**Input:** testing/chapter1.txt (chapter2 content, ~51.6k chars)  
**Mode:** `--mock --images 4 --no-video --force`  
**Output:** `/tmp/e2e-test2` (successful run)

## Summary

| Stage | Status | Notes |
|-------|--------|-------|
| Text analysis | PASS | 402 segments created |
| Mock TTS | PASS | 395 segments approved, ~213s WAV (mock-capped) |
| Audio concat + MP3 | PASS | 37.5MB WAV / 1.57MB MP3 |
| Storyboard (mock) | PASS | 4 scenes + cover + QA |
| Final audit | PASS (after QA schema fix) | Initially failed |
| Video | SKIPPED | `--no-video` |
| Real TTS / ComfyUI / Ollama | NOT TESTED | Environment lacks models |

**Overall mock e2e: PASS** (after fixing storyboard-qa schema contract)

## Bugs & Issues Found

### P0 – Critical (blocks reliable e2e / production)

1. **QA schema contract fragile** (`audiobook.py` `_final_audit` vs `poster-generator`)
   - Python expects `storyboard-qa.json` = **array** of `{sceneId, platform, approved, ...}`
   - Easy to break if TS changes shape or mock is wrong
   - First run crashed: `AttributeError: 'str' object has no attribute 'get'`
   - **Fix:** Share a single Zod/JSON Schema; validate on both sides; add contract test

2. **poster-generator build unreliable**
   - `pnpm` fails with EPERM symlink on some filesystems / sandboxes
   - No fallback when `dist/` missing
   - **Fix:** Document `pnpm install --config.package-import-method=copy`; ship prebuilt `dist/` in releases; or add pure-Python mock path when `--mock`

3. **Over-segmentation (395–402 segments for 1 chapter)**
   - Default `max_segment_length=500` but pipeline still creates ~400 segments
   - Causes: slow mock path, huge quality-report JSON, many tiny WAV files, weak prosody continuity
   - **Fix:** Review `text_processing` + pipeline chunking; merge short adjacent narration; target 40–80 segments for a chapter this size

### P1 – High (quality / UX)

4. **`character_cast` = null in manifest**
   - Character detection / voice assignment not flowing into final manifest
   - Breaks multi-voice audiobook story
   - **Fix:** Wire `CharacterDetector` + voice registry into manifest + TTS assignment

5. **Speaker attribution errors** (from earlier unit analysis)
   - Examples: `"Amos đột"` instead of `"Amos"`
   - Long attribution paragraphs attached to dialogue lines
   - **Fix:** Improve `dialogue_parser` Vietnamese heuristics; strip attribution; normalize speaker names

6. **Mock duration cap too aggressive**
   - `--mock` sets `mock_max_duration_seconds = 0.12` → entire chapter becomes ~3.5 min
   - Hides duration-based image count / video timeline bugs
   - **Fix:** Use slightly longer mock duration (e.g. 0.8–1.5s per segment) or scale by text length with a sane max

7. **Semantic QA disabled in mock path**
   - All segments `semantic.status = "disabled"`
   - Real quality gate not exercised in smoke-test
   - **Fix:** Optional lightweight mock semantic score; document that full QA needs faster-whisper

### P2 – Medium

8. **Scene selection quality** (storyboard)
   - Even with real pipeline, need to verify key beats (ritual aftermath, footprint discovery, ice golem, Abyss Seal) are selected
   - Mock evenly slices lines → not representative
   - **Fix:** Golden-scene tests with expected scene anchors for chapter2

9. **Filesystem sensitivity**
   - Writes under project `artifacts/` hit `Errno 5` I/O on some environments
   - State/cache writes not resilient
   - **Fix:** Atomic write + retry; prefer user temp when needed; better error message

10. **smoke-test hardcodes `chapter1.txt`**
    - Inflexible; should accept path or use whatever is in `testing/`
    - **Fix:** Parameterize or auto-pick first chapter file

11. **No video path validated in this run**
    - FFmpeg present, but `--no-video` used
    - Need separate test with mock images + real concat

### P3 – Low / polish

12. Progress JSON noise (`@@progress {...}`) mixed with human logs  
13. `character_cast` and voice mapping docs missing for users  
14. No automated CI job that runs `smoke-test --mock` on PR  

## What worked well

- Unified CLI orchestration (audio → storyboard → audit)
- MockTTS generates valid WAV/MP3 without models
- Cache + state machinery exists (when FS allows)
- Manifest structure is rich and useful
- Progress callbacks functional
- Audio quality report always produced

## Artifacts from successful run

```
/tmp/e2e-test2/
├── audio/
│   ├── chapter1_chapter_001_audiocomic.wav   (~213s, 37.5MB)
│   ├── chapter1_chapter_001_audiocomic.mp3
│   └── audio-quality-report.json             (395 segments approved)
├── images/
│   ├── cover.jpg
│   ├── scenes/scene_001..004.png
│   ├── storyboard.json
│   └── storyboard-qa.json                    (array schema)
├── audiobook-manifest.json
└── audiobook-progress.json
```
