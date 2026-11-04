# OCI EDA Quickstart

A customer demo for deploying two OCI E6 managed workers with Terraform, running a self-checking digital RTL simulation, and measuring scaling from one simulator worker to two.

## Publish this repository on GitHub Pages

1. Create a public GitHub repository. The OCI deploy button needs a package URL accessible without authentication. No OCI account credentials belong in this repository.
2. Upload the CONTENTS of this folder at the repository root. Include `.github/workflows/pages.yml`; GitHub's file picker may hide the `.github` directory, so enable hidden-file display or use Git. Keep `stack`, `tools`, `benchmark`, `docs` and `tests` at the root. Use a `main` default branch.
3. Under Settings > Actions > General, allow the actions used by the workflow and allow workflows to publish repository contents if your organization policy requires it.
4. Under Settings > Pages, select GitHub Actions as the publishing source. Run `Publish E6 demo` from Actions if it did not start automatically.
5. The workflow validates Terraform, runs local tests, creates versioned ZIP assets in a GitHub release, and publishes `docs` to GitHub Pages. Open the URL in the successful `github-pages` deployment.

The OCI deploy button points at the Terraform release ZIP for that exact source revision. The workflow fills the repository URL automatically; no username is hardcoded. No OCI credentials or secrets are needed for GitHub Actions: deployment into the customer's tenancy happens through OCI Console.

## EDA scope

The runnable demo is **RTL simulation with Verilator**: eight self-checking circuit tests per batch, 100 million simulated clock cycles per test, three measured repeats at one and two workers, and two logical CPUs / 4 GiB per pod. The reference run includes 48 measured passes.

The catalog also identifies two planned EDA extensions:

- **Logic synthesis:** a validated RTL-to-netlist flow, potentially using Yosys.
- **Static timing analysis:** a validated flow with a gate-level netlist, timing cell library and timing constraints, potentially using OpenSTA.

These roadmap entries have no run controls, scripts or claimed performance results. They are not included in this release. See the [Yosys project](https://github.com/YosysHQ/yosys) and [OpenSTA examples](https://github.com/The-OpenROAD-Project/OpenSTA/blob/master/doc/Examples.md) for tool and input requirements.

## Customer flow

Follow [RUNBOOK.md](RUNBOOK.md) or the published page:

1. Deploy the E6 Terraform stack using the OCI button or upload its ZIP to Resource Manager.
2. Connect Cloud Shell to the cluster and verify two Ready E6 nodes.
3. Download the benchmark bundle and run prepare, then run.
4. Inspect status, export the evidence and view the result JSON in the page.
5. Export results, remove benchmark jobs, then Destroy the Resource Manager stack.

Use `--demo rtl` on prepare, run and cleanup. Status and export refer to the latest run, which records the RTL workload ID.

## Local build

```sh
python3 tools/build.py
python3 -m unittest discover -s tests -v
python3 -m http.server 8080 --directory docs
```

Open http://localhost:8080. Download links work in the local preview. The OCI deploy button activates after the publishing workflow supplies a public release URL.

## Repository layout

- `stack/`: E6-only Terraform, Resource Manager schema and deployment guide.
- `benchmark/`: pinned Oracle Linux image manifest, preparation script, runner and SystemVerilog sources.
- `tools/`: background operator, scaling controller and reproducible ZIP builder.
- `docs/`: static GitHub Pages site with local result viewer.
- `tests/`: offline operator and packaging checks.

Reference results displayed in the page are an illustrative E6 run on 3 November 2026: 240.73 s at one worker, 120.88 s at two, and 48 measured passes. They are not a performance guarantee. The demo measures a small synthetic digital MAC RTL regression with two logical CPUs and 4 GiB per pod. It does not measure full-node throughput, analog SPICE performance or production customer EDA performance.

See the [Verilator guide](https://verilator.org/guide/latest/), [OCI deploy-button documentation](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/deploybutton.htm) and [GitHub Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
