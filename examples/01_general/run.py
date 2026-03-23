"""
Example 01 — General Query
Pure LLM reasoning. No external APIs. No vector DB.
Give it any task — agents are invented at runtime.

Run:
    python run.py
    python run.py "your task here"
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from spawnverse.core.engine import Orchestrator, DEFAULT_CONFIG

# os.environ["GROQ_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""

CONFIG = {**DEFAULT_CONFIG, **{
    "max_depth"     : 2,
    "wave1_agents"  : 3,
    "wave2_agents"  : 3,
    "parallel"      : True,
    "output_format" : "structured",
    "show_stdout"   : True,
    "show_messages" : True,
}}
 
TASK = {
    "description": (
        "Research and compare the top 5 electric vehicles in India "
        "under INR 25 lakhs for 2025. For each: real-world range, "
        "charging time, 5-year cost of ownership, FAME-II subsidy, "
        "pros and cons. End with a ranked recommendation table."
    ),
    "context": {
        "budget_inr" : 2500000,
        "use_case"   : "daily urban commute + weekend highway",
        "buyer_type" : "first-time EV buyer",
        "location"   : "Bangalore, India",
    }
}
 
if __name__ == "__main__":
    if len(sys.argv) > 1:
        TASK = {"description": " ".join(sys.argv[1:]), "context": {}}
    for f in [CONFIG["db_path"]]:
        if os.path.exists(f): os.remove(f)
    if os.path.exists(CONFIG["agents_dir"]):
        shutil.rmtree(CONFIG["agents_dir"])
    Orchestrator(CONFIG).run(TASK)
 