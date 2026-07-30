#!/usr/bin/env python3
"""P5a — lõi: PCA bước 0, GLM nhị thức trên feature THÔ, ba kiểm chứng,
thang attenuation. KHÔNG bảng so mô hình, KHÔNG holdout (P5b, sau duyệt).

Thiết kế đọc từ PLAN.md P5 + chỉ định P5a:

- Tập fit = frozen/split.json fit_seeds (6-29). Holdout 30-35 KHÔNG đọc —
  bất biến cưỡng chế trong code, không chỉ trong lời.
- Feature THÔ (quy tắc 5): rssi_level [dBm], rssi_slope [dB/s], retry_rate.
- Nhãn nhị thức per-attempt: (trials_future - fails_future, fails_future) —
  không post-ARQ, không nhị phân hoá (quy tắc 3).
- GLM tự do có intercept (quy tắc 4), cluster-robust theo seed (quy tắc 6).
- Xuất frozen/weights.json ở THANG LOGIT THÔ — dạng P8 thực chạy: TTT tính
  trên z = b0 + b1·rssi + b2·slope + b3·retry, không trên LinkScore đã clip
  (clip ghim s_rssi=1 với 100% dòng 0-200 m -> d(LinkScore)/dt = 0 -> TTT
  vô hạn -> mất cảnh báo sớm). (a,b,c) chuẩn hoá chỉ để trình bày paper.
- PCA trên ma trận tương quan (= z-score) của đúng các dòng GLM dùng.
- Thang attenuation: fit thô -> phân tầng rssi_n (KHÔNG lọc — mọi dòng đều
  ở đúng một tầng) -> reliability-ratio CHỈ KHI phân tầng cho thấy β_slope
  tăng đơn điệu theo n.

Dùng:
    python3 analysis/fit/p5a_fit.py data/train --split frozen/split.json \
        --weights frozen/weights.json --json data/p5a_fit.json
"""
import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
import statsmodels.api as sm  # noqa: E402

FEATURES = ["rssi_level", "rssi_slope", "retry_rate"]
TAU_S = 4.0            # cửa sổ nhãn (conf labelWin) — kiểm chứng vật lý quy tắc 7
DELTA_S = 4.0          # cửa sổ feature (conf featureWin)
S_T2 = DELTA_S ** 2 / 12.0   # phương sai thời điểm mẫu beacon ~ uniform trên Δ
# σ fading theo tier Nakagami — ĐO Ở P0 (không phải lý thuyết):
#   m=8 (d<100), m=5 (100<=d<300), m=3 (d>=300); nakagamiD1/D2 = 100/300 m
SIGMA_TIER = [(100.0, 1.594), (300.0, 2.026), (float("inf"), 2.755)]
N_BANDS = [(3, 9), (10, 19), (20, 29), (30, 10 ** 9)]
BOOT_B = 200
BOOT_SEED = 20260727


def sigma_fading(dist):
    for lim, sig in SIGMA_TIER:
        if dist < lim:
            return sig
    return SIGMA_TIER[-1][1]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_fit_set(root, fit_seeds):
    rows = {k: [] for k in ("seed", "dist", "level", "slope", "n_rssi",
                            "retry", "succ", "fail")}
    n_total = n_missing = 0
    for seed in fit_seeds:
        path = os.path.join(root, f"seed-{seed}", "rows.csv")
        if not os.path.isfile(path):
            sys.exit(f"TỪ CHỐI: thiếu {path}.")
        with open(path) as fh:
            for r in csv.DictReader(fh):
                n_total += 1
                if r["retry_rate"] == "":
                    n_missing += 1          # GLM bỏ âm thầm -> đếm tường minh
                    continue
                trials = int(r["trials_future"])
                fails = int(r["fails_future"])
                rows["seed"].append(int(r["seed"]))
                rows["dist"].append(float(r["dist_m"]))
                rows["level"].append(float(r["rssi_level"]))
                rows["slope"].append(float(r["rssi_slope"]))
                rows["n_rssi"].append(int(r["rssi_n"]))
                rows["retry"].append(float(r["retry_rate"]))
                rows["succ"].append(trials - fails)
                rows["fail"].append(fails)
    out = {k: np.asarray(v) for k, v in rows.items()}
    return out, n_total, n_missing


def glm_fit(d, idx=None, cluster=True, start=None):
    """GLM nhị thức trên chỉ số idx (None = cả tập)."""
    if idx is None:
        idx = np.arange(len(d["seed"]))
    X = sm.add_constant(np.column_stack([d["level"][idx], d["slope"][idx],
                                         d["retry"][idx]]))
    y = np.column_stack([d["succ"][idx], d["fail"][idx]])
    model = sm.GLM(y, X, family=sm.families.Binomial())
    if cluster:
        return model.fit(start_params=start, cov_type="cluster",
                         cov_kwds={"groups": d["seed"][idx]})
    return model.fit(start_params=start)


def main():
    ap = argparse.ArgumentParser(description="P5a: PCA + GLM thô + kiểm chứng + thang attenuation")
    ap.add_argument("root", help="data/train")
    ap.add_argument("--split", default="frozen/split.json")
    ap.add_argument("--weights", default="frozen/weights.json")
    ap.add_argument("--json", help="kết quả máy-đọc-được")
    args = ap.parse_args()

    if "eval" in args.root:
        sys.exit("TỪ CHỐI: data/eval là vùng cấm tới P10.")
    if os.path.exists(args.weights):
        sys.exit(f"TỪ CHỐI: {args.weights} đã tồn tại — frozen/ bất biến (tạo -v2 nếu buộc phải đổi).")

    with open(args.split) as fh:
        split = json.load(fh)
    fit_seeds = split["fit_seeds"]
    assert fit_seeds == list(range(6, 30)), "tập fit phải đúng seeds 6-29"
    # Bất biến: không bao giờ đọc holdout trong P5a
    forbidden = set(split["holdout_seeds"])

    manifests = []
    for seed in fit_seeds:
        with open(os.path.join(args.root, f"seed-{seed}", "run_manifest.json")) as fh:
            manifest = json.load(fh)
        assert manifest["seed"] == seed, f"manifest seed-{seed} tự khai sai seed"
        manifests.append(manifest)
    design_keys = ("binary_sha256", "config_sim_sha256")
    designs = {tuple(m[k] for k in design_keys) for m in manifests}
    assert len(designs) == 1, "24 seed fit không cùng binary/config random design"
    realized_params = {str(m["seed"]): m["sim_params_sha256"] for m in manifests}

    d, n_total, n_missing = load_fit_set(args.root, fit_seeds)
    assert not (set(d["seed"].tolist()) & forbidden), "holdout lọt vào tập fit!"
    n_used = len(d["seed"])
    print(f"=== tập fit seeds 6-29: {n_total} dòng, dùng {n_used} "
          f"(loại {n_missing} thiếu retry = {100*n_missing/n_total:.2f}%) ===\n")

    out = {"fit_seeds": fit_seeds, "n_rows_total": n_total,
           "n_rows_used": n_used, "n_rows_missing_retry": n_missing,
           "provenance": {
               "data_git_sha": manifests[0]["git_sha"],
               **dict(zip(design_keys, next(iter(designs)))),
               "sim_params_sha256_by_seed": realized_params,
               "split": f"{args.split}@sha256:{sha256_file(args.split)}",
               "analysis_script": f"{__file__}@sha256:{sha256_file(__file__)}",
           }}

    # ---------------- Bước 0: PCA trên ma trận tương quan ------------------
    F = np.column_stack([d["level"], d["slope"], d["retry"]])
    R = np.corrcoef(F, rowvar=False)
    eigval, eigvec = np.linalg.eigh(R)         # tăng dần -> đảo
    order = np.argsort(eigval)[::-1]
    eigval, eigvec = eigval[order], eigvec[:, order]
    ratio = eigval / eigval.sum()
    cum2 = ratio[0] + ratio[1]
    print("Bước 0 — PCA (ma trận tương quan, z-score ngầm):")
    for i in range(3):
        print(f"  PC{i+1}: {100*ratio[i]:5.1f}% phương sai   loading (level, slope, retry) = "
              f"[{eigvec[0,i]:+.3f}, {eigvec[1,i]:+.3f}, {eigvec[2,i]:+.3f}]")
    print(f"  2 thành phần đầu: {100*cum2:.1f}%  (tiêu chí PLAN: >95% -> thừa một số hạng)"
          f" -> {'THỪA MỘT SỐ HẠNG — phải nói trong paper' if cum2 > 0.95 else 'ba số hạng đứng được'}\n")
    out["pca"] = {"eigenvalues": eigval.tolist(), "variance_ratio": ratio.tolist(),
                  "loadings_cols_PC": eigvec.tolist(), "first_two_ratio": float(cum2),
                  "criterion_95_exceeded": bool(cum2 > 0.95)}

    # ---------------- GLM đầy đủ, cluster-robust theo seed -----------------
    res = glm_fit(d)
    names = ["intercept", "rssi_level", "rssi_slope", "retry_rate"]
    params = dict(zip(names, res.params))
    ses = dict(zip(names, res.bse))
    zstats = dict(zip(names, res.tvalues))
    pvalues = dict(zip(names, res.pvalues))
    ci95 = dict(zip(names, res.conf_int().tolist()))
    print("GLM nhị thức, feature THÔ, cluster-robust theo seed (24 cluster):")
    for nm in names:
        z = params[nm] / ses[nm]
        print(f"  {nm:<11} beta {params[nm]:+.6f}   SE_cluster {ses[nm]:.6f}   z {z:+7.2f}")
    expected_sign = {"rssi_level": +1, "rssi_slope": +1, "retry_rate": -1}
    signs = {nm: ("ĐÚNG chiều" if np.sign(params[nm]) == s else "NGƯỢC chiều — PHÁT HIỆN, không clip")
             for nm, s in expected_sign.items()}
    print("  dấu:", ", ".join(f"{nm}: {v}" for nm, v in signs.items()))
    out["glm_full"] = {"params": params, "cluster_se": ses,
                       "z": zstats, "p_value": pvalues, "ci95": ci95,
                       "cov_cluster": res.cov_params().tolist(),
                       "n_clusters": int(len(set(d["seed"].tolist()))),
                       "sign_check": signs}

    # ---------------- Kiểm chứng vật lý: β_slope/β_RSSI ~ τ ----------------
    b_r, b_s = params["rssi_level"], params["rssi_slope"]
    ratio_full = b_s / b_r
    C = res.cov_params()
    g = np.array([0.0, -b_s / b_r ** 2, 1.0 / b_r, 0.0])   # delta method
    se_ratio = float(np.sqrt(g @ C @ g))
    print(f"\nKiểm chứng vật lý (mô hình đầy đủ): β_slope/β_RSSI = {ratio_full:.2f} s"
          f"  (SE {se_ratio:.2f}; τ = {TAU_S:.0f} s)")
    out["physics_ratio"] = {"full_model_s": float(ratio_full), "se_delta": se_ratio,
                            "tau_s": TAU_S}

    # ---------------- Bootstrap theo seed ----------------------------------
    rng = np.random.default_rng(BOOT_SEED)
    seed_idx = {s: np.where(d["seed"] == s)[0] for s in fit_seeds}
    boot = np.empty((BOOT_B, 4))
    for b in range(BOOT_B):
        pick = rng.choice(fit_seeds, size=len(fit_seeds), replace=True)
        idx = np.concatenate([seed_idx[s] for s in pick])
        boot[b] = glm_fit(d, idx=idx, cluster=False, start=res.params).params
    lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)
    bsd = boot.std(axis=0, ddof=1)
    bratio = boot[:, 2] / boot[:, 1]
    print(f"\nBootstrap theo seed (B={BOOT_B}, resample 24 seed):")
    for i, nm in enumerate(names):
        print(f"  {nm:<11} SD_boot {bsd[i]:.6f}   CI95 [{lo[i]:+.6f}, {hi[i]:+.6f}]")
    print(f"  tỉ số slope/RSSI: CI95 [{np.percentile(bratio,2.5):.2f}, {np.percentile(bratio,97.5):.2f}] s")
    out["bootstrap"] = {"B": BOOT_B, "rng_seed": BOOT_SEED,
                        "sd": dict(zip(names, bsd.tolist())),
                        "ci95_lo": dict(zip(names, lo.tolist())),
                        "ci95_hi": dict(zip(names, hi.tolist())),
                        "ratio_ci95": [float(np.percentile(bratio, 2.5)),
                                       float(np.percentile(bratio, 97.5))]}

    # ---------------- Thang attenuation: phân tầng theo rssi_n -------------
    print("\nThang attenuation — fit phân tầng theo rssi_n (KHÔNG lọc dòng nào):")
    strata = []
    n_stratified = 0
    for lo_n, hi_n in N_BANDS:
        mask = (d["n_rssi"] >= lo_n) & (d["n_rssi"] <= hi_n)
        idx = np.where(mask)[0]
        n_stratified += len(idx)
        if len(idx) < 1000:
            strata.append({"band": f"{lo_n}-{hi_n}", "n_rows": int(len(idx)), "skipped": True})
            continue
        r = glm_fit(d, idx=idx)
        strata.append({"band": f"{lo_n}-{hi_n if hi_n < 10**9 else '+'}",
                       "n_rows": int(len(idx)),
                       "beta_slope": float(r.params[2]), "se_slope": float(r.bse[2]),
                       "beta_rssi": float(r.params[1]), "beta_retry": float(r.params[3])})
        s = strata[-1]
        print(f"  n∈[{lo_n:>2},{'∞' if hi_n>10**8 else hi_n:>2}]  {s['n_rows']:>6} dòng   "
              f"β_slope {s['beta_slope']:+.4f} ± {s['se_slope']:.4f}   "
              f"β_rssi {s['beta_rssi']:+.4f}")
    bs = [s["beta_slope"] for s in strata if not s.get("skipped")]
    assert n_stratified == n_used, "phân tầng rssi_n đã làm rơi dòng"
    monotone = all(b2 > b1 for b1, b2 in zip(bs, bs[1:]))
    usable = [s for s in strata if not s.get("skipped")]
    stable = max(s["beta_slope"] - 1.96 * s["se_slope"] for s in usable) <= \
        min(s["beta_slope"] + 1.96 * s["se_slope"] for s in usable)
    if monotone:
        stratum_result = "monotone_increasing"
        message = "TĂNG ĐƠN ĐIỆU — bằng chứng trực tiếp attenuation"
    elif stable:
        stratum_result = "stable"
        message = "ỔN ĐỊNH (CI95 giao nhau) — không có attenuation đáng kể"
    else:
        stratum_result = "mixed"
        message = "KHÔNG đơn điệu VÀ KHÔNG ổn định — bằng chứng attenuation chưa kết luận"
    print(f"  β_slope theo tầng: {message}")
    out["strata"] = {"bands": strata, "n_rows_covered": n_stratified,
                     "monotone_increasing": bool(monotone),
                     "stable_ci95_intersection": bool(stable),
                     "result": stratum_result}

    # Reliability ratio — CHỈ áp khi (b) cho bằng chứng trực tiếp.
    out["reliability"] = {"applied": bool(monotone)}
    if monotone:
        var_meas_row = np.array([sigma_fading(dd) ** 2 / (S_T2 * nn)
                                 for dd, nn in zip(d["dist"], d["n_rssi"])])
        var_obs = float(d["slope"].var(ddof=1))
        lam = 1.0 - float(var_meas_row.mean()) / var_obs
        if not 0.0 < lam <= 1.0:
            sys.exit(f"TỪ CHỐI hiệu chỉnh reliability-ratio: λ={lam:.3f} ngoài (0,1].")
        b_corr = params["rssi_slope"] / lam
        out["reliability"].update({
            "E_var_meas": float(var_meas_row.mean()),
            "var_obs_slope": var_obs,
            "lambda": lam,
            "s_t2": S_T2,
            "sigma_tiers_P0": SIGMA_TIER[:2] + [(None, SIGMA_TIER[2][1])],
            "beta_slope_observed": params["rssi_slope"],
            "beta_slope_corrected": float(b_corr),
        })
        print(f"  ÁP HIỆU CHỈNH: β_slope quan sát {params['rssi_slope']:+.4f} -> "
               f"β_thật ước lượng {b_corr:+.4f} (báo CẢ HAI)")
    else:
        out["reliability"]["reason"] = (
            "Bước (b) không cho thấy beta_slope tăng đơn điệu; theo PLAN P5 "
            "không được tính hay áp reliability-ratio."
        )
        print("  KHÔNG tính/áp reliability-ratio: điều kiện bước (b) không kích hoạt.")

    # ---------------- frozen/weights.json ----------------------------------
    train_manifest = manifests[0]
    norm = json.load(open("frozen/normalization.json"))
    lvl, slp = norm["features"]["rssi_level"], norm["features"]["rssi_slope"]
    span_l, span_s = lvl["p80"] - lvl["p20"], slp["p80"] - slp["p20"]
    w = np.array([params["rssi_level"] * span_l, params["rssi_slope"] * span_s,
                  -params["retry_rate"]])
    abc = (w / w.sum()).tolist() if (w > 0).all() else None
    weights = {
        "artifact": args.weights, "phase": "P5a", "created": "2026-07-27", "frozen": True,
        "model": "binomial GLM (logit), RAW features, free intercept, cluster-robust by seed",
        "label": "per-attempt: successes = trials_future - fails_future (pooled probe+cbr)",
        "fit_set": {"seeds": fit_seeds, "n_rows_used": n_used,
                    "n_rows_missing_retry": n_missing},
        "provenance": {
            "data_git_sha": train_manifest["git_sha"],
            "binary_sha256": train_manifest["binary_sha256"],
            "config_sim_sha256": train_manifest["config_sim_sha256"],
            "sim_params_sha256_by_seed": realized_params,
            "split": f"frozen/split.json@sha256:{sha256_file('frozen/split.json')}",
            "analysis_script": f"{__file__}@sha256:{sha256_file(__file__)}",
        },
        "coefficients_raw_scale": {
            "intercept": params["intercept"],
            "rssi_level_per_dB": params["rssi_level"],
            "rssi_slope_per_dB_per_s": params["rssi_slope"],
            "retry_rate": params["retry_rate"],
        },
        "cluster_robust_se": ses,
        "cluster_robust_z": zstats,
        "cluster_robust_p_value": pvalues,
        "cluster_robust_ci95": ci95,
        "cov_params_order_intercept_level_slope_retry": res.cov_params().tolist(),
        "deployment": {
            "formula": "z = b0 + b1*rssi_level + b2*rssi_slope + b3*retry_rate; p_hat = 1/(1+exp(-z))",
            "note": ("P8 chạy TTT trên thang logit z, KHÔNG trên LinkScore đã clip: "
                     "clip ghim s_rssi=1 với 100% dòng 0-200 m nên d(LinkScore)/dt = 0 "
                     "chính xác -> TTT vô hạn -> mất cảnh báo sớm đúng vùng giá trị nhất."),
        },
        "presentation_abc": {
            "note": ("CHỈ để trình bày paper (LinkScore = a*s_rssi + b*s_slope + c*s_mac "
                     "trên feature chuẩn hoá [0,1] cùng chiều); controller KHÔNG dùng. "
                     "w = [b1*(p80-p20)_level, b2*(p80-p20)_slope, -b3]; (a,b,c) = w/sum(w)."),
            "w_raw": w.tolist(),
            "abc": abc,
            "normalization_ref": f"frozen/normalization.json@sha256:{sha256_file('frozen/normalization.json')}",
        },
        "validation_snapshot": {
            "ratio_slope_over_rssi_s": float(ratio_full), "tau_s": TAU_S,
            "bootstrap_sd": dict(zip(names, bsd.tolist())),
            "strata_monotone": bool(monotone),
            "strata_stable_ci95_intersection": bool(stable),
            "strata_result": stratum_result,
        },
    }
    with open(args.weights, "w") as fh:
        json.dump(weights, fh, indent=2, ensure_ascii=False)
    print(f"\nđã ghi {args.weights} (sha256 {sha256_file(args.weights)[:12]}…)")
    if abc:
        print(f"  (a,b,c) trình bày = [{abc[0]:.3f}, {abc[1]:.3f}, {abc[2]:.3f}]")
    else:
        print("  (a,b,c) KHÔNG chuẩn hoá được — có trọng số hiệu dụng âm (phát hiện, xem báo cáo)")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print(f"đã ghi {args.json}")


if __name__ == "__main__":
    main()
