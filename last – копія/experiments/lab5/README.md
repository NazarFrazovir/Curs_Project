# ЛР5 — сирі дані експериментів

Тут лежать скрипти та «сирі» результати, на яких побудовано звіт ЛР5. Нічого з цієї папки
не запускається в CI (pytest шукає тести лише в `tests/`).

Стенд: Linux, 2 vCPU, 8 GB RAM; PostgreSQL 16; застосунок `python app.py` (як у Dockerfile);
k6 v0.54.0 на тій самій машині; у БД 50 товарів і 5000 рухів.

| Папка / файл | Що це |
|---|---|
| `measure.py` | збір lizard / radon / complexipy / ruff для одного файлу → JSON |
| `reliability/scenario_A_encoding_eol.jsonl.txt` | reports.py у CRLF, LF, змішаних EOL, UTF-8+BOM, CP1251 |
| `reliability/scenario_B_versions.jsonl.txt` | ті самі файли під Python 3.9 / 3.11 / 3.12 / 3.13 і старими версіями інструментів |
| `reliability/complexipy_versions.txt` | Cognitive Complexity у 4 версіях complexipy; NLOC у 2 версіях lizard |
| `stability_run.sh` | один прогін k6 (`PROFILE=ci`) + квота CPU через cgroup (той самий механізм, що `docker --cpus`) + шум `xz -9e` |
| `stability_series.sh` | 5 сценаріїв × 3 повтори по колу (round-robin) |
| `stability/<сценарій>_r<N>/` | `summary.json` (k6), `k6.txt` (вивід, steal ticks, код виходу), `resources.txt` |
| `stability/single_run_cpus05_outlier/` | окремий одиночний прогін `--cpus=0.5`, що дав p95 = 430 мс (у серії 3/3 прогони ≈ 100 мс) |
| `mutation/test_goodhart_farm.py` | **антиприклад**: тести без assert, що піднімають coverage |
| `mutation/*.json` | coverage та статистика mutmut для 3 етапів: honest / farm / contract |

Повторити Stability-серію (знадобляться root для cgroup v1 і застосунок на :5000;
шляхи `W=` і до `load/balance.js` у `stability_run.sh` відповідають стенду — змініть під свою машину):

```bash
./stability_series.sh
python summarize.py 'expS/[A-E]_*'
python ../../scripts/loadtest_gate.py expS/A_isolated_r*/summary.json
```
