"""Từ điển phát âm tên riêng cho pipeline TTS.

File JSON là nguồn sự thật duy nhất cho cách đọc tên riêng fantasy.
Thay thế có word-boundary để không đụng vào từ dài hơn (Rosselt ≠ Rosseltian).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Pattern

from utils.logging_config import get_logger

logger = get_logger("text_processing.pronunciation")

DEFAULT_RELATIVE_PATH = Path("config") / "pronunciation_dict.json"


def _candidate_paths(path: str | Path) -> list[Path]:
    """Trả về các vị trí có thể chứa file từ điển."""
    candidate = Path(path)
    if candidate.is_absolute():
        return [candidate]
    # app root = thư mục audio-comic (cha của text_processing/)
    app_root = Path(__file__).resolve().parent.parent
    return [Path.cwd() / candidate, app_root / candidate]


class PronunciationDict:
    """Load và áp dụng từ điển phát âm tên riêng.

    Ví dụ: ``"Rosselt và Teident"`` → ``"Rốt-sen và Tay-đen"``.
    Không thay thế bên trong từ dài hơn nhờ word-boundary.
    """

    def __init__(self, path: str = "config/pronunciation_dict.json") -> None:
        self.requested_path = str(path)
        self.path: Path | None = None
        self.entries: Dict[str, str] = {}
        self._pattern: Pattern[str] | None = None
        self._lookup: Dict[str, str] = {}
        self.reload()

    def _resolve_path(self) -> Path | None:
        candidates = _candidate_paths(self.requested_path)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        logger.warning(
            "Không tìm thấy từ điển phát âm: %s (đã thử: %s)",
            self.requested_path,
            ", ".join(str(c) for c in candidates),
        )
        return None

    def reload(self) -> None:
        """Nạp lại file JSON và biên dịch pattern thay thế."""
        self.path = self._resolve_path()
        self.entries = {}
        self._pattern = None
        self._lookup = {}

        if self.path is None:
            return

        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            logger.warning("Không đọc được từ điển phát âm %s: %s", self.path, exc)
            return

        raw_entries = payload.get("entries", {}) if isinstance(payload, dict) else {}
        for key, value in raw_entries.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            key = key.strip()
            value = value.strip()
            if key and value:
                self.entries[key] = value

        if not self.entries:
            logger.warning("Từ điển phát âm rỗng: %s", self.path)
            return

        alternatives = sorted(self.entries, key=len, reverse=True)
        body = "|".join(
            rf"(?<!\w){re.escape(key)}(?!\w)" for key in alternatives
        )
        self._pattern = re.compile(body, re.IGNORECASE)
        self._lookup = {key.casefold(): value for key, value in self.entries.items()}
        logger.debug(
            "Đã nạp %d mục phát âm từ %s", len(self.entries), self.path
        )

    def apply(self, text: str) -> str:
        """Thay tên riêng trong văn bản bằng cách đọc tiếng Việt.

        So khớp không phân biệt hoa/thường và có word-boundary.

        Args:
            text: Văn bản đã qua ``VietnameseTextNormalizer``.

        Returns:
            Văn bản với tên riêng đã được thay cách đọc.
        """
        if not text or self._pattern is None:
            return text

        def _replace(match: re.Match) -> str:
            return self._lookup.get(match.group(0).casefold(), match.group(0))

        return self._pattern.sub(_replace, text)

    @property
    def is_loaded(self) -> bool:
        """True nếu từ điển đã nạp được ít nhất một mục."""
        return bool(self.entries)
