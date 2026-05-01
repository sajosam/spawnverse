"""
Example 09 — Product Launch Research
Run:
    export GROQ_API_KEY=your_key
    python 09_product_launch.py
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from spawnverse import Orchestrator, DEFAULT_CONFIG

CONFIG = {**DEFAULT_CONFIG, **{
    "wave1_agents" : 4,
    "wave2_agents" : 2,
    "model_routing": True,
    "external_apis": True,
    "db_path"      : "sv_launch.db",
    "agents_dir"   : ".sv_launch",
}}

TASK = {
    "description": (
        "Research and plan the launch of a new food delivery app in India. "
        "Fetch latest news about Zomato, Swiggy, and food tech in India. "
        "Get India country profile and population data. "
        "Identify top 3 competitors and their weaknesses. "
        "Identify the best target city to launch first. "
        "Suggest a go-to-market strategy, pricing model, and launch checklist."
    ),
    "context": {"stage": "pre-launch", "budget_usd": 50000, "team_size": 8},
}

if __name__ == "__main__":
    if os.path.exists(CONFIG["agents_dir"]): shutil.rmtree(CONFIG["agents_dir"])
    Orchestrator(CONFIG).run(TASK)
