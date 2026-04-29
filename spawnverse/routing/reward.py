# spawnverse/routing/reward.py
from ..config import MODEL_REGISTRY


class RewardEngine:
    """
    Reward / penalty after each agent run.

    Success:  reward  = drift × quality × reward_mult
    Failure:  penalty = -(gap × penalty_mult)

    Cheap models get higher reward_mult, so a successful cheap model
    earns a disproportionately large reward — teaching the bandit to
    prefer cheap models for tasks they can handle.
    """

    def compute(
        self,
        model_id: str,
        drift: float,
        quality: float,
        domain: str,
        skill: str,
        config: dict,
    ) -> float:
        info    = MODEL_REGISTRY.get(model_id, {})
        r_mult  = info.get("reward_mult",  1.0)
        p_mult  = info.get("penalty_mult", 0.5)
        thresh  = config.get("drift_threshold", 0.65)
        q_min   = config.get("quality_min",     0.45)

        if skill in ("extract", "format"):
            # Data agents: quality is the primary signal, but drift < 0.1 means
            # the output is provably off-topic (wrong country, wrong domain) — penalise.
            if drift < 0.1:
                reward = -(p_mult * 0.3)
            elif quality >= q_min:
                reward = quality * r_mult
            else:
                reward = -((q_min - quality) * p_mult)
        elif drift >= thresh and quality >= q_min:
            reward = drift * quality * r_mult
        else:
            # Penalise on whichever dimension fell short (drift or quality)
            drift_gap   = thresh - min(drift, thresh)
            quality_gap = q_min  - min(quality, q_min)
            gap = max(drift_gap, quality_gap)
            reward = -(gap * p_mult)

        return round(reward, 4)
