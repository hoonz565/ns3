#!/usr/bin/env python3
"""P5b: frozen inference and holdout-only predictive evaluation.

This script deliberately contains no fitting code.  It reads only:
  - frozen/split.json
  - frozen/weights.json
  - frozen/normalization.json
  - data/train/seed-{30..35}/rows_norm.csv

This is the legacy v1 frozen evaluation. Its primary unit is an individual
future transmission attempt. Because the
CSV stores binomial counts, metrics are computed exactly with successes and
failures as integer weights; no row expansion or post-ARQ label is used.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SPLIT_PATH = ROOT / "frozen/split.json"
WEIGHTS_PATH = ROOT / "frozen/weights.json"
NORM_PATH = ROOT / "frozen/normalization.json"
PREDICTIONS_PATH = ROOT / "data/processed/P5b-holdout-predictions.csv.gz"
METRICS_PATH = ROOT / "reports/P5b-metrics.json"
RELIABILITY_PATH = ROOT / "reports/P5b-reliability.csv"
CALIBRATION_FIG_PATH = ROOT / "figures/P5b-calibration.png"
RAW_CLIP_FIG_PATH = ROOT / "figures/P5b-raw-vs-clip.png"
SCATTER_FIG_PATH = ROOT / "figures/P5b-holdout-scatter.png"

EXPECTED_FIT = list(range(6, 30))
EXPECTED_HOLDOUT = list(range(30, 36))
REQUIRED_COLUMNS = {
    "seed", "t", "src", "dst", "dist_m", "rssi_level", "rssi_slope",
    "retry_rate", "trials_future", "fails_future", "pdr_future",
    "s_rssi", "s_slope", "s_mac",
}
MODEL_ORDER = ("full_raw", "full_clipped", "ar")
MODEL_LABELS = {
    "full_raw": "Full frozen GLM — raw logit",
    "full_clipped": "Full frozen GLM — clipped-input equivalent",
    "ar": "AR baseline — s_mac = 1 - retry_rate",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def optional_float(value: str) -> float:
    return math.nan if value == "" else float(value)


def expit(z: np.ndarray) -> np.ndarray:
    out = np.empty_like(z, dtype=float)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


def weighted_auc(scores: np.ndarray, successes: np.ndarray,
                 failures: np.ndarray) -> float:
    """Exact ROC AUC from aggregate binomial rows, with 0.5 credit for ties."""
    order = np.argsort(scores, kind="mergesort")
    s = scores[order]
    pos = successes[order].astype(float)
    neg = failures[order].astype(float)
    total_pos = pos.sum()
    total_neg = neg.sum()
    if total_pos == 0 or total_neg == 0:
        return math.nan

    numerator = 0.0
    cumulative_neg = 0.0
    start = 0
    while start < len(s):
        end = start + 1
        while end < len(s) and s[end] == s[start]:
            end += 1
        group_pos = pos[start:end].sum()
        group_neg = neg[start:end].sum()
        numerator += group_pos * (cumulative_neg + 0.5 * group_neg)
        cumulative_neg += group_neg
        start = end
    return numerator / (total_pos * total_neg)


def weighted_average_precision(scores: np.ndarray, successes: np.ndarray,
                               failures: np.ndarray) -> float:
    """Exact non-interpolated average precision from aggregate binomial rows."""
    order = np.argsort(-scores, kind="mergesort")
    s = scores[order]
    pos = successes[order].astype(float)
    neg = failures[order].astype(float)
    total_pos = pos.sum()
    if total_pos == 0:
        return math.nan

    cumulative_pos = 0.0
    cumulative_neg = 0.0
    ap = 0.0
    start = 0
    while start < len(s):
        end = start + 1
        while end < len(s) and s[end] == s[start]:
            end += 1
        group_pos = pos[start:end].sum()
        group_neg = neg[start:end].sum()
        cumulative_pos += group_pos
        cumulative_neg += group_neg
        precision = cumulative_pos / (cumulative_pos + cumulative_neg)
        ap += (group_pos / total_pos) * precision
        start = end
    return ap


def reliability(scores: np.ndarray, successes: np.ndarray,
                failures: np.ndarray) -> list[dict]:
    trials = successes + failures
    bin_ids = np.minimum((scores * 10).astype(int), 9)
    rows = []
    for bin_id in range(10):
        mask = bin_ids == bin_id
        n_trials = int(trials[mask].sum())
        n_successes = int(successes[mask].sum())
        mean_prediction = (
            float(np.average(scores[mask], weights=trials[mask]))
            if n_trials else math.nan
        )
        observed = n_successes / n_trials if n_trials else math.nan
        rows.append({
            "bin": bin_id,
            "lower": bin_id / 10,
            "upper": (bin_id + 1) / 10,
            "n_rows": int(mask.sum()),
            "n_trials": n_trials,
            "n_successes": n_successes,
            "mean_prediction": mean_prediction,
            "observed_success_rate": observed,
            "calibration_gap": observed - mean_prediction if n_trials else math.nan,
        })
    return rows


def evaluate(scores: np.ndarray, successes: np.ndarray,
             failures: np.ndarray) -> tuple[dict, list[dict]]:
    trials = successes + failures
    observed_rates = successes / trials
    observed_mean = float(np.average(observed_rates, weights=trials))
    residual_ss = float(np.sum(trials * (observed_rates - scores) ** 2))
    total_ss = float(np.sum(trials * (observed_rates - observed_mean) ** 2))
    eps = 1e-15
    p = np.clip(scores, eps, 1 - eps)
    n_trials = int(trials.sum())
    n_successes = int(successes.sum())
    n_failures = int(failures.sum())
    logloss = -float(
        (successes * np.log(p) + failures * np.log1p(-p)).sum() / n_trials
    )
    brier = float(
        (successes * (1 - scores) ** 2 + failures * scores ** 2).sum()
        / n_trials
    )
    table = reliability(scores, successes, failures)
    ece = sum(
        row["n_trials"] * abs(row["calibration_gap"])
        for row in table if row["n_trials"]
    ) / n_trials
    return {
        "n_rows": int(len(scores)),
        "n_trials": n_trials,
        "n_successes": n_successes,
        "n_failures": n_failures,
        "success_prevalence": n_successes / n_trials,
        "log_loss": logloss,
        "brier_score": brier,
        "roc_auc": weighted_auc(scores, successes, failures),
        "pr_auc_average_precision": weighted_average_precision(
            scores, successes, failures
        ),
        "aggregate_rate_r2_attempt_weighted": 1 - residual_ss / total_ss,
        "ece_10_fixed_bins": ece,
        "mean_prediction": float(np.average(scores, weights=trials)),
        "row_fraction_probability_zero": float(np.mean(scores == 0)),
        "row_fraction_probability_one": float(np.mean(scores == 1)),
        "attempt_fraction_probability_at_endpoint": float(
            trials[(scores == 0) | (scores == 1)].sum() / n_trials
        ),
    }, table


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def main() -> None:
    split = load_json(SPLIT_PATH)
    weights = load_json(WEIGHTS_PATH)
    norm = load_json(NORM_PATH)

    fit_seeds = split["fit_seeds"]
    holdout_seeds = split["holdout_seeds"]
    assert fit_seeds == EXPECTED_FIT, f"unexpected fit seeds: {fit_seeds}"
    assert holdout_seeds == EXPECTED_HOLDOUT, (
        f"unexpected holdout seeds: {holdout_seeds}"
    )
    assert not set(fit_seeds) & set(holdout_seeds), "fit/holdout overlap"
    assert weights["frozen"] is True and weights["phase"] == "P5a"
    assert norm["frozen"] is True and norm["phase"] == "P3"

    records: list[dict] = []
    per_seed_rows: dict[str, int] = {}
    for seed in holdout_seeds:
        path = ROOT / f"data/train/seed-{seed}/rows_norm.csv"
        assert path.is_file(), f"missing holdout file: {path}"
        count = 0
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames is not None
            missing = REQUIRED_COLUMNS - set(reader.fieldnames)
            assert not missing, f"{path}: missing columns {sorted(missing)}"
            for row in reader:
                row_seed = int(row["seed"])
                assert row_seed == seed, (
                    f"{path}: row seed {row_seed} does not match directory"
                )
                trials = int(row["trials_future"])
                failures = int(row["fails_future"])
                assert trials > 0 and 0 <= failures <= trials
                retry = optional_float(row["retry_rate"])
                s_mac = optional_float(row["s_mac"])
                assert math.isnan(retry) == math.isnan(s_mac)
                records.append({
                    "seed": row_seed,
                    "t": float(row["t"]),
                    "src": int(row["src"]),
                    "dst": int(row["dst"]),
                    "dist_m": float(row["dist_m"]),
                    "rssi_level": float(row["rssi_level"]),
                    "rssi_slope": float(row["rssi_slope"]),
                    "retry_rate": retry,
                    "trials": trials,
                    "failures": failures,
                    "successes": trials - failures,
                    "pdr": float(row["pdr_future"]),
                    "s_rssi": float(row["s_rssi"]),
                    "s_slope": float(row["s_slope"]),
                    "s_mac": s_mac,
                })
                count += 1
        per_seed_rows[str(seed)] = count

    columns = {
        key: np.asarray([row[key] for row in records])
        for key in records[0]
    }
    assert set(np.unique(columns["seed"]).tolist()) == set(holdout_seeds)
    assert not set(np.unique(columns["seed"]).tolist()) & set(fit_seeds)

    valid = np.isfinite(columns["retry_rate"])
    missing_retry = ~valid
    assert np.all(np.isfinite(columns["rssi_level"]))
    assert np.all(np.isfinite(columns["rssi_slope"]))
    assert np.all(np.isfinite(columns["s_rssi"]))
    assert np.all(np.isfinite(columns["s_slope"]))
    assert np.allclose(
        columns["pdr"],
        columns["successes"] / columns["trials"],
        rtol=0,
        atol=5.1e-5,
    )

    level_norm = norm["features"]["rssi_level"]
    slope_norm = norm["features"]["rssi_slope"]
    level_span = level_norm["p80"] - level_norm["p20"]
    slope_span = slope_norm["p80"] - slope_norm["p20"]
    expected_s_rssi = np.clip(
        (columns["rssi_level"] - level_norm["p20"]) / level_span, 0, 1
    )
    expected_s_slope = np.clip(
        (columns["rssi_slope"] - slope_norm["p20"]) / slope_span, 0, 1
    )
    assert np.allclose(columns["s_rssi"], expected_s_rssi, atol=5.1e-7)
    assert np.allclose(columns["s_slope"], expected_s_slope, atol=5.1e-7)
    assert np.allclose(
        columns["s_mac"][valid],
        1 - np.clip(columns["retry_rate"][valid], 0, 1),
        atol=5.1e-7,
    )

    coef = weights["coefficients_raw_scale"]
    b0 = coef["intercept"]
    b_level = coef["rssi_level_per_dB"]
    b_slope = coef["rssi_slope_per_dB_per_s"]
    b_retry = coef["retry_rate"]
    abc = np.asarray(weights["presentation_abc"]["abc"], dtype=float)
    w_raw = np.asarray(weights["presentation_abc"]["w_raw"], dtype=float)
    assert np.all(abc >= 0) and math.isclose(float(abc.sum()), 1.0)
    expected_w = np.asarray(
        [b_level * level_span, b_slope * slope_span, -b_retry]
    )
    assert np.allclose(w_raw, expected_w, atol=1e-12)

    n = len(records)
    raw_logit = np.full(n, np.nan)
    full_probability = np.full(n, np.nan)
    linkscore = np.full(n, np.nan)
    clipped_logit = np.full(n, np.nan)
    clipped_probability = np.full(n, np.nan)
    ar_probability = np.full(n, np.nan)

    raw_logit[valid] = (
        b0
        + b_level * columns["rssi_level"][valid]
        + b_slope * columns["rssi_slope"][valid]
        + b_retry * columns["retry_rate"][valid]
    )
    full_probability[valid] = expit(raw_logit[valid])
    linkscore[valid] = (
        abc[0] * columns["s_rssi"][valid]
        + abc[1] * columns["s_slope"][valid]
        + abc[2] * columns["s_mac"][valid]
    )

    # Frozen affine mapping from clipped LinkScore to the full model's logit.
    # This is not a calibration fit: it follows algebraically from weights.json.
    linkscore_intercept = (
        b0 + b_level * level_norm["p20"]
        + b_slope * slope_norm["p20"] + b_retry
    )
    clipped_logit[valid] = linkscore_intercept + w_raw.sum() * linkscore[valid]
    clipped_level_raw = (
        level_norm["p20"] + level_span * columns["s_rssi"][valid]
    )
    clipped_slope_raw = (
        slope_norm["p20"] + slope_span * columns["s_slope"][valid]
    )
    clipped_retry_raw = 1 - columns["s_mac"][valid]
    clipped_logit_direct = (
        b0 + b_level * clipped_level_raw
        + b_slope * clipped_slope_raw + b_retry * clipped_retry_raw
    )
    assert np.allclose(
        clipped_logit[valid], clipped_logit_direct, atol=2e-6
    )
    clipped_probability[valid] = expit(clipped_logit[valid])
    ar_probability[valid] = columns["s_mac"][valid]

    model_scores = {
        "full_raw": full_probability[valid],
        "full_clipped": clipped_probability[valid],
        "ar": ar_probability[valid],
    }
    successes = columns["successes"][valid].astype(np.int64)
    failures = columns["failures"][valid].astype(np.int64)
    model_metrics = {}
    reliability_tables = {}
    for model in MODEL_ORDER:
        model_metrics[model], reliability_tables[model] = evaluate(
            model_scores[model], successes, failures
        )

    prevalence = int(successes.sum()) / int((successes + failures).sum())
    imbalance_ratio = max(prevalence, 1 - prevalence) / min(
        prevalence, 1 - prevalence
    )

    distance_specs = [
        ("0-200", 0.0, 200.0),
        ("200-400", 200.0, 400.0),
        ("400-600", 400.0, 600.0),
        ("600-800", 600.0, 800.0),
        ("800+", 800.0, math.inf),
    ]
    distance_analysis = []
    for label, lo, hi in distance_specs:
        mask_all = (
            (columns["dist_m"] >= lo)
            & (columns["dist_m"] < hi)
        )
        mask = mask_all & valid
        item = {
            "distance_m": label,
            "n_rows_all": int(mask_all.sum()),
            "n_rows_evaluable": int(mask.sum()),
            "rssi_upper_clip_fraction": float(
                np.mean(columns["s_rssi"][mask_all] == 1)
            ) if mask_all.any() else math.nan,
            "rssi_interior_fraction": float(
                np.mean(
                    (columns["s_rssi"][mask_all] > 0)
                    & (columns["s_rssi"][mask_all] < 1)
                )
            ) if mask_all.any() else math.nan,
            "mean_absolute_probability_change": float(
                np.mean(np.abs(
                    full_probability[mask] - clipped_probability[mask]
                ))
            ) if mask.any() else math.nan,
        }
        if mask.any():
            item["full_raw"], _ = evaluate(
                full_probability[mask],
                columns["successes"][mask].astype(np.int64),
                columns["failures"][mask].astype(np.int64),
            )
            item["full_clipped"], _ = evaluate(
                clipped_probability[mask],
                columns["successes"][mask].astype(np.int64),
                columns["failures"][mask].astype(np.int64),
            )
        distance_analysis.append(item)

    near = (columns["dist_m"] >= 0) & (columns["dist_m"] < 200)
    raw_level_contribution = b_level * columns["rssi_level"][near]
    clipped_level_contribution = b_level * (
        level_norm["p20"] + level_span * columns["s_rssi"][near]
    )
    raw_vs_clip = {
        "linkscore_affine_mapping": {
            "formula": "z_clip = intercept_clip + sum(w_raw) * LinkScore",
            "intercept_clip": linkscore_intercept,
            "sum_w_raw": float(w_raw.sum()),
            "max_abs_equivalence_error": float(np.max(np.abs(
                clipped_logit[valid] - clipped_logit_direct
            ))),
        },
        "overall": {
            "mean_absolute_probability_change": float(np.mean(np.abs(
                full_probability[valid] - clipped_probability[valid]
            ))),
            "max_absolute_probability_change": float(np.max(np.abs(
                full_probability[valid] - clipped_probability[valid]
            ))),
            "raw_minus_clipped_log_loss": (
                model_metrics["full_raw"]["log_loss"]
                - model_metrics["full_clipped"]["log_loss"]
            ),
            "raw_minus_clipped_brier": (
                model_metrics["full_raw"]["brier_score"]
                - model_metrics["full_clipped"]["brier_score"]
            ),
        },
        "distance_0_200_m": {
            "n_rows_all": int(near.sum()),
            "n_rows_evaluable": int((near & valid).sum()),
            "rssi_upper_clip_fraction": float(
                np.mean(columns["s_rssi"][near] == 1)
            ),
            "rssi_interior_fraction": float(np.mean(
                (columns["s_rssi"][near] > 0)
                & (columns["s_rssi"][near] < 1)
            )),
            "raw_dz_d_rssi": b_level,
            "clipped_dz_d_rssi_fraction_zero": float(np.mean(
                (columns["s_rssi"][near] == 0)
                | (columns["s_rssi"][near] == 1)
            )),
            "raw_level_contribution_std": float(np.std(
                raw_level_contribution
            )),
            "clipped_level_contribution_std": float(np.std(
                clipped_level_contribution
            )),
            "raw_level_contribution_range": float(np.ptp(
                raw_level_contribution
            )),
            "clipped_level_contribution_range": float(np.ptp(
                clipped_level_contribution
            )),
        },
        "by_distance": distance_analysis,
    }

    baseline_availability = {
        "rssi_only": {
            "status": "not_evaluated",
            "reason": (
                "No frozen RSSI-only coefficients or inference implementation "
                "exists; deriving one would be a new implementation or refit."
            ),
        },
        "rssi_plus_slope": {
            "status": "not_evaluated",
            "reason": (
                "No frozen RSSI+slope coefficients or inference implementation "
                "exists; deleting retry from the full conditional model would "
                "not reproduce the registered reduced model."
            ),
        },
        "full_model": {
            "status": "evaluated",
            "implementation": "frozen/weights.json raw deployment formula",
        },
        "let": {
            "status": "not_evaluated",
            "reason": "No LET inference implementation exists in the repository.",
        },
        "ar": {
            "status": "evaluated",
            "implementation": (
                "frozen normalization: s_mac = 1 - clip(retry_rate, 0, 1)"
            ),
        },
    }

    PREDICTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    prediction_fields = [
        "seed", "t", "src", "dst", "dist_m", "trials_future",
        "fails_future", "successes_future", "pdr_future", "rssi_level",
        "rssi_slope", "retry_rate", "s_rssi", "s_slope", "s_mac",
        "full_model_evaluable", "raw_logit", "full_probability",
        "clipped_linkscore", "clipped_logit_equivalent",
        "clipped_probability", "ar_probability",
    ]
    with gzip.open(PREDICTIONS_PATH, "wt", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=prediction_fields)
        writer.writeheader()
        for i, row in enumerate(records):
            is_valid = bool(valid[i])
            writer.writerow({
                "seed": row["seed"],
                "t": f"{row['t']:.4f}",
                "src": row["src"],
                "dst": row["dst"],
                "dist_m": f"{row['dist_m']:.4f}",
                "trials_future": row["trials"],
                "fails_future": row["failures"],
                "successes_future": row["successes"],
                "pdr_future": f"{row['pdr']:.4f}",
                "rssi_level": f"{row['rssi_level']:.4f}",
                "rssi_slope": f"{row['rssi_slope']:.4f}",
                "retry_rate": (
                    f"{row['retry_rate']:.4f}" if is_valid else ""
                ),
                "s_rssi": f"{row['s_rssi']:.6f}",
                "s_slope": f"{row['s_slope']:.6f}",
                "s_mac": f"{row['s_mac']:.6f}" if is_valid else "",
                "full_model_evaluable": int(is_valid),
                "raw_logit": f"{raw_logit[i]:.12g}" if is_valid else "",
                "full_probability": (
                    f"{full_probability[i]:.12g}" if is_valid else ""
                ),
                "clipped_linkscore": (
                    f"{linkscore[i]:.12g}" if is_valid else ""
                ),
                "clipped_logit_equivalent": (
                    f"{clipped_logit[i]:.12g}" if is_valid else ""
                ),
                "clipped_probability": (
                    f"{clipped_probability[i]:.12g}" if is_valid else ""
                ),
                "ar_probability": (
                    f"{ar_probability[i]:.12g}" if is_valid else ""
                ),
            })

    with RELIABILITY_PATH.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "model", "bin", "lower", "upper", "n_rows", "n_trials",
            "n_successes", "mean_prediction", "observed_success_rate",
            "calibration_gap",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for model in MODEL_ORDER:
            for row in reliability_tables[model]:
                writer.writerow({"model": model, **row})

    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-p5b")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 6.2))
    ax.plot([0, 1], [0, 1], color="0.45", linestyle="--", label="Perfect")
    for model in MODEL_ORDER:
        table = reliability_tables[model]
        x = [row["mean_prediction"] for row in table if row["n_trials"]]
        y = [row["observed_success_rate"] for row in table if row["n_trials"]]
        ax.plot(x, y, marker="o", linewidth=1.7, label=MODEL_LABELS[model])
    ax.set(
        xlabel="Mean predicted success probability (fixed 0.1 bins)",
        ylabel="Observed per-attempt success rate (legacy v1)",
        title="P5b holdout calibration — seeds 30–35",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(CALIBRATION_FIG_PATH, dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))
    labels = [row["distance_m"] for row in distance_analysis]
    upper = [100 * row["rssi_upper_clip_fraction"] for row in distance_analysis]
    delta = [
        100 * row["mean_absolute_probability_change"]
        for row in distance_analysis
    ]
    axes[0].bar(labels, upper, color="#d55e00")
    axes[0].set(
        xlabel="Distance band (m)",
        ylabel="Rows pinned at s_RSSI = 1 (%)",
        title="Upper clipping removes RSSI-level sensitivity",
        ylim=(0, 105),
    )
    axes[1].bar(labels, delta, color="#0072b2")
    axes[1].set(
        xlabel="Distance band (m)",
        ylabel="Mean |p_raw - p_clipped| (percentage points)",
        title="Prediction change caused by clipping",
    )
    for ax in axes:
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("P5b raw-logit versus clipped-LinkScore analysis")
    fig.tight_layout()
    fig.savefig(RAW_CLIP_FIG_PATH, dpi=180)
    plt.close(fig)

    observed_rates = successes / (successes + failures)
    fig, axes = plt.subplots(1, 3, figsize=(14.4, 4.5), sharex=True, sharey=True)
    for ax, model in zip(axes, MODEL_ORDER):
        ax.hexbin(
            model_scores[model],
            observed_rates,
            gridsize=45,
            extent=(0, 1, 0, 1),
            bins="log",
            mincnt=1,
            cmap="viridis",
        )
        ax.plot([0, 1], [0, 1], color="white", linestyle="--", linewidth=1.2)
        r2 = model_metrics[model]["aggregate_rate_r2_attempt_weighted"]
        ax.set_title(f"{MODEL_LABELS[model]}\nweighted R² = {r2:.3f}", fontsize=9)
        ax.set_xlabel("Predicted success probability")
        ax.grid(alpha=0.15)
    axes[0].set_ylabel("Observed aggregate future PDR")
    fig.suptitle("P5b holdout predictions versus observed aggregate PDR")
    fig.tight_layout()
    fig.savefig(SCATTER_FIG_PATH, dpi=180)
    plt.close(fig)

    output = {
        "artifact": "reports/P5b-metrics.json",
        "phase": "P5b",
        "protocol": {
            "inference_only": True,
            "refit_performed": False,
            "holdout_seed_source": "frozen/split.json",
            "fit_seeds": fit_seeds,
            "holdout_seeds": holdout_seeds,
            "fit_holdout_overlap": [],
            "label": (
                "legacy v1 per-attempt successes = trials_future - fails_future; "
                "aggregate binomial counts used as exact weights"
            ),
            "metric_weighting": "legacy v1 per future transmission attempt",
            "log_loss_numerical_clip": "probability clipped to [1e-15, 1-1e-15]",
        },
        "input_sha256": {
            "frozen/split.json": sha256(SPLIT_PATH),
            "frozen/weights.json": sha256(WEIGHTS_PATH),
            "frozen/normalization.json": sha256(NORM_PATH),
        },
        "holdout_integrity": {
            "per_seed_rows": per_seed_rows,
            "n_rows_total": int(n),
            "n_rows_evaluable_full": int(valid.sum()),
            "n_rows_missing_retry": int(missing_retry.sum()),
            "prediction_file_keeps_all_rows": True,
            "seeds_observed": sorted(
                int(value) for value in np.unique(columns["seed"])
            ),
            "attempt_success_prevalence_evaluable": prevalence,
            "majority_to_minority_ratio": imbalance_ratio,
        },
        "baseline_availability": baseline_availability,
        "metrics": model_metrics,
        "reliability": reliability_tables,
        "raw_vs_clip": raw_vs_clip,
        "artifacts": {
            "predictions": str(PREDICTIONS_PATH.relative_to(ROOT)),
            "reliability_table": str(RELIABILITY_PATH.relative_to(ROOT)),
            "calibration_figure": str(CALIBRATION_FIG_PATH.relative_to(ROOT)),
            "raw_vs_clip_figure": str(RAW_CLIP_FIG_PATH.relative_to(ROOT)),
            "holdout_scatter_figure": str(SCATTER_FIG_PATH.relative_to(ROOT)),
        },
    }
    with METRICS_PATH.open("w", encoding="utf-8") as f:
        json.dump(json_safe(output), f, indent=2, ensure_ascii=False)
        f.write("\n")

    print("P5b frozen holdout evaluation: PASS")
    print(f"  seeds: {holdout_seeds}; overlap: none")
    print(
        f"  rows: {n}; evaluable: {int(valid.sum())}; "
        f"missing retry kept: {int(missing_retry.sum())}"
    )
    for model in MODEL_ORDER:
        m = model_metrics[model]
        print(
            f"  {model}: LogLoss={m['log_loss']:.6f}, "
            f"Brier={m['brier_score']:.6f}, ROC-AUC={m['roc_auc']:.6f}, "
            f"PR-AUC={m['pr_auc_average_precision']:.6f}, "
            f"ECE={m['ece_10_fixed_bins']:.6f}"
        )
    print(f"  wrote {PREDICTIONS_PATH.relative_to(ROOT)}")
    print(f"  wrote {METRICS_PATH.relative_to(ROOT)}")
    print(f"  wrote {RELIABILITY_PATH.relative_to(ROOT)}")
    print(f"  wrote {CALIBRATION_FIG_PATH.relative_to(ROOT)}")
    print(f"  wrote {RAW_CLIP_FIG_PATH.relative_to(ROOT)}")
    print(f"  wrote {SCATTER_FIG_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
