#!/usr/bin/env python3
"""P4 — VIF trên BA FEATURE THÔ, chỉ tập fit (analysis/validate).

Cổng PLAN.md P4: VIF < 5 cho cả ba feature, và cả ba có phương sai đáng kể.

- Tập fit đọc từ frozen/split.json (seeds 6-29) — KHÔNG lấy holdout, không
  lấy calib: VIF phục vụ diễn giải β của P5, nên đo trên đúng tập P5 sẽ fit.
- Feature THÔ (rssi_level, rssi_slope, retry_rate) — quy tắc 5: P5 fit thô.
- Chỉ dòng có retry_rate (GLM cũng chỉ dùng được các dòng này); số dòng bị
  loại vì thiếu retry được đếm và in — CLAUDE.md: GLM loại chúng LẶNG LẼ,
  ở đây phải thành số nhìn thấy được.
- VIF_j = đường chéo của nghịch đảo ma trận tương quan (tương đương chính
  xác 1/(1-R²_j) khi hồi quy feature j lên hai feature kia có intercept).

Dùng:
    python3 analysis/validate/p4_vif.py data/train \
            --split frozen/split.json --json data/p4_vif.json
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np

FEATURES = ["rssi_level", "rssi_slope", "retry_rate"]


def main():
    ap = argparse.ArgumentParser(description="P4: VIF ba feature thô trên tập fit")
    ap.add_argument("root", help="thư mục chứa seed-*/rows.csv (data/train)")
    ap.add_argument("--split", default="frozen/split.json")
    ap.add_argument("--json", help="ghi kết quả máy-đọc-được vào file này")
    args = ap.parse_args()

    if "eval" in args.root:
        sys.exit("TỪ CHỐI: data/eval là vùng cấm tới P10 (CLAUDE.md quy tắc 15).")

    with open(args.split) as fh:
        split = json.load(fh)
    fit_seeds = split["fit_seeds"]

    triples = []
    n_total = 0
    n_missing_retry = 0
    for seed in fit_seeds:
        path = os.path.join(args.root, f"seed-{seed}", "rows.csv")
        if not os.path.isfile(path):
            sys.exit(f"TỪ CHỐI: thiếu {path} — tập fit phải đủ {len(fit_seeds)} seed.")
        with open(path) as fh:
            for row in csv.DictReader(fh):
                n_total += 1
                if row["retry_rate"] == "":
                    n_missing_retry += 1
                    continue
                triples.append((float(row["rssi_level"]),
                                float(row["rssi_slope"]),
                                float(row["retry_rate"])))

    X = np.asarray(triples)
    sds = X.std(axis=0, ddof=1)
    means = X.mean(axis=0)
    R = np.corrcoef(X, rowvar=False)
    vifs = np.diag(np.linalg.inv(R))

    print(f"=== tập fit: seeds {fit_seeds[0]}..{fit_seeds[-1]} ({len(fit_seeds)} seed), "
          f"{n_total} dòng, dùng {len(triples)} (loại {n_missing_retry} thiếu retry = "
          f"{100.0*n_missing_retry/n_total:.2f}%) ===\n")
    print("Phương sai (cổng: 'đáng kể' cho cả ba):")
    for f, m, s in zip(FEATURES, means, sds):
        print(f"  {f:<11} mean {m:+9.4f}   SD {s:8.4f}")
    print("\nTương quan Pearson (tập fit):")
    pairs = [(0, 1, "level~slope"), (0, 2, "level~retry"), (1, 2, "slope~retry")]
    for i, j, name in pairs:
        print(f"  {name:<12} {R[i, j]:+.3f}")
    print("\nVIF (cổng: < 5 cho cả ba):")
    ok = True
    for f, v in zip(FEATURES, vifs):
        mark = "✓" if v < 5.0 else "✗"
        ok = ok and v < 5.0
        print(f"  {f:<11} VIF {v:6.3f}  {mark}")
    print(f"\nKẾT LUẬN: {'ĐẠT' if ok else 'TRƯỢT'} cổng VIF < 5")

    if args.json:
        out = {
            "fit_seeds": fit_seeds,
            "n_rows_total": n_total,
            "n_rows_used": len(triples),
            "n_rows_missing_retry": n_missing_retry,
            "features": FEATURES,
            "mean": means.tolist(),
            "sd": sds.tolist(),
            "corr": {name: float(R[i, j]) for i, j, name in pairs},
            "vif": {f: float(v) for f, v in zip(FEATURES, vifs)},
            "gate_vif_lt_5": bool(ok),
        }
        with open(args.json, "w") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print(f"đã ghi {args.json}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
