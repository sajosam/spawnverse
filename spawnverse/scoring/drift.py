# spawnverse/scoring/drift.py
from ..llm import _llm, _safe_json


class IntentDriftScorer:
    """
    Scores 0–1: how well an agent's output addresses the root task.
    1.0 = fully on-task, 0.0 = completely unrelated.
    Returns 0.5 on empty output (neutral, not penalised).
    """

    def score(self, task: str, role: str, output, client, config: dict) -> float:
        if not output or (isinstance(output, dict) and not any(output.values())):
            return 0.5

        text, _ = _llm(
            client, config,
            [{"role": "system", "content": "Return ONLY valid JSON. Start with {."},
             {"role": "user",   "content": (
                 f"Score 0.0-1.0: does this output address the task?\n"
                 f"TASK: {task[:150]}\nROLE: {role}\n"
                 f"OUTPUT (first 600 chars): {str(output)[:600]}\n"
                 "1.0=excellent relevant content. 0.0=empty or completely wrong domain.\n"
                 "Data-gathering agents (weather, rates, country data, prices, news) score 0.7-1.0 "
                 "when the data they return is relevant to the task domain.\n"
                 'Return ONLY: {"score": 0.X}'
             )}],
            max_tokens=80,
        )
        r = _safe_json(text)
        try:
            return round(max(0.0, min(1.0, float(r.get("score", 0.5)))), 3)
        except (TypeError, ValueError):
            return 0.5
