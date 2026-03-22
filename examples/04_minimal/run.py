"""
Example 04 — Minimal Config
Fastest possible run. 2 agents, no sub-agents, sequential.
Best for: quick tests, debugging, tight token budgets.

Run:
    export GROQ_API_KEY=your_key
    python run.py "your task"
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from core.engine import Orchestrator, DEFAULT_CONFIG

CONFIG = {**DEFAULT_CONFIG, **{
    "max_depth"          : 1,
    "wave1_agents"       : 2,
    "wave2_agents"       : 1,
    "parallel"           : False,
    "retry_failed"       : False,
    "show_stdout"        : False,
    "show_messages"      : False,
    "show_progress"      : False,
    "guardrail_semantic" : False,
    "token_budget"       : 20000,
    "per_agent_tokens"   : 3000,
}}

TASK = {
    "description": (
        sys.argv[1] if len(sys.argv) > 1
        else "Summarise the pros and cons of Python vs Go for backend APIs."
    ),
    "context": {}
}

if __name__ == "__main__":
    for f in [CONFIG["db_path"]]:
        if os.path.exists(f): os.remove(f)
    if os.path.exists(CONFIG["agents_dir"]):
        shutil.rmtree(CONFIG["agents_dir"])
    Orchestrator(CONFIG).run(TASK)
