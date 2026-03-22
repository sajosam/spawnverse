"""
Example 02 — External APIs
Agents call real public APIs (no keys needed):
  wttr.in         real weather data
  open.er-api.com real forex rates
  restcountries.com country info

Run:
    pip install groq requests
    export GROQ_API_KEY=your_key
    python run.py
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))
from core.engine import Orchestrator, DEFAULT_CONFIG

# Extra helpers injected into every agent when using external APIs
EXTRA_STDLIB = '''
import requests as _req

def api_get(url, params=None, headers=None, timeout=10):
    try:
        r = _req.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        try:    return r.json()
        except: return r.text
    except Exception as e:
        vlog("API_FAILED", str(e)); return None

def get_weather(city):
    d = api_get(f"https://wttr.in/{city}?format=j1")
    if not d or not isinstance(d, dict): return None
    c = d.get("current_condition", [{}])[0]
    return {"temp_c": c.get("temp_C"), "desc": c.get("weatherDesc",[{}])[0].get("value"),
            "humidity": c.get("humidity"), "wind_kmph": c.get("windspeedKmph")}

def get_rate(base, target):
    d = api_get(f"https://open.er-api.com/v6/latest/{base}")
    return d.get("rates",{}).get(target) if d else None
'''

CONFIG = {**DEFAULT_CONFIG, **{
    "max_depth"    : 2,
    "wave1_agents" : 4,
    "wave2_agents" : 3,
    "parallel"     : True,
    "extra_stdlib" : EXTRA_STDLIB,
}}

TASK = {
    "description": (
        "Plan a 7-day trip from Bangalore to Tokyo for 2 people, "
        "budget INR 2,00,000. Use real weather data for Tokyo in October "
        "and real INR/JPY exchange rates. Include flights, hotels, "
        "day-by-day itinerary, food guide, transport guide, and "
        "full budget breakdown."
    ),
    "context": {
        "persons"     : 2,
        "budget_inr"  : 200000,
        "origin"      : "Bangalore, India",
        "destination" : "Tokyo, Japan",
        "dates"       : "October 2025",
    }
}

if __name__ == "__main__":
    for f in [CONFIG["db_path"]]:
        if os.path.exists(f): os.remove(f)
    if os.path.exists(CONFIG["agents_dir"]):
        shutil.rmtree(CONFIG["agents_dir"])
    Orchestrator(CONFIG).run(TASK)
