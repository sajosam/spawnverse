"""
Example 03 — Vector DB / RAG
Agents semantically search your internal documents.

HOW:
  1. Add documents to KNOWLEDGE_BASE below
  2. They are chunked + embedded into ChromaDB on startup
  3. Agents call rag_context("query") before calling think()
  4. Agent outputs are auto-indexed for future runs

Install:
    pip install groq chromadb

Run:
    export GROQ_API_KEY=your_key
    python run.py
"""
import sys, os, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from spawnverse import Orchestrator, DEFAULT_CONFIG

os.environ["GROQ_API_KEY"] = ""

KNOWLEDGE_BASE = [
    # Plain text strings:
    "Dubai Marina 2BHK apartments average AED 1.1M in Q1 2025.",
    "JVC (Jumeirah Village Circle) offers the best ROI at 7-8% annually.",
    "RERA requires all Dubai property agents to be licensed.",
    "Off-plan payment plans: typically 50% during construction, 50% on handover.",
 
    # Or file paths:
    # "/path/to/your/document.txt",
    # "/path/to/market-report.md",
]
 
CONFIG = {**DEFAULT_CONFIG, **{
    "vector_db_enabled" : True,
    "vector_db_path"    : "./sv_vectordb_03",
    "rag_top_k"         : 5,
    "max_depth"         : 2,
    "wave1_agents"      : 4,
    "wave2_agents"      : 3,
    "parallel"          : True,
}}
 
TASK = {
    "description": (
        "Analyse the Dubai real estate market for off-plan 2BHK investments "
        "under AED 1.2M in 2025. Use the knowledge base for market data. "
        "Cover: top areas, best developers, expected ROI, payment plans, "
        "legal process for foreign buyers, and 3 negotiation offer templates."
    ),
    "context": {
        "budget_aed"  : 1200000,
        "buyer_type"  : "foreign investor",
        "property"    : "2BHK off-plan",
    }
}
 
if __name__ == "__main__":
    for f in [CONFIG["db_path"]]:
        if os.path.exists(f): os.remove(f)
    if os.path.exists(CONFIG["agents_dir"]):
        shutil.rmtree(CONFIG["agents_dir"])
    Orchestrator(CONFIG).run(TASK, knowledge_base=KNOWLEDGE_BASE)