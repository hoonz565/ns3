#!/usr/bin/env python3
"""P4 — áp normalization ĐÓNG BĂNG lên toàn bộ dataset (analysis/features).

Với mỗi seed-*/rows.csv sinh seed-*/rows_norm.csv = NGUYÊN VẸN mọi cột thô
(P5 fit trên thô — CLAUDE.md quy tắc 5) + ba cột triển khai:

    s_rssi  = clip((rssi_level - p20) / (p80 - p20), 0, 1)
    s_slope = clip((rssi_slope - p20) / (p80 - p20), 0, 1)
    s_mac   = 1 - clip(retry_rate, 0, 1)     # đảo chiều; RỖNG giữ rỗng
                                             # (rỗng nghĩa "chưa truyền gì",
                                             # khác 0 — CLAUDE.md known trap)

Ngưỡng đọc từ frozen/normalization.json — KHÔNG tính lại ở đây (quy tắc 9:
train và deploy tính feature giống hệt nhau; file frozen là định nghĩa duy
nhất). Cột vật chất hoá CHỈ theo cặp triển khai (p20, p80). Bản clip-rộng
(p5, p95) không sinh cột — tránh hai "bộ triển khai" song song — nhưng thống
kê ghim biên được báo cho CẢ HAI bản, vì P5 cần biết mỗi bản kiểm duyệt bao
nhiêu trước khi so raw-vs-clip.

Dùng:
    python3 analysis/features/p4_apply_normalization.py data/calib data/train \
            --norm frozen/normalization.json --json data/p4_norm_stats.json
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import sys

BIN_EDGES = [0, 200, 400, 600, 800, float("inf")]


def bin_name(dist):
    for lo, hi in zip(BIN_EDGES, BIN_EDGES[1:]):
        if lo <= dist < hi:
            return f"{lo:.0f}-{hi:.0f} m" if hi != float("inf") else f">={lo:.0f} m"
    return "?"


BIN_ORDER = [bin_name(x) for x in (0, 200, 400, 600, 800)]


def clip01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


class PinCounter:
    """Đếm ghim biên 0/1 theo bin cho một biến chuẩn hoá."""

    def __init__(self):
        self.n = {b: 0 for b in BIN_ORDER}
        self.lo = {b: 0 for b in BIN_ORDER}
        self.hi = {b: 0 for b in BIN_ORDER}

    def add(self, b, s):
        self.n[b] += 1
        if s <= 0.0:
            self.lo[b] += 1
        elif s >= 1.0:
            self.hi[b] += 1

    def row(self, b):
        n = self.n[b]
        if n == 0:
            return None
        return {"n": n, "pinned_lo_pct": 100.0 * self.lo[b] / n,
                "pinned_hi_pct": 100.0 * self.hi[b] / n}

    def total(self):
        n = sum(self.n.values())
        return {"n": n, "pinned_lo_pct": 100.0 * sum(self.lo.values()) / n,
                "pinned_hi_pct": 100.0 * sum(self.hi.values()) / n} if n else None


def main():
    ap = argparse.ArgumentParser(description="P4: áp frozen normalization, sinh rows_norm.csv + thống kê ghim biên")
    ap.add_argument("roots", nargs="+", help="thư mục chứa seed-*/rows.csv (data/calib data/train)")
    ap.add_argument("--norm", default="frozen/normalization.json")
    ap.add_argument("--json", help="ghi thống kê máy-đọc-được vào file này")
    args = ap.parse_args()

    for root in args.roots:
        if "eval" in root:
            sys.exit("TỪ CHỐI: data/eval là vùng cấm tới P10 (CLAUDE.md quy tắc 15).")

    with open(args.norm) as fh:
        norm = json.load(fh)
    with open(args.norm, "rb") as fh:
        norm_sha = hashlib.sha256(fh.read()).hexdigest()
    lv, sl = norm["features"]["rssi_level"], norm["features"]["rssi_slope"]
    variants = {
        "deploy_p20_p80": {"level": (lv["p20"], lv["p80"]), "slope": (sl["p20"], sl["p80"])},
        "wide_p5_p95": {"level": (lv["p5"], lv["p95"]), "slope": (sl["p5"], sl["p95"])},
    }

    # PinCounter[variant][feature]; s_mac không phụ thuộc variant (ngưỡng vật lý)
    pins = {v: {"s_rssi": PinCounter(), "s_slope": PinCounter()} for v in variants}
    pin_mac = PinCounter()
    n_rows = 0
    n_retry_missing = 0
    seeds = []

    for root in args.roots:
        for seed_dir in sorted(glob.glob(os.path.join(root, "seed-*"))):
            seeds.append(seed_dir)
            in_path = os.path.join(seed_dir, "rows.csv")
            out_path = os.path.join(seed_dir, "rows_norm.csv")
            with open(in_path) as fin, open(out_path, "w", newline="") as fout:
                reader = csv.DictReader(fin)
                writer = csv.writer(fout)
                writer.writerow(list(reader.fieldnames) + ["s_rssi", "s_slope", "s_mac"])
                for row in reader:
                    n_rows += 1
                    b = bin_name(float(row["dist_m"]))
                    level = float(row["rssi_level"])
                    slope = float(row["rssi_slope"])

                    for vname, vv in variants.items():
                        p20l, p80l = vv["level"]
                        p20s, p80s = vv["slope"]
                        pins[vname]["s_rssi"].add(b, clip01((level - p20l) / (p80l - p20l)))
                        pins[vname]["s_slope"].add(b, clip01((slope - p20s) / (p80s - p20s)))

                    p20l, p80l = variants["deploy_p20_p80"]["level"]
                    p20s, p80s = variants["deploy_p20_p80"]["slope"]
                    s_rssi = clip01((level - p20l) / (p80l - p20l))
                    s_slope = clip01((slope - p20s) / (p80s - p20s))
                    if row["retry_rate"] == "":
                        n_retry_missing += 1
                        s_mac_str = ""
                    else:
                        s_mac = 1.0 - clip01(float(row["retry_rate"]))
                        pin_mac.add(b, s_mac)
                        s_mac_str = f"{s_mac:.6f}"
                    writer.writerow(list(row.values()) + [f"{s_rssi:.6f}", f"{s_slope:.6f}", s_mac_str])

    out = {
        "n_rows": n_rows,
        "n_seed_dirs": len(seeds),
        "n_retry_missing": n_retry_missing,
        "normalization": f"{args.norm}@sha256:{norm_sha}",
        "materialized_columns": "s_rssi,s_slope,s_mac from the DEPLOY pair (p20,p80) only; "
                                "wide (p5,p95) is reported here but never materialized",
        "pinning": {},
    }
    print(f"=== {n_rows} dòng / {len(seeds)} seed; retry rỗng: {n_retry_missing} "
          f"({100.0*n_retry_missing/n_rows:.2f}%) — s_mac giữ rỗng ===")
    print(f"norm: {out['normalization'][:60]}…\n")

    for vname in variants:
        out["pinning"][vname] = {}
        print(f"-- bản {vname} --")
        for feat in ("s_rssi", "s_slope"):
            pc = pins[vname][feat]
            out["pinning"][vname][feat] = {"by_bin": {}, "total": pc.total()}
            t = pc.total()
            print(f"  {feat:<8} TOÀN TẬP: ghim-0 {t['pinned_lo_pct']:5.1f}%  ghim-1 {t['pinned_hi_pct']:5.1f}%")
            for b in BIN_ORDER:
                r = pc.row(b)
                if r is None:
                    continue
                out["pinning"][vname][feat]["by_bin"][b] = r
                print(f"    {b:<12} ghim-0 {r['pinned_lo_pct']:5.1f}%  ghim-1 {r['pinned_hi_pct']:5.1f}%  (n {r['n']})")
        print()

    out["pinning"]["s_mac_physical"] = {"by_bin": {}, "total": pin_mac.total()}
    t = pin_mac.total()
    print(f"-- s_mac (ngưỡng vật lý, mọi bản) --")
    print(f"  s_mac    TOÀN TẬP: ghim-0 {t['pinned_lo_pct']:5.1f}% (retry=1)  ghim-1 {t['pinned_hi_pct']:5.1f}% (retry=0)")
    for b in BIN_ORDER:
        r = pin_mac.row(b)
        if r is None:
            continue
        out["pinning"]["s_mac_physical"]["by_bin"][b] = r
        print(f"    {b:<12} ghim-0 {r['pinned_lo_pct']:5.1f}%  ghim-1 {r['pinned_hi_pct']:5.1f}%  (n {r['n']})")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print(f"\nđã ghi {args.json}")


if __name__ == "__main__":
    main()
