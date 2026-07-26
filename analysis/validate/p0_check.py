#!/usr/bin/env python3
"""P0 — kiểm chứng thiết bị đo. Ba cổng nghiệm thu của PLAN.md mục P0.

  Cổng 1  RSSI giảm đơn điệu và bám đường path-loss lý thuyết (chế độ no-fading)
  Cổng 2  MAC retry khác 0 nhưng không phải toàn bộ
  Cổng 3  Residual σ ở chế độ fading khớp giá trị suy ra từ Nakagami m
          (m = 5 → σ ≈ 2.0 dB)

Đường lý thuyết được tính LẠI trong Python từ tần số và exponent trong
meta.json, không lấy lại con số mà C++ đã tính. Nếu callback đọc nhầm trường
(noise thay vì signal) hay gain PHY khác 0, residual lệch hàng chục dB và cổng 1
bắt được.

Kỳ vọng σ và độ lệch trung bình suy trực tiếp từ cách ns-3 hiện thực Nakagami
(propagation-loss-model.cc): độ lợi công suất ~ Gamma(m, 1/m), trung bình 1.
Sang dB thì

    σ_dB    = sqrt(ψ₁(m)) · 10/ln10
    E[dB]   = (ψ(m) − ln m) · 10/ln10      ← ÂM, không phải 0

Số hạng thứ hai hay bị bỏ qua: fading giữ nguyên công suất trung bình nhưng
*hạ* dBm trung bình (bất đẳng thức Jensen). Không tính tới nó thì residual trông
như bị lệch hệ thống trong khi thực ra là đúng.

Chạy:
    python3 analysis/validate/p0_check.py \
        --nofading data/smoke/p0-nofading --fading data/smoke/p0-fading
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
DB_PER_NEPER = 10.0 / math.log(10.0)

# Ngưỡng cổng nghiệm thu — công bố trước, không nới sau khi nhìn số liệu.
GATE_MAX_ABS_RESIDUAL_DB = 0.5  # no-fading: lệch lớn hơn thế là đọc sai trường
GATE_MIN_SPEARMAN = 0.999  # |rho| giữa RSSI và khoảng cách
GATE_SIGMA_TOL_DB = 0.25  # sai lệch σ đo được so với σ lý thuyết
GATE_MIN_TIER_SAMPLES = 200  # dưới mức này thì σ của tier là nhiễu

# ns-3 mặc định gắn ThresholdPreambleDetectionModel với MinimumRssi = -82 dBm:
# frame yếu hơn thế KHÔNG BAO GIỜ được detect, bất kể SNR. Đó là một sàn kiểm
# duyệt cứng trên RSSI. Sát sàn, chỉ những lần fading thuận lợi mới qua được
# nên σ đo ra bị thu hẹp và mean bị kéo lên — phải loại vùng đó ra trước khi
# đo σ, chứ không thì cổng 3 đo chính cái sàn.
RSSI_FLOOR_DBM = -82.0
FLOOR_MARGIN_DB = 8.0


# --------------------------------------------------------------------------- #
# digamma / trigamma / Spearman — tự viết, không dùng scipy
#
# scipy 1.8 của hệ thống không tương thích ABI với numpy 2.x đang cài, và cả
# script chỉ cần đúng ba hàm này. Công thức: đẩy đối số lên > 10 bằng hệ thức
# truy hồi rồi dùng khai triển tiệm cận. Sai số ~1e-13 với m trong khoảng 1–10,
# dư sức cho một ngưỡng 0.25 dB.
# --------------------------------------------------------------------------- #


def digamma(x: float) -> float:
    """ψ(x) = d/dx ln Γ(x), x > 0."""
    result = 0.0
    while x < 10.0:
        result -= 1.0 / x  # ψ(x) = ψ(x+1) − 1/x
        x += 1.0
    inv = 1.0 / x
    inv2 = inv * inv
    return (
        result
        + math.log(x)
        - 0.5 * inv
        - inv2 * (1.0 / 12.0 - inv2 * (1.0 / 120.0 - inv2 * (1.0 / 252.0 - inv2 / 240.0)))
    )


def trigamma(x: float) -> float:
    """ψ₁(x) = dψ/dx, x > 0."""
    result = 0.0
    while x < 10.0:
        result += 1.0 / (x * x)  # ψ₁(x) = ψ₁(x+1) + 1/x²
        x += 1.0
    inv = 1.0 / x
    inv2 = inv * inv
    return (
        result
        + inv
        + 0.5 * inv2
        + inv2 * inv * (1.0 / 6.0 - inv2 * (1.0 / 30.0 - inv2 * (1.0 / 42.0 - inv2 / 30.0)))
    )


def _ranks(values: np.ndarray) -> np.ndarray:
    """Hạng trung bình (xử lý cả trường hợp trùng giá trị)."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(1, len(values) + 1, dtype=float)
    # gộp hạng cho các nhóm trùng nhau
    sorted_vals = values[order]
    start = 0
    for i in range(1, len(values) + 1):
        if i == len(values) or sorted_vals[i] != sorted_vals[start]:
            if i - start > 1:
                ranks[order[start:i]] = (start + i + 1) / 2.0
            start = i
    return ranks


def spearman(x, y) -> float:
    xr = _ranks(np.asarray(x, dtype=float))
    yr = _ranks(np.asarray(y, dtype=float))
    return float(np.corrcoef(xr, yr)[0, 1])


def load_run(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    meta = json.loads((run_dir / "meta.json").read_text())
    rx = pd.read_csv(run_dir / "rx.csv")
    tx = pd.read_csv(run_dir / "tx.csv")
    return rx, tx, meta


def theory_rssi_dbm(dist_m, meta: dict) -> np.ndarray:
    """Friis tại 1 m + log-distance. Tính lại từ đầu, không dùng ref_loss_db của C++."""
    c = 299792458.0
    lam = c / (meta["freq_mhz"] * 1e6)
    ref_loss = 20.0 * np.log10(4.0 * np.pi / lam)
    d = np.asarray(dist_m, dtype=float)
    return meta["tx_power_dbm"] - ref_loss - 10.0 * meta["exponent"] * np.log10(d)


def nakagami_m_of(dist_m, meta: dict) -> np.ndarray:
    d = np.asarray(dist_m, dtype=float)
    m = np.full(d.shape, meta["nakagami_m2"], dtype=float)
    m[d < meta["nakagami_distance2_m"]] = meta["nakagami_m1"]
    m[d < meta["nakagami_distance1_m"]] = meta["nakagami_m0"]
    return m


def predicted_sigma_db(m: float) -> float:
    return math.sqrt(trigamma(m)) * DB_PER_NEPER


def predicted_mean_db(m: float) -> float:
    return (digamma(m) - math.log(m)) * DB_PER_NEPER


def per_bin(tx: pd.DataFrame, rx: pd.DataFrame, bin_m: float = 10.0) -> pd.DataFrame:
    """Gộp theo bin khoảng cách: attempts, retries, rx thành công.

    Mẫu số là MAC attempts chứ không phải số lần gọi Send: một lần phát lại là
    một attempt mới nhưng không có Send tương ứng, và queue có thể drop trước
    khi phát.
    """
    tx = tx.copy()
    tx["bin"] = (tx["dist_m"] // bin_m) * bin_m
    rx = rx.copy()
    rx["bin"] = (rx["dist_m"] // bin_m) * bin_m

    counts = tx.pivot_table(index="bin", columns="event", aggfunc="size", fill_value=0)
    for col in ("attempt", "retry", "final_fail", "send"):
        if col not in counts:
            counts[col] = 0
    counts["rx_ok"] = rx.groupby("bin").size().reindex(counts.index, fill_value=0)
    counts["retry_rate"] = counts["retry"] / counts["attempt"].replace(0, np.nan)
    counts["frame_success"] = counts["rx_ok"] / counts["attempt"].replace(0, np.nan)
    return counts.reset_index()


# --------------------------------------------------------------------------- #
# cổng nghiệm thu
# --------------------------------------------------------------------------- #


def gate1_theory(rx: pd.DataFrame, meta: dict) -> dict:
    resid = rx["rssi_dbm"].to_numpy() - theory_rssi_dbm(rx["dist_m"], meta)
    rho = spearman(rx["dist_m"], rx["rssi_dbm"])
    rssi = rx.sort_values("dist_m")["rssi_dbm"].to_numpy()
    increases = int(np.sum(np.diff(rssi) > 0))
    return {
        "n": int(len(rx)),
        "dist_range_m": (float(rx["dist_m"].min()), float(rx["dist_m"].max())),
        "rssi_range_dbm": (float(rx["rssi_dbm"].min()), float(rx["rssi_dbm"].max())),
        "resid_mean_db": float(resid.mean()),
        "resid_max_abs_db": float(np.abs(resid).max()),
        "spearman_rho": float(rho),
        "rssi_increases": increases,
        "pass": bool(
            np.abs(resid).max() <= GATE_MAX_ABS_RESIDUAL_DB
            and abs(rho) >= GATE_MIN_SPEARMAN
            and rho < 0
        ),
    }


def gate2_retry(meta: dict, bins: pd.DataFrame) -> dict:
    rate = meta["retry_rate"]
    with_retry = bins[bins["retry"] > 0]
    without = bins[(bins["attempt"] > 0) & (bins["retry"] == 0)]
    return {
        "mac_attempts": meta["mac_attempts"],
        "mac_retries": meta["mac_retries"],
        "mac_final_fails": meta["mac_final_fails"],
        "retry_rate_overall": rate,
        "bins_with_retry": int(len(with_retry)),
        "bins_without_retry": int(len(without)),
        "first_retry_dist_m": (
            float(with_retry["bin"].min()) if len(with_retry) else float("nan")
        ),
        # Cổng: có retry, nhưng không phải mọi attempt đều retry, và phải có
        # CẢ vùng sạch lẫn vùng lỗi — retry đều khắp nghĩa là callback hoặc
        # tải sai, không phải kênh.
        "pass": bool(0.0 < rate < 1.0 and len(with_retry) > 0 and len(without) > 0),
    }


def floor_of(meta: dict) -> float:
    """Sàn detect của run. Run cũ không có trường này thì là mặc định ns-3."""
    return float(meta.get("min_rssi_dbm", RSSI_FLOOR_DBM))


def _residuals(rx: pd.DataFrame, meta: dict, margin_db: float):
    """(residual, m mỗi dòng, offset so với dự đoán Jensen, số dòng bị loại).

    `offset` = residual − E[dB](m) đã trừ sẵn kỳ vọng theo từng tier, nên gộp
    được các tier khác m vào một phép thử duy nhất cho độ lệch cộng tính.
    """
    theory = theory_rssi_dbm(rx["dist_m"], meta)
    keep = theory >= (floor_of(meta) + margin_db)
    n_dropped = int((~keep).sum())

    rx = rx[keep].reset_index(drop=True)
    resid = rx["rssi_dbm"].to_numpy() - theory_rssi_dbm(rx["dist_m"], meta)
    m_of_row = nakagami_m_of(rx["dist_m"], meta)
    offset = resid - np.array([predicted_mean_db(m) for m in m_of_row])
    return resid, m_of_row, offset, n_dropped


def gate3_sigma(sigma_runs: list[dict], margin_db: float = FLOOR_MARGIN_DB) -> dict:
    """Residual σ theo từng tier m, gộp mọi seed được truyền vào.

    Gộp nhiều seed để tách hai giả thuyết cho độ lệch mean: hiện vật RNG của
    một seed (gộp lại thì tan về 0) so với lệch hệ thống (giữ nguyên ở mọi
    seed). Với một seed thì SE của mean gộp ~0.022 dB, không đủ để kết luận.
    """
    all_resid, all_m, all_offset = [], [], []
    per_seed, n_dropped_total = [], 0

    for run in sigma_runs:
        resid, m_of_row, offset, n_dropped = _residuals(run["rx"], run["meta"], margin_db)
        n_dropped_total += n_dropped
        all_resid.append(resid)
        all_m.append(m_of_row)
        all_offset.append(offset)
        per_seed.append(
            {
                "seed": run["meta"]["seed"],
                "n": int(len(offset)),
                "offset_mean_db": float(np.mean(offset)),
                "offset_se_db": float(np.std(offset, ddof=1) / math.sqrt(len(offset))),
            }
        )

    resid = np.concatenate(all_resid)
    m_of_row = np.concatenate(all_m)
    offset = np.concatenate(all_offset)
    meta = sigma_runs[0]["meta"]

    tiers = []
    for m in (meta["nakagami_m0"], meta["nakagami_m1"], meta["nakagami_m2"]):
        sel = m_of_row == m
        n = int(sel.sum())
        tier = {
            "m": float(m),
            "n": n,
            "sigma_pred_db": predicted_sigma_db(m),
            "mean_pred_db": predicted_mean_db(m),
        }
        if n >= 2:
            tier["sigma_meas_db"] = float(np.std(resid[sel], ddof=1))
            tier["mean_meas_db"] = float(np.mean(resid[sel]))
            tier["sigma_err_db"] = tier["sigma_meas_db"] - tier["sigma_pred_db"]
            # σ của mẫu có sai số chuẩn σ/sqrt(2n) — cần để biết lệch là thật
            # hay chỉ là ít mẫu.
            tier["sigma_se_db"] = tier["sigma_meas_db"] / math.sqrt(2 * n)
            tier["offset_mean_db"] = float(np.mean(offset[sel]))
            tier["offset_se_db"] = float(
                np.std(offset[sel], ddof=1) / math.sqrt(n)
            )
        tiers.append(tier)

    checkable = [t for t in tiers if t["n"] >= GATE_MIN_TIER_SAMPLES]
    ok = bool(checkable) and all(
        abs(t["sigma_err_db"]) <= GATE_SIGMA_TOL_DB for t in checkable
    )

    pooled_mean = float(np.mean(offset))
    pooled_se = float(np.std(offset, ddof=1) / math.sqrt(len(offset)))
    return {
        "tiers": tiers,
        "tiers_checked": [t["m"] for t in checkable],
        "tiers_skipped_few_samples": [
            t["m"] for t in tiers if t["n"] < GATE_MIN_TIER_SAMPLES
        ],
        "rssi_floor_dbm": floor_of(meta),
        "floor_margin_db": margin_db,
        "rows_dropped_near_floor": n_dropped_total,
        "rows_used": int(len(offset)),
        "n_seeds": len(sigma_runs),
        "per_seed": per_seed,
        # Độ lệch cộng tính dùng chung, đã trừ kỳ vọng Jensen của từng tier.
        "offset_pooled_db": pooled_mean,
        "offset_pooled_se_db": pooled_se,
        "offset_pooled_z": pooled_mean / pooled_se if pooled_se else float("nan"),
        "pass": ok,
    }


def _crossing(bins: pd.DataFrame, column: str, level: float) -> float:
    """Khoảng cách nơi `column` lần đầu tụt xuống dưới `level`, nội suy tuyến tính."""
    b = bins.dropna(subset=[column]).sort_values("bin")
    d = b["bin"].to_numpy(dtype=float)
    v = b[column].to_numpy(dtype=float)
    for i in range(1, len(v)):
        if v[i] < level <= v[i - 1]:
            if v[i - 1] == v[i]:
                return float(d[i])
            frac = (v[i - 1] - level) / (v[i - 1] - v[i])
            return float(d[i - 1] + frac * (d[i] - d[i - 1]))
    return float("nan")


def range_summary(run: dict) -> dict:
    """Tầm phủ và bề rộng vùng chuyển tiếp của một run.

    Bề rộng báo cáo bằng **dB** bên cạnh mét: dB không phụ thuộc TxPower nên
    suy được tầm phủ ở công suất khác, còn mét thì không.
    """
    rx, bins, meta = run["rx"], run["bins"], run["meta"]
    noise = float(rx["noise_dbm"].iloc[0])
    floor = floor_of(meta)
    # Sàn hiệu dụng = max(MinimumRssi, noise + Threshold). Threshold mặc định
    # 4 dB SNR — dựa trên SNR nên nó là ràng buộc vật lý, khác với hằng số tuyệt đối.
    floor_eff = max(floor, noise + 4.0)

    out = {
        "label": run.get("label"),
        "tx_power_dbm": meta["tx_power_dbm"],
        "min_rssi_dbm": floor,
        "noise_dbm": noise,
        "floor_effective_dbm": floor_eff,
        "last_rx_dist_m": float(rx["dist_m"].max()),
        "last_rx_rssi_dbm": float(rx["rssi_dbm"].min()),
        "probe_interval_ms": meta["probe_interval_ms"],
    }
    for level in (0.9, 0.5, 0.1):
        d = _crossing(bins, "frame_success", level)
        out[f"dist_at_success_{level:g}_m"] = d
        out[f"rssi_at_success_{level:g}_dbm"] = (
            float(theory_rssi_dbm([d], meta)[0]) if not math.isnan(d) else float("nan")
        )
    d90, d10 = out["dist_at_success_0.9_m"], out["dist_at_success_0.1_m"]
    out["waterfall_width_m"] = d10 - d90
    out["waterfall_width_db"] = (
        out["rssi_at_success_0.9_dbm"] - out["rssi_at_success_0.1_dbm"]
    )
    # TxPower cần để đạt R = 500 m với chính sàn hiệu dụng của run này.
    c = 299792458.0
    ref_loss = 20.0 * math.log10(4.0 * math.pi / (c / (meta["freq_mhz"] * 1e6)))
    out["txpower_for_500m_dbm"] = (
        floor_eff + ref_loss + 10.0 * meta["exponent"] * math.log10(500.0)
    )
    return out


# --------------------------------------------------------------------------- #
# hình
# --------------------------------------------------------------------------- #


def make_figures(runs: dict, sigma_label: str, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []

    fig, axes = plt.subplots(1, len(runs), figsize=(6.5 * len(runs), 5), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, (label, run) in zip(axes, runs.items()):
        rx, _, meta = run["rx"], run["tx"], run["meta"]
        ax.scatter(rx["dist_m"], rx["rssi_dbm"], s=2, alpha=0.35, label="RSSI đo được")
        d = np.linspace(max(1.0, rx["dist_m"].min()), rx["dist_m"].max(), 400)
        ax.plot(d, theory_rssi_dbm(d, meta), "r-", lw=1.6, label="lý thuyết (Friis+log-dist)")
        for dist, name in (
            (meta["nakagami_distance1_m"], "d1"),
            (meta["nakagami_distance2_m"], "d2"),
        ):
            if rx["dist_m"].min() <= dist <= rx["dist_m"].max():
                ax.axvline(dist, color="gray", ls=":", lw=1)
                ax.text(dist, ax.get_ylim()[1], f" {name}", va="top", fontsize=8, color="gray")
        ax.axhline(RSSI_FLOOR_DBM, color="tab:orange", ls="--", lw=1.2,
                   label=f"sàn detect {RSSI_FLOOR_DBM:.0f} dBm")
        ax.set_title(f"{label}  (n={len(rx)})")
        ax.set_xlabel("khoảng cách (m)")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)
    axes[0].set_ylabel("RSSI (dBm)")
    fig.suptitle("P0 — RSSI theo khoảng cách so với path loss lý thuyết")
    fig.tight_layout()
    path = out_dir / "P0-rssi-vs-distance.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    written.append(path)

    # Residual + histogram theo tier — dùng run dành riêng cho σ, và chỉ phần
    # không bị sàn detect kiểm duyệt.
    fading = runs.get(sigma_label)
    if fading is not None:
        rx, meta = fading["rx"], fading["meta"]
        keep = theory_rssi_dbm(rx["dist_m"], meta) >= RSSI_FLOOR_DBM + FLOOR_MARGIN_DB
        rx = rx[keep].reset_index(drop=True)
        resid = rx["rssi_dbm"].to_numpy() - theory_rssi_dbm(rx["dist_m"], meta)
        m_of_row = nakagami_m_of(rx["dist_m"], meta)

        fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
        axes[0].scatter(rx["dist_m"], resid, s=2, alpha=0.35)
        axes[0].axhline(0, color="k", lw=0.8)
        for dist in (meta["nakagami_distance1_m"], meta["nakagami_distance2_m"]):
            axes[0].axvline(dist, color="gray", ls=":", lw=1)
        axes[0].set_xlabel("khoảng cách (m)")
        axes[0].set_ylabel("residual (dB)")
        axes[0].set_title("Residual = RSSI đo − lý thuyết")
        axes[0].grid(alpha=0.3)

        for m in sorted(set(m_of_row.tolist())):
            sel = m_of_row == m
            if sel.sum() < 2:
                continue
            axes[1].hist(
                resid[sel],
                bins=50,
                density=True,
                histtype="step",
                lw=1.5,
                label=f"m={m:g}, n={int(sel.sum())}, "
                f"σ={np.std(resid[sel], ddof=1):.2f} (dự kiến {predicted_sigma_db(m):.2f})",
            )
        axes[1].set_xlabel("residual (dB)")
        axes[1].set_ylabel("mật độ")
        axes[1].set_title("Phân bố residual theo tier Nakagami m")
        axes[1].legend(fontsize=8)
        axes[1].grid(alpha=0.3)
        fig.tight_layout()
        path = out_dir / "P0-residual-sigma.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        written.append(path)

    # retry_rate và frame success theo khoảng cách (chỉ hai run công suất nominal)
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax2 = ax.twinx()
    for label, run in runs.items():
        if label == sigma_label and len(runs) > 2:
            continue  # run công suất cao: link không bao giờ xấu, không có gì để xem
        b = run["bins"]
        style = "-" if "on" in label else "--"
        ax.plot(b["bin"], b["retry_rate"], style, lw=1.4, label=f"retry_rate ({label})")
        ax2.plot(b["bin"], b["frame_success"], style, color="tab:green", lw=1.0, alpha=0.7,
                 label=f"frame success ({label})")
    ax.set_xlabel("khoảng cách (m)")
    ax.set_ylabel("retry_rate = retries / MAC attempts")
    ax2.set_ylabel("tỉ lệ frame giải mã được", color="tab:green")
    ax.grid(alpha=0.3)
    handles = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    labels = ax.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax.legend(handles, labels, fontsize=8, loc="center left")
    ax.set_title("P0 — retry và tỉ lệ giải mã theo khoảng cách")
    fig.tight_layout()
    path = out_dir / "P0-retry-vs-distance.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    written.append(path)

    return written


# --------------------------------------------------------------------------- #


def fmt_gate(name: str, ok: bool) -> str:
    return f"{'ĐẠT ' if ok else 'KHÔNG ĐẠT'}  {name}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Kiểm tra ba cổng nghiệm thu của P0")
    p.add_argument("--nofading", required=True, help="thư mục run --fading=false (cổng 1)")
    p.add_argument("--fading", required=True, help="thư mục run --fading=true (cổng 2)")
    p.add_argument(
        "--sigma",
        nargs="+",
        default=None,
        metavar="DIR",
        help="một hoặc nhiều thư mục run cho cổng 3 (mặc định: chính --fading). "
        "Dùng run TxPower cao để cả ba tier m đều nằm trên sàn detect. Truyền "
        "nhiều seed để kiểm độ lệch mean là hiện vật RNG hay hệ thống.",
    )
    p.add_argument(
        "--range",
        nargs="+",
        default=[],
        metavar="DIR",
        dest="range_dirs",
        help="các run để đo tầm phủ và bề rộng vùng chuyển tiếp (không phải cổng)",
    )
    p.add_argument("--figures", default="figures", help="thư mục ghi hình")
    p.add_argument("--bin", type=float, default=10.0, help="độ rộng bin khoảng cách (m)")
    p.add_argument("--json-out", help="ghi toàn bộ kết quả ra JSON")
    args = p.parse_args(argv)

    def load(label, raw):
        run_dir = Path(raw)
        if not run_dir.is_absolute():
            run_dir = REPO_ROOT / run_dir
        rx, tx, meta = load_run(run_dir)
        return {
            "label": label,
            "dir": str(run_dir),
            "rx": rx,
            "tx": tx,
            "meta": meta,
            "bins": per_bin(tx, rx, args.bin),
        }

    sigma_dirs = args.sigma or [args.fading]
    sigma_label = "fading=on"
    sources = [("fading=off", args.nofading), ("fading=on", args.fading)]
    if Path(sigma_dirs[0]) != Path(args.fading):
        sigma_label = "fading=on, TxPower cao"
        sources.append((sigma_label, sigma_dirs[0]))

    runs = {label: load(label, raw) for label, raw in sources}
    sigma_runs = (
        [runs[sigma_label]]
        if sigma_label == "fading=on"
        else [load(f"sigma[{i}]", d) for i, d in enumerate(sigma_dirs)]
    )
    range_runs = [load(f"range[{i}]", d) for i, d in enumerate(args.range_dirs)]

    off, on = runs["fading=off"], runs["fading=on"]
    if off["meta"]["fading"] or not on["meta"]["fading"]:
        print("LỖI: --nofading/--fading trỏ sai thư mục (kiểm tra meta.json).", file=sys.stderr)
        return 1

    g1 = gate1_theory(off["rx"], off["meta"])
    g2 = gate2_retry(on["meta"], on["bins"])
    g3 = gate3_sigma(sigma_runs)

    print("=" * 78)
    print("P0 — KIỂM CHỨNG THIẾT BỊ ĐO")
    print("=" * 78)
    for label, run in runs.items():
        m = run["meta"]
        print(
            f"\n[{label}] {m['start_dist_m']:.0f} -> {m['end_dist_m']:.0f} m, "
            f"txPower {m['tx_power_dbm']:.0f} dBm, n={m['sends']} probe, "
            f"attempts={m['mac_attempts']}, retries={m['mac_retries']}, "
            f"delivered={m['delivered']} (pdr {m['pdr']:.3f})"
        )

    print("\n--- Cổng 1: RSSI bám lý thuyết, giảm đơn điệu (fading=off) ---")
    print(f"  n mẫu                  : {g1['n']}")
    print(f"  khoảng cách quét       : {g1['dist_range_m'][0]:.0f} – {g1['dist_range_m'][1]:.0f} m")
    print(f"  RSSI quét              : {g1['rssi_range_dbm'][1]:.1f} – {g1['rssi_range_dbm'][0]:.1f} dBm")
    print(f"  residual trung bình    : {g1['resid_mean_db']:+.4f} dB")
    print(f"  |residual| lớn nhất    : {g1['resid_max_abs_db']:.4f} dB   (ngưỡng ≤ {GATE_MAX_ABS_RESIDUAL_DB})")
    print(f"  Spearman(dist, RSSI)   : {g1['spearman_rho']:+.6f}   (ngưỡng ≤ −{GATE_MIN_SPEARMAN})")
    print(f"  số lần RSSI tăng       : {g1['rssi_increases']}")
    print("  " + fmt_gate("cổng 1", g1["pass"]))

    print("\n--- Cổng 2: MAC retry khác 0 nhưng không phải toàn bộ (fading=on) ---")
    print(f"  MAC attempts / retries : {g2['mac_attempts']} / {g2['mac_retries']}")
    print(f"  final fails            : {g2['mac_final_fails']}")
    print(f"  retry_rate toàn run    : {g2['retry_rate_overall']:.4f}")
    print(f"  bin có retry / sạch    : {g2['bins_with_retry']} / {g2['bins_without_retry']}")
    print(f"  retry xuất hiện từ     : {g2['first_retry_dist_m']:.0f} m")
    print("  " + fmt_gate("cổng 2", g2["pass"]))

    print(f"\n--- Cổng 3: residual σ khớp Nakagami m (run: {sigma_label}) ---")
    print(
        f"  loại {g3['rows_dropped_near_floor']} mẫu có RSSI lý thuyết dưới "
        f"{g3['rssi_floor_dbm'] + g3['floor_margin_db']:.0f} dBm "
        f"(sàn detect {g3['rssi_floor_dbm']:.0f} + biên {g3['floor_margin_db']:.0f} dB); "
        f"còn {g3['rows_used']} mẫu"
    )
    print(f"  {'m':>4} {'n':>7} {'σ đo':>8} {'σ dự kiến':>10} {'lệch':>8} {'σ SE':>7}"
          f"  {'mean đo':>8} {'mean dự kiến':>12}")
    for t in g3["tiers"]:
        if "sigma_meas_db" in t:
            print(
                f"  {t['m']:>4.0f} {t['n']:>7} {t['sigma_meas_db']:>8.3f} "
                f"{t['sigma_pred_db']:>10.3f} {t['sigma_err_db']:>+8.3f} "
                f"{t['sigma_se_db']:>7.3f}  {t['mean_meas_db']:>+8.3f} "
                f"{t['mean_pred_db']:>+12.3f}"
            )
        else:
            print(f"  {t['m']:>4.0f} {t['n']:>7}   (không đủ mẫu — tier này không kiểm được)")
    if g3["tiers_skipped_few_samples"]:
        print(
            f"  BỎ QUA tier m = {g3['tiers_skipped_few_samples']} vì < "
            f"{GATE_MIN_TIER_SAMPLES} mẫu — link chết trước khi tới đó."
        )
    print(f"  ngưỡng |lệch σ| ≤ {GATE_SIGMA_TOL_DB} dB   ({g3['n_seeds']} seed)")
    print("  " + fmt_gate("cổng 3", g3["pass"]))

    print("\n--- Độ lệch cộng tính so với dự đoán Jensen (không phải cổng) ---")
    print("  offset = residual − E[dB](m), đã trừ kỳ vọng của từng tier nên gộp được")
    print(f"  {'seed':>6} {'n':>7} {'offset':>9} {'SE':>7} {'z':>7}")
    for s in g3["per_seed"]:
        z = s["offset_mean_db"] / s["offset_se_db"] if s["offset_se_db"] else float("nan")
        print(
            f"  {s['seed']:>6} {s['n']:>7} {s['offset_mean_db']:>+9.4f} "
            f"{s['offset_se_db']:>7.4f} {z:>+7.2f}"
        )
    print(
        f"  {'GỘP':>6} {g3['rows_used']:>7} {g3['offset_pooled_db']:>+9.4f} "
        f"{g3['offset_pooled_se_db']:>7.4f} {g3['offset_pooled_z']:>+7.2f}"
    )
    print("  theo tier:")
    for t in g3["tiers"]:
        if "offset_mean_db" in t:
            z = t["offset_mean_db"] / t["offset_se_db"] if t["offset_se_db"] else 0.0
            print(
                f"    m={t['m']:.0f}: {t['offset_mean_db']:+.4f} dB "
                f"(SE {t['offset_se_db']:.4f}, z {z:+.2f}, n {t['n']})"
            )
    verdict = (
        "TAN VỀ 0 khi gộp seed → hiện vật RNG, đóng lại"
        if abs(g3["offset_pooled_z"]) < 3
        else "GIỮ NGUYÊN qua các seed → lệch hệ thống, cần truy nguồn"
    )
    print(f"  Kết luận: {verdict}")

    if range_runs:
        print("\n--- Tầm phủ và bề rộng vùng chuyển tiếp (không phải cổng) ---")
        rs = [range_summary(r) for r in range_runs]
        hdr = (
            f"  {'TxPwr':>6} {'MinRssi':>8} {'sàn hd':>7} {'d(0.9)':>7} {'d(0.5)':>7} "
            f"{'d(0.1)':>7} {'rộng m':>7} {'rộng dB':>8} {'Ptx→500m':>9}"
        )
        print(hdr)
        for r in rs:
            print(
                f"  {r['tx_power_dbm']:>6.0f} {r['min_rssi_dbm']:>8.0f} "
                f"{r['floor_effective_dbm']:>7.1f} {r['dist_at_success_0.9_m']:>7.0f} "
                f"{r['dist_at_success_0.5_m']:>7.0f} {r['dist_at_success_0.1_m']:>7.0f} "
                f"{r['waterfall_width_m']:>7.0f} {r['waterfall_width_db']:>8.2f} "
                f"{r['txpower_for_500m_dbm']:>9.1f}"
            )
        print("  d(x) = khoảng cách nơi tỉ lệ giải mã tụt xuống x; rộng dB không phụ")
        print("  thuộc TxPower nên suy được tầm phủ ở công suất khác.")

    figures = make_figures(runs, sigma_label, REPO_ROOT / args.figures)
    print("\n--- Hình ---")
    for f in figures:
        print(f"  {f.relative_to(REPO_ROOT)}")

    all_pass = g1["pass"] and g2["pass"] and g3["pass"]
    print("\n" + "=" * 78)
    print(f"KẾT LUẬN P0: {'TẤT CẢ CỔNG ĐẠT' if all_pass else 'CÓ CỔNG KHÔNG ĐẠT — dừng, không sang P1'}")
    print("=" * 78)

    if args.json_out:
        out = Path(args.json_out)
        if not out.is_absolute():
            out = REPO_ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "gate1_theory": g1,
                    "gate2_retry": g2,
                    "gate3_sigma": g3,
                    "range_summary": [range_summary(r) for r in range_runs],
                    "all_pass": all_pass,
                    "meta": {k: v["meta"] for k, v in runs.items()},
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        print(f"JSON: {out.relative_to(REPO_ROOT) if out.is_relative_to(REPO_ROOT) else out}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
