"""
Example 05 — Maximum Config
Every feature enabled. Deep tree, parallel, vector DB, all guardrails.
Best for: complex research, production-grade analysis.

Install:
    pip install groq chromadb

Run:
    export GROQ_API_KEY=your_key
    python run.py
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from core.engine import Orchestrator, DEFAULT_CONFIG

KNOWLEDGE_BASE = [
    # Add domain documents for RAG
]

CONFIG = {**DEFAULT_CONFIG, **{
    "model"              : "llama-3.3-70b-versatile",
    "max_depth"          : 3,
    "wave1_agents"       : 5,
    "wave2_agents"       : 5,
    "parallel"           : True,
    "max_parallel"       : 5,
    "timeout_depth0"     : 150,
    "timeout_depth1"     : 120,
    "timeout_depth2"     : 90,
    "retry_failed"       : True,
    "min_spawn_score"    : 0.5,
    "token_budget"       : 150000,
    "per_agent_tokens"   : 12000,
    "sandbox_enabled"    : True,
    "guardrail_code"     : True,
    "guardrail_output"   : True,
    "guardrail_semantic" : True,
    "vector_db_enabled"  : True,
    "vector_db_path"     : "./sv_vectordb_05",
    "rag_top_k"          : 7,
    "output_format"      : "structured",
    "show_stdout"        : True,
    "show_messages"      : True,
    "show_progress"      : True,
}}

TASK = {
    "description": (
        "Perform a complete investment due diligence report on the Indian "
        "EV sector for 2025. Cover: market size and 3-year forecast, top players "
        "(Tata, Ola, Ather, Bajaj, TVS), government FAME-II policy, charging "
        "infrastructure gaps, consumer adoption barriers, competitive dynamics, "
        "investment risks and opportunities, and a final capital allocation "
        "recommendation across 2W, 3W, 4W, and commercial segments."
    ),
    "context": {
        "investor_type" : "Series B VC",
        "check_size_usd": 5000000,
        "thesis"        : "Indian mobility transformation",
        "horizon_years" : 3,
    }
}

if __name__ == "__main__":
    for f in [CONFIG["db_path"]]:
        if os.path.exists(f): os.remove(f)
    if os.path.exists(CONFIG["agents_dir"]):
        shutil.rmtree(CONFIG["agents_dir"])
    Orchestrator(CONFIG).run(TASK, knowledge_base=KNOWLEDGE_BASE)
