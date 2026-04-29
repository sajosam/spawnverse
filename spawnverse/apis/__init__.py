# spawnverse/apis/__init__.py
from .registry import detect_needed_apis, build_api_stdlib, _API_REGISTRY

__all__ = ["detect_needed_apis", "build_api_stdlib", "_API_REGISTRY"]
