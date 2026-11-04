# Validation and scope

- Terraform CLI 1.5.7: the E6-only stack validates against OCI provider 8.29.0. No cloud resources were created during local validation.
- Offline tests cover scheduling, failure/timeout/correctness-marker detection, detached execution, retained evidence, export, scoped cleanup and ZIP contents.
- The RTL manifest selects two distinct E6 workers with matching 2-CPU / 4-GiB requests and limits and a pinned Oracle Linux image digest.
- The runnable catalog contains RTL simulation only. Logic synthesis and static timing analysis are visibly marked planned, with no run controls or included tools.
- The RTL reference comes from a completed OKE run on 3 November 2026. It is a synthetic small digital circuit, not a production EDA workload or full-node benchmark.
- The GitHub Actions workflow has not run in a GitHub repository yet. Publication and provisioning must be verified after upload.
