"""
Example 02 — External APIs (auto-injected)
════════════════════════════════════════════
SpawnVerse auto-detects what APIs the task needs and
injects helpers into every agent automatically.

Auto-detected from task keywords:
  "weather"        → get_weather(city)
  "exchange rate"  → get_rate(base, target)
  "country"        → get_country(name)
  "holiday"        → get_holidays(country_code, year)
  "crypto/bitcoin" → get_crypto(symbol)
  "news"           → get_news()

Run:
    pip install groq
    export GROQ_API_KEY=your_key
    python run.py
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from spawnverse.core.engine import Orchestrator, DEFAULT_CONFIG

os.environ["GROQ_API_KEY"] = ""



CONFIG = {
    **DEFAULT_CONFIG,
    "max_depth"     : 2,
    "wave1_agents"  : 4,
    "wave2_agents"  : 3,
    "parallel"      : True,
    "output_format" : "structured",
 
    # This one line triggers auto-detection + injection.
    # True  = engine reads task and decides what APIs to inject
    # list  = explicit: ["weather", "forex", "country"]
    "external_apis" : True,
 
    # For paid APIs: "external_api_key": {"openweather": "key"}
}
 
TASK = {
    "description": (
        "Plan a 7-day trip from Bangalore to Tokyo for 2 people, "
        "budget INR 2,00,000. "
        "Use real weather data for Tokyo in October. "
        "Use real INR to JPY exchange rates. "
        "Get real country information for Japan. "
        "Check Japanese public holidays in October 2025. "
        "Include: flights, hotels, day-by-day itinerary, "
        "food guide, local transport, packing list, budget breakdown."
    ),
    "context": {
        "persons"    : 2,
        "budget_inr" : 200000,
        "origin"     : "Bangalore, India",
        "destination": "Tokyo, Japan",
        "dates"      : "October 1-7, 2025",
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