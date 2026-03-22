# __init__.py
"""
SpawnVerse — Self-Spawning Cognitive Agent System
The universe where agents are born from tasks.
"""
from .core.engine import Orchestrator, DEFAULT_CONFIG

__version__ = "0.1.0"
__all__ = ["Orchestrator", "DEFAULT_CONFIG"]
