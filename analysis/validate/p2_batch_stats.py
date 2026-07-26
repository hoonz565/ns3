#!/usr/bin/env python3
"""Phân tích batch P2 trên rows.csv — KHÔNG chạy mô phỏng (analysis/validate).

1. Phân bố rssi_n theo bin khoảng cách (p10/p50/p90) — rssi_n quyết định
   SE(slope); link biên nhận ít beacon hơn nên slope ồn hơn đúng vùng quan
   trọng nhất.
2. SD liên-link vs trong-link của rssi_level theo bin — nếu dải liên-link
   hẹp hơn nhiễu trong-link thì RSSI không phân biệt được link trong bin đó.
   Định nghĩa: nhóm = (seed, src, dst, bin), cần >= 3 dòng; trong-link =
   SD của rssi_level trong nhóm theo thời gian; liên-link = SD giữa các
   mean của nhóm trong cùng bin.
3. Ma trận tương quan (rssi_level, rssi_slope, retry_rate) toàn tập + theo
   bin. Cặp có retry chỉ tính trên dòng có retry (pairwise complete).

Dùng: python3 analysis/validate/p2_batch_stats.py data/calib data/train --json data/train/batch_stats.json
"""
import csv
import glob
import json
import math
import sys

BIN_EDGES = [0, 200, 400, 600, 800, float("inf")]


def bin_name(dist):
    for lo, hi in zip(BIN_EDGES, BIN_EDGES[1:]):
        if lo <= dist < hi:
            return f"{lo:.0f}-{hi:.0f} m" if hi != float("inf") else f">={lo:.0f} m"
    return "?"


BIN_ORDER = [bin_name(x) for x in (0, 200, 400, 600, 800)]


def pctl(sorted_xs, q):
    return sorted_xs[int(q * (len(sorted_xs) - 1))]


class Corr:
    """Pearson tích luỹ, không giữ mảng."""

    def __init__(self):
        self.n = 0
        self.sx = self.sy = self.sxx = self.syy = self.sxy = 0.0

    def add(self, x, y):
        self.n += 1
        self.sx += x
        self.sy += y
        self.sxx += x * x
        self.syy += y * y
        self.sxy += x * y

    def r(self):
        if self.n < 3:
            return float("nan")
        cov = self.sxy - self.sx * self.sy / self.n
        vx = self.sxx - self.sx * self.sx / self.n
        vy = self.syy - self.sy * self.sy / self.n
        if vx <= 0 or vy <= 0:
            return float("nan")
        return cov / math.sqrt(vx * vy)


class Welford:
    def __init__(self):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0

    def add(self, x):
        self.n += 1
        d = x - self.mean
        self.mean += d / self.n
        self.m2 += d * (x - self.mean)

    def sd(self):
        return math.sqrt(self.m2 / (self.n - 1)) if self.n >= 2 else float("nan")


def main(roots):
    rssi_n_by_bin = {b: [] for b in BIN_ORDER}
    groups = {}  # (bin, seed, src, dst) -> Welford của rssi_level
    pairs = ("level~slope", "level~retry", "slope~retry")
    corr_all = {p: Corr() for p in pairs}
    corr_bin = {b: {p: Corr() for p in pairs} for b in BIN_ORDER}
    n_rows = 0
    n_seeds = set()

    for root in roots:
        for path in sorted(glob.glob(f"{root}/seed-*/rows.csv")):
            with open(path) as fh:
                for row in csv.DictReader(fh):
                    n_rows += 1
                    seed = row["seed"]
                    n_seeds.add(seed)
                    b = bin_name(float(row["dist_m"]))
                    level = float(row["rssi_level"])
                    slope = float(row["rssi_slope"])
                    rssi_n_by_bin[b].append(int(row["rssi_n"]))
                    key = (b, seed, row["src"], row["dst"])
                    groups.setdefault(key, Welford()).add(level)
                    corr_all["level~slope"].add(level, slope)
                    corr_bin[b]["level~slope"].add(level, slope)
                    if row["retry_rate"] != "":
                        retry = float(row["retry_rate"])
                        corr_all["level~retry"].add(level, retry)
                        corr_all["slope~retry"].add(slope, retry)
                        corr_bin[b]["level~retry"].add(level, retry)
                        corr_bin[b]["slope~retry"].add(slope, retry)

    out = {"n_rows": n_rows, "n_seeds": len(n_seeds)}
    print(f"=== {n_rows} dòng, {len(n_seeds)} seed ===\n")

    print("1) rssi_n theo bin (p10/p50/p90) — mẫu RSSI trong cửa sổ 4 s:")
    out["rssi_n"] = {}
    for b in BIN_ORDER:
        xs = sorted(rssi_n_by_bin[b])
        if not xs:
            continue
        p10, p50, p90 = pctl(xs, 0.1), pctl(xs, 0.5), pctl(xs, 0.9)
        out["rssi_n"][b] = {"p10": p10, "p50": p50, "p90": p90, "n": len(xs)}
        print(f"  {b:<12} p10 {p10:>3.0f}  p50 {p50:>3.0f}  p90 {p90:>3.0f}   ({len(xs)} dòng)")

    print("\n2) rssi_level: SD liên-link vs trong-link theo bin (nhóm >= 3 dòng):")
    out["level_sd"] = {}
    for b in BIN_ORDER:
        means = []
        within = []
        for (gb, *_), w in groups.items():
            if gb == b and w.n >= 3:
                means.append(w.mean)
                within.append(w.sd())
        if len(means) < 3:
            continue
        between = Welford()
        for m in means:
            between.add(m)
        wsorted = sorted(within)
        w_med = pctl(wsorted, 0.5)
        ratio = between.sd() / w_med if w_med else float("nan")
        out["level_sd"][b] = {"between_sd": between.sd(), "within_sd_median": w_med,
                              "ratio": ratio, "n_groups": len(means)}
        print(f"  {b:<12} liên-link SD {between.sd():5.2f} dB   trong-link SD(median) "
              f"{w_med:5.2f} dB   tỉ số {ratio:4.2f}   ({len(means)} nhóm)")

    print("\n3) Tương quan Pearson (cặp có retry: chỉ dòng có retry):")
    out["corr"] = {"all": {p: corr_all[p].r() for p in pairs}}
    print(f"  toàn tập     level~slope {corr_all['level~slope'].r():+.3f}   "
          f"level~retry {corr_all['level~retry'].r():+.3f}   "
          f"slope~retry {corr_all['slope~retry'].r():+.3f}   "
          f"(n retry = {corr_all['level~retry'].n})")
    out["corr"]["by_bin"] = {}
    for b in BIN_ORDER:
        cb = corr_bin[b]
        if cb["level~slope"].n < 3:
            continue
        out["corr"]["by_bin"][b] = {p: cb[p].r() for p in pairs}
        print(f"  {b:<12} level~slope {cb['level~slope'].r():+.3f}   "
              f"level~retry {cb['level~retry'].r():+.3f}   "
              f"slope~retry {cb['slope~retry'].r():+.3f}")

    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Phân tích batch P2 trên rows.csv, không mô phỏng")
    ap.add_argument("roots", nargs="+", help="thư mục chứa seed-*/rows.csv")
    ap.add_argument("--json", help="ghi kết quả máy-đọc-được vào file này")
    args = ap.parse_args()
    result = main(args.roots)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
