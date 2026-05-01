"""
Example 07 — Travel Planner
Run:
    export GROQ_API_KEY=your_key
    python 07_travel_planner.py
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from spawnverse import Orchestrator, DEFAULT_CONFIG

CONFIG = {**DEFAULT_CONFIG, **{
    "wave1_agents" : 4,
    "wave2_agents" : 2,
    "model_routing": True,
    "external_apis": True,
    "db_path"      : "sv_travel.db",
    "agents_dir"   : ".sv_travel",
}}

TASK = {
    "description": (
        "Plan a 7-day trip to Japan for a solo traveller from India. "
        "Get current weather in Tokyo, Kyoto, Osaka. "
        "Get USD/JPY and INR/JPY exchange rates. "
        "Fetch Japan country profile. "
        "Get latest travel news and advisories. "
        "Suggest day-by-day itinerary, budget breakdown, best places to eat, "
        "and top cultural experiences."
    ),
    "context": {"budget_usd": 2000, "travel_month": "March", "interests": "culture, food, nature"},
}

if __name__ == "__main__":
    if os.path.exists(CONFIG["agents_dir"]): shutil.rmtree(CONFIG["agents_dir"])
    Orchestrator(CONFIG).run(TASK)
