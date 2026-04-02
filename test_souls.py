import tempfile
import os
import uuid
from core.engine import Orchestrator, DistributedMemory


def make_mem():
    """Each test gets a truly isolated in-memory database."""
    o = Orchestrator()
    unique_db = f"file:test_{uuid.uuid4().hex}?mode=memory&cache=shared"
    cfg = {**o.cfg, "db_path": unique_db}
    mem = DistributedMemory(cfg)
    return mem


def test_soul_lifecycle():
    mem = make_mem()
    runs = [0.85, 0.90, 0.80]
    for q in runs:
        mem.update_soul(role="test researcher", quality=q, constitution=f"code_v_{q}")
    soul = mem.get_soul("test researcher", min_runs=3)
    assert soul is not None, "Soul should exist but was not found"
    assert abs(soul["avg_quality"] - sum(runs) / len(runs)) < 1e-6
    assert soul["best_quality"] == max(runs)
    assert soul["total_runs"] == len(runs)


def test_min_runs_gate():
    mem = make_mem()
    mem.update_soul("threshold_test", 0.9, "v1")
    mem.update_soul("threshold_test", 0.9, "v2")
    soul = mem.get_soul("threshold_test", min_runs=3)
    assert soul is None, "Soul should NOT exist below min_runs"


def test_quality_drop():
    mem = make_mem()
    mem.update_soul("degradation_test", 0.9, "best")
    mem.update_soul("degradation_test", 0.2, "worse")
    mem.update_soul("degradation_test", 0.1, "worst")
    soul = mem.get_soul("degradation_test", min_runs=3)
    assert soul["best_constitution"] == "best", \
        "Best constitution should not regress"


def test_high_volume():
    mem = make_mem()
    for _ in range(1000):
        mem.update_soul("stress_test", 0.5, "same")
    soul = mem.get_soul("stress_test", min_runs=3)
    assert soul["total_runs"] == 1000, \
        f"Expected 1000 runs, got {soul['total_runs']}"


def test_soul_injection_threshold():
    mem = make_mem()
    for _ in range(3):
        mem.update_soul("injection_test", 0.5, "low_quality_pattern")
    soul = mem.get_soul("injection_test", min_runs=3)
    assert soul is not None
    assert soul["avg_quality"] < 0.7, "Should be below threshold"
    print("Soul exists but avg_quality below injection threshold - correct")


if __name__ == "__main__":
    test_soul_lifecycle()
    print("test_soul_lifecycle passed")
    test_min_runs_gate()
    print("test_min_runs_gate passed")
    test_quality_drop()
    print("test_quality_drop passed")
    test_high_volume()
    print("test_high_volume passed")
    test_soul_injection_threshold()
    print("test_soul_injection_threshold passed")
    print("\nAll tests passed")