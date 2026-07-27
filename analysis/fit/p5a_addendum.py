#!/usr/bin/env python3
"""P5a addendum: midpoint nhãn + attenuation trong dist [400,600).

Chỉ đọc rows_norm.csv của fit seeds 6-29. Không đọc holdout 30-35, không
fit mô hình đối chứng P5b.
"""
import argparse
import csv
import json
import os

import numpy as np

from p5a_fit import glm_fit, sha256_file

FIT_SEEDS = list(range(6, 30))
LABEL_WIN_S = 4.0
CBR_PERIOD_S = 1.0 / 8.0
PROBE_MID_S = LABEL_WIN_S / 2.0
CBR_GRID_MID_S = (LABEL_WIN_S - CBR_PERIOD_S) / 2.0
RATIO_P5A_S = 2.149818747452404
RATIO_BOOT_CI95_S = [2.0793362662194808, 2.212627281053448]


def fit_bands(d, bands):
    out = []
    for lo, hi in bands:
        idx = np.where((d["n_rssi"] >= lo) & (d["n_rssi"] <= hi))[0]
        res = glm_fit(d, idx=idx)
        out.append({
            "band": [int(lo), int(hi)],
            "n_rows": int(len(idx)),
            "n_clusters": int(len(set(d["seed"][idx]))),
            "beta_slope": float(res.params[2]),
            "se_slope": float(res.bse[2]),
            "ci95_slope": [
                float(res.params[2] - 1.96 * res.bse[2]),
                float(res.params[2] + 1.96 * res.bse[2]),
            ],
            "beta_rssi": float(res.params[1]),
            "beta_retry": float(res.params[3]),
        })
    slopes = [row["beta_slope"] for row in out]
    return {
        "bands": out,
        "monotone_increasing": all(b > a for a, b in zip(slopes, slopes[1:])),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default="data/train")
    ap.add_argument("--split", default="frozen/split.json")
    ap.add_argument("--json", default="data/p5a_addendum.json")
    args = ap.parse_args()
    if "eval" in args.root:
        raise SystemExit("TỪ CHỐI: data/eval là vùng cấm tới P10.")

    split = json.load(open(args.split))
    assert split["fit_seeds"] == FIT_SEEDS

    d = {k: [] for k in ("seed", "level", "slope", "n_rssi", "retry", "succ", "fail")}
    attempts = {"probe": 0, "cbr": 0}
    row_midpoints = []
    rows_probe_only = rows_cbr_only = 0
    rows_used = rows_distance = 0
    profiles = set()
    queue_p99_ms = []
    queue_max_ms = []
    for seed in FIT_SEEDS:
        manifest = json.load(open(os.path.join(args.root, f"seed-{seed}", "run_manifest.json")))
        assert manifest["seed"] == seed
        profiles.add(tuple(manifest[k] for k in
                           ("binary_sha256", "config_sim_sha256", "sim_params_sha256")))
        summary = json.load(open(os.path.join(args.root, f"seed-{seed}", "summary.json")))
        queue_p99_ms.append(summary["queue_delay_ms_p99"])
        queue_max_ms.append(summary["queue_delay_ms_max"])
        with open(os.path.join(args.root, f"seed-{seed}", "rows_norm.csv")) as fh:
            for row in csv.DictReader(fh):
                if not row["retry_rate"]:
                    continue
                rows_used += 1
                tp, tc = int(row["trials_probe"]), int(row["trials_cbr"])
                trials, fails = int(row["trials_future"]), int(row["fails_future"])
                assert tp + tc == trials
                attempts["probe"] += tp
                attempts["cbr"] += tc
                row_midpoints.append((tp * PROBE_MID_S + tc * CBR_GRID_MID_S) / trials)
                rows_probe_only += tc == 0
                rows_cbr_only += tp == 0
                dist = float(row["dist_m"])
                if not 400.0 <= dist < 600.0:
                    continue
                rows_distance += 1
                for key, value in (
                    ("seed", int(row["seed"])),
                    ("level", float(row["rssi_level"])),
                    ("slope", float(row["rssi_slope"])),
                    ("n_rssi", int(row["rssi_n"])),
                    ("retry", float(row["retry_rate"])),
                    ("succ", trials - fails),
                    ("fail", fails),
                ):
                    d[key].append(value)
    assert len(profiles) == 1
    d = {k: np.asarray(v) for k, v in d.items()}

    total_attempts = attempts["probe"] + attempts["cbr"]
    # CBR start và period đều nằm trên lưới 0.125 s so với anchor 4 s:
    # các phase [0, 0.125, ..., 3.875] có mean 1.9375 s. Cho phép phase
    # bất kỳ trong một period tạo khoảng bảo thủ [1.9375, 2.0625].
    cbr_mid_range = [CBR_GRID_MID_S, CBR_GRID_MID_S + CBR_PERIOD_S]
    weighted_mid = (
        attempts["probe"] * PROBE_MID_S + attempts["cbr"] * CBR_GRID_MID_S
    ) / total_attempts
    weighted_range = [
        (attempts["probe"] * PROBE_MID_S + attempts["cbr"] * x) / total_attempts
        for x in cbr_mid_range
    ]

    q25, q50, q75 = np.percentile(d["n_rssi"], [25, 50, 75])
    assert q25 < q50 < q75 and all(float(q).is_integer() for q in (q25, q50, q75))
    quartile_bands = [
        (int(d["n_rssi"].min()), int(q25) - 1),
        (int(q25), int(q50) - 1),
        (int(q50), int(q75) - 1),
        (int(q75), int(d["n_rssi"].max())),
    ]
    quartile = fit_bands(d, quartile_bands)
    original = fit_bands(d, [(3, 9), (10, 19), (20, 29), (30, 10**9)])

    profile = next(iter(profiles))
    out = {
        "scope": {"fit_seeds": FIT_SEEDS, "holdout_read": False},
        "provenance": {
            "binary_sha256": profile[0],
            "config_sim_sha256": profile[1],
            "sim_params_sha256": profile[2],
            "split": f"{args.split}@sha256:{sha256_file(args.split)}",
            "analysis_script": f"{__file__}@sha256:{sha256_file(__file__)}",
        },
        "midpoint": {
            "method": "scheduler-derived expectation; per-attempt timestamps are not stored",
            "probe_stop_restart_timing_observed": False,
            "n_rows_glm": rows_used,
            "attempts": {**attempts, "total": total_attempts},
            "cbr_attempt_fraction": attempts["cbr"] / total_attempts,
            "probe_expected_s": PROBE_MID_S,
            "cbr_grid_expected_s": CBR_GRID_MID_S,
            "cbr_unknown_phase_range_s": cbr_mid_range,
            "per_row_expected_s": {
                "probe_only_rows": rows_probe_only,
                "cbr_only_rows": rows_cbr_only,
                "mean_unweighted": float(np.mean(row_midpoints)),
                "p05_p50_p95": np.percentile(row_midpoints, [5, 50, 95]).tolist(),
                "min_max": [float(min(row_midpoints)), float(max(row_midpoints))],
            },
            "attempt_weighted_expected_s": weighted_mid,
            "attempt_weighted_phase_range_s": weighted_range,
            "queue_delay_p99_ms_across_seeds": {
                "median": float(np.median(queue_p99_ms)),
                "max": float(max(queue_p99_ms)),
            },
            "queue_delay_max_ms_across_seeds": float(max(queue_max_ms)),
            "p5a_ratio_s": RATIO_P5A_S,
            "p5a_ratio_bootstrap_ci95_s": RATIO_BOOT_CI95_S,
            "ratio_minus_weighted_expected_s": RATIO_P5A_S - weighted_mid,
            "feature_window_center_relative_t_s": -LABEL_WIN_S / 2.0,
            "label_center_relative_t_s": weighted_mid,
            "center_to_center_horizon_s": weighted_mid + LABEL_WIN_S / 2.0,
            "midpoint_explains_ratio": False,
            "conclusion": (
                "Not supported under the scheduler-derived expectation; unknown "
                "probe admission stop/restart timing prevents a direct timestamp test."
            ),
        },
        "fixed_distance": {
            "range_m": [400.0, 600.0],
            "n_rows": rows_distance,
            "rssi_n_quantiles": [float(q25), float(q50), float(q75)],
            "quartile_bands": quartile,
            "original_bands_sensitivity": original,
        },
    }
    with open(args.json, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    print(f"midpoint kỳ vọng: {weighted_mid:.4f} s "
          f"(phase range {weighted_range[0]:.4f}-{weighted_range[1]:.4f}); "
          f"ratio P5a {RATIO_P5A_S:.4f} s -> KHÔNG khớp")
    print("beta_slope [400,600), quartile rssi_n:",
          " -> ".join(f"{x['beta_slope']:.4f}" for x in quartile["bands"]),
          f"; monotone={quartile['monotone_increasing']}")
    print(f"đã ghi {args.json}")


if __name__ == "__main__":
    main()
