# Min–Max metrics test: scenarios 0001–0081

Run from the repository root:

```bash
python3 test/minmax_metrics_s0001_s0081/analyze.py
```

The script streams all usable `rows.csv` files twice: once for exact summary
statistics and once for exact histogram counts. It does not create a second
multi-gigabyte row-level dataset. Results are written to `results/`.

Outputs include three histograms with raw and normalized axes, three normalized
boxplots by scenario, global statistics, per-scenario normalized statistics,
exact histogram bins, an input audit, and a short interpretation report.
