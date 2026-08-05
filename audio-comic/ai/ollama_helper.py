"""Use a local Ollama model to plan expressive, lossless narration."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from models.segment import Segment, SegmentType
from ai.parameter_policy import ParameterPolicy
from utils.logging_config import get_logger

logger = get_logger("ai.ollama_helper")

_NARRATION_MODEL_PRIORITY = ("qwen2.5:1.5b", "llama3.2:3b", "gemma4:12b")
_STORY_MODEL_PRIORITY = ("qwen2.5:7b", "qwen2.5:1.5b", "llama3.2:3b")
_EMOTIONS = {
    "neutral", "calm", "mysterious", "tense", "sad", "happy",
    "angry", "fearful", "excited", "contemplative", "whisper",
}


class OllamaNarrationHelper:
    """Generate per-segment reading directions without rewriting story text."""

    def __init__(
        self,
        model: str = "",
        story_model: str = "",
        base_url: str | None = None,
        timeout: int | None = 3600,
        batch_size: int = 12,
        retries: int = 1,
        parameter_policy: ParameterPolicy | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11435")).rstrip("/")
        self.timeout = timeout
        self.batch_size = max(1, batch_size)
        self.retries = max(1, retries)
        self.model = model or self.recommended_model(_NARRATION_MODEL_PRIORITY)
        self.story_model = story_model or self.recommended_model(_STORY_MODEL_PRIORITY)
        self.parameter_policy = parameter_policy

    def list_models(self) -> list[str]:
        payload = self._request("GET", "/api/tags")
        return [item.get("name", "") for item in payload.get("models", []) if item.get("name")]

    def server_ready(self) -> bool:
        try:
            request = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(request, timeout=1) as response:
                return response.status == 200
        except (OSError, urllib.error.URLError):
            return False

    def ensure_server(self, startup_timeout: int = 20) -> tuple[bool, str]:
        """Start ``ollama serve`` in the background when the API is offline."""
        if self.server_ready():
            return True, "Ollama server đang chạy"
        executable = _find_ollama_executable()
        if executable is None:
            return False, "Không tìm thấy Ollama. Chạy installer với --with-ai"
        try:
            kwargs: dict[str, Any] = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([executable, "serve"], **kwargs)
        except OSError as exc:
            return False, f"Không thể bật Ollama server: {exc}"
        deadline = time.monotonic() + max(1, startup_timeout)
        while time.monotonic() < deadline:
            if self.server_ready():
                return True, f"Đã tự động bật Ollama server ({executable})"
            time.sleep(0.5)
        return False, "Đã gọi ollama serve nhưng API không sẵn sàng sau thời gian chờ"

    def recommended_model(self, priority: tuple[str, ...] | None = None) -> str:
        try:
            available = self.list_models()
        except (OSError, ValueError):
            return priority[0] if priority else "qwen2.5:1.5b"
        for candidate in (priority or _NARRATION_MODEL_PRIORITY):
            if candidate in available:
                return candidate
        excluded = ("embed", "moondream")
        return next((name for name in available if not any(x in name.lower() for x in excluded)), "")

    def enhance_segments(self, segments: list[Segment]) -> list[Segment]:
        """Add robust structured guidance while preserving every source character."""
        enhanced: list[Segment] = []
        speech = [segment for segment in segments if not segment.is_silent]
        plans: dict[int, dict[str, Any]] = {}
        for batch in _batches(speech, self.batch_size):
            last_error: Exception | None = None
            for attempt in range(1, self.retries + 1):
                try:
                    plans.update(self._plan_batch(batch))
                    last_error = None
                    break
                except (OSError, ValueError, KeyError) as exc:
                    last_error = exc
                    if attempt < self.retries:
                        logger.warning(
                            "Ollama guidance lỗi lần %d/%d; đang thử lại: %s",
                            attempt, self.retries, exc,
                        )
                        time.sleep(min(8.0, 0.5 * 2 ** (attempt - 1)))
            if last_error is not None:
                logger.warning("Ollama guidance failed; using heuristic fallback: %s", last_error)
                for segment in batch:
                    plans[segment.segment_id] = self._fallback_plan(segment)

        for segment in segments:
            if segment.is_silent:
                enhanced.append(segment)
                continue
            plan = plans.get(segment.segment_id, self._fallback_plan(segment))
            # User TTS settings are authoritative. AI may choose emotion and
            # pauses, but must never silently alter playback speed or pitch.
            speed = segment.speed
            pitch = segment.pitch
            pause = int(_clamp(float(plan.get("pause_ms", segment.pause_after_ms)), 180, 1600))
            emotion = str(plan.get("emotion", segment.emotion)).lower()
            if emotion not in _EMOTIONS:
                emotion = segment.emotion if segment.emotion in _EMOTIONS else "neutral"
            options = self.parameter_policy.options(plan) if self.parameter_policy else {}
            reason = str(plan.get("reason", "AI Director chapter profile")).strip()
            enhanced.append(replace(
                segment,
                emotion=emotion,
                speed=speed,
                pitch=pitch,
                pause_after_ms=pause,
                reading_instruction=str(plan.get("instruction", "")).strip(),
                inference_options=options,
                attempt_history=[{"attempt": 0, "config": options, "reason": reason}],
            ))
        return enhanced

    def _plan_batch(self, segments: list[Segment]) -> dict[int, dict[str, Any]]:
        items = [
            {
                "id": s.segment_id,
                "type": s.type.value,
                "speaker": s.speaker,
                "text": s.text,
            }
            for s in segments
        ]
        prompt = (
            "Bạn là đạo diễn giọng đọc tiểu thuyết tiếng Việt. Phân tích từng đoạn, "
            "không sửa, không tóm tắt và không lặp lại nội dung. Trả JSON duy nhất dạng "
            "{\"items\":[{\"id\":1,\"emotion\":\"calm\",\"speed\":0.98,"
            "\"pitch\":-0.01,\"pause_ms\":500,\"instruction\":\"đọc trầm, chậm, nhấn cuối câu\"}]}. "
            "emotion chỉ dùng neutral, calm, mysterious, tense, sad, happy, angry, fearful, "
            "excited, contemplative, whisper. Không trả về speed/pitch và không thay đổi "
            "thông số TTS của user. Chỉ trả pause_ms 180-1600. Giữ chuyển tiếp cảm xúc "
            "tự nhiên giữa các đoạn.\nDữ liệu:\n"
            "For each item, also return temperature, top_k, top_p, repetition_penalty and a reason; "
            "these are bounded by the supplied user policy. Do not change voice, model, device, pitch or tempo.\n"
            + json.dumps(items, ensure_ascii=False)
        )
        response = self._request("POST", "/api/chat", {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "seed": 42},
            "messages": [{"role": "user", "content": prompt}],
        })
        content = response.get("message", {}).get("content", "")
        parsed = json.loads(content)
        result: dict[int, dict[str, Any]] = {}
        for item in parsed.get("items", []):
            segment_id = int(item["id"])
            result[segment_id] = item
        if not result:
            raise ValueError("Ollama trả về kế hoạch rỗng")
        return result

    @staticmethod
    def _fallback_plan(segment: Segment) -> dict[str, Any]:
        emotion = segment.emotion or "neutral"
        speed = segment.speed
        pause = segment.pause_after_ms
        instruction = "đọc tự nhiên, rõ chữ"
        text = segment.text.lower()
        if segment.type == SegmentType.CHAPTER_TITLE:
            emotion, speed, pause = "mysterious", 0.94, 1200
            instruction = "đọc trang trọng, chậm, ngắt rõ"
        elif any(mark in text for mark in ("!", "chạy", "hét", "la lên")):
            emotion, speed = "excited", 1.04
            instruction = "tăng năng lượng, nhấn động từ"
        elif any(word in text for word in ("sợ", "kinh hoàng", "run rẩy", "bóng tối")):
            emotion, speed = "fearful", 0.97
            instruction = "hạ giọng, căng thẳng, nhấn từ khóa"
        elif segment.type == SegmentType.INNER_THOUGHT:
            emotion, speed = "contemplative", 0.95
            instruction = "đọc nhỏ, suy tư, mềm ở cuối câu"
        return {
            "emotion": emotion,
            "speed": speed,
            "pitch": segment.pitch,
            "pause_ms": pause,
            "instruction": instruction,
        }

    def generate_story_prompt(self, chapter_text: str, context_md: str = "") -> str:
        """Generate a detailed scene description for image generation using story model (7b)."""
        system_prompt = (
            "Bạn là đạo diễn hình ảnh, đang xử lý truyện được viết bằng tiếng Việt. "
            "Tiếng Việt chỉ là ngôn ngữ văn bản, không phải bằng chứng về văn hóa Việt Nam. "
            "Chỉ dùng văn hóa, thời đại, trang phục, kiến trúc, nhân vật, vật thể và phép thuật "
            "có bằng chứng trong chương hoặc canon; thiếu bằng chứng thì giữ fantasy trung tính, không tự bịa. "
            "Dựa vào đoạn văn bản và ngữ cảnh, hãy mô tả chi tiết 1-3 cảnh hình ảnh "
            "để làm ảnh bìa/video. Mô tả bằng tiếng Anh, phong cách cinematic, "
            "dark fantasy, chi tiết ánh sáng, màu sắc, biểu cảm nhân vật, bối cảnh. "
            "Chỉ trả JSON dạng "
            "{\"scenes\":[{\"title\":\"...\",\"description\":\"...\",\"mood\":\"...\",\"lighting\":\"...\",\"colors\":\"...\"}]}"
        )
        user_content = f"--- NGỮ CẢI ---\n{context_md}\n--- CHƯƠNG ---\n{chapter_text[:6000]}" if context_md else chapter_text[:6000]
        response = self._request("POST", "/api/chat", {
            "model": self.story_model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.4, "seed": 42},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        })
        content = response.get("message", {}).get("content", "")
        return content

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        body = json.dumps(data).encode("utf-8") if data is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=body, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise OSError(f"Không kết nối được Ollama tại {self.base_url}: {exc}") from exc


def _batches(items: list[Segment], size: int) -> Iterable[list[Segment]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _find_ollama_executable() -> str | None:
    """Resolve real Ollama binaries before Windows package-manager shims."""
    candidates: list[Path] = []
    if os.name == "nt":
        home = Path.home()
        local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        candidates.extend([
            home / "scoop" / "apps" / "ollama" / "current" / "ollama.exe",
            local_app_data / "Programs" / "Ollama" / "ollama.exe",
        ])
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ollama")
