#!/usr/bin/env python3
"""
Example 07 — Extreme Capability Showcase
══════════════════════════════════════════════════════════════════════
Pushes every SpawnVerse subsystem simultaneously:

  ✦ Model routing      UCB1 bandit across all 6 model tiers
  ✦ All 5 APIs         forex · country · weather · crypto · news (all explicit)
  ✦ Vector DB + RAG    4-doc knowledge base ingested pre-run; agents rag_context() live
  ✦ Soul system        proven constitutions auto-injected after 2 warm runs
  ✦ Fossil record      every agent's DNA accumulates in SQLite across runs
  ✦ 4-layer guardrails code · budget · output · semantic — all enabled
  ✦ Parallel DAG       5 gathering agents race; 3 synthesis agents wait on deps
  ✦ Intent tracker     drift + quality per agent + system alignment report
  ✦ Dynamic spawns     agents may request depth-2 sub-agents (max_depth=3)
  ✦ Agent messaging    send / broadcast / inbox — cross-agent coordination
  ✦ Routing audit      per-model reward table + accumulated reputation printed

TASK — Global Market Entry Intelligence (Indian B2B SaaS → US / UAE / Japan):
  A Series-B Indian HR-tech startup needs a board-ready intelligence brief
  before committing $2M to simultaneous expansion in three markets.

  Why this task pushes every system:
    • forex        : 3 currency pairs (INR/USD, INR/AED, INR/JPY) live rates
    • country      : profiles for US, UAE, Japan (population, capital, languages)
    • weather      : 4 cities — Mumbai HQ + each target market capital
    • crypto       : BTC + ETH as global tech-funding sentiment proxy
    • news         : latest tech/startup headlines from HackerNews
    • RAG          : India-SaaS expansion playbook + currency risk + TAM framework
    • 5 gathering agents  → tier 1–3 models expected (cheap + capable for extract/research)
    • 3 synthesis agents  → tier 4–5 models expected (reason / plan / synthesize)
    • Soul warm-up        → run 3× to see constitutions injected automatically
    • Dynamic spawn       → funding_market_analyst may spawn a sub-analyst for crypto deep-dive

AGENT DAG:
  Wave 1 — Gathering (parallel, depends_on=[]):
    1. forex_rate_collector          extract   INR/USD · INR/AED · INR/JPY live rates
    2. market_profile_collector      extract   Country profiles: US, UAE, Japan
    3. climate_environment_analyst   extract   Weather for Mumbai, New York, Dubai, Tokyo
    4. funding_market_analyst        research  BTC/ETH prices + tech news headlines
    5. competitive_intelligence      research  TAM + top 5 competitors per market via RAG+think

  Wave 2 — Synthesis (depends_on = all wave-1 ids):
    6. market_scoring_engine         reason    Score 3 markets on 8 dimensions using live data
    7. go_to_market_planner          plan      Per-market entry playbook with hiring + milestones
    8. executive_report_generator    synthesize Board-ready brief + capital allocation rec

MODEL TIER EXPECTATION (cold start — bandit explores, then learns):
  extract   → groq/compound-mini or llama-3.1-8b-instant  (tier 1–2)
  research  → llama-4-scout or qwen3-32b                  (tier 3–4)
  reason    → qwen3-32b                                   (tier 4)
  plan      → qwen3-32b or llama-3.3-70b                  (tier 4–5)
  synthesize→ llama-3.3-70b-versatile                     (tier 5)

HOW TO RUN:
  export GROQ_API_KEY=your_key
  python run.py          # cold start  — bandit explores all tiers
  python run.py          # warm run    — bandit starts converging
  python run.py          # exploitation— cheap models locked in for extract
  python run.py "custom" # override task description
"""

import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from spawnverse import Orchestrator, DEFAULT_CONFIG

# ── API key ───────────────────────────────────────────────────────────
# Preferred: export GROQ_API_KEY=your_key before running.
# Quick test only — never commit a real key:
os.environ["GROQ_API_KEY"] = ""

# ── Knowledge Base — indexed into ChromaDB before wave 1 ──────────────
# Agents call rag_context("query") to retrieve relevant chunks.
# The soul system + vector DB together create true warm-run intelligence.
KNOWLEDGE_BASE = [
    """India SaaS Global Expansion Playbook (2024):
    Indian B2B SaaS companies expanding to the US typically enter via the SMB segment first.
    Average ACV in the US market is 3–5× higher than India for equivalent products.
    Key success factors: localised support in EST timezone, USD billing, SOC2 compliance.
    UAE / Middle East entry is faster due to cultural proximity and no data residency issues.
    Japan requires a Japanese-language product and a local partnership — expect an 18–24 month
    timeline before meaningful revenue. Recommended sequencing: UAE (fastest to first revenue)
    → US (scale + brand) → Japan (long-term moat). Minimum runway required: 18 months before
    first international ARR milestone.""",

    """Currency Risk Management for Indian Startups Expanding Globally:
    INR has depreciated approximately 3–4% annually versus USD over the last five years.
    Startups billing entirely in USD gain a natural hedge against INR weakness.
    AED is pegged to USD at 3.6725 — effectively zero forex risk for UAE-billed contracts.
    JPY has been volatile (-30% vs USD since 2020); recommend invoicing Japanese clients in USD
    even if payment is collected locally. Hedging instruments: RBI-authorised banks offer forward
    contracts with 3–12 month tenors. For Series-B startups the rule of thumb is to hedge 50%
    of projected international revenue 6 months forward.""",

    """TAM and Competitive Landscape — B2B HR-Tech / AI Automation (2024):
    Global HR-tech market: $32B (2024), expected to reach $56B by 2028 at 15% CAGR.
    US HR-tech TAM: $14B; dominated by Workday, SAP SuccessFactors, BambooHR, Rippling.
    UAE HR-tech TAM: $1.2B; under-served SMB segment, government mandates driving adoption.
    Japan HR-tech TAM: $3.4B; 78% of SMBs still on spreadsheets — very high greenfield opportunity.
    Key differentiation for Indian AI-native HR platforms: cost (60–70% below US incumbents),
    multi-language support, and compliance modules for local labour laws.
    Top competitors by market: US — Rippling, Gusto, Deel; UAE — Bayzat, HRMantra; Japan — SmartHR.""",

    """Series-B International Expansion — Capital Allocation Framework:
    Typical allocation for $2M international expansion budget (18-month horizon):
    US (40%  = $800K): AE hire × 2 ($240K OTE each), sales tools + CRM ($60K), events ($100K),
                        compliance / legal ($60K), customer success ($100K).
    UAE (35% = $700K): Country manager ($90K), sales + BD hire ($70K), office + visa ($80K),
                        marketing & Arabic localisation ($100K), runway buffer ($360K).
    Japan (25% = $500K): Local partner + distributor deal ($150K), Japanese UX localisation ($120K),
                          Country manager (bilingual, $100K), regulatory + legal ($130K).
    ROI expectation: break-even per market at 18 months; UAE fastest at 9–12 months typically.""",
]

# ── Config — every knob at its optimal extreme ────────────────────────
CONFIG = {**DEFAULT_CONFIG, **{
    # routing
    "model_routing"               : True,
    "routing_explore_c"           : 1.2,      # UCB1 exploration constant
    "routing_tier_floor_enabled"  : True,
    "routing_context_safety_mult" : 2,         # lower than default-3 to allow compound-mini
    "drift_threshold"             : 0.65,
    # qwen3-32b hallucinates generic industry content for synthesis tasks (ignores upstream deps).
    # llama-3.1-70b-versatile and deepseek are decommissioned on Groq.
    "agent_model_blacklist"       : [
        "groq/compound",
        "llama-3.1-70b-versatile",
        "deepseek-r1-distill-llama-70b",
        "qwen/qwen3-32b",              # hallucinates industry verticals on synthesis tasks
    ],

    # wave shape
    "wave1_agents"                : 5,
    "wave2_agents"                : 3,
    "max_depth"                   : 3,         # allows dynamic spawns up to depth 3
    "parallel"                    : True,
    "max_parallel"                : 5,

    # token budgets
    "token_budget"                : 200_000,
    "per_agent_tokens"            : 12_000,    # gathering agents (generous for multi-city calls)
    "per_agent_tokens_synthesis"  : 25_000,    # synthesis agents need more room

    # timing & retry
    "timeout_depth0"              : 180,
    "timeout_depth1"              : 120,
    "timeout_depth2"              : 90,
    "retry_failed"                : True,
    "rate_limit_retry"            : 5,
    "rate_limit_wait"             : 3,

    # APIs — explicit list forces ALL 5 including news (which is in _AUTO_SKIP)
    "external_apis"               : ["weather", "forex", "country", "crypto", "news"],

    # vector DB — ingests KNOWLEDGE_BASE before wave 1; agents call rag_context()
    "vector_db_enabled"           : True,
    "vector_db_path"              : "./sv_vectordb_07",
    "rag_top_k"                   : 4,
    "rag_chunk_size"              : 600,
    "rag_chunk_overlap"           : 80,

    # guardrails — all 4 layers on
    "guardrail_code"              : True,
    "guardrail_output"            : True,
    "guardrail_semantic"          : True,
    "sandbox_enabled"             : True,
    "sandbox_cpu_sec"             : 60,
    "sandbox_ram_mb"              : 512,
    "sandbox_fsize_mb"            : 10,

    # soul system — low threshold so constitutions warm-in after 2 runs
    "soul_quality_threshold"      : 0.65,
    "soul_min_runs"               : 2,
    "soul_constitution_max_chars" : 800,

    # quality scoring
    "quality_min"                 : 0.45,
    "drift_warn"                  : 0.45,
    "min_spawn_score"             : 0.4,

    # storage — isolated from every other example
    "db_path"                     : "sv_global_expansion.db",
    "agents_dir"                  : ".sv_global_07",

    # display — everything visible
    "output_format"               : "structured",
    "show_stdout"                 : True,
    "show_messages"               : True,
    "show_progress"               : True,
}}

# ── Task — engineered to fire all 5 APIs and all 9 skill types ─────────
TASK = {
    "description": (
        "Global market entry intelligence report for an Indian B2B SaaS startup "
        "planning simultaneous expansion into United States, UAE, and Japan. "
        # forex keywords → get_rate() calls for 3 pairs
        "Fetch live INR/USD, INR/AED, and INR/JPY exchange rates for financial modelling. "
        # country keywords → get_country() for 3 markets
        "Get country profiles for United States, UAE, and Japan — including population, "
        "capital, region, and official languages. "
        # weather/climate keywords → get_weather() for 4 cities
        "Fetch current weather and climate data for Mumbai, New York, Dubai, and Tokyo. "
        # news keywords → get_news() (forced via explicit API list)
        "Retrieve latest tech startup and funding news headlines. "
        # crypto keywords → get_crypto() BTC + ETH
        "Fetch bitcoin and ethereum prices as a proxy for global tech funding sentiment. "
        # research via think() + RAG
        "Research total addressable market size, top 5 competitors per market, and key "
        "regulatory requirements for an AI HR-automation platform in each market. "
        # reason + plan
        "Score each market on: forex cost, TAM, regulatory burden, sales cycle length, "
        "cultural fit, talent availability, speed-to-first-revenue, and strategic moat value. "
        "Build per-market go-to-market playbooks covering hiring plan, pricing strategy, "
        "partnership approach, and 12-month revenue milestones. "
        # synthesize
        "Generate a board-ready executive intelligence brief with a concrete capital "
        "allocation recommendation across the three markets and a sequenced expansion roadmap."
    ),
    "context": {
        "company"           : "IndiaAI SaaS Co.",
        "stage"             : "Series B",
        "arr_inr_crore"     : 40,
        "product"           : "AI-powered HR automation platform",
        "target_markets"    : ["US", "UAE", "Japan"],
        "expansion_budget_usd" : 2_000_000,
        "timeline_months"   : 18,
        "team_size"         : 120,
        "india_headcount_remote" : True,
    },
}

if __name__ == "__main__":
    # Wipe agent code files so every run generates fresh code.
    # The DB (sv_global_expansion.db) is PRESERVED across runs so that:
    #   - Fossils accumulate (agent DNA history)
    #   - Souls mature (quality-gated constitutions auto-inject after 2+ runs)
    #   - Model reputation accumulates (UCB1 bandit learns over time)
    # The vector DB is also preserved so knowledge chunks don't re-embed each run.
    if os.path.exists(CONFIG["agents_dir"]):
        shutil.rmtree(CONFIG["agents_dir"])

    Orchestrator(CONFIG).run(TASK, knowledge_base=KNOWLEDGE_BASE)
