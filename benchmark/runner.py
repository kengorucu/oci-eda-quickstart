#!/usr/bin/env python3
"""Run a deterministic shard of test seeds; emit one JSON timing record per seed.

SIM_COMMAND_JSON is an argv array, with optional {seed}/{cycles} placeholders.
Custom simulator wrappers must exit nonzero for test failures. No shell is used.
"""
import hashlib
import json
import os
import platform
import resource
import shlex
import subprocess
import sys
import time


def emit(record):
    print("POC_RESULT " + json.dumps(record, sort_keys=True), flush=True)


def positive(name, default):
    value = int(os.environ.get(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def main():
    total = positive("TOTAL_TESTS", "32")
    shards = positive("SHARDS", "4")
    index = int(os.environ.get("JOB_COMPLETION_INDEX", "0"))
    if index < 0 or index >= shards:
        raise ValueError("JOB_COMPLETION_INDEX must be in [0, SHARDS)")
    cycles = positive("SIM_CYCLES", "1000000")
    timeout = positive("TEST_TIMEOUT_SECONDS", "1800")
    base_seed = positive("BASE_SEED", "1000")
    template = json.loads(os.environ.get(
        "SIM_COMMAND_JSON", '["/opt/poc/sim", "+seed={seed}", "+cycles={cycles}"]'))
    if not isinstance(template, list) or not template or not all(isinstance(s, str) for s in template):
        raise ValueError("SIM_COMMAND_JSON must be a nonempty JSON array of strings")
    command_hash = hashlib.sha256(json.dumps(template).encode()).hexdigest()
    cpu_model = "unknown"
    try:
        with open("/proc/cpuinfo") as cpuinfo:
            cpu_model = next((line.split(":", 1)[1].strip() for line in cpuinfo
                              if line.startswith("model name")), "unknown")
    except OSError:
        pass
    emit({"event": "shard_start", "shard": index, "shards": shards,
          "total_tests": total, "hostname": platform.node(),
          "architecture": platform.machine(), "command_sha256": command_hash,
          "cpu_model": cpu_model, "cycles": cycles, "base_seed": base_seed,
          "run_id": os.environ.get("RUN_ID", "local"),
          "suite_id": os.environ.get("SUITE_ID", "rtl-smoke-v1"),
          "time_unix": time.time()})
    failures = 0
    for test in range(index, total, shards):
        seed = base_seed + test
        argv = [arg.replace("{seed}", str(seed)).replace("{cycles}", str(cycles)) for arg in template]
        print("Running " + shlex.join(argv), flush=True)
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        started_unix = time.time()
        start = time.perf_counter()
        timed_out = False
        try:
            # Each command gets a new process group, so timeout kills descendants too.
            proc = subprocess.Popen(argv, start_new_session=True)
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                import signal
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                rc = 124
        except OSError as exc:
            print(str(exc), file=sys.stderr, flush=True)
            rc = 127
        elapsed = time.perf_counter() - start
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        failures += int(rc != 0)
        emit({"event": "test", "test_id": test, "seed": seed, "shard": index,
              "run_id": os.environ.get("RUN_ID", "local"),
              "suite_id": os.environ.get("SUITE_ID", "rtl-smoke-v1"),
              "started_unix": started_unix, "elapsed_seconds": elapsed,
              "cpu_seconds": after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime,
              "exit_code": rc, "timed_out": timed_out})
    emit({"event": "shard_end", "shard": index, "failures": failures, "time_unix": time.time()})
    return int(failures > 0)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"Invalid runner configuration: {exc}", file=sys.stderr)
        sys.exit(2)

