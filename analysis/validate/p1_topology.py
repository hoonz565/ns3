#!/usr/bin/env python3
"""P1 — đo hình học mà dataset sẽ được thu trong đó.

Hai câu hỏi, cả hai phải đo chứ không suy từ công thức:

  a) DEGREE. Chiều cao hộp (500 m) xấp xỉ bằng tầm phủ, nên công thức 2D và 3D
     lệch nhau gần gấp đôi và cầu phủ sóng bị biên cắt. Báo cáo **phân bố**
     (mean, median, p10, p90, tỉ lệ thời gian cô lập), không chỉ mean.
  b) PHÂN BỐ VỊ TRÍ. Node có dồn vào biên không? `GaussMarkovMobilityModel::
     DoWalk` phản xạ (đảo dấu vận tốc VÀ lật mean direction/pitch) nên không kỳ
     vọng dán trần — nhưng hiện vật đáng nghi hơn là z đi ngang chậm: 500 m ở
     ~1 m/s ≈ 500 s > run 300 s, tức mỗi node chỉ quét một phần dải cao.
     Histogram gộp không phân biệt được "quét đều" với "mỗi node kẹt một dải",
     nên script báo cả **z-range từng node**.

Degree báo cáo dưới HAI định nghĩa, vì con số 5.28 trong sim-config/fanet-tier2.conf
đến từ một scenario khác (link-dataset-fanet.cc, không có trong cây này) với luật
nạp neighbor khác:

    chặt  — link i->j tồn tại nếu tỉ lệ nhận beacon >= ngưỡng trong cửa sổ
    lỏng  — link i->j tồn tại nếu nhận được >= 1 beacon trong cửa sổ
            (tương tự luật neighborTtl: "vừa nghe thấy")

Chạy:
    python3 analysis/validate/p1_topology.py --run data/smoke/p1-topology
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Ngưỡng công bố TRƯỚC khi nhìn số liệu.
GATE_DEGREE_LO = 4.0  # mean degree dưới mức này -> mạng quá thưa
GATE_DEGREE_HI = 8.0  # trên mức này -> quá dày, và conf cảnh báo vùng abort
GATE_ISOLATED_MAX = 0.10  # tỉ lệ thời gian node có degree 0
GATE_BOUNDARY_RATIO = 2.0  # mật độ lớp biên / kỳ vọng đều
BOUNDARY_FRAC = 0.05  # lớp biên = 5% mỗi chiều, mỗi phía
WARMUP_S = 30.0  # CLAUDE.md: bỏ 30 s đầu, Gauss-Markov cần warmup


def load_conf(path: Path) -> dict:
    """Đọc sim-config/*.conf — cùng định dạng key = value mà C++ đọc."""
    out = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


# --------------------------------------------------------------------------- #
# degree
# --------------------------------------------------------------------------- #


def degree_table(nb: pd.DataFrame, n_nodes: int, threshold: float) -> dict:
    """Phân bố degree dưới hai định nghĩa link.

    Degree tính trên mọi (node, thời điểm). Node không xuất hiện trong dòng nào
    ở một thời điểm vẫn phải được tính là degree 0 — đó là lý do scenario ghi
    đủ mọi cặp có hướng, kể cả cặp tỉ lệ 0.
    """
    nb = nb.copy()
    nb["ratio"] = nb["recv"] / nb["sent"]
    out = {}
    for name, mask in (
        ("chặt (ratio >= %.2f)" % threshold, nb["ratio"] >= threshold),
        ("lỏng (recv >= 1)", nb["recv"] >= 1),
    ):
        links = nb[mask]
        # in-degree: số node mà dst nghe được
        counts = links.groupby(["t_s", "dst"]).size()
        # điền 0 cho mọi (t, node) không có link nào
        times = nb["t_s"].unique()
        full = pd.MultiIndex.from_product([times, range(n_nodes)], names=["t_s", "dst"])
        deg = counts.reindex(full, fill_value=0)

        # link hai chiều: cả i->j và j->i cùng tồn tại
        pairs = set(zip(links["t_s"], links["src"], links["dst"]))
        bidir = sum(1 for (t, i, j) in pairs if (t, j, i) in pairs) / max(len(times), 1) / n_nodes

        per_node = deg.groupby("dst").mean()
        out[name] = {
            "mean": float(deg.mean()),
            "median": float(deg.median()),
            "p10": float(deg.quantile(0.10)),
            "p90": float(deg.quantile(0.90)),
            "max": int(deg.max()),
            "isolated_frac": float((deg == 0).mean()),
            "bidir_mean": float(bidir),
            "per_node_min": float(per_node.min()),
            "per_node_max": float(per_node.max()),
            "n_samples": int(len(deg)),
        }
    return out


def range_from_ratio(nb: pd.DataFrame, threshold: float, bin_m: float = 25.0) -> dict:
    """Khoảng cách nơi tỉ lệ nhận beacon trung bình cắt các mức — tầm phủ đo được."""
    nb = nb.copy()
    nb["ratio"] = nb["recv"] / nb["sent"]
    nb["bin"] = (nb["dist_m"] // bin_m) * bin_m
    curve = nb.groupby("bin")["ratio"].agg(["mean", "size"]).reset_index()
    curve = curve[curve["size"] >= 20]

    def crossing(level):
        d = curve["bin"].to_numpy(float)
        v = curve["mean"].to_numpy(float)
        for i in range(1, len(v)):
            if v[i] < level <= v[i - 1]:
                if v[i - 1] == v[i]:
                    return float(d[i])
                frac = (v[i - 1] - level) / (v[i - 1] - v[i])
                return float(d[i - 1] + frac * (d[i] - d[i - 1]))
        return float("nan")

    return {
        "r_at_0.9_m": crossing(0.9),
        "r_at_threshold_m": crossing(threshold),
        "r_at_0.1_m": crossing(0.1),
        "curve": curve,
    }


def degree_vs_range(pos: pd.DataFrame, n_nodes: int, radii) -> pd.DataFrame:
    """Degree kỳ vọng nếu tầm phủ là R, tính từ phân bố khoảng cách THẬT.

    Dùng vị trí đo được chứ không dùng công thức mật độ: hộp cao 500 m xấp xỉ
    bằng R nên cầu phủ sóng bị biên cắt, và công thức 2D/3D lệch nhau gần gấp
    đôi. Đây là cách suy TxPower cho một degree mục tiêu mà không cần chạy lại.
    """
    rows = []
    for t, frame in pos.groupby("t_s"):
        p = frame.sort_values("node")[["x", "y", "z"]].to_numpy()
        d = np.linalg.norm(p[:, None, :] - p[None, :, :], axis=-1)
        np.fill_diagonal(d, np.inf)
        rows.append([(d < r).sum(axis=1).mean() for r in radii])
    arr = np.array(rows)
    return pd.DataFrame({"radius_m": radii, "mean_degree": arr.mean(axis=0)})


# --------------------------------------------------------------------------- #
# vị trí
# --------------------------------------------------------------------------- #


def position_summary(pos: pd.DataFrame, meta: dict) -> dict:
    bounds = {
        "x": (0.0, meta["area_x_m"]),
        "y": (0.0, meta["area_y_m"]),
        "z": (meta["alt_min_m"], meta["alt_max_m"]),
    }
    out = {"axes": {}}
    for axis, (lo, hi) in bounds.items():
        v = pos[axis].to_numpy()
        span = hi - lo
        layer = BOUNDARY_FRAC * span
        near = ((v < lo + layer) | (v > hi - layer)).mean()
        # kỳ vọng nếu phân bố đều: 2 lớp x 5% = 10%
        out["axes"][axis] = {
            "min": float(v.min()),
            "max": float(v.max()),
            "mean": float(v.mean()),
            "uniform_mean": float((lo + hi) / 2),
            "boundary_frac": float(near),
            "boundary_expected": 2 * BOUNDARY_FRAC,
            "boundary_ratio": float(near / (2 * BOUNDARY_FRAC)),
        }
    # z-range từng node: phân biệt "quét đều" với "mỗi node kẹt một dải"
    z = pos.groupby("node")["z"]
    spans = (z.max() - z.min()).to_numpy()
    out["z_span_per_node"] = {
        "mean": float(spans.mean()),
        "median": float(np.median(spans)),
        "min": float(spans.min()),
        "max": float(spans.max()),
        "frac_span_below_half": float((spans < 0.5 * (bounds["z"][1] - bounds["z"][0])).mean()),
        "full_range_m": float(bounds["z"][1] - bounds["z"][0]),
    }
    return out


# --------------------------------------------------------------------------- #


def make_figures(nb: pd.DataFrame, pos: pd.DataFrame, meta: dict, curve, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    nb = nb.copy()
    nb["ratio"] = nb["recv"] / nb["sent"]
    axes[0].plot(curve["bin"], curve["mean"], lw=1.6)
    axes[0].axhline(0.5, color="r", ls="--", lw=1, label="ngưỡng 0.5")
    axes[0].set_xlabel("khoảng cách (m)")
    axes[0].set_ylabel("tỉ lệ nhận beacon")
    axes[0].set_title("Tỉ lệ nhận beacon theo khoảng cách")
    axes[0].grid(alpha=0.3)
    axes[0].legend(fontsize=8)

    links = nb[nb["ratio"] >= 0.5]
    times = nb["t_s"].unique()
    counts = links.groupby(["t_s", "dst"]).size()
    full = pd.MultiIndex.from_product([times, range(meta["num_nodes"])], names=["t_s", "dst"])
    deg = counts.reindex(full, fill_value=0)
    axes[1].hist(deg.to_numpy(), bins=range(0, int(deg.max()) + 2), align="left", rwidth=0.85)
    axes[1].set_xlabel("degree (ratio ≥ 0.5)")
    axes[1].set_ylabel("số mẫu (node × thời điểm)")
    axes[1].set_title(f"Phân bố degree, mean={deg.mean():.2f}")
    axes[1].grid(alpha=0.3)

    per_t = deg.groupby("t_s").mean()
    axes[2].plot(per_t.index, per_t.to_numpy(), lw=1)
    axes[2].axhline(deg.mean(), color="r", ls="--", lw=1, label=f"mean {deg.mean():.2f}")
    axes[2].set_xlabel("t (s)")
    axes[2].set_ylabel("degree trung bình")
    axes[2].set_title("Degree theo thời gian")
    axes[2].grid(alpha=0.3)
    axes[2].legend(fontsize=8)
    fig.tight_layout()
    p = out_dir / "P1-degree.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    written.append(p)

    fig, axes = plt.subplots(1, 4, figsize=(17, 4))
    for ax, axis, (lo, hi) in zip(
        axes[:3],
        ("x", "y", "z"),
        ((0, meta["area_x_m"]), (0, meta["area_y_m"]), (meta["alt_min_m"], meta["alt_max_m"])),
    ):
        ax.hist(pos[axis], bins=50, density=True)
        ax.axhline(1.0 / (hi - lo), color="r", ls="--", lw=1.2, label="đều")
        span = hi - lo
        ax.axvspan(lo, lo + BOUNDARY_FRAC * span, color="orange", alpha=0.2)
        ax.axvspan(hi - BOUNDARY_FRAC * span, hi, color="orange", alpha=0.2, label="lớp biên 5%")
        ax.set_xlabel(f"{axis} (m)")
        ax.set_title(f"Phân bố {axis}")
        ax.legend(fontsize=8)
        ax.grid(alpha=0.3)
    z = pos.groupby("node")["z"]
    spans = (z.max() - z.min()).to_numpy()
    axes[3].hist(spans, bins=15)
    axes[3].axvline(meta["alt_max_m"] - meta["alt_min_m"], color="r", ls="--", lw=1.2,
                    label="cả dải")
    axes[3].set_xlabel("z span mỗi node (m)")
    axes[3].set_title("Mỗi node quét bao nhiêu dải cao")
    axes[3].legend(fontsize=8)
    axes[3].grid(alpha=0.3)
    fig.tight_layout()
    p = out_dir / "P1-positions.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    written.append(p)
    return written


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="P1 — đo degree và phân bố vị trí")
    p.add_argument("--run", required=True, help="thư mục run của topology-probe")
    p.add_argument("--conf", default="sim-config/p1-topology.conf")
    p.add_argument("--figures", default="figures")
    p.add_argument("--warmup", type=float, default=WARMUP_S)
    p.add_argument("--json-out")
    args = p.parse_args(argv)

    run_dir = Path(args.run)
    if not run_dir.is_absolute():
        run_dir = REPO_ROOT / run_dir
    meta = json.loads((run_dir / "meta.json").read_text())
    conf = load_conf(REPO_ROOT / args.conf)
    threshold = float(conf.get("topoDegreeThreshold", 0.5))

    nb = pd.read_csv(run_dir / "neighbors.csv")
    pos = pd.read_csv(run_dir / "positions.csv")
    nb = nb[nb["t_s"] >= args.warmup]
    pos = pos[pos["t_s"] >= args.warmup]

    n_nodes = int(meta["num_nodes"])
    deg = degree_table(nb, n_nodes, threshold)
    rng = range_from_ratio(nb, threshold)
    posum = position_summary(pos, meta)
    radii = list(range(100, 1201, 25))
    dvr = degree_vs_range(pos, n_nodes, radii)

    print("=" * 78)
    print("P1 — HÌNH HỌC ĐO ĐƯỢC")
    print("=" * 78)
    print(
        f"\n{meta['num_nodes']} node, {meta['sim_time_s']:.0f} s "
        f"(bỏ {args.warmup:.0f} s warmup), hộp {meta['area_x_m']:.0f}×{meta['area_y_m']:.0f}"
        f"×[{meta['alt_min_m']:.0f},{meta['alt_max_m']:.0f}] m"
    )
    print(
        f"txPower {meta['tx_power_dbm']:.0f} dBm, sàn detect {meta['min_rssi_dbm']:.0f} dBm, "
        f"beacon {meta['beacon_interval_s']*1000:.0f} ms, cửa sổ {meta['neighbor_window_s']:.0f} s"
    )
    print(
        f"beacon: {meta['beacons_sent']} phát / {meta['beacons_received']} nhận "
        f"= {meta['beacons_received']/meta['beacons_sent']:.3f} người nhận mỗi beacon"
    )

    print("\n--- a) DEGREE ---")
    print(f"  {'định nghĩa link':<24} {'mean':>6} {'med':>5} {'p10':>5} {'p90':>5} {'max':>5}"
          f" {'cô lập':>8} {'2 chiều':>8}")
    for name, d in deg.items():
        print(
            f"  {name:<24} {d['mean']:>6.2f} {d['median']:>5.0f} {d['p10']:>5.0f} "
            f"{d['p90']:>5.0f} {d['max']:>5} {d['isolated_frac']:>7.1%} {d['bidir_mean']:>8.2f}"
        )
    primary = list(deg.values())[0]
    print(f"  degree trung bình theo node: {primary['per_node_min']:.2f} – "
          f"{primary['per_node_max']:.2f}  ({primary['n_samples']} mẫu node×thời điểm)")

    print("\n  Tầm phủ đo được (tỉ lệ nhận beacon cắt các mức):")
    print(f"    R(0.9) = {rng['r_at_0.9_m']:.0f} m   R({threshold:g}) = "
          f"{rng['r_at_threshold_m']:.0f} m   R(0.1) = {rng['r_at_0.1_m']:.0f} m")

    ok_degree = GATE_DEGREE_LO <= primary["mean"] <= GATE_DEGREE_HI
    ok_isolated = primary["isolated_frac"] <= GATE_ISOLATED_MAX
    print(f"\n  [{'ĐẠT' if ok_degree else 'KHÔNG ĐẠT'}] mean degree trong "
          f"[{GATE_DEGREE_LO}, {GATE_DEGREE_HI}]")
    print(f"  [{'ĐẠT' if ok_isolated else 'KHÔNG ĐẠT'}] tỉ lệ cô lập ≤ "
          f"{GATE_ISOLATED_MAX:.0%}")

    print("\n--- b) PHÂN BỐ VỊ TRÍ ---")
    print(f"  {'trục':>5} {'min':>8} {'max':>8} {'mean':>8} {'mean đều':>9} "
          f"{'lớp biên':>9} {'/kỳ vọng':>9}")
    for axis, a in posum["axes"].items():
        print(
            f"  {axis:>5} {a['min']:>8.0f} {a['max']:>8.0f} {a['mean']:>8.0f} "
            f"{a['uniform_mean']:>9.0f} {a['boundary_frac']:>8.1%} {a['boundary_ratio']:>9.2f}"
        )
    zs = posum["z_span_per_node"]
    print(f"\n  z-span mỗi node: mean {zs['mean']:.0f} m, median {zs['median']:.0f} m, "
          f"min {zs['min']:.0f}, max {zs['max']:.0f}  (cả dải {zs['full_range_m']:.0f} m)")
    print(f"  tỉ lệ node quét dưới nửa dải cao: {zs['frac_span_below_half']:.1%}")
    worst = max(a["boundary_ratio"] for a in posum["axes"].values())
    ok_bound = worst <= GATE_BOUNDARY_RATIO
    print(f"  [{'ĐẠT' if ok_bound else 'KHÔNG ĐẠT'}] mật độ lớp biên ≤ "
          f"{GATE_BOUNDARY_RATIO}× kỳ vọng đều (xấu nhất {worst:.2f}×)")

    print("\n--- c) ĐỀ XUẤT (không sửa config) ---")
    r_now = rng["r_at_threshold_m"]
    print(f"  Degree kỳ vọng theo tầm phủ, tính từ vị trí THẬT đo được:")
    print(f"    {'R (m)':>7} {'degree':>8}")
    for _, row in dvr.iterrows():
        if row["radius_m"] % 100 == 0 and row["radius_m"] <= 900:
            print(f"    {row['radius_m']:>7.0f} {row['mean_degree']:>8.2f}")
    target = 6.0
    idx = (dvr["mean_degree"] - target).abs().idxmin()
    r_target = float(dvr.loc[idx, "radius_m"])
    exponent = float(meta["exponent"])
    delta_db = 10.0 * exponent * math.log10(r_target / r_now) if r_now > 0 else float("nan")
    print(f"\n  Để degree ≈ {target:.0f} cần R ≈ {r_target:.0f} m "
          f"(đang là {r_now:.0f} m) → ΔP = {delta_db:+.1f} dB")
    print(f"    tức txPower ≈ {meta['tx_power_dbm'] + delta_db:.0f} dBm ở sàn "
          f"{meta['min_rssi_dbm']:.0f} dBm,")
    print(f"    hoặc {meta['tx_power_dbm'] + delta_db - 8:.0f} dBm nếu hạ sàn về −101 "
          f"(sàn hiệu dụng −90, tức +8 dB ngân sách)")

    figures = make_figures(nb, pos, meta, rng["curve"], REPO_ROOT / args.figures)
    print("\n--- Hình ---")
    for f in figures:
        print(f"  {f.relative_to(REPO_ROOT)}")

    if args.json_out:
        out = Path(args.json_out)
        if not out.is_absolute():
            out = REPO_ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "meta": meta,
            "degree": deg,
            "range": {k: v for k, v in rng.items() if k != "curve"},
            "positions": posum,
            "degree_vs_range": dvr.to_dict("records"),
            "recommendation": {
                "r_now_m": r_now,
                "r_for_degree_6_m": r_target,
                "delta_db": delta_db,
                "txpower_same_floor_dbm": meta["tx_power_dbm"] + delta_db,
            },
            "gates": {
                "degree_in_range": ok_degree,
                "isolated_ok": ok_isolated,
                "boundary_ok": ok_bound,
            },
        }
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=float) + "\n")
        print(f"JSON: {out.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
