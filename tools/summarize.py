"""Summarize self-checking simulator results."""

def summarize(records, expected_tests):
    tests = [r for r in records if r.get("event") == "test"]
    ids = [r["test_id"] for r in tests]
    complete = len(ids) == expected_tests and set(ids) == set(range(expected_tests))
    passed = sum(r["exit_code"] == 0 and not r.get("timed_out", False) for r in tests)
    starts = [r["started_unix"] for r in tests]
    ends = [r["started_unix"] + r["elapsed_seconds"] for r in tests]
    window = max(ends) - min(starts) if tests else 0
    return {
        "expected_tests": expected_tests, "observed_tests": len(tests),
        "complete_unique_coverage": complete, "passed": passed,
        "failed": len(tests) - passed,
        "success": complete and passed == expected_tests,
        "simulation_window_seconds": window,
        "passed_tests_per_hour": passed * 3600 / window if window > 0 else 0,
        "summed_test_wall_seconds": sum(r["elapsed_seconds"] for r in tests),
    }

