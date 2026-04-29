# spawnverse/routing/router.py
import math

from ..config import MODEL_REGISTRY
from .complexity import ComplexityScorer


class ModelRouter:
    """
    UCB1 bandit that picks the cheapest capable model for each agent.

    UCB score = (avg_reward × skill_prior) + C × √(ln N_total / n_m)

    Cold start (n_m = 0): seeds avg_reward from the model's declared skill
    prior so unvisited models are explored proportionally to their strength
    rather than all receiving the same ∞ bonus.
    """

    def __init__(self, config: dict) -> None:
        self.cfg              = config
        self.C                = config.get("routing_explore_c", 1.2)
        self.safety_mult      = config.get("routing_context_safety_mult", 3)
        self.tier_floor_enabled = config.get("routing_tier_floor_enabled", True)

    def assign(self, spec: dict, complexity: float, skill: str, domain: str, mem) -> str:
        token_estimate = len(spec.get("task", "").split()) * 4
        blacklist      = set(self.cfg.get("agent_model_blacklist", ["groq/compound"]))

        candidates = {
            mid: info for mid, info in MODEL_REGISTRY.items()
            if info["context_window"] >= token_estimate * self.safety_mult
            and mid not in blacklist
        }
        if not candidates:
            candidates = {mid: info for mid, info in MODEL_REGISTRY.items()
                          if mid not in blacklist} or dict(MODEL_REGISTRY)

        if self.tier_floor_enabled:
            floor      = ComplexityScorer().tier_floor(complexity)
            # API-capable agents need at least tier 2 — tier 1 (8b) can't follow injection instructions.
            if self.cfg.get("external_apis"):
                floor = max(floor, 2)
            floored    = {mid: info for mid, info in candidates.items() if info["tier"] >= floor}
            candidates = floored or dict(MODEL_REGISTRY)

        stats   = mem.get_model_reputation(domain, skill)
        N_total = sum(s["total_runs"] for s in stats.values()) + 1

        best_model, best_ucb = None, -999.0

        for mid, info in candidates.items():
            skill_prior = info["skills"].get(skill, 0.3)
            s           = stats.get(mid, {"total_runs": 0, "avg_reward": skill_prior})
            n_m, avg_r  = s["total_runs"], s["avg_reward"]

            if n_m == 0:
                ucb = skill_prior + self.C * math.sqrt(math.log(N_total + 1))
            else:
                ucb = avg_r * skill_prior + self.C * math.sqrt(math.log(N_total) / n_m)

            if ucb > best_ucb:
                best_ucb, best_model = ucb, mid

        return best_model or list(candidates.keys())[0]
