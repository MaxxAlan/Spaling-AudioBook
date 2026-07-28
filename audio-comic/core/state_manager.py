"""State manager for pipeline progress tracking and resume.

Persists pipeline state to project_state.json, enabling resume
after crashes, pauses, or application restarts.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

from utils.logging_config import get_logger

logger = get_logger("core.state_manager")


@dataclass
class PipelineState:
    """Represents the current state of a project's processing pipeline.

    Attributes:
        project_id: Unique project identifier.
        status: Current pipeline stage.
        total_segments: Total number of segments to process.
        completed_segments: Number of segments processed successfully.
        failed_segments: List of segment IDs that failed.
        audio_completed: Whether audio concatenation is done.
        started_at: ISO timestamp when pipeline started.
        updated_at: ISO timestamp of last update.
        elapsed_seconds: Total elapsed processing time.
        error_message: Last error message, if any.
    """

    project_id: str = ""
    status: str = "pending"
    total_segments: int = 0
    completed_segments: int = 0
    completed_segment_ids: List[int] = field(default_factory=list)
    failed_segments: List[int] = field(default_factory=list)
    audio_completed: bool = False
    started_at: str = ""
    updated_at: str = ""
    elapsed_seconds: float = 0.0
    error_message: str = ""

    @property
    def progress_percent(self) -> float:
        """Calculate overall progress percentage."""
        if self.total_segments == 0:
            return 0.0

        tts_progress = (self.completed_segments / self.total_segments) * 90
        audio_progress = 10.0 if self.audio_completed else 0.0
        return min(100.0, tts_progress + audio_progress)

    @property
    def is_complete(self) -> bool:
        """Check if the entire pipeline is complete."""
        return (
            self.completed_segments >= self.total_segments
            and self.audio_completed
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> PipelineState:
        """Deserialize from dictionary."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        state = cls(**filtered)
        if not state.completed_segment_ids and state.completed_segments:
            state.completed_segment_ids = list(range(1, state.completed_segments + 1))
        return state


class StateManager:
    """Manages pipeline state persistence for resume capability.

    Saves state to a JSON file in the project directory,
    allowing the pipeline to resume from the last checkpoint
    after a crash or user cancellation.
    """

    def __init__(self, state_file: Path) -> None:
        """Initialize state manager.

        Args:
            state_file: Path to the project_state.json file.
        """
        self._state_file = state_file
        self._state: Optional[PipelineState] = None
        self._start_time: float = 0.0

    def load(self) -> PipelineState:
        """Load existing state or create a new one.

        Returns:
            Current pipeline state.
        """
        if self._state_file.exists():
            try:
                with open(self._state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._state = PipelineState.from_dict(data)
                logger.info(
                    "Loaded state: %s (progress: %.1f%%)",
                    self._state.status, self._state.progress_percent,
                )
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("State file corrupted, creating new: %s", e)
                self._state = PipelineState()
        else:
            self._state = PipelineState()

        return self._state

    def save(self) -> None:
        """Save current state to disk."""
        if self._state is None:
            return

        self._state.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        if self._start_time > 0:
            self._state.elapsed_seconds = time.time() - self._start_time

        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._state_file, "w", encoding="utf-8") as f:
            json.dump(self._state.to_dict(), f, ensure_ascii=False, indent=2)

    def initialize(self, project_id: str, total_segments: int) -> PipelineState:
        """Initialize state for a new pipeline run.

        Args:
            project_id: Project identifier.
            total_segments: Total segments to process.

        Returns:
            Initialized pipeline state.
        """
        if (
            self._state
            and self._state.project_id == project_id
            and self._state.total_segments == total_segments
            and self._state.completed_segments > 0
        ):
            self._start_time = time.time()
            self._state.status = "resuming"
            self.save()
            return self._state

        self._state = PipelineState(
            project_id=project_id,
            status="initialized",
            total_segments=total_segments,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        )
        self._start_time = time.time()
        self.save()
        logger.info("Initialized state: %s (%d segments)", project_id, total_segments)
        return self._state

    def update_status(self, status: str) -> None:
        """Update the pipeline status.

        Args:
            status: New status string.
        """
        if self._state:
            self._state.status = status
            self.save()

    def mark_segment_complete(self, segment_id: int) -> None:
        """Mark a segment as successfully processed.

        Args:
            segment_id: Completed segment ID.
        """
        if self._state:
            if segment_id not in self._state.completed_segment_ids:
                self._state.completed_segment_ids.append(segment_id)
            self._state.completed_segments = len(self._state.completed_segment_ids)
            # Remove from failed list if it was there (retry success)
            if segment_id in self._state.failed_segments:
                self._state.failed_segments.remove(segment_id)
            self.save()

    def mark_segment_failed(self, segment_id: int, error: str = "") -> None:
        """Mark a segment as failed.

        Args:
            segment_id: Failed segment ID.
            error: Error description.
        """
        if self._state:
            if segment_id not in self._state.failed_segments:
                self._state.failed_segments.append(segment_id)
            self._state.error_message = error
            self.save()

    def mark_audio_complete(self) -> None:
        """Mark audio concatenation as complete."""
        if self._state:
            self._state.audio_completed = True
            self.save()

    def mark_error(self, error: str) -> None:
        """Record an error without changing status.

        Args:
            error: Error message.
        """
        if self._state:
            self._state.error_message = error
            self._state.status = "error"
            self.save()

    def get_resumable_segments(self) -> int:
        """Get the next segment ID to process for resume.

        Returns:
            The segment ID to resume from (0-based count of completed).
        """
        if self._state:
            if self._state.completed_segment_ids:
                completed = set(self._state.completed_segment_ids)
                next_id = 1
                while next_id in completed:
                    next_id += 1
                return next_id - 1
            return self._state.completed_segments
        return 0

    @property
    def state(self) -> Optional[PipelineState]:
        """Current pipeline state."""
        return self._state

    def reset(self) -> None:
        """Reset state for a fresh pipeline run."""
        if self._state:
            project_id = self._state.project_id
            total = self._state.total_segments
            self.initialize(project_id, total)
