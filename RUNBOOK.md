# Run the E6 OKE EDA lab

## 1. Deploy

Use the page's Deploy to Oracle Cloud button, or download oke-e6-stack.zip and upload it in Resource Manager > Stacks > Create stack > My configuration.

The stack creates a Basic OKE cluster, a private managed E6 worker pool, VCN, public API subnet, private worker subnet, routes, security lists, and internet/NAT/service gateways. Defaults are two VM.Standard.E6.Flex nodes with 16 OCPUs, 128 GB RAM and 100-GB boot volumes each. It requires capacity for 32 OCPUs and 256 GB RAM. Infrastructure incurs normal OCI charges until destroyed. No load balancer or public application is created.

Select region, compartment, full tenancy-specific availability domain, full supported Kubernetes version and trusted API CIDR. The image is automatically selected from OKE options and checked for E6 compatibility. Run Plan before Apply: expect 12 resources to add, zero to change, zero to destroy in a new stack. Capacity is verified by the actual provisioning attempt, not guaranteed by a successful Plan.

For Cloud Shell public access, first select an appropriate network mode and run:

```sh
curl -4 -fsS --connect-timeout 5 --max-time 10 https://api.ipify.org; echo
```

Enter the returned IPv4 address followed by /32 as admin_cidr. Availability-domain names are specific to your tenancy. Copy one with E6 capacity; do not copy an example from another tenancy.

## 2. Connect

Use one file for both generating the configuration and running kubectl. Replace the cluster ID placeholder with the stack's cluster_id output and set the deployment region:

```sh
# Replace this value with cluster_id from the stack outputs.
DEMO_CLUSTER_OCID="REPLACE_WITH_CLUSTER_ID_OUTPUT"
# Set this to your deployment region.
DEMO_REGION="eu-frankfurt-1"

export KUBECONFIG="$HOME/.kube/eda-e6-demo-config"
mkdir -p "$HOME/.kube"

oci ce cluster create-kubeconfig \
  --cluster-id "$DEMO_CLUSTER_OCID" \
  --region "$DEMO_REGION" \
  --file "$KUBECONFIG" \
  --token-version 2.0.0 \
  --kube-endpoint PUBLIC_ENDPOINT

kubectl config current-context
kubectl --request-timeout=10s get nodes -o wide \
  -L compute-family,node.kubernetes.io/instance-type
```

If copying the OKE Console's Access cluster command, change its --file value to "$KUBECONFIG". The Console's default ~/.kube/config differs from this quickstart's file. Export KUBECONFIG again after starting a new shell session. A missing context or localhost:8080 endpoint means the cluster configuration has not been loaded.

You need two Ready VM.Standard.E6.Flex nodes labelled compute-family=e6 and workload=eda-regression.

If the API times out, compare the endpoint in kubeconfig with the cluster details. Check the current client egress IP against admin_cidr and confirm TCP 6443 is allowed in the API subnet. Cloud Shell's successful web-IP lookup does not prove API-port connectivity. For private access, attach Cloud Shell to the worker subnet named in cloud_shell_private_network and regenerate kubeconfig with --kube-endpoint PRIVATE_ENDPOINT.

## 3. Prepare and run

Download oke-e6-benchmark.zip from the page and upload it to Cloud Shell. Then:

```sh
unzip -o ~/oke-e6-benchmark.zip -d ~/
cd ~/e6-oke-demo
python3 tools/demo.py prepare --demo rtl
python3 tools/demo.py run --demo rtl
```

This release includes only the RTL simulation workload. Use `--demo rtl` for prepare, run and cleanup.

Preparation installs Verilator and GCC, compiles the circuit and runs a correctness self-test in two pods. The manifest pins the Oracle Linux container digest. Installed packages can change over time; actual inventories and source hashes are captured and compared between pods. No local Docker/Podman build is required.

The controller starts in the background. It performs an excluded warm-up, then three repeats at one and two workers: eight tests per batch and 48 measured test executions. Each test runs 100 million simulated clock cycles with seeds 1000–1007. One worker runs all eight tests sequentially; two workers run four each on distinct nodes. Each simulator pod requests and is limited to two Kubernetes logical CPUs and 4 GiB RAM. The simulator is single threaded; this does not measure the node's full 16-OCPU capacity.

The RTL reference measurement took approximately 18 minutes, excluding preparation and provisioning. Runtime varies. Pods expire four hours after creation. Run one controller at a time. A failed or interrupted controller retains evidence and does not automatically remeasure. Logic synthesis and static timing analysis are planned EDA additions, not deployable tests in this release.

## 4. Status and export

```sh
cd ~/e6-oke-demo
python3 tools/demo.py status
python3 tools/demo.py export
```

A terminal disconnection does not itself kill the detached controller, but a Cloud Shell reset or termination can. Reconnect and run status; do not start another measurement automatically. If a dead process leaves a lock, inspect status and guest/pod activity first, then `python3 tools/demo.py unlock` can release the stale local lock.

The export command prints paths to a raw evidence archive and comparison.json. Download both. Load comparison.json in the page to view your results; it is read locally in your browser, not uploaded. The chart displays reported medians and derived scaling, not an independent raw-log audit. Source and binary hashes, metadata, package inventories, setup logs, raw records and summaries are saved in the result directory. Kubernetes ConfigMap checkpoints provide a second copy of completed records but do not survive cluster deletion. Do not publish raw archives by default; they can contain tenancy, cluster, node or infrastructure metadata.

## 5. Cleanup

After exporting:

```sh
python3 tools/demo.py cleanup --demo rtl
```

This deletes only this demo's worker Job and input ConfigMap. It does not delete the shared namespace, other workloads, result ConfigMaps or local archives.

Detach Cloud Shell private networking from the demo subnet if used. Run Destroy in Resource Manager and wait for success. Delete the stack record afterward if desired. Deleting only the stack record does not terminate its cloud resources.
