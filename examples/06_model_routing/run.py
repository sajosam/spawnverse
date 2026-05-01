#!/usr/bin/env python3
"""
Example 06 — Full Capability Showcase
══════════════════════════════════════════════════════════════════════
Every SpawnVerse feature in one run:

  ✦ Model routing    UCB1 bandit picks cheapest capable model per agent
  ✦ External APIs    weather · forex · country · news · crypto
  ✦ Soul system      proven constitutions injected on warm runs
  ✦ Fossil record    every agent's DNA persists in SQLite across runs
  ✦ 4-layer guardrails  code scan · budget · output · semantic
  ✦ Parallel DAG     5 gathering agents run concurrently; synthesis waits
  ✦ Intent tracker   drift + quality scored on every agent

AGENT PLAN (designed for mixed skill/tier routing):
  Gathering (wave 1 — parallel, no dependencies):
    1. ev_market_analyst       extract   → tier 1–2   EV models, prices, range
    2. forex_analyst           extract   → tier 1–2   INR/USD/EUR/JPY rates (forex API)
    3. climate_risk_analyst    extract   → tier 2     Manufacturing city weather (weather API)
    4. market_context_analyst  research  → tier 3     India country profile + macro (country API)
    5. policy_news_analyst     research  → tier 3     EV policy news + crypto (news + crypto APIs)

  Synthesis (wave 2 — reads all wave-1 outputs):
    6. financial_modeller      code      → tier 4     5-year TCO model per segment
    7. risk_assessor           reason    → tier 4     Macro + climate + policy risks
    8. investment_thesis       synthesize → tier 5    Final VC recommendation

KEY CONFIG FIXES vs naive defaults:
  routing_context_safety_mult: 2   (was 3 → caused groq/compound-mini to get 413s)
  per_agent_tokens: 12_000         (was 8_000 → too small → 413 in think())
  per_agent_tokens_synthesis: 25_000
  soul_min_runs: 2                 (was 3 → soul injections start sooner)
  external_apis: True              (auto-injects all matching API helpers)
  timeout_depth0: 180              (generous for rate-limit retries)

RUNS:
  export GROQ_API_KEY=your_key
  python run.py                    # cold start — bandit explores all models
  python run.py                    # warm start — bandit starts learning
  python run.py                    # exploitation — cheap models win gathering
  python run.py "custom task"      # custom task, routing still applies
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from spawnverse import Orchestrator, DEFAULT_CONFIG

# ── API key ───────────────────────────────────────────────────────────
# Preferred: export GROQ_API_KEY=your_key before running.
# Quick test only — never commit a real key:
os.environ["GROQ_API_KEY"] = ""


CONFIG = {**DEFAULT_CONFIG, **{
    "wave1_agents" : 4,
    "wave2_agents" : 2,
    "model_routing": True,
    "external_apis": True,
    "db_path"      : "sv_hiring.db",
    "agents_dir"   : ".sv_hiring",
}}

TASK = {
    "description": (
        "Hiring market intelligence report for a startup building an AI team in India. "
        "Get latest tech hiring news and layoff trends. "
        "Get India country profile. "
        "Get USD/INR rate to benchmark salaries in USD. "
        "Research salary ranges for: ML Engineer, Data Scientist, AI Product Manager "
        "in Bangalore, Hyderabad, and remote roles. "
        "Identify the top 5 companies competing for the same talent. "
        "Suggest hiring strategy, compensation bands, and interview process."
    ),
    "context": {"roles": ["ML Engineer", "Data Scientist", "AI PM"], "city": "Bangalore", "headcount": 10},
}

if __name__ == "__main__":
    if os.path.exists(CONFIG["agents_dir"]): shutil.rmtree(CONFIG["agents_dir"])
    Orchestrator(CONFIG).run(TASK)