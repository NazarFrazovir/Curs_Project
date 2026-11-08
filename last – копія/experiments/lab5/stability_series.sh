#!/usr/bin/env bash
# 3 повтори кожного сценарію, порядок чергується (round-robin), щоб дрейф хоста не корелював зі сценарієм
cd /home/claude/work
for rep in 1 2 3; do
  ./scripts/stability_run.sh A_isolated_r$rep        none no ci
  ./scripts/stability_run.sh B_noise_xz_r$rep        none yes ci
  ./scripts/stability_run.sh C_cpus05_r$rep          0.5 no ci
  ./scripts/stability_run.sh D_cpus05_noise_r$rep    0.5 yes ci
  ./scripts/stability_run.sh E_cpus025_r$rep         0.25 no ci
done
echo SERIES_DONE > expS/series_done.txt
