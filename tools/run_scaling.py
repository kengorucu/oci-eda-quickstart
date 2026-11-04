#!/usr/bin/env python3
"""Measure a fixed RTL workload at one and two prepared E6 pods.

Requires only Python 3.9+ and kubectl on the operator machine. All simulations
execute on the selected workers. Both pods must finish setup before this script starts.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import shutil
import subprocess
import sys
import time

from summarize import summarize
from workloads import WORKLOADS


def call(args, timeout=90, payload=None):
    return subprocess.run(["kubectl", *args], input=payload, capture_output=True, text=True, timeout=timeout)


def checked(args, payload=None):
    process = call(args, payload=payload)
    if process.returncode:
        raise RuntimeError(process.stderr.strip())
    return process.stdout


def run_shard(namespace, pod, shard, shards, tests, cycles, run_id, timeout, command):
    env = {"TOTAL_TESTS": tests, "SHARDS": shards, "JOB_COMPLETION_INDEX": shard,
           "SIM_CYCLES": cycles, "BASE_SEED": 1000, "TEST_TIMEOUT_SECONDS": timeout,
           "RUN_ID": run_id, "SUITE_ID": "e6-demo-scaling-v1",
           "SIM_COMMAND_JSON": json.dumps(command)}
    # Forward exec output into the pod's main stdout as well, so kubectl logs
    # retains a second copy until the pod is deleted. Positional argv avoids
    # interpolating command arguments into shell source. pipefail preserves errors.
    argv = ["-n", namespace, "exec", pod, "-c", "simulator", "--",
            "/bin/bash", "-c", 'set -o pipefail; "$@" 2>&1 | tee /proc/1/fd/1',
            "eda-batch", "env",
            *[f"{key}={value}" for key, value in env.items()], "python3", "/config/runner.py"]
    max_tests = (tests + shards - 1) // shards
    process = call(argv, timeout=max_tests * timeout + 120)
    records = [json.loads(line[len("POC_RESULT "):]) for line in process.stdout.splitlines()
               if line.startswith("POC_RESULT ")]
    return {"pod": pod, "returncode": process.returncode,
            "stdout": process.stdout, "stderr": process.stderr, "records": records}


def batch(namespace, pods, tests, cycles, run_id, timeout, directory, command):
    directory.mkdir()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(pods)) as pool:
        futures = [pool.submit(run_shard, namespace, pod, i, len(pods), tests, cycles, run_id, timeout, command)
                   for i, pod in enumerate(pods)]
        pending = set(futures)
        while pending:
            _, pending = wait(pending, timeout=30)
            if pending:
                print(f"{run_id}: {len(pending)} worker(s) still executing", flush=True)
        results = [future.result() for future in futures]
    wall = time.perf_counter() - started
    records = []
    for result in results:
        (directory / (result["pod"] + ".log")).write_text(result["stdout"])
        (directory / (result["pod"] + ".stderr")).write_text(result["stderr"])
        records.extend(result["records"])
    summary = summarize(records, tests)
    summary.update({"run_id": run_id, "workers": len(pods), "cycles_per_test": cycles,
                    "controller_wall_seconds": wall, "success": summary["success"] and
                    all(result["returncode"] == 0 for result in results) and
                    sum(result["stdout"].count("POC_TEST_PASS") for result in results) == tests})
    (directory / "records.json").write_text(json.dumps(records, indent=2))
    (directory / "summary.json").write_text(json.dumps(summary, indent=2))
    if not summary["success"]:
        raise RuntimeError(f"Incomplete or failed batch: {directory}; inspect logs")
    return summary


def checkpoint(namespace, output, complete=False):
    """Retain settings and completed batch records beyond pod/Cloud Shell lifetime."""
    paths = [output / "settings.json", output / "runs.json", output / "comparison.json", output / "environment.json"]
    for directory in sorted(path for pattern in ("e6-p*-r*",)
                            for path in output.glob(pattern)):
        paths.extend([directory / "summary.json", directory / "records.json"])
    data = {str(path.relative_to(output)).replace("/", "__"): path.read_text()
            for path in paths if path.is_file()}
    data["status.json"] = json.dumps({"complete": complete, "run": output.name,
                                      "scope": "E6 demo scaling"})
    if len(json.dumps(data).encode()) > 750000:
        raise RuntimeError("Result checkpoint exceeds the safe ConfigMap size; export local results before continuing")
    name = "eda-results-" + output.name
    document = {"apiVersion": "v1", "kind": "ConfigMap",
                "metadata": {"name": name, "namespace": namespace,
                             "labels": {"app.kubernetes.io/name": "eda-scaling-results"}}, "data": data}
    checked(["apply", "--server-side", "--field-manager=eda-scaling-results", "-f", "-"],
            payload=json.dumps(document))
    return name


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="eda-native-poc")
    parser.add_argument("--worker-job")
    parser.add_argument("--workload", choices=list(WORKLOADS), default="rtl")
    parser.add_argument("--compute-family", choices=["e6"], default="e6")
    parser.add_argument("--tests", type=int, default=8)
    parser.add_argument("--cycles", type=int)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--test-timeout", type=int, default=300)
    parser.add_argument("--output", type=Path, default=Path.home() / "eda-scaling-results")
    args = parser.parse_args(argv)
    workload = WORKLOADS[args.workload]
    args.worker_job = args.worker_job or workload["job"]
    args.cycles = workload["cycles"] if args.cycles is None else args.cycles
    if args.tests < 2 or min(args.cycles, args.repeats, args.test_timeout) < 1:
        parser.error("Require at least two tests and positive cycles/repeats/timeouts")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    output = args.output / timestamp
    output.mkdir(parents=True, exist_ok=False)
    pods_state = json.loads(checked(["-n", args.namespace, "get", "pods", "-l",
                                    f"poc-run={args.worker_job}", "-o", "json"]))
    ready = [pod for pod in pods_state["items"] if not pod["metadata"].get("deletionTimestamp")
             and any(c["type"] == "Ready" and c["status"] == "True"
                     for c in pod.get("status", {}).get("conditions", []))]
    if len(ready) != 2 or len({pod["spec"]["nodeName"] for pod in ready}) != 2:
        raise RuntimeError("Need exactly two prepared Ready worker pods on distinct nodes")
    ready.sort(key=lambda pod: pod["metadata"]["name"])
    pods = [pod["metadata"]["name"] for pod in ready]
    (output / "pods-before.json").write_text(json.dumps(pods_state, indent=2))
    node_data = json.loads(checked(["get", "nodes", "-o", "json"]))
    (output / "nodes.json").write_text(json.dumps(node_data, indent=2))
    node_index = {node["metadata"]["name"]: node for node in node_data["items"]}
    expected_shape = "VM.Standard.E6.Flex"
    if any(node_index[pod["spec"]["nodeName"]]["metadata"]["labels"].get("node.kubernetes.io/instance-type") != expected_shape for pod in ready):
        raise RuntimeError(f"All selected workers must be on {expected_shape}")
    (output / "settings.json").write_text(json.dumps({k: str(v) if isinstance(v, Path) else v
                                                     for k, v in vars(args).items()}, indent=2))
    for pod in ready:
        resources = pod["spec"]["containers"][0]["resources"]
        if any(resources[section].get("cpu") != "2" or resources[section].get("memory") != "4Gi"
               for section in ("requests", "limits")):
            raise RuntimeError("This demo requires matching 2-CPU / 4-GiB requests and limits")
    fingerprints = []
    for pod in pods:
        checked(["-n", args.namespace, "exec", pod, "-c", "simulator", "--",
                 "/bin/bash", "-c", "test -f /work/prepared"])
        fingerprint = checked(["-n", args.namespace, "exec", pod, "-c", "simulator", "--",
                               "/bin/bash", "-c", "rpm -qa --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\\n' | sort"])
        fingerprints.append(hashlib.sha256(fingerprint.encode()).hexdigest())
        (output / (pod + "-packages.txt")).write_text(fingerprint)
        (output / (pod + "-setup.log")).write_text(checked(["-n", args.namespace, "logs", pod, "-c", "simulator"]))
    image_ids = {status["imageID"] for pod in ready for status in pod["status"]["containerStatuses"]}
    if len(set(fingerprints)) != 1 or len(image_ids) != 1:
        raise RuntimeError("Workers have different package sets or image IDs; rebuild a consistent pair before measuring")
    environment = {
        "sources": {},
        "installed_rpm_sha256": fingerprints[0],
        "container_image_id": next(iter(image_ids)),
        "per_pod_resources": [pod["spec"]["containers"][0]["resources"] for pod in ready],
    }
    for pod in pods:
        environment["sources"][pod] = checked([
            "-n", args.namespace, "exec", pod, "-c", "simulator", "--",
            "sha256sum", "/config/runner.py",
            "/config/mac.sv", "/config/tb.sv", "/work/obj/Vtb"])
    source_fingerprints = [
        [line.split()[0] for line in evidence.splitlines()[:3]]
        for evidence in environment["sources"].values()
    ]
    if len(source_fingerprints) != 2 or source_fingerprints[0] != source_fingerprints[1]:
        raise RuntimeError("Prepared simulator source files differ between pods")
    (output / "environment.json").write_text(json.dumps(environment, indent=2))
    print(f"Results: {output}", flush=True)
    backup_name = checkpoint(args.namespace, output)
    print(f"Kubernetes checkpoint: {args.namespace}/{backup_name}", flush=True)
    print("Both workers prepared; performing an unmeasured warm-up", flush=True)
    batch(args.namespace, pods, 2, workload["warmup"], "warm-up", args.test_timeout, output / "warm-up", workload["command"])
    summaries = []
    for repeat in range(1, args.repeats + 1):
        # Alternate ordering and the single worker to reduce node/order bias.
        levels = [1, 2] if repeat % 2 else [2, 1]
        for workers in levels:
            targets = [pods[(repeat - 1) % 2]] if workers == 1 else pods
            run_id = f"{args.compute_family}-p{workers}-r{repeat}"
            print(f"Batch {len(summaries)+1}/{args.repeats*2} — starting {run_id}: {args.tests} tests, {args.cycles} {workload['unit']} each", flush=True)
            summary = batch(args.namespace, targets, args.tests, args.cycles, run_id,
                            args.test_timeout, output / run_id, workload["command"])
            summaries.append(summary)
            (output / "runs.json").write_text(json.dumps(summaries, indent=2))
            checkpoint(args.namespace, output)
            print(f"{run_id}: PASS; measured window {summary['simulation_window_seconds']:.2f}s", flush=True)
    medians = {str(workers): statistics.median(s["simulation_window_seconds"] for s in summaries
                                              if s["workers"] == workers) for workers in (1, 2)}
    speedup = medians["1"] / medians["2"]
    comparison = {"success": True, "tests_per_batch": args.tests, "cycles_per_test": args.cycles,
                  "compute_family": args.compute_family, "shape": expected_shape,
                  "repeats_per_level": args.repeats, "workload_id": args.workload,
                  "workload_name": workload["name"], "work_units_per_test": args.cycles, "unit_label": workload["unit"],
                  "median_seconds_by_workers": medians,
                  "two_worker_speedup": speedup, "two_worker_parallel_efficiency": speedup / 2,
                  "scope": f"Scaling of {workload['name']} on E6; not a customer production benchmark."}
    (output / "comparison.json").write_text(json.dumps(comparison, indent=2))
    checkpoint(args.namespace, output, complete=True)
    archive = shutil.make_archive(str(output), "gztar", root_dir=output.parent, base_dir=output.name)
    print(json.dumps(comparison, indent=2), flush=True)
    print(f"Download this archive now: {archive}", flush=True)
    print(f"Results are also in ConfigMap {backup_name}. Worker Job remains running; delete it after exporting results.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
