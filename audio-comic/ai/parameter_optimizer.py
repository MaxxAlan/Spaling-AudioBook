"""Small deterministic optimizer used after a rejected audio candidate."""

from __future__ import annotations

from ai.parameter_policy import ParameterPolicy


def propose_retry(previous: dict[str, float], reasons: list[str], policy: ParameterPolicy) -> dict[str, float]:
    candidate = dict(previous or policy.base)
    if "clipping" in reasons or "near_silence" in reasons:
        candidate["temperature"] = candidate.get("temperature", policy.base["temperature"]) - 0.04
        candidate["top_p"] = candidate.get("top_p", policy.base["top_p"]) - 0.03
    elif "duration_too_short" in reasons:
        candidate["temperature"] = candidate.get("temperature", policy.base["temperature"]) + 0.04
        candidate["top_k"] = candidate.get("top_k", policy.base["top_k"]) + 3
    else:
        candidate["repetition_penalty"] = candidate.get("repetition_penalty", policy.base["repetition_penalty"]) + 0.03
    return policy.options(candidate)
