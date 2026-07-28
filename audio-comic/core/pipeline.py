"""Audio generation pipeline used by the audiobook application."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.cache_manager import CacheManager
from core.state_manager import StateManager
from core.exceptions import (
    PipelineCancelledError,
    PipelineError,
    TTSGenerationError,
)
from models.project import Project
from models.segment import Segment, SegmentType
from text_processing.script_analyzer import analyze_script
from text_processing.normalizer import NORMALIZATION_VERSION, normalize_text
from audio.concatenator import concatenate_segments
from audio.quality import verify_tts_wav
from audio.semantic_quality import LocalSpeechVerifier
from ai.parameter_optimizer import propose_retry
from audio.exporter import export_wav, export_mp3
from tts.base import TTSProvider
from video.ffmpeg_manager import FFmpegManager
from video.subtitles import write_srt
from video.validator import validate_audio
from utils.logging_config import get_logger
from utils.paths import ensure_dir

logger = get_logger("core.pipeline")

# Progress callback signature: (stage_name, percent, message)
ProgressCallback = Callable[[str, float, str], None]


class Pipeline:
    """Analyze text, synthesize and validate narration audio."""

    def __init__(
        self,
        tts_provider: TTSProvider,
        ffmpeg_manager: FFmpegManager,
        cache_manager: CacheManager,
        progress_callback: Optional[ProgressCallback] = None,
        max_segment_length: Optional[int] = None,
        ai_helper: Optional[Any] = None,
        semantic_qa: Optional[dict[str, Any]] = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            tts_provider: TTS engine to use.
            ffmpeg_manager: FFmpeg manager instance.
            cache_manager: Cache manager for TTS segments.
            progress_callback: Optional callback for progress updates.
        """
        self._tts = tts_provider
        self._ffmpeg = ffmpeg_manager
        self._cache = cache_manager
        self._progress = progress_callback
        self._max_segment_length = max_segment_length or 500
        self._ai_helper = ai_helper
        semantic_qa = semantic_qa or {}
        self._semantic_verifier = LocalSpeechVerifier(
            model_name=str(semantic_qa.get("model", "small")),
            device=str(semantic_qa.get("device", "cpu")),
            compute_type=str(semantic_qa.get("compute_type", "int8")),
        ) if semantic_qa.get("enabled", False) else None
        self._cancelled = False
        self._paused = False

    def cancel(self) -> None:
        """Request pipeline cancellation."""
        self._cancelled = True
        logger.info("Pipeline cancellation requested")

    def pause(self) -> None:
        """Request pipeline pause."""
        self._paused = True
        logger.info("Pipeline pause requested")

    def resume(self) -> None:
        """Resume a paused pipeline."""
        self._paused = False
        logger.info("Pipeline resumed")

    def _check_cancelled(self) -> None:
        """Check if cancellation was requested."""
        if self._cancelled:
            raise PipelineCancelledError("Pipeline đã bị hủy bởi người dùng")

    def _wait_if_paused(self) -> None:
        """Block while pipeline is paused."""
        while self._paused and not self._cancelled:
            time.sleep(0.5)

    def _emit_progress(self, stage: str, percent: float, message: str) -> None:
        """Emit a progress update."""
        if self._progress:
            try:
                self._progress(stage, percent, message)
            except Exception:
                pass

    def run(
        self,
        project: Project,
        state_manager: Optional[StateManager] = None,
    ) -> Dict[str, str]:
        """Generate and validate narration audio for a project.

        Args:
            project: The project to process.
            state_manager: Optional state manager for resume support.

        Returns:
            Dict mapping output type to file path.

        Raises:
            PipelineError: If the pipeline fails.
            PipelineCancelledError: If cancelled by user.
        """
        self._cancelled = False
        self._paused = False
        start_time = time.time()

        project_dir = Path(project.project_dir) if project.project_dir else Path(".")
        output_dir = Path(project.output_dir) if project.output_dir else project_dir
        ensure_dir(output_dir)

        # Initialize state
        sm = state_manager
        if sm:
            state = sm.load()
            resume_from = sm.get_resumable_segments()
        else:
            resume_from = 0

        logger.info("=" * 60)
        logger.info("Pipeline started: %s", project.project_id)
        logger.info("=" * 60)

        outputs: Dict[str, str] = {}

        try:
            # ── Stage 1: Text Analysis ──────────────────────────
            self._emit_progress("Phân tích văn bản", 5.0, "Đang phân tích nội dung...")
            self._check_cancelled()

            if not project.segments:
                logger.info("Analyzing script...")
                segments, characters = analyze_script(
                    project.source_text,
                    max_segment_length=self._max_segment_length,
                )
                project.segments = segments
                project.characters = characters
                logger.info("Found %d segments, %d characters", len(segments), len(characters))
            else:
                logger.info("Using existing %d segments", len(project.segments))

            # A newly analyzed project has no cache keys yet. An old state file
            # with the same story/chapter name must not make it reuse arbitrary
            # segment WAVs produced by an earlier voice or provider setting.
            if resume_from and not any(segment.cache_key for segment in project.segments):
                logger.info("Ignoring stale resume state because TTS cache keys are absent")
                resume_from = 0

            if self._ai_helper is not None:
                self._emit_progress(
                    "AI hỗ trợ", 8.0,
                    f"Đang tạo hướng dẫn đọc bằng {self._ai_helper.model}...",
                )
                project.segments = self._ai_helper.enhance_segments(project.segments)
                logger.info(
                    "AI narration guidance applied with model %s",
                    self._ai_helper.model,
                )

            if sm:
                sm.initialize(project.project_id, len(project.segments))
                sm.update_status("tts_processing")

            # ── Stage 2: TTS Synthesis ──────────────────────────
            self._emit_progress("Sinh giọng nói", 10.0, "Đang tải model TTS...")
            self._check_cancelled()

            if not self._tts.is_loaded:
                self._tts.load_model()
            mock_tts = self._tts.provider_name == "MockTTS"

            segments_dir = project_dir / "audio" / "segments"
            ensure_dir(segments_dir)

            segment_files: List[Tuple[str, int, Segment]] = []
            semantic_reviews: Dict[int, Dict[str, Any]] = {}
            total = len(project.segments)

            for i, segment in enumerate(project.segments):
                self._wait_if_paused()
                self._check_cancelled()

                # Skip already completed segments (resume)
                if i < resume_from:
                    cached = self._cache.get_cached_path(segment.cache_key) if segment.cache_key else None
                    seg_path = cached or str(segments_dir / f"segment_{segment.segment_id:04d}.wav")
                    if Path(seg_path).exists():
                        segment.audio_path = seg_path
                        segment_files.append((seg_path, segment.pause_after_ms, segment))
                        continue

                progress = 10.0 + (i / total) * 50.0
                self._emit_progress(
                    "Sinh giọng nói",
                    progress,
                    f"Segment {i + 1}/{total}: {segment.text[:30]}...",
                )

                # Skip silent segments
                if segment.is_silent:
                    segment_files.append(("", segment.pause_after_ms, segment))
                    if sm:
                        sm.mark_segment_complete(segment.segment_id)
                    continue

                # Check cache
                normalized_text = normalize_text(segment.text)
                cache_key = self._cache.get_cache_key(
                    normalized_text,
                    segment.voice_id or "default",
                    segment.speed,
                    segment.pitch,
                    model_version=f"{self._tts.provider_name}:{NORMALIZATION_VERSION}:{json.dumps(segment.inference_options, sort_keys=True)}",
                )
                segment.cache_key = cache_key

                cached_path = self._cache.get_cached_path(cache_key)
                if cached_path:
                    valid, reasons = verify_tts_wav(cached_path, normalized_text)
                    if mock_tts:
                        valid, reasons = True, []
                    if valid and self._semantic_verifier is not None:
                        review = self._semantic_verifier.verify(cached_path, normalized_text)
                        semantic_reviews[segment.segment_id] = review.to_dict()
                        valid, reasons = review.approved, review.reasons
                    if valid:
                        logger.debug("Cache hit for segment %d", segment.segment_id)
                        segment.cached = True
                        segment.audio_path = cached_path
                        segment_files.append((cached_path, segment.pause_after_ms, segment))
                        if sm:
                            sm.mark_segment_complete(segment.segment_id)
                        continue
                    logger.warning("Rejecting bad cached segment %d: %s", segment.segment_id, ", ".join(reasons))
                    self._cache.invalidate(cache_key)

                # Synthesize
                seg_path = str(segments_dir / f"segment_{segment.segment_id:04d}.wav")
                try:
                    result_path = ""
                    last_reasons: list[str] = []
                    for attempt in range(1, 3):
                        attempt_text = normalize_text(segment.text, conservative=attempt > 1)
                        set_options = getattr(self._tts, "set_segment_options", None)
                        if set_options:
                            set_options(segment.inference_options)
                        result_path = self._tts.synthesize(
                            text=attempt_text,
                            voice_id=segment.voice_id or "narrator_male_01",
                            output_path=seg_path,
                            speed=segment.speed,
                            pitch=segment.pitch,
                            emotion=segment.emotion,
                        )
                        valid, last_reasons = verify_tts_wav(result_path, attempt_text)
                        if mock_tts:
                            valid, last_reasons = True, []
                        if valid and self._semantic_verifier is not None:
                            review = self._semantic_verifier.verify(result_path, attempt_text)
                            semantic_reviews[segment.segment_id] = review.to_dict()
                            valid, last_reasons = review.approved, review.reasons
                        if valid:
                            cache_key = self._cache.get_cache_key(
                                attempt_text,
                                segment.voice_id or "default",
                                segment.speed,
                                segment.pitch,
                                model_version=f"{self._tts.provider_name}:{NORMALIZATION_VERSION}:{json.dumps(segment.inference_options, sort_keys=True)}",
                            )
                            segment.cache_key = cache_key
                            break
                        logger.warning("Rejected TTS segment %d attempt %d: %s", segment.segment_id, attempt, ", ".join(last_reasons))
                        Path(result_path).unlink(missing_ok=True)
                        policy = getattr(self._ai_helper, "parameter_policy", None)
                        if policy and attempt < 2:
                            segment.inference_options = propose_retry(segment.inference_options, last_reasons, policy)
                            segment.attempt_history.append({"attempt": attempt, "config": segment.inference_options, "issues": last_reasons})
                    if not result_path or last_reasons:
                        raise TTSGenerationError(
                            f"Kiểm duyệt thất bại segment {segment.segment_id}",
                            details=", ".join(last_reasons),
                        )
                    self._cache.store(cache_key, result_path, {"project_id": project.project_id, "segment_id": segment.segment_id})
                    segment.audio_path = result_path
                    segment.cached = True
                    segment_files.append((result_path, segment.pause_after_ms, segment))
                    if sm:
                        sm.mark_segment_complete(segment.segment_id)

                except TTSGenerationError as e:
                    logger.error("TTS failed for segment %d: %s", segment.segment_id, e)
                    segment.error = str(e)
                    if sm:
                        sm.mark_segment_failed(segment.segment_id, str(e))
                    # Continue with other segments

            # ── Stage 3: Audio QA and concatenation ─────────────
            self._emit_progress("Kiểm duyệt audio", 64.0, "Đang xác minh lại toàn bộ segment...")
            self._check_cancelled()
            failed_segments = [
                (segment.segment_id, segment.error)
                for segment in project.segments if segment.error
            ]
            if failed_segments and not mock_tts:
                raise TTSGenerationError(
                    "Không ghép audio vì có segment sinh lỗi",
                    details="; ".join(
                        f"segment {sid}: {reason}" for sid, reason in failed_segments
                    ),
                )
            rejected = [
                (segment.segment_id, verify_tts_wav(path, segment.text)[1])
                for path, _pause, segment in segment_files
                if not mock_tts and path and Path(path).exists() and not verify_tts_wav(path, segment.text)[0]
            ]
            if rejected:
                raise TTSGenerationError(
                    "Kiểm duyệt audio thất bại trước khi ghép",
                    details="; ".join(f"segment {sid}: {', '.join(reasons)}" for sid, reasons in rejected),
                )
            if self._semantic_verifier is not None:
                for path, _pause, segment in segment_files:
                    if not path or segment.segment_id in semantic_reviews:
                        continue
                    review = self._semantic_verifier.verify(
                        path, normalize_text(segment.text)
                    )
                    semantic_reviews[segment.segment_id] = review.to_dict()
                semantic_rejected = [
                    (segment_id, review["reasons"])
                    for segment_id, review in semantic_reviews.items()
                    if not review["approved"]
                ]
                if semantic_rejected:
                    raise TTSGenerationError(
                        "Kiểm duyệt nội dung audio thất bại trước khi ghép",
                        details="; ".join(
                            f"segment {sid}: {', '.join(reasons)}"
                            for sid, reasons in semantic_rejected
                        ),
                    )
            quality_report = {
                "voice": getattr(self._tts, "provider_name", "unknown"),
                "segments": [
                    {
                        "segment_id": segment.segment_id,
                        "approved": (
                            semantic_reviews.get(segment.segment_id, {}).get(
                                "approved", True
                            )
                        ),
                        "technical_score": 1.0,
                        "approval_scope": (
                            "technical_and_semantic"
                            if self._semantic_verifier is not None
                            else "technical_only"
                        ),
                        "semantic": semantic_reviews.get(segment.segment_id, {
                            "approved": self._semantic_verifier is None,
                            "status": "disabled",
                        }),
                        "attempts": segment.attempt_history,
                        "selected_attempt": (segment.attempt_history[-1]["attempt"] if segment.attempt_history else 0),
                    }
                    for path, _pause, segment in segment_files if path and Path(path).exists()
                ],
            }
            quality_report_path = output_dir / "audio-quality-report.json"
            quality_report_path.write_text(
                json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            outputs["audio_quality_report"] = str(quality_report_path)
            valid_entries = [(p, pause, segment) for p, pause, segment in segment_files if p and Path(p).exists()]
            valid_segments = [(p, pause) for p, pause, _ in valid_entries]

            if not valid_segments:
                raise TTSGenerationError(
                    "Không tạo được đoạn giọng nói nào từ tệp đầu vào",
                    details="Kiểm tra TTS provider/model và log lỗi của từng segment.",
                )

            self._emit_progress("Ghép audio", 65.0, "Đang ghép các đoạn âm thanh...")

            audio_filename = project.get_output_filename("audiocomic", "wav")
            audio_output = str(output_dir / audio_filename)

            subtitle_timings: List[Tuple[str, float, float]] = []

            def remember_timing(index: int, start_ms: float, end_ms: float) -> None:
                if index < len(valid_entries):
                    subtitle_timings.append((valid_entries[index][2].text, start_ms, end_ms))

            concatenate_segments(
                valid_segments,
                audio_output,
                target_sample_rate=project.export_settings.audio_sample_rate,
                target_channels=project.export_settings.audio_channels,
                timing_callback=remember_timing if project.export_settings.export_subtitles else None,
            )
            outputs["audio"] = audio_output

            if project.export_settings.export_subtitles:
                subtitle_filename = project.get_output_filename("vi", "srt")
                outputs["subtitles"] = write_srt(
                    subtitle_timings, str(output_dir / subtitle_filename)
                )

            if sm:
                sm.mark_audio_complete()

            # Export MP3 if requested
            if project.export_settings.export_mp3:
                mp3_filename = project.get_output_filename("audiocomic", "mp3")
                mp3_output = str(output_dir / mp3_filename)
                try:
                    export_mp3(
                        audio_output, mp3_output,
                        bitrate=project.export_settings.mp3_bitrate,
                        ffmpeg_path=self._ffmpeg.ffmpeg_path,
                    )
                    outputs["audio_mp3"] = mp3_output
                except Exception as e:
                    logger.warning("MP3 export failed: %s", e)

            report = validate_audio(outputs["audio"], self._ffmpeg)
            if sm:
                sm.update_status(
                    "completed" if report.all_passed else "completed_with_warnings"
                )
            elapsed = time.time() - start_time
            self._emit_progress(
                "Hoàn thành", 100.0, f"Đã tạo audio trong {elapsed:.0f}s"
            )
            logger.info("Audio pipeline completed in %.1fs", elapsed)
            logger.info("Outputs: %s", {k: Path(v).name for k, v in outputs.items()})
            return outputs
        except PipelineCancelledError:
            logger.info("Pipeline cancelled by user")
            if sm:
                sm.update_status("cancelled")
            raise
        except Exception as e:
            logger.error("Pipeline error: %s", e, exc_info=True)
            if sm:
                sm.mark_error(str(e))
            raise PipelineError(
                f"Pipeline thất bại: {e}",
                details=str(e),
            )
