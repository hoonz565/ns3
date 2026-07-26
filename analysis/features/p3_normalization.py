#!/usr/bin/env python3
"""P3 — hiệu chuẩn ngưỡng chuẩn hoá, đóng băng vào frozen/normalization.json.

Gộp rows.csv của ĐÚNG 5 seed calibration (data/calib/seed-{1..5}), tính
percentile cho hai feature liên tục:

    rssi_level  : p20/p80 (bộ ĐÓNG BĂNG cho triển khai P8)
                  + p5/p95 (chỉ để P5 so bản clip rộng — PLAN.md P3)
    rssi_slope  : như trên
    retry_rate  : KHÔNG percentile — ngưỡng vật lý [0, 1] theo định nghĩa
                  của tỉ lệ; triển khai đảo chiều s_mac = 1 − clip(retry, 0, 1)

Percentile = nội suy tuyến tính giữa hai hạng kề (R type-7, trùng mặc định
numpy): pos = q·(n−1). Ghi rõ ở đây vì p2_batch_stats.py dùng phép lấy hạng
thô hơn (int index) — hai script KHÔNG hoán đổi được cho nhau.

Bất biến cưỡng chế trong code, không chỉ trong tài liệu:
  - từ chối chạy nếu file output đã tồn tại (frozen/ bất biến — cần đổi thì
    tạo normalization-v2.json và ghi lý do vào report, WORKFLOW.md mục 2);
  - từ chối mọi root có chữ "eval" (data/eval cấm tới P10);
  - đòi hỏi đúng seeds 1–5, manifest sạch (git_dirty=false) và đồng nhất
    (một git_sha, một config_sha256, một binary_sha256).

Dùng:
    python3 analysis/features/p3_normalization.py data/calib \
            --out frozen/normalization.json
"""
import argparse
import csv
import glob
import hashlib
import json
import math
import os
import sys

EXPECTED_SEEDS = [1, 2, 3, 4, 5]
QUANTILES = {"p5": 0.05, "p20": 0.20, "p80": 0.80, "p95": 0.95}


def pctl(sorted_xs, q):
    """R type-7 / numpy 'linear': nội suy tuyến tính tại pos = q*(n-1)."""
    n = len(sorted_xs)
    if n == 0:
        raise ValueError("empty sample")
    pos = q * (n - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_xs[lo] * (1.0 - frac) + sorted_xs[hi] * frac


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description="P3: percentile 5 seed calibration -> frozen/normalization.json")
    ap.add_argument("root", help="thư mục calibration chứa seed-*/rows.csv (data/calib)")
    ap.add_argument("--out", default="frozen/normalization.json")
    args = ap.parse_args()

    if "eval" in args.root:
        sys.exit("TỪ CHỐI: data/eval là vùng cấm tới P10 (CLAUDE.md quy tắc 15).")
    if os.path.exists(args.out):
        sys.exit(f"TỪ CHỐI: {args.out} đã tồn tại — frozen/ bất biến. "
                 "Cần đổi thì tạo bản -v2 và ghi lý do vào report (WORKFLOW.md mục 2).")

    seed_dirs = sorted(glob.glob(os.path.join(args.root, "seed-*")))
    seeds = sorted(int(os.path.basename(d).split("-")[1]) for d in seed_dirs)
    if seeds != EXPECTED_SEEDS:
        sys.exit(f"TỪ CHỐI: batch calibration phải là đúng seeds {EXPECTED_SEEDS}, thấy {seeds}.")

    # --- provenance: manifest sạch và đồng nhất trên cả 5 seed ---------------
    shas, cfg_shas, bin_shas = set(), set(), set()
    for d in seed_dirs:
        with open(os.path.join(d, "run_manifest.json")) as fh:
            m = json.load(fh)
        if m.get("git_dirty"):
            sys.exit(f"TỪ CHỐI: {d} có git_dirty=true — không tái lập được.")
        shas.add(m["git_sha"])
        cfg_shas.add(m["config_sha256"])
        bin_shas.add(m["binary_sha256"])
    for name, s in (("git_sha", shas), ("config_sha256", cfg_shas), ("binary_sha256", bin_shas)):
        if len(s) != 1:
            sys.exit(f"TỪ CHỐI: {name} không đồng nhất giữa 5 seed: {sorted(s)}")

    # --- đọc feature (CHỈ cột feature — ranh giới analysis/features) ---------
    level, slope = [], []
    rows_per_seed = {}
    n_missing = 0
    for d in seed_dirs:
        seed = int(os.path.basename(d).split("-")[1])
        n = 0
        with open(os.path.join(d, "rows.csv")) as fh:
            for row in csv.DictReader(fh):
                n += 1
                if row["rssi_level"] == "" or row["rssi_slope"] == "":
                    n_missing += 1
                    continue
                level.append(float(row["rssi_level"]))
                slope.append(float(row["rssi_slope"]))
        rows_per_seed[seed] = n
    n_rows = sum(rows_per_seed.values())
    level.sort()
    slope.sort()

    # --- percentile gộp + per-seed (per-seed chỉ để báo cáo độ ổn định) ------
    pooled = {
        "rssi_level": {k: pctl(level, q) for k, q in QUANTILES.items()},
        "rssi_slope": {k: pctl(slope, q) for k, q in QUANTILES.items()},
    }
    per_seed = {}
    for d in seed_dirs:
        seed = int(os.path.basename(d).split("-")[1])
        lv, sl = [], []
        with open(os.path.join(d, "rows.csv")) as fh:
            for row in csv.DictReader(fh):
                if row["rssi_level"] == "" or row["rssi_slope"] == "":
                    continue
                lv.append(float(row["rssi_level"]))
                sl.append(float(row["rssi_slope"]))
        lv.sort()
        sl.sort()
        per_seed[str(seed)] = {
            "rssi_level": {k: pctl(lv, q) for k, q in QUANTILES.items()},
            "rssi_slope": {k: pctl(sl, q) for k, q in QUANTILES.items()},
            "n_rows": rows_per_seed[seed],
        }

    out = {
        "artifact": args.out,
        "phase": "P3",
        "created": "2026-07-27",
        "frozen": True,
        "source": {
            "batch": "calibration",
            "roots": [os.path.relpath(d) for d in seed_dirs],
            "seeds": seeds,
            "n_rows": n_rows,
            "n_rows_missing_feature": n_missing,
            "git_sha": sorted(shas)[0],
            "config_sha256": sorted(cfg_shas)[0],
            "binary_sha256": sorted(bin_shas)[0],
        },
        "method": ("pooled rows across the 5 calibration seeds; percentile = linear "
                   "interpolation between closest ranks at pos = q*(n-1) "
                   "(R type-7, numpy default)"),
        "features": {
            "rssi_level": {"unit": "dBm", **pooled["rssi_level"]},
            "rssi_slope": {"unit": "dB/s", **pooled["rssi_slope"]},
            "retry_rate": {
                "unit": "ratio", "lo": 0.0, "hi": 1.0,
                "note": ("physical bounds, NOT percentiles: retry_rate is a ratio in [0,1] "
                         "by definition; deployment inverts direction, s_mac = 1 - clip(retry_rate, 0, 1)"),
            },
        },
        "deployment_formula": ("s = clip((x - p20) / (p80 - p20), 0, 1); the FROZEN deployment pair "
                               "is (p20, p80). (p5, p95) are recorded ONLY so P5 can compare the "
                               "wider-clip variant (PLAN.md P3) without recomputing on calib data."),
        "fitting_note": ("P5 fits on RAW features (CLAUDE.md rule 5) — these constants exist for "
                         "deployment (P8) and for the P5 clipped-variant comparison, never for fitting."),
        "per_seed_stability": per_seed,
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f"đã ghi {args.out}  (sha256 {sha256_file(args.out)[:12]}…)\n")

    print(f"=== {n_rows} dòng, seeds {seeds}, thiếu feature: {n_missing} ===")
    for feat in ("rssi_level", "rssi_slope"):
        p = pooled[feat]
        unit = "dBm" if feat == "rssi_level" else "dB/s"
        print(f"  {feat:<11} p5 {p['p5']:+9.4f}  p20 {p['p20']:+9.4f}  "
              f"p80 {p['p80']:+9.4f}  p95 {p['p95']:+9.4f}  [{unit}]"
              f"   (p80-p20 = {p['p80']-p['p20']:.4f})")
    print("  retry_rate  ngưỡng vật lý [0, 1], không percentile — s_mac = 1 - clip(retry, 0, 1)")
    print("\n  per-seed p20/p80 (độ ổn định giữa seed):")
    for s in map(str, seeds):
        ps = per_seed[s]
        print(f"    seed {s}: level p20 {ps['rssi_level']['p20']:+8.4f} / p80 {ps['rssi_level']['p80']:+8.4f}"
              f"   slope p20 {ps['rssi_slope']['p20']:+7.4f} / p80 {ps['rssi_slope']['p80']:+7.4f}"
              f"   ({ps['n_rows']} dòng)")


if __name__ == "__main__":
    main()
