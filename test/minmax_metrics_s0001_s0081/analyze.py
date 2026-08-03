#!/usr/bin/env python3
"""Aggregate and visualize RSSI, RSSI slope, and MAC retry for scenarios 1..81."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/ns3-metrics-matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


FEATURES = {
    "rssi_level": ("RSSI", "dBm", "rssi"),
    "rssi_slope": ("RSSI Slope", "dB/s", "rssi_slope"),
    "retry_rate": ("MAC Retry", "ratio", "retry"),
}
REQUIRED_COLUMNS = set(FEATURES)
SAMPLE_STRIDE = 100
SAMPLE_LIMIT_PER_SCENARIO = 10_000
HISTOGRAM_BINS = 80
CHUNK_ROWS = 250_000


@dataclass
class OnlineStats:
    count: int = 0
    missing: int = 0
    invalid: int = 0
    minimum: float = math.inf
    maximum: float = -math.inf
    mean: float = 0.0
    m2: float = 0.0
    m3: float = 0.0

    def add_batch(self, values: np.ndarray, missing: int, invalid: int) -> None:
        self.missing += missing
        self.invalid += invalid
        if not len(values):
            return
        batch_count = len(values)
        batch_mean = float(values.mean())
        centered = values - batch_mean
        batch_m2 = float(np.dot(centered, centered))
        batch_m3 = float(np.sum(centered * centered * centered))
        if not self.count:
            self.count = batch_count
            self.mean = batch_mean
            self.m2 = batch_m2
            self.m3 = batch_m3
        else:
            old_count = self.count
            total = old_count + batch_count
            delta = batch_mean - self.mean
            self.m3 = (
                self.m3
                + batch_m3
                + delta**3 * old_count * batch_count * (old_count - batch_count) / total**2
                + 3 * delta * (old_count * batch_m2 - batch_count * self.m2) / total
            )
            self.m2 += batch_m2 + delta**2 * old_count * batch_count / total
            self.mean += delta * batch_count / total
            self.count = total
        self.minimum = min(self.minimum, float(values.min()))
        self.maximum = max(self.maximum, float(values.max()))

    @property
    def std(self) -> float:
        return math.sqrt(self.m2 / (self.count - 1)) if self.count > 1 else 0.0

    @property
    def skewness(self) -> float:
        return (
            math.sqrt(self.count) * self.m3 / (self.m2 ** 1.5)
            if self.count > 2 and self.m2 > 0
            else 0.0
        )


@dataclass
class FeatureResult:
    stats: OnlineStats = field(default_factory=OnlineStats)
    sample: list[float] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("dataset_1000x10"))
    parser.add_argument("--scenario-start", type=int, default=1)
    parser.add_argument("--scenario-end", type=int, default=81)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "results")
    return parser.parse_args()


def atomic_text(path: Path, text: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def discover_inputs(args: argparse.Namespace) -> tuple[list[tuple[int, int, Path]], dict]:
    usable: list[tuple[int, int, Path]] = []
    missing: list[str] = []
    empty: list[str] = []
    invalid_header: list[str] = []
    for scenario in range(args.scenario_start, args.scenario_end + 1):
        for seed in range(1, args.seeds + 1):
            path = args.dataset / f"scenario_{scenario:04d}" / f"seed_{seed:04d}" / "rows.csv"
            relative = str(path)
            if not path.is_file():
                missing.append(relative)
                continue
            if path.stat().st_size == 0:
                empty.append(relative)
                continue
            with path.open(newline="", encoding="utf-8") as handle:
                header = next(csv.reader(handle), [])
            if not REQUIRED_COLUMNS.issubset(header):
                invalid_header.append(relative)
                continue
            usable.append((scenario, seed, path))
    audit = {
        "expected_files": (args.scenario_end - args.scenario_start + 1) * args.seeds,
        "usable_files": len(usable),
        "missing_files": missing,
        "empty_files": empty,
        "invalid_header_files": invalid_header,
        "complete": not (missing or empty or invalid_header),
    }
    return usable, audit


def first_pass(
    inputs: list[tuple[int, int, Path]], scenario_ids: list[int]
) -> tuple[dict[str, FeatureResult], dict[int, dict[str, FeatureResult]], int]:
    global_results = {feature: FeatureResult() for feature in FEATURES}
    per_scenario = {
        scenario: {feature: FeatureResult() for feature in FEATURES} for scenario in scenario_ids
    }
    rows_seen = 0
    scenario_row_numbers = {scenario: 0 for scenario in scenario_ids}

    for file_number, (scenario, seed, path) in enumerate(inputs, 1):
        for frame in pd.read_csv(path, usecols=list(FEATURES), chunksize=CHUNK_ROWS):
            chunk_rows = len(frame)
            row_positions = scenario_row_numbers[scenario] + np.arange(chunk_rows)
            sample_mask = row_positions % SAMPLE_STRIDE == 0
            rows_seen += chunk_rows
            scenario_row_numbers[scenario] += chunk_rows
            for feature in FEATURES:
                raw_values = frame[feature].to_numpy(dtype=np.float64, copy=False)
                missing_mask = np.isnan(raw_values)
                finite_mask = np.isfinite(raw_values)
                valid = raw_values[finite_mask]
                missing = int(missing_mask.sum())
                invalid = int((~finite_mask & ~missing_mask).sum())
                result = global_results[feature]
                local = per_scenario[scenario][feature]
                result.stats.add_batch(valid, missing, invalid)
                local.stats.add_batch(valid, missing, invalid)
                remaining = SAMPLE_LIMIT_PER_SCENARIO - len(local.sample)
                if remaining > 0:
                    sampled = raw_values[sample_mask & finite_mask][:remaining]
                    local.sample.extend(sampled.tolist())
        if file_number == 1 or file_number % 50 == 0 or file_number == len(inputs):
            print(f"Pass 1: {file_number}/{len(inputs)} files, {rows_seen:,} rows", flush=True)

    for feature in FEATURES:
        global_results[feature].sample = [
            value
            for scenario in scenario_ids
            for value in per_scenario[scenario][feature].sample
        ]
    return global_results, per_scenario, rows_seen


def quantiles(sample: list[float]) -> dict[str, float]:
    values = np.asarray(sample, dtype=np.float64)
    points = np.quantile(values, [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
    return dict(zip(("p01", "p05", "p25", "p50", "p75", "p95", "p99"), map(float, points)))


def second_pass(
    inputs: list[tuple[int, int, Path]],
    global_results: dict[str, FeatureResult],
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray], dict[str, int], dict[str, dict[str, float | int]]]:
    edges: dict[str, np.ndarray] = {}
    counts: dict[str, np.ndarray] = {}
    outliers = {feature: 0 for feature in FEATURES}
    endpoint_checks: dict[str, dict[str, float | int]] = {
        feature: {
            "count_raw_equal_global_min": 0,
            "count_raw_equal_global_max": 0,
            "count_normalized_equal_0": 0,
            "count_normalized_equal_1": 0,
            "normalized_min_seen": math.inf,
            "normalized_max_seen": -math.inf,
        }
        for feature in FEATURES
    }
    bounds = {}
    for feature, result in global_results.items():
        low, high = result.stats.minimum, result.stats.maximum
        if not math.isfinite(low) or not math.isfinite(high):
            raise RuntimeError(f"No valid values for {feature}")
        if low == high:
            high = low + 1.0
        edges[feature] = np.linspace(0.0, 1.0, HISTOGRAM_BINS + 1)
        counts[feature] = np.zeros(HISTOGRAM_BINS, dtype=np.int64)
        q = quantiles(result.sample)
        iqr = q["p75"] - q["p25"]
        bounds[feature] = (q["p25"] - 1.5 * iqr, q["p75"] + 1.5 * iqr)

    rows_seen = 0
    for file_number, (_scenario, _seed, path) in enumerate(inputs, 1):
        for frame in pd.read_csv(path, usecols=list(FEATURES), chunksize=CHUNK_ROWS):
            rows_seen += len(frame)
            for feature in FEATURES:
                values = frame[feature].to_numpy(dtype=np.float64, copy=False)
                values = values[np.isfinite(values)]
                if not len(values):
                    continue
                stats = global_results[feature].stats
                span = stats.maximum - stats.minimum
                normalized_values = (
                    (values - stats.minimum) / span if span else np.zeros_like(values)
                )
                counts[feature] += np.histogram(normalized_values, bins=edges[feature])[0]
                checks = endpoint_checks[feature]
                checks["count_raw_equal_global_min"] += int(np.count_nonzero(values == stats.minimum))
                checks["count_raw_equal_global_max"] += int(np.count_nonzero(values == stats.maximum))
                checks["count_normalized_equal_0"] += int(np.count_nonzero(normalized_values == 0.0))
                checks["count_normalized_equal_1"] += int(np.count_nonzero(normalized_values == 1.0))
                checks["normalized_min_seen"] = min(
                    float(checks["normalized_min_seen"]), float(normalized_values.min())
                )
                checks["normalized_max_seen"] = max(
                    float(checks["normalized_max_seen"]), float(normalized_values.max())
                )
                low, high = bounds[feature]
                outliers[feature] += int(np.count_nonzero((values < low) | (values > high)))
        if file_number == 1 or file_number % 50 == 0 or file_number == len(inputs):
            print(f"Pass 2: {file_number}/{len(inputs)} files, {rows_seen:,} rows", flush=True)
    return edges, counts, outliers, endpoint_checks


def normalized(value: float, minimum: float, maximum: float) -> float:
    return (value - minimum) / (maximum - minimum) if maximum > minimum else 0.0


def write_statistics(
    out: Path,
    args: argparse.Namespace,
    audit: dict,
    rows_seen: int,
    global_results: dict[str, FeatureResult],
    per_scenario: dict[int, dict[str, FeatureResult]],
    edges: dict[str, np.ndarray],
    counts: dict[str, np.ndarray],
    outliers: dict[str, int],
    endpoint_checks: dict[str, dict[str, float | int]],
) -> dict:
    global_json = {}
    for feature, result in global_results.items():
        stats = result.stats
        q = quantiles(result.sample)
        span = stats.maximum - stats.minimum
        iqr = q["p75"] - q["p25"]
        global_json[feature] = {
            "count": stats.count,
            "missing": stats.missing,
            "invalid": stats.invalid,
            "min": stats.minimum,
            "max": stats.maximum,
            "mean": stats.mean,
            "std": stats.std,
            "skewness": stats.skewness,
            "normalized_min": 0.0,
            "normalized_max": 1.0 if span else 0.0,
            "normalized_mean": normalized(stats.mean, stats.minimum, stats.maximum),
            "normalized_std": stats.std / span if span else 0.0,
            **endpoint_checks[feature],
            **q,
            "iqr": iqr,
            "iqr_outlier_count": outliers[feature],
            "iqr_outlier_fraction": outliers[feature] / stats.count if stats.count else 0.0,
            "minmax_formula": f"({feature} - {stats.minimum}) / {span}",
            "central_98pct_fraction_of_minmax_span": (
                (q["p99"] - q["p01"]) / span if span else 0.0
            ),
        }

    statistics = {
        "dataset": str(args.dataset),
        "scenario_start": args.scenario_start,
        "scenario_end": args.scenario_end,
        "rows_seen": rows_seen,
        "normalization": "global Min-Max per feature over every valid row",
        "sample_note": (
            f"Quantiles and boxplots use every {SAMPLE_STRIDE}th row per scenario; "
            "count/min/max/mean/std/skewness and histogram counts use all valid rows."
        ),
        "input_audit": audit,
        "features": global_json,
    }
    atomic_text(out / "statistics.json", json.dumps(statistics, indent=2, ensure_ascii=False) + "\n")

    fields = [
        "scenario", "feature", "count", "missing", "invalid", "min", "max", "mean", "std",
        "global_min", "global_max", "normalized_min", "normalized_max", "normalized_mean",
        "normalized_std",
    ]
    temporary = out / "per_scenario_statistics.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for scenario, feature_results in per_scenario.items():
            for feature, result in feature_results.items():
                stats = result.stats
                global_stats = global_results[feature].stats
                if not stats.count:
                    writer.writerow({
                        "scenario": scenario, "feature": feature, "count": 0,
                        "missing": stats.missing, "invalid": stats.invalid,
                        "global_min": global_stats.minimum, "global_max": global_stats.maximum,
                    })
                    continue
                span = global_stats.maximum - global_stats.minimum
                writer.writerow({
                    "scenario": scenario,
                    "feature": feature,
                    "count": stats.count,
                    "missing": stats.missing,
                    "invalid": stats.invalid,
                    "min": stats.minimum,
                    "max": stats.maximum,
                    "mean": stats.mean,
                    "std": stats.std,
                    "global_min": global_stats.minimum,
                    "global_max": global_stats.maximum,
                    "normalized_min": normalized(stats.minimum, global_stats.minimum, global_stats.maximum),
                    "normalized_max": normalized(stats.maximum, global_stats.minimum, global_stats.maximum),
                    "normalized_mean": normalized(stats.mean, global_stats.minimum, global_stats.maximum),
                    "normalized_std": stats.std / span if span else 0.0,
                })
    temporary.replace(out / "per_scenario_statistics.csv")

    temporary = out / "histogram_bins.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["feature", "bin", "raw_left", "raw_right", "normalized_left", "normalized_right", "count"])
        for feature in FEATURES:
            low, high = global_results[feature].stats.minimum, global_results[feature].stats.maximum
            span = high - low
            for index, count in enumerate(counts[feature]):
                writer.writerow([
                    feature,
                    index,
                    low + edges[feature][index] * span,
                    low + edges[feature][index + 1] * span,
                    edges[feature][index],
                    edges[feature][index + 1],
                    int(count),
                ])
    temporary.replace(out / "histogram_bins.csv")
    return statistics


def add_raw_axis(ax, stats: OnlineStats, title: str, unit: str) -> None:
    span = stats.maximum - stats.minimum
    if span <= 0:
        return
    secondary = ax.secondary_xaxis(
        "top",
        functions=(
            lambda z: z * span + stats.minimum,
            lambda raw: (raw - stats.minimum) / span,
        ),
    )
    secondary.set_xlabel(f"Raw {title} ({unit})")


def plot_histograms(
    out: Path,
    global_results: dict[str, FeatureResult],
    edges: dict[str, np.ndarray],
    counts: dict[str, np.ndarray],
    endpoint_checks: dict[str, dict[str, float | int]],
) -> None:
    colors = {"rssi_level": "#2563eb", "rssi_slope": "#16a34a", "retry_rate": "#dc2626"}
    for feature, (title, unit, filename) in FEATURES.items():
        result = global_results[feature]
        q = quantiles(result.sample)
        fig, ax = plt.subplots(figsize=(10, 6))
        widths = np.diff(edges[feature])
        median_norm = normalized(q["p50"], result.stats.minimum, result.stats.maximum)
        mean_norm = normalized(result.stats.mean, result.stats.minimum, result.stats.maximum)
        ax.bar(edges[feature][:-1], counts[feature], width=widths, align="edge", color=colors[feature], alpha=0.82)
        ax.axvline(median_norm, color="black", linestyle="--", linewidth=1.4, label=f"Median z={median_norm:.4g} (raw {q['p50']:.4g})")
        ax.axvline(mean_norm, color="#f59e0b", linestyle=":", linewidth=1.8, label=f"Mean z={mean_norm:.4g} (raw {result.stats.mean:.4g})")
        ax.set_title(f"Histogram normalized {title} — scenarios 0001–0081")
        ax.set_xlabel(f"{title} Min–Max normalized")
        ax.set_xlim(0.0, 1.0)
        ax.set_ylabel("Number of rows")
        ax.grid(axis="y", alpha=0.2)
        ax.legend()
        checks = endpoint_checks[feature]
        ax.text(
            0.01,
            0.97,
            f"exact z=0: {int(checks['count_normalized_equal_0']):,}\n"
            f"exact z=1: {int(checks['count_normalized_equal_1']):,}",
            transform=ax.transAxes,
            va="top",
        )
        add_raw_axis(ax, result.stats, title, unit)
        fig.tight_layout()
        fig.savefig(out / f"histogram_{filename}.png", dpi=180)
        plt.close(fig)


def plot_boxplots(
    out: Path,
    scenario_ids: list[int],
    per_scenario: dict[int, dict[str, FeatureResult]],
    global_results: dict[str, FeatureResult],
) -> None:
    for feature, (title, unit, filename) in FEATURES.items():
        stats = global_results[feature].stats
        span = stats.maximum - stats.minimum
        data = [
            [normalized(value, stats.minimum, stats.maximum) for value in per_scenario[scenario][feature].sample]
            or [math.nan]
            for scenario in scenario_ids
        ]
        fig, ax = plt.subplots(figsize=(20, 7))
        ax.boxplot(
            data,
            positions=scenario_ids,
            widths=0.65,
            showfliers=True,
            flierprops={"markersize": 1.0, "alpha": 0.2},
            medianprops={"color": "#dc2626", "linewidth": 1.0},
        )
        missing = [scenario for scenario in scenario_ids if not per_scenario[scenario][feature].stats.count]
        for scenario in missing:
            ax.axvspan(scenario - 0.5, scenario + 0.5, color="#ef4444", alpha=0.10)
        ticks = [scenario for scenario in scenario_ids if scenario == 1 or scenario % 5 == 0 or scenario == scenario_ids[-1]]
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{scenario:04d}" for scenario in ticks], rotation=45)
        ax.set_title(
            f"Boxplot {title} by scenario — global Min–Max, sampled every {SAMPLE_STRIDE} rows"
        )
        ax.set_xlabel("Scenario")
        ax.set_ylabel(f"{title} normalized [0, 1]")
        ax.set_ylim(-0.02, 1.02)
        if span > 0:
            secondary = ax.secondary_yaxis(
                "right",
                functions=(
                    lambda z: z * span + stats.minimum,
                    lambda raw: (raw - stats.minimum) / span,
                ),
            )
            secondary.set_ylabel(f"Raw {title} ({unit})")
        ax.grid(axis="y", alpha=0.2)
        if missing:
            ax.text(
                0.01,
                0.99,
                "Missing/empty: " + ", ".join(f"{scenario:04d}" for scenario in missing),
                transform=ax.transAxes,
                va="top",
                fontsize=9,
                color="#b91c1c",
            )
        fig.tight_layout()
        fig.savefig(out / f"boxplot_{filename}.png", dpi=180)
        plt.close(fig)


def interpretation(feature: str, values: dict) -> str:
    skew = values["skewness"]
    if skew > 1:
        direction = "lệch phải mạnh"
    elif skew > 0.25:
        direction = "lệch phải"
    elif skew < -1:
        direction = "lệch trái mạnh"
    elif skew < -0.25:
        direction = "lệch trái"
    else:
        direction = "khá đối xứng"
    compression = values["central_98pct_fraction_of_minmax_span"]
    warning = (
        "Min–Max dễ nén phần lớn dữ liệu vì biên bị chi phối bởi cực trị."
        if compression < 0.5
        else "98% dữ liệu sử dụng phần đáng kể của khoảng Min–Max."
    )
    return (
        f"- **{FEATURES[feature][0]}**: {direction} (skew={skew:.3f}); "
        f"outlier IQR xấp xỉ {100 * values['iqr_outlier_fraction']:.2f}%; {warning}"
    )


def write_report(out: Path, statistics: dict) -> None:
    audit = statistics["input_audit"]
    feature_lines = [interpretation(feature, statistics["features"][feature]) for feature in FEATURES]
    empty_scenarios = sorted({int(Path(path).parts[-3].split("_")[1]) for path in audit["empty_files"]})
    report = f"""# RSSI / RSSI Slope / MAC Retry — scenarios 0001–0081

## Input

- Expected files: {audit['expected_files']}
- Usable files: {audit['usable_files']}
- Rows scanned: {statistics['rows_seen']:,}
- Complete: {audit['complete']}
- Empty scenarios: {', '.join(f'{value:04d}' for value in empty_scenarios) or 'none'}

The missing scenarios are excluded rather than silently treated as zeros.

## Min–Max scaling

Each feature uses one global range over every valid row:

`x_norm = (x - global_min) / (global_max - global_min)`

Exact global constants and distribution statistics are in `statistics.json`.
Normalized per-scenario summaries are in `per_scenario_statistics.csv`.
Exact histogram counts with both raw and normalized bin edges are in `histogram_bins.csv`.

## Distribution notes

{chr(10).join(feature_lines)}

Quantiles and boxplots use a deterministic 1/{SAMPLE_STRIDE} sample. Counts, min, max,
mean, standard deviation, skewness, and histogram bins use all valid rows.
"""
    atomic_text(out / "REPORT.md", report)


def main() -> int:
    args = parse_args()
    if not (1 <= args.scenario_start <= args.scenario_end and args.seeds > 0):
        raise SystemExit("Invalid scenario range or seed count")
    args.out.mkdir(parents=True, exist_ok=True)
    scenario_ids = list(range(args.scenario_start, args.scenario_end + 1))
    inputs, audit = discover_inputs(args)
    atomic_text(args.out / "input_audit.json", json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    if not inputs:
        raise SystemExit("No usable rows.csv files found")
    print(
        f"Inputs: {len(inputs)}/{audit['expected_files']} usable; "
        f"{len(audit['empty_files'])} empty; {len(audit['missing_files'])} missing",
        flush=True,
    )
    global_results, per_scenario, rows_seen = first_pass(inputs, scenario_ids)
    edges, counts, outliers, endpoint_checks = second_pass(inputs, global_results)
    statistics = write_statistics(
        args.out,
        args,
        audit,
        rows_seen,
        global_results,
        per_scenario,
        edges,
        counts,
        outliers,
        endpoint_checks,
    )
    plot_histograms(args.out, global_results, edges, counts, endpoint_checks)
    plot_boxplots(args.out, scenario_ids, per_scenario, global_results)
    write_report(args.out, statistics)
    print(f"Done: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
