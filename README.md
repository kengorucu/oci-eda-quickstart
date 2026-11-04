# OCI EDA Quickstart

Performance-intensive workloads need infrastructure matched to their compute, memory, networking and storage requirements. Oracle Cloud Infrastructure (OCI) provides a range of compute options to support that workload-driven approach.

**OCI EDA Quickstart puts this approach into practice for Electronic Design Automation:** deploy E6 compute on Oracle Kubernetes Engine (OKE), run a self-checking RTL regression, and measure simulation completion time and parallel scaling.

**[Start the quickstart](https://kengorucu.github.io/oci-eda-quickstart/)** · **[Download Terraform stack](https://kengorucu.github.io/oci-eda-quickstart/downloads/oke-e6-stack.zip)** · **[Download benchmark](https://kengorucu.github.io/oci-eda-quickstart/downloads/oke-e6-benchmark.zip)**

## OCI's approach to performance-intensive workloads

OCI's compute portfolio spans flexible virtual machines, bare metal, HPC and GPU options. Selecting infrastructure begins with the workload: the resources each job needs, the number of jobs that can run independently, and the networking and storage patterns of the application. See [OCI Compute](https://www.oracle.com/cloud/compute/) and [planning compute resources](https://docs.oracle.com/en/solutions/oci-best-practices/plan-compute-resources1.html).

EDA illustrates why this matters. A regression can distribute independent simulations across workers, while other design stages have different processor, memory and data-access requirements. This quickstart focuses on the RTL regression stage and provides a repeatable way to measure it on E6.

| Workload requirement | Approach in this quickstart | What to evaluate |
| --- | --- | --- |
| Processor-intensive simulation | E6 compute executes a compiled Verilator model | Completion time for a fixed regression batch |
| Parallel regression execution | OKE places independent simulator pods on separate workers | Throughput and scaling from one worker to two |
| Consistent execution resources | Identical software, inputs and per-pod CPU/memory limits | Correctness and repeatability across measured runs |
| Infrastructure automation | Terraform provisions the cluster, workers and networking | A reproducible environment for further evaluation |
| Workload-specific sizing | Flexible E6 OCPU and memory configuration | Resource requirements of the intended design and toolchain |

The process is **deploy, validate, measure and scale**. Use the same approach to evaluate representative EDA designs against their own requirements; the measured workload determines the appropriate infrastructure configuration.

## What you will run

The demo uses **Verilator** to compile a SystemVerilog multiply-and-accumulate circuit and its testbench into an executable simulator. Each test supplies deterministic inputs and checks the circuit's output.

| Test setting | Configuration |
| --- | --- |
| Tests per measured batch | 8, using seeds 1000–1007 |
| Simulated clock cycles | 100 million per test |
| Worker counts | 1 and 2 |
| Repeats | 3 at each worker count |
| Total measured test executions | 48 |
| Simulator pod resources | 2 Kubernetes logical CPUs and 4 GiB RAM |

One worker runs all eight tests sequentially. Two workers run four tests each on separate nodes. Package installation, circuit compilation and the initial warm-up are excluded from the measured simulation windows.

**Available now:** digital RTL simulation. Logic synthesis and static timing analysis are planned additions and are not runnable in this release.

## Prerequisites

- An OCI tenancy and a compartment with permission to create OKE, compute and network resources through Resource Manager.
- E6 capacity and service limits for **32 OCPUs and 256 GB RAM** at the default sizing.
- An availability domain with E6 capacity and a currently supported OKE Kubernetes version.
- OCI Cloud Shell, or an authorized client with OCI CLI, kubectl and Python 3.9 or later.

Normal OCI infrastructure charges apply until you destroy the stack.

## 1. Deploy the OCI stack

Open the [quickstart](https://kengorucu.github.io/oci-eda-quickstart/#step-deploy) and select **Deploy to Oracle Cloud**. Alternatively, upload the [stack ZIP](https://kengorucu.github.io/oci-eda-quickstart/downloads/oke-e6-stack.zip) in **OCI Console → Resource Manager → Stacks → Create stack → My configuration**.

The stack creates:

| Component | Default configuration |
| --- | --- |
| Cluster | One Basic OKE cluster |
| Workers | Two `VM.Standard.E6.Flex` managed nodes |
| Sizing | 16 OCPUs and 128 GB RAM per node |
| Boot volumes | 100 GB per node |
| Worker image | Compatible Oracle Linux OKE x86_64 image, selected automatically |
| Networking | Dedicated VCN, private workers, API subnet, gateways, routes and security rules |

Configure the region, compartment, full tenancy-specific availability domain, full supported Kubernetes version and trusted client IPv4 CIDR. The default region is Frankfurt (`eu-frankfurt-1`).

From Cloud Shell on the network you will use for kubectl, check your public egress IP:

```sh
curl -4 -fsS --connect-timeout 5 --max-time 10 https://api.ipify.org; echo
```

Enter the returned IPv4 address followed by `/32` as the trusted CIDR. This allows that client to connect to the public Kubernetes API on TCP port 6443.

Run **Plan**. For a new stack, expect **12 resources to add, zero to change and zero to destroy**. Review the selected image and worker configuration, then **Apply**. Wait for both workers to become Ready. A successful Plan checks configuration compatibility; it does not reserve E6 capacity.

## 2. Connect to OKE

Copy the `create_kubeconfig` command from the stack outputs and run it in Cloud Shell. Then run:

```sh
export KUBECONFIG="$HOME/.kube/eda-e6-demo-config"

kubectl --request-timeout=10s get nodes -o wide \
  -L compute-family,node.kubernetes.io/instance-type
```

Confirm that both nodes are **Ready**, with shape `VM.Standard.E6.Flex` and label `compute-family=e6`.

If the API times out, confirm that kubeconfig targets the new cluster, check the current client egress IP against the trusted CIDR, and verify the API subnet allows TCP 6443. For private access, attach Cloud Shell to the worker subnet identified in `cloud_shell_private_network` and generate kubeconfig using `--kube-endpoint PRIVATE_ENDPOINT`.

## 3. Prepare the EDA workload

Download [oke-e6-benchmark.zip](https://kengorucu.github.io/oci-eda-quickstart/downloads/oke-e6-benchmark.zip), upload it to Cloud Shell, and run:

```sh
unzip -o ~/oke-e6-benchmark.zip -d ~/
cd ~/e6-oke-demo
python3 tools/demo.py prepare --demo rtl
```

Preparation creates one simulator pod on each E6 node, installs Verilator and the compiler inside the pods, compiles the circuit, and performs a correctness self-test. It does not start the timed benchmark. No local Docker build or worker SSH connection is required.

Check the pods if preparation has not finished:

```sh
kubectl -n eda-native-poc get pods -o wide
```

Both demo pods must show **1/1 Running** before measurement starts.

## 4. Run the tests

```sh
cd ~/e6-oke-demo
python3 tools/demo.py run --demo rtl
```

The controller checks worker placement, matching software inventories, source hashes and pod resource limits. It runs an unmeasured warm-up, then six measured batches: three at one worker and three at two workers. Each test must report a correctness pass.

The controller runs in the background and saves its evidence under `~/eda-e6-demo-results/`. Check progress with:

```sh
python3 tools/demo.py status
```

The reference run took approximately **18 minutes**, excluding provisioning and preparation; your runtime may differ. A terminal disconnect does not automatically restart the benchmark. Reconnect and inspect status before taking further action. A Cloud Shell reset or termination can still interrupt the controller.

Run one controller at a time. The worker pods have a four-hour deadline from creation, so complete the measurement within that period.

## 5. Export and analyze the results

When status reports `complete`, export the results:

```sh
python3 tools/demo.py export
```

The command prints paths to:

- **`comparison.json`**: median times and scaling metrics.
- **A `.tar.gz` archive**: raw logs, per-test records, package inventories, source and binary hashes, Kubernetes metadata and summaries.

Download both. Open the [results explorer](https://kengorucu.github.io/oci-eda-quickstart/#results), select **Load your result JSON**, and choose `comparison.json`. The file is processed locally in your browser. The charts display the reported summary; they do not independently verify the raw logs.

### Read the summary

| Field | Meaning |
| --- | --- |
| `success` | All required batches passed the controller's checks |
| `median_seconds_by_workers.1` | Median completion time with one simulator worker |
| `median_seconds_by_workers.2` | Median completion time with two simulator workers |
| `two_worker_speedup` | One-worker median divided by two-worker median |
| `two_worker_parallel_efficiency` | Speedup divided by two; multiply by 100 for a percentage |

Compare equivalent workloads: keep the circuit, seeds, cycle count, tool versions, compiler options and resource limits consistent. Confirm all six batches passed and retain the raw evidence for detailed verification.

### Example interpretation

The measured E6 reference from 3 November 2026 produced:

| Metric | Reference result |
| --- | --- |
| One-worker median | 240.73 seconds |
| Two-worker median | 120.88 seconds |
| Speedup | 1.99× |
| Parallel efficiency | 99.57% |
| Measured tests passed | 48 of 48 |

This means dividing the same eight-test batch across two workers approximately halved its completion time. The parallelism is **between independent simulations**, not multiple threads accelerating one simulation.

These are reference observations, not performance targets. Each simulator is single threaded and its pod is capped at two logical CPUs; it does not consume the full 16-OCPU node. The measurement scope is a small synthetic digital circuit with limited per-pod resources. Evaluate production designs, analog SPICE and full-node throughput separately with the relevant tools and inputs. Worker placement, clock synchronization and background activity can affect measurements.

## 6. Clean up

Export and download the results first. Raw evidence can contain infrastructure metadata, so retain it in an appropriate location.

Remove the benchmark workers:

```sh
cd ~/e6-oke-demo
python3 tools/demo.py cleanup --demo rtl
```

This removes the demo Job and its input ConfigMap. Local evidence and result checkpoints are retained. Kubernetes checkpoints do not survive cluster deletion.

Detach any Cloud Shell private-network attachment from the demo subnet. In **Resource Manager**, run **Destroy** for the stack and wait for success. Delete the stack record afterward if desired. Deleting a stack record alone does not terminate its infrastructure.

## Further reading

- [Detailed operating runbook](RUNBOOK.md)
- [Verilator overview](https://verilator.org/guide/latest/overview.html)
- [Running Verilator simulations](https://verilator.org/guide/latest/simulating.html)
- [OCI Resource Manager destroy jobs](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/create-job-destroy.htm)
