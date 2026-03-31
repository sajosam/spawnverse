from core.engine import Orchestrator


def test_soul_lifecycle():
    o = Orchestrator()
    role = "test researcher"
    with o.mem._conn() as conn:
        conn.execute("DELETE FROM souls WHERE role = ?", (role,))
    runs = [0.85, 0.90, 0.80]
    for q in runs:
        o.mem.update_soul(role=role, quality=q, constitution=f"code_v_{q}")
    soul = o.mem.get_soul(role, min_runs=3)
    assert soul is not None, "Soul should exist but was not found"
    expected_avg  = sum(runs) / len(runs)
    expected_best = max(runs)
    expected_runs = len(runs)
    assert abs(soul["avg_quality"] - expected_avg) < 1e-6, \
        f"Avg mismatch: {soul['avg_quality']} != {expected_avg}"
    assert soul["best_quality"] == expected_best, \
        f"Best quality mismatch: {soul['best_quality']} != {expected_best}"
    assert soul["total_runs"] == expected_runs, \
        f"Run count mismatch: {soul['total_runs']} != {expected_runs}"


def test_min_runs_gate():
    o = Orchestrator()
    role = "threshold_test"
    with o.mem._conn() as conn:
        conn.execute("DELETE FROM souls WHERE role = ?", (role,))
    o.mem.update_soul(role, 0.9, "v1")
    o.mem.update_soul(role, 0.9, "v2")
    soul = o.mem.get_soul(role, min_runs=3)
    assert soul is None, "Soul should NOT exist below min_runs"


def test_quality_drop():
    o = Orchestrator()
    role = "degradation_test"
    with o.mem._conn() as conn:
        conn.execute("DELETE FROM souls WHERE role = ?", (role,))
    o.mem.update_soul(role, 0.9, "best")
    o.mem.update_soul(role, 0.2, "worse")
    o.mem.update_soul(role, 0.1, "worst")
    soul = o.mem.get_soul(role, min_runs=3)
    assert soul["best_constitution"] == "best", \
        "Best constitution should not regress"


def test_high_volume():
    o = Orchestrator()
    role = "stress_test"
    with o.mem._conn() as conn:
        conn.execute("DELETE FROM souls WHERE role = ?", (role,))
    for _ in range(1000):
        o.mem.update_soul(role, 0.5, "same")
    soul = o.mem.get_soul(role, min_runs=3)
    assert soul["total_runs"] == 1000, \
        f"Expected 1000 runs, got {soul['total_runs']}"


def test_soul_injection_threshold():
    o = Orchestrator()
    role = "injection_test"
    with o.mem._conn() as conn:
        conn.execute("DELETE FROM souls WHERE role = ?", (role,))
    for _ in range(3):
        o.mem.update_soul(role, 0.5, "low_quality_pattern")
    soul = o.mem.get_soul(role, min_runs=3)
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