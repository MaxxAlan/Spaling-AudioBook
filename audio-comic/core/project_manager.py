"""Project manager for CRUD operations on Audio-Comic projects.

Handles creating, opening, saving, and listing projects.
Each project has a standardized directory structure.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List, Optional

from core.exceptions import ProjectError, ProjectNotFoundError, ProjectCorruptedError
from models.project import Project
from utils.paths import (
    create_project_structure,
    get_project_dir,
    slugify,
    ensure_dir,
)
from utils.encoding import read_text_file
from utils.logging_config import get_logger

logger = get_logger("core.project_manager")


class ProjectManager:
    """Manages project lifecycle: create, save, open, list, delete.

    Each project is a directory containing all files for one chapter:
    source text, segments, voice profiles, cache, audio, poster, video.
    """

    def __init__(self, projects_root: Path) -> None:
        """Initialize project manager.

        Args:
            projects_root: Root directory for all projects.
        """
        self._projects_root = projects_root
        ensure_dir(self._projects_root)

    def create_project(
        self,
        story_name: str,
        chapter_number: int,
        chapter_title: str = "",
        source_text: str = "",
        source_file: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        language: str = "vi",
    ) -> Project:
        """Create a new project with directory structure.

        Args:
            story_name: Name of the story.
            chapter_number: Chapter number.
            chapter_title: Optional chapter title.
            source_text: Direct text content.
            source_file: Path to a .txt file to import.
            output_dir: Custom output directory.
            language: Content language.

        Returns:
            The created Project instance.

        Raises:
            ProjectError: If project creation fails.
        """
        story_slug = slugify(story_name)
        project_dir = get_project_dir(self._projects_root, story_slug, chapter_number)

        # Create directory structure
        subdirs = create_project_structure(project_dir)
        logger.info("Created project directory: %s", project_dir)

        # Load source text
        if source_file and source_file.exists():
            source_text = read_text_file(source_file)
            # Copy source file to project
            shutil.copy2(str(source_file), str(subdirs["source"] / source_file.name))
        elif source_text:
            # Save source text
            source_path = subdirs["source"] / "chapter.txt"
            source_path.write_text(source_text, encoding="utf-8")

        if not source_text:
            logger.warning("Creating project with empty source text")

        # Create project
        project = Project(
            story_name=story_name,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            language=language,
            source_text=source_text,
            project_dir=str(project_dir),
            output_dir=str(output_dir or project_dir),
        )

        # Save project file
        self.save_project(project)

        logger.info(
            "Project created: %s (chapter %d)",
            story_name, chapter_number,
        )
        return project

    def save_project(self, project: Project) -> Path:
        """Save project state to project.json.

        Args:
            project: Project to save.

        Returns:
            Path to the project.json file.
        """
        if not project.project_dir:
            raise ProjectError("Project has no project_dir set")

        project_dir = Path(project.project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)

        project_file = project_dir / "project.json"
        project.save(project_file)

        # Also save segments separately for easier inspection
        if project.segments:
            segments_file = project_dir / "script" / "segments.json"
            segments_file.parent.mkdir(parents=True, exist_ok=True)
            with open(segments_file, "w", encoding="utf-8") as f:
                json.dump(
                    [s.to_dict() for s in project.segments],
                    f, ensure_ascii=False, indent=2,
                )

        logger.info("Saved project: %s", project_file)
        return project_file

    def open_project(self, project_dir: Path) -> Project:
        """Open an existing project from its directory.

        Args:
            project_dir: Path to the project directory.

        Returns:
            The loaded Project instance.

        Raises:
            ProjectNotFoundError: If project.json doesn't exist.
            ProjectCorruptedError: If project.json is invalid.
        """
        project_file = project_dir / "project.json"

        if not project_file.exists():
            raise ProjectNotFoundError(
                f"project.json không tồn tại trong: {project_dir}",
            )

        try:
            project = Project.load(project_file)
            project.project_dir = str(project_dir)
            logger.info("Opened project: %s", project.project_id)
            return project
        except json.JSONDecodeError as e:
            raise ProjectCorruptedError(
                f"project.json bị hỏng: {e}",
                details=str(e),
            )
        except Exception as e:
            raise ProjectCorruptedError(
                f"Không thể mở project: {e}",
                details=str(e),
            )

    def list_projects(self) -> List[dict]:
        """List all projects in the projects root.

        Returns:
            List of dicts with basic project info (name, chapter, path, status).
        """
        projects = []

        if not self._projects_root.exists():
            return projects

        for project_dir in sorted(self._projects_root.iterdir()):
            if not project_dir.is_dir():
                continue

            project_file = project_dir / "project.json"
            if not project_file.exists():
                continue

            try:
                with open(project_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                projects.append({
                    "story_name": data.get("story_name", ""),
                    "chapter_number": data.get("chapter_number", 0),
                    "chapter_title": data.get("chapter_title", ""),
                    "path": str(project_dir),
                    "has_audio": (project_dir / "audio").exists(),
                    "has_poster": (project_dir / "poster").exists(),
                    "has_video": (project_dir / "video").exists(),
                })
            except (json.JSONDecodeError, OSError):
                logger.warning("Skipping corrupted project: %s", project_dir.name)
                continue

        return projects

    def delete_project(self, project_dir: Path, confirm: bool = False) -> bool:
        """Delete a project and all its files.

        Args:
            project_dir: Path to the project directory.
            confirm: Safety flag — must be True to actually delete.

        Returns:
            True if deleted successfully.
        """
        if not confirm:
            logger.warning("Delete not confirmed for: %s", project_dir)
            return False

        if project_dir.exists():
            shutil.rmtree(project_dir)
            logger.info("Deleted project: %s", project_dir)
            return True

        return False

    @property
    def projects_root(self) -> Path:
        """Get the projects root directory."""
        return self._projects_root
