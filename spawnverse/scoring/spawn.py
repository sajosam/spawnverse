# spawnverse/scoring/spawn.py
class SpawnScorer:
    """
    Heuristic score for agent sub-spawn requests.
    Rejects vague roles, duplicate IDs, and tasks that are too short.
    Score range: 0.0–1.0. Requests below min_spawn_score are dropped.
    """

    VAGUE_TERMS = {
        "sub role", "sub task", "helper", "assistant", "booker", "processor",
        "handler", "worker", "sub agent", "subagent", "do work", "complete task",
        "perform task", "generate report",
    }
    ACTION_VERBS = {
        "research", "find", "calculate", "compare", "summarise", "evaluate",
        "validate", "extract", "compile", "recommend", "estimate", "identify",
        "rank", "filter", "verify", "draft", "generate", "plan", "search",
        "review", "assess", "create", "analyse", "analyze", "write", "build",
        "design", "synthesize",
    }

    def score(self, name: str, role: str, task: str, existing_ids: set) -> float:
        s  = 0.0
        rl = role.lower().strip()
        tl = task.lower().strip()

        s += min(len(rl) / 60, 0.15)
        s += min(len(tl) / 80, 0.15)
        if not any(w in rl or w in tl for w in self.VAGUE_TERMS):
            s += 0.30
        if any(w in tl for w in self.ACTION_VERBS):
            s += 0.20
        if name not in existing_ids:
            s += 0.20

        return round(min(s, 1.0), 2)
