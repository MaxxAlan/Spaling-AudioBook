"""Exception hierarchy for Audio-Comic Offline System.

Every module uses specific exception types so errors can be caught
and handled gracefully without crashing the entire pipeline.
"""


class AudioComicError(Exception):
    """Base exception for all Audio-Comic errors."""

    def __init__(self, message: str = "", details: str = "") -> None:
        self.message = message
        self.details = details
        super().__init__(message)

    def user_message(self) -> str:
        """Return a user-friendly error message (no stack trace)."""
        return self.message


# ── TTS Errors ──────────────────────────────────────────────────────────────

class TTSError(AudioComicError):
    """Base exception for TTS-related errors."""
    pass


class TTSModelNotFoundError(TTSError):
    """TTS model files are missing or path is invalid."""
    pass


class TTSGenerationError(TTSError):
    """TTS synthesis failed for a segment.

    Attributes:
        segment_id: The segment that failed.
        retry_count: Number of retries attempted.
    """

    def __init__(
        self,
        message: str = "",
        details: str = "",
        segment_id: int = 0,
        retry_count: int = 0,
    ) -> None:
        super().__init__(message, details)
        self.segment_id = segment_id
        self.retry_count = retry_count


class TTSProviderError(TTSError):
    """TTS provider failed to initialize."""
    pass


# ── Poster Errors ───────────────────────────────────────────────────────────

class PosterError(AudioComicError):
    """Base exception for poster generation errors."""
    pass


class ComfyUIConnectionError(PosterError):
    """Cannot connect to local ComfyUI instance."""
    pass


class ComfyUIWorkflowError(PosterError):
    """ComfyUI workflow execution failed."""
    pass


class PosterGenerationError(PosterError):
    """Poster image generation failed."""
    pass


# ── FFmpeg / Video Errors ───────────────────────────────────────────────────

class VideoError(AudioComicError):
    """Base exception for video-related errors."""
    pass


class FFmpegNotFoundError(VideoError):
    """FFmpeg binary not found on the system."""

    def user_message(self) -> str:
        return (
            "FFmpeg không được tìm thấy trên hệ thống.\n"
            "Vui lòng cài đặt FFmpeg và cấu hình đường dẫn trong Settings."
        )


class FFprobeNotFoundError(VideoError):
    """FFprobe binary not found on the system."""
    pass


class VideoExportError(VideoError):
    """Video export/encoding failed."""
    pass


class VideoValidationError(VideoError):
    """Output video failed validation checks."""
    pass


# ── Audio Processing Errors ─────────────────────────────────────────────────

class AudioError(AudioComicError):
    """Base exception for audio processing errors."""
    pass


class AudioConcatenationError(AudioError):
    """Audio segment concatenation failed."""
    pass


class AudioNormalizationError(AudioError):
    """Audio loudness normalization failed."""
    pass


class AudioExportError(AudioError):
    """Audio file export failed."""
    pass


# ── Text Processing Errors ──────────────────────────────────────────────────

class TextProcessingError(AudioComicError):
    """Base exception for text analysis errors."""
    pass


class EncodingError(TextProcessingError):
    """File encoding detection or conversion failed."""
    pass


class DialogueParsingError(TextProcessingError):
    """Dialogue parsing encountered an unrecoverable issue."""
    pass


# ── Project Errors ──────────────────────────────────────────────────────────

class ProjectError(AudioComicError):
    """Base exception for project management errors."""
    pass


class ProjectNotFoundError(ProjectError):
    """Project directory or file not found."""
    pass


class ProjectCorruptedError(ProjectError):
    """Project JSON is corrupted or invalid."""
    pass


# ── Cache Errors ────────────────────────────────────────────────────────────

class CacheError(AudioComicError):
    """Base exception for cache-related errors."""
    pass


class CacheCorruptedError(CacheError):
    """Cache data is corrupted."""
    pass


# ── Configuration Errors ────────────────────────────────────────────────────

class ConfigError(AudioComicError):
    """Base exception for configuration errors."""
    pass


class ConfigValidationError(ConfigError):
    """Configuration file has invalid values."""
    pass


# ── Pipeline Errors ─────────────────────────────────────────────────────────

class PipelineError(AudioComicError):
    """Base exception for pipeline orchestration errors."""
    pass


class PipelineCancelledError(PipelineError):
    """Pipeline was cancelled by the user."""
    pass


class ValidationError(AudioComicError):
    """General validation error for output files."""
    pass
