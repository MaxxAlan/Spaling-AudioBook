"""Small deterministic optimizer used after a rejected audio candidate."""

from __future__ import annotations

from ai.parameter_policy import ParameterPolicy


def propose_retry(previous: dict[str, float], reasons: list[str], policy: ParameterPolicy) -> dict[str, float]:
    """Đề xuất tham số retry thông minh hơn cho P0 miss-chữ.

    - missing_critical_words / content_mismatch / word_omission
      → hạ temperature, tăng max_chars, tăng repetition_penalty nhẹ.
    """
    candidate = dict(previous or policy.base)
    base_temp = policy.base.get("temperature", 0.5)
    base_max = policy.base.get("max_chars", 360)

    miss_reasons = {
        "missing_critical_words", "content_mismatch",
        "word_omission", "low_integrity",
    }
    if miss_reasons & set(reasons):
        candidate["temperature"] = max(0.25, candidate.get("temperature", base_temp) - 0.08)
        candidate["max_chars"] = min(480, candidate.get("max_chars", base_max) + 40)
        candidate["repetition_penalty"] = candidate.get(
            "repetition_penalty", policy.base.get("repetition_penalty", 1.15)
        ) + 0.04
        candidate["top_p"] = max(0.7, candidate.get("top_p", 0.88) - 0.05)
    elif "clipping" in reasons or "near_silence" in reasons:
        candidate["temperature"] = candidate.get("temperature", base_temp) - 0.04
        candidate["top_p"] = candidate.get("top_p", policy.base.get("top_p", 0.88)) - 0.03
    elif "duration_too_short" in reasons:
        candidate["temperature"] = candidate.get("temperature", base_temp) + 0.04
        candidate["top_k"] = candidate.get("top_k", policy.base.get("top_k", 20)) + 3
    else:
        candidate["repetition_penalty"] = candidate.get(
            "repetition_penalty", policy.base.get("repetition_penalty", 1.15)
        ) + 0.03
    return policy.options(candidate)
