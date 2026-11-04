#!/usr/bin/env bash
set -euo pipefail

# Functional smoke-test preparation inside the pod, never on the worker host.
# Use Oracle repositories; do not disable signature checks or FIPS settings.
printf 'POC_STAGE package-install-start\n'
dnf -y install oracle-epel-release-el9
dnf -y --enablerepo=ol9_developer_EPEL,ol9_codeready_builder install \
  verilator verilator-devel gcc-c++ make python3
dnf clean all
printf 'POC_STAGE package-install-complete\n'
verilator --version
g++ --version
rpm -q verilator verilator-devel gcc-c++ python3

printf 'POC_STAGE compile-start\n'
verilator --binary --timing -Wno-fatal -O3 -j 2 \
  -CFLAGS '-std=c++20' --top-module tb --Mdir /work/obj \
  /config/mac.sv /config/tb.sv
printf 'POC_STAGE compile-complete\n'

if [ "${POC_PREPARE_ONLY:-0}" = "1" ]; then
  /work/obj/Vtb +seed=999 +cycles=1000000
  touch /work/prepared
  printf 'POC_STAGE prepared-for-scaling\n'
  # The operator runs measured batches through kubectl exec after ALL pods are
  # ready. Setup, image pulls, and compilation cannot overlap measured tests.
  exec sleep 14400
fi

export SIM_COMMAND_JSON='["/work/obj/Vtb", "+seed={seed}", "+cycles={cycles}"]'
printf 'POC_STAGE simulation-start\n'
exec python3 /config/runner.py

