# spawnverse/scoring/quality.py
from ..llm import _llm, _safe_json

_USELESS_PHRASES = [
    "no context", "no relevant", "no data", "not available",
    "unable to", "insufficient data", "no information",
]


class OutputQualityScorer:
    """
    Scores 0–1: independent LLM-as-judge on every agent output.
    Short outputs containing known useless phrases are short-circuited to 0.05
    without an extra LLM call.
    """

    def score(self, task: str, output, client, config: dict) -> float:
        if not output or (isinstance(output, dict) and not any(output.values())):
            return 0.0

        output_str = str(output).lower()
        if len(output_str) < 100 and any(p in output_str for p in _USELESS_PHRASES):
            return 0.05

        text, _ = _llm(
            client, config,
            [{"role": "system", "content": "Return ONLY valid JSON. Start with {."},
             {"role": "user",   "content": (
                 f"Score output quality 0.0-1.0.\n"
                 f"TASK: {task[:150]}\nOUTPUT: {str(output)[:300]}\n"
                 "1.0=excellent specific answer. 0.0=empty or wrong domain.\n"
                 'Return ONLY: {"score": 0.X}'
             )}],
            max_tokens=80,
        )
        r = _safe_json(text)
        try:
            return round(max(0.0, min(1.0, float(r.get("score", 0.5)))), 3)
        except (TypeError, ValueError):
            return 0.0
