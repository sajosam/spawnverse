# spawnverse/routing/complexity.py
from ..config import SKILL_KEYWORDS


class ComplexityScorer:
    """
    Zero-LLM complexity estimation from an agent spec.
    Returns (complexity: float 0–1, skill: str, domain: str).

    Signals used:
      1. Task word count          → longer = harder
      2. Upstream dependency count → more deps = synthesis = harder
      3. Role verb type           → synthesis verbs score higher than gathering
      4. Spawn depth              → deeper = harder
    """

    SYNTHESIS_VERBS = {
        "synthesize", "combine", "merge", "integrate", "compile",
        "consolidate", "aggregate", "compare", "evaluate", "plan",
        "recommend", "rank", "assess", "write report", "final",
    }
    GATHERING_VERBS = {
        "fetch", "get", "retrieve", "find", "search", "collect",
        "look up", "extract", "scrape", "gather",
    }
    DOMAIN_KEYWORDS = {
        "finance":    ["invest", "stock", "financial", "budget", "cost",
                       "revenue", "market", "valuation", "portfolio",
                       "aed", "inr", "usd", "forex", "currency"],
        "travel":     ["trip", "hotel", "flight", "itinerary", "city",
                       "country", "tourist", "visa", "destination"],
        "code":       ["code", "function", "api", "backend", "database",
                       "deploy", "bug", "script", "implement", "algorithm"],
        "research":   ["research", "analyse", "compare", "evaluate",
                       "synthesize", "report", "study", "survey"],
        "weather":    ["weather", "temperature", "forecast", "climate",
                       "rain", "humidity"],
        "data":       ["data", "parse", "csv", "json", "table", "dataset",
                       "schema", "extract"],
        "realestate": ["property", "real estate", "apartment", "villa",
                       "rent", "mortgage", "developer", "off-plan", "rera"],
    }

    def score(self, spec: dict) -> tuple[float, str, str]:
        task_l = spec.get("task", "").lower()
        role_l = spec.get("role", "").lower()
        full   = task_l + " " + role_l

        s = 0.0
        s += min(len(spec.get("task", "").split()) / 60, 0.20)
        s += min(len(spec.get("depends_on", [])) * 0.15, 0.30)

        if any(v in full for v in self.SYNTHESIS_VERBS):
            s += 0.30
        elif any(v in full for v in self.GATHERING_VERBS):
            s += 0.05

        s += spec.get("_depth", 0) * 0.10

        skill = self._detect_skill(full)
        # Agents with upstream dependencies are synthesizers — override extract misclassification.
        # "gather" in task descriptions (e.g. "gather upstream data and synthesize") triggers
        # the extract skill keyword even though the agent is doing synthesis.
        if spec.get("depends_on") and skill == "extract":
            skill = "synthesize" if any(v in full for v in self.SYNTHESIS_VERBS) else "plan"

        return round(min(s, 1.0), 3), skill, self._detect_domain(full)

    def tier_floor(self, complexity: float) -> int:
        if complexity < 0.25: return 1
        if complexity < 0.45: return 2
        if complexity < 0.65: return 3
        if complexity < 0.80: return 4
        return 5

    def _detect_skill(self, text: str) -> str:
        scores = {skill: sum(1 for k in kws if k in text)
                  for skill, kws in SKILL_KEYWORDS.items()}
        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return "synthesize" if any(v in text for v in self.SYNTHESIS_VERBS) else "extract"
        return best

    def _detect_domain(self, text: str) -> str:
        for domain, keywords in self.DOMAIN_KEYWORDS.items():
            if any(k in text for k in keywords):
                return domain
        return "general"
