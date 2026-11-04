# OCI EDA Quickstart — OCI Resource Manager stack

Deploys one Basic OKE cluster, two VM.Standard.E6.Flex managed workers and dedicated networking. Worker defaults: 16 OCPUs, 128 GB RAM and 100-GB boot volume each. Fixed worker count: two. No SSH key required.

Configure your region, compartment, full tenancy availability domain, currently supported Kubernetes patch version, and trusted client IPv4 CIDR. Oracle Linux 9 OKE x86_64 worker images are selected automatically from current OKE options. Image/shape compatibility is checked during Plan.

Run Plan: expect 12 managed resources to add, zero to change, zero to destroy in a new stack. Review the resolved image and sizing, then Apply. After both nodes are Ready, use the create_kubeconfig output to access the cluster and run the separate benchmark operator.

The stack provisions infrastructure only. Benchmark tools install inside pods after deployment. The public Kubernetes API is restricted to the supplied CIDR and internal worker traffic; nodes use private IPs. For private Cloud Shell access, use cloud_shell_private_network outputs and PRIVATE_ENDPOINT kubeconfig.

The selected benchmark runs a synthetic digital RTL workload, not a complete customer application. Export results before removing resources. Run Resource Manager Destroy to stop infrastructure charges; delete the stack record only after Destroy succeeds.
