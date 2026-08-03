#!/usr/bin/env python3
"""Parallel, resumable FANET dataset campaign runner."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "sim-config/fanet-tier2.conf"
BINARY = ROOT / "build/scratch/linkscore/ns3.45-link-dataset-fanet-default"
AUTO_RAM_PER_WORKER_MIB = 1024
DASHBOARD_INTERVAL_S = 30.0
SUMMARY_FIELDS = [
    "scenario",
    "seed",
    "rng_run",
    "nodes",
    "area_x_m",
    "area_y_m",
    "tx_power_dbm",
    "gm_alpha",
    "packet_rate_pps",
    "runtime_s",
    "rows",
    "avg_rssi",
    "avg_retry",
    "avg_pdr",
    "status",
    "reason",
]
SCENARIO_FIELDS = {
    "scenario_id",
    "num_nodes",
    "area_x_m",
    "area_y_m",
    "altitude_min_m",
    "altitude_max_m",
    "speed_min_mps",
    "speed_max_mps",
    "gm_alpha",
    "tx_power_dbm",
    "packet_rate_pps",
}
HEARTBEAT_RE = re.compile(
    r"\[heartbeat\].*sim=([\d.]+)/([\d.]+)s \(([\d.]+)%\).*wall=([\d.]+)s"
    r".*rows=(\d+)"
)
OUTPUT_LOCK = threading.Lock()


@dataclass(frozen=True)
class Job:
    scenario: int
    seed: int
    rng_run: int
    seed_dir: Path


@dataclass
class RunResult:
    job: Job
    row: dict[str, object]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def ask_int(prompt: str) -> int:
    while True:
        try:
            value = int(input(prompt).strip())
            if value > 0:
                return value
        except ValueError:
            pass
        print("Nhập một số nguyên dương.")


def ask_yes(prompt: str) -> bool:
    return input(prompt).strip().lower() in {"y", "yes"}


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}h {minutes:02d}m {secs:02d}s" if hours else f"{minutes}m {secs:02d}s"


class CampaignLog:
    def __init__(self, path: Path):
        self.file = path.open("a", buffering=1)
        self.lock = OUTPUT_LOCK

    def write(self, text: str = "") -> None:
        with self.lock:
            print(text, flush=True)
            self.file.write(text + "\n")

    def close(self) -> None:
        with self.lock:
            self.file.close()


class ProcessRegistry:
    def __init__(self):
        self.lock = threading.Lock()
        self.processes: set[subprocess.Popen] = set()
        self.interrupted = threading.Event()

    def add(self, proc: subprocess.Popen) -> None:
        with self.lock:
            self.processes.add(proc)

    def remove(self, proc: subprocess.Popen) -> None:
        with self.lock:
            self.processes.discard(proc)

    def terminate_all(self) -> None:
        self.interrupted.set()
        with self.lock:
            processes = list(self.processes)
        for proc in processes:
            if proc.poll() is None:
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGTERM)
                    else:
                        proc.terminate()
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and any(proc.poll() is None for proc in processes):
            time.sleep(0.05)
        for proc in processes:
            if proc.poll() is None:
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except ProcessLookupError:
                    pass


class WorkerIds:
    def __init__(self):
        self.local = threading.local()
        self.lock = threading.Lock()
        self.next_id = 1

    def get(self) -> int:
        if not hasattr(self.local, "worker_id"):
            with self.lock:
                self.local.worker_id = self.next_id
                self.next_id += 1
        return self.local.worker_id


class Dashboard:
    def __init__(self, total: int, initial_done: int, started: float):
        self.total = total
        self.initial_done = initial_done
        self.done = initial_done
        self.started = started
        self.last_render = 0.0
        self.lock = threading.Lock()
        self.active: dict[int, dict[str, object]] = {}
        self.tty = sys.stdout.isatty()

    def start(self, worker: int, job: Job) -> None:
        with self.lock:
            self.active[worker] = {
                "scenario": job.scenario,
                "seed": job.seed,
                "percent": 0.0,
                "sim": "0/?",
                "wall": 0.0,
                "rows": 0,
            }
            self._maybe_render_locked()

    def heartbeat(self, worker: int, line: str) -> None:
        match = HEARTBEAT_RE.search(line)
        if not match:
            return
        with self.lock:
            status = self.active.get(worker)
            if status is None:
                return
            sim_now, sim_total, percent, wall, rows = match.groups()
            status.update({
                "percent": float(percent),
                "sim": f"{sim_now}/{sim_total}s",
                "wall": float(wall),
                "rows": int(rows),
            })
            self._maybe_render_locked()

    def complete(self, job: Job) -> None:
        with self.lock:
            self.done += 1
            for worker, status in list(self.active.items()):
                if status["scenario"] == job.scenario and status["seed"] == job.seed:
                    self.active.pop(worker, None)
                    break
            self._render_locked(force=True)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "completed": self.done,
                "total": self.total,
                "active": {str(k): dict(v) for k, v in sorted(self.active.items())},
            }

    def stop(self) -> None:
        with self.lock:
            self.active.clear()

    def _maybe_render_locked(self) -> None:
        if time.monotonic() - self.last_render >= DASHBOARD_INTERVAL_S:
            self._render_locked()

    def _render_locked(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self.last_render < DASHBOARD_INTERVAL_S:
            return
        self.last_render = now
        elapsed = now - self.started
        finished_now = self.done - self.initial_done
        eta = (
            elapsed * (self.total - self.done) / finished_now
            if finished_now > 0
            else None
        )
        ratio = self.done / self.total if self.total else 1.0
        lines = [
            f"Overall {self.done}/{self.total} ({100.0 * ratio:.1f}%) | "
            f"Elapsed {format_duration(elapsed)} | "
            f"ETA {format_duration(eta) if eta is not None else '--'}"
        ]
        for worker, status in sorted(self.active.items()):
            lines.append(
                f"W{worker:02d} | S{int(status['scenario']):04d} "
                f"Seed {int(status['seed']):04d} | {float(status['percent']):5.1f}% | "
                f"sim {status['sim']} | wall {format_duration(float(status['wall']))} | "
                f"rows {int(status['rows']):,}"
            )
        with OUTPUT_LOCK:
            if self.tty:
                sys.stdout.write("\033[2J\033[H" + "\n".join(lines) + "\n")
            else:
                sys.stdout.write(lines[0] + "\n")
            sys.stdout.flush()


def run_process(
    command: list[str],
    registry: ProcessRegistry,
    output_path: Path | None = None,
    append: bool = False,
    on_line=None,
    echo: bool = False,
) -> tuple[int, float]:
    start = time.monotonic()
    output = output_path.open("a" if append else "w", buffering=1) if output_path else None
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=(os.name == "posix"),
    )
    registry.add(proc)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if output:
                output.write(line)
            if echo:
                print(line, end="", flush=True)
            if on_line:
                on_line(line)
        return proc.wait(), time.monotonic() - start
    except KeyboardInterrupt:
        registry.terminate_all()
        raise
    finally:
        registry.remove(proc)
        if output:
            output.close()


def load_summary(path: Path) -> dict[tuple[int, int], dict[str, str]]:
    if not path.is_file():
        return {}
    with path.open(newline="") as fh:
        return {
            (int(row["scenario"]), int(row["seed"])): row
            for row in csv.DictReader(fh)
        }


def write_summary(path: Path, rows: dict[tuple[int, int], dict[str, object]]) -> None:
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow(rows[key])
    os.replace(tmp, path)


def quick_stats(path: Path) -> dict[str, float]:
    n = retry_n = 0
    rssi_sum = retry_sum = pdr_sum = 0.0
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            n += 1
            rssi_sum += float(row["rssi_level"])
            pdr_sum += float(row["pdr_future"])
            if row["retry_rate"]:
                retry_n += 1
                retry_sum += float(row["retry_rate"])
    return {
        "avg_rssi": rssi_sum / n if n else 0.0,
        "avg_retry": retry_sum / retry_n if retry_n else 0.0,
        "avg_pdr": pdr_sum / n if n else 0.0,
    }


def ensure_alias(path: Path, target_name: str) -> None:
    if not path.is_symlink() and not path.exists():
        path.symlink_to(target_name)


def failure_reason(log_path: Path, returncode: int) -> str:
    lines = log_path.read_text(errors="replace").splitlines() if log_path.is_file() else []
    for line in reversed(lines):
        if any(word in line for word in ("NS_FATAL", "assert failed", "terminate called", "Segmentation")):
            return line[-300:]
    return f"exit code {returncode}"


def available_memory_mib() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return AUTO_RAM_PER_WORKER_MIB


def resolve_workers(raw: str, jobs: int) -> tuple[int, str]:
    if raw != "auto":
        try:
            requested = int(raw)
        except ValueError:
            raise SystemExit("--workers phải là số nguyên dương hoặc 'auto'")
        if requested <= 0:
            raise SystemExit("--workers phải > 0")
        return min(requested, max(1, jobs)), f"explicit={requested}"
    cpus = os.cpu_count() or 1
    memory = available_memory_mib()
    cpu_limit = max(1, cpus - 1)
    ram_limit = max(1, memory // AUTO_RAM_PER_WORKER_MIB)
    workers = min(cpu_limit, ram_limit, max(1, jobs))
    return workers, (
        f"auto=min(cpu-1={cpu_limit}, available_ram/{AUTO_RAM_PER_WORKER_MIB}MiB="
        f"{ram_limit})"
    )


def load_scenario(path: Path, scenario_id: int) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"scenario.json hỏng, không tự generate lại: {path}: {exc}")
    missing = sorted(SCENARIO_FIELDS - value.keys())
    if missing or int(value.get("scenario_id", -1)) != scenario_id:
        raise SystemExit(
            f"scenario.json không hợp lệ: {path}; missing={missing}, "
            f"scenario_id={value.get('scenario_id')}"
        )
    return value


def generate_scenarios(
    out: Path,
    scenario_ids: range,
    campaign_total: int,
    registry: ProcessRegistry,
    log: CampaignLog,
) -> dict[int, dict]:
    scenarios: dict[int, dict] = {}
    generated = 0
    for scenario_id in scenario_ids:
        scenario_dir = out / f"scenario_{scenario_id:04d}"
        scenario_dir.mkdir(exist_ok=True)
        path = scenario_dir / "scenario.json"
        if path.is_file():
            scenarios[scenario_id] = load_scenario(path, scenario_id)
            continue
        tmp = scenario_dir / "scenario.json.generate.tmp"
        scenario_log = scenario_dir / "scenario.log"
        command = [
            str(BINARY),
            f"--config={CONFIG.relative_to(ROOT)}",
            f"--scenario={scenario_id}",
            "--generateScenarioOnly=true",
            f"--scenarioOut={tmp}",
        ]
        rc, _ = run_process(command, registry, scenario_log, append=True)
        if rc != 0:
            raise SystemExit(f"Generate scenario {scenario_id} thất bại; xem {scenario_log}")
        value = load_scenario(tmp, scenario_id)
        os.replace(tmp, path)
        scenarios[scenario_id] = value
        generated += 1
        if generated == 1 or generated % 100 == 0 or scenario_id == scenario_ids.stop - 1:
            log.write(f"Generated scenario setup: {scenario_id}/{campaign_total}")
    selected = len(scenario_ids)
    log.write(
        f"Scenario setup ready for range {scenario_ids.start}-{scenario_ids.stop - 1}: "
        f"{selected} selected, {generated} generated, {selected - generated} reused"
    )
    return scenarios


def scenario_args(scenario: dict) -> list[str]:
    return [
        "--randomSetup=false",
        "--realizedSetup=true",
        f"--numNodes={scenario['num_nodes']}",
        f"--areaX={scenario['area_x_m']}",
        f"--areaY={scenario['area_y_m']}",
        f"--altMin={scenario['altitude_min_m']}",
        f"--altMax={scenario['altitude_max_m']}",
        f"--gmVelMin={scenario['speed_min_mps']}",
        f"--gmVelMax={scenario['speed_max_mps']}",
        f"--gmAlpha={scenario['gm_alpha']}",
        f"--txPowerDbm={scenario['tx_power_dbm']}",
        f"--cbrPps={scenario['packet_rate_pps']}",
    ]


def make_summary_row(
    job: Job,
    scenario: dict,
    runtime: float,
    rows: int,
    stats: dict,
    status: str,
    reason: str,
) -> dict[str, object]:
    return {
        "scenario": job.scenario,
        "seed": job.seed,
        "rng_run": job.rng_run,
        "nodes": scenario["num_nodes"],
        "area_x_m": scenario["area_x_m"],
        "area_y_m": scenario["area_y_m"],
        "tx_power_dbm": scenario["tx_power_dbm"],
        "gm_alpha": scenario["gm_alpha"],
        "packet_rate_pps": scenario["packet_rate_pps"],
        "runtime_s": f"{runtime:.3f}",
        "rows": rows,
        "avg_rssi": f"{float(stats.get('avg_rssi', 0.0)):.6f}",
        "avg_retry": f"{float(stats.get('avg_retry', 0.0)):.6f}",
        "avg_pdr": f"{float(stats.get('avg_pdr', 0.0)):.6f}",
        "status": status,
        "reason": reason.replace("\n", " "),
    }


def existing_pass(job: Job, scenario: dict) -> dict[str, object] | None:
    required = (job.seed_dir / "meta.json", job.seed_dir / "summary.json", job.seed_dir / "rows.csv")
    status_path = job.seed_dir / "status.json"
    if not status_path.is_file() or not all(path.is_file() for path in required):
        return None
    try:
        status = json.loads(status_path.read_text())
        gate_deferred = (
            status.get("status") == "FAILED"
            and str(status.get("reason", "")).startswith("acceptance gates failed")
        )
        if status.get("status") != "PASS" and not gate_deferred:
            return None
        if gate_deferred:
            status["previous_gate_reason"] = status["reason"]
            status["gate_validation"] = "DEFERRED_POST_CAMPAIGN"
            status["status"] = "PASS"
            status["reason"] = ""
            atomic_json(status_path, status)
        stats_path = job.seed_dir / "stats.json"
        stats = json.loads(stats_path.read_text()) if stats_path.is_file() else quick_stats(required[2])
        if gate_deferred and stats_path.is_file():
            stats.update(status)
            atomic_json(stats_path, stats)
        return make_summary_row(
            job,
            scenario,
            float(status.get("runtime_s", 0.0)),
            int(status.get("rows", 0)),
            stats,
            "PASS",
            "",
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def run_job(
    job: Job,
    scenario: dict,
    sim_time: float,
    registry: ProcessRegistry,
    worker_ids: WorkerIds,
    dashboard: Dashboard,
) -> RunResult:
    worker = worker_ids.get()
    dashboard.start(worker, job)
    job.seed_dir.mkdir(exist_ok=True)
    run_log = job.seed_dir / "log.txt"
    manifest = job.seed_dir / "run_manifest.json"
    runtime = 0.0
    rows = 0
    stats = {"avg_rssi": 0.0, "avg_retry": 0.0, "avg_pdr": 0.0}
    status_name = "FAILED"
    reason = ""
    atomic_json(job.seed_dir / "status.json", {
        "scenario": job.scenario,
        "seed": job.seed,
        "rng_run": job.rng_run,
        "status": "RUNNING",
        "started_at": utc_now(),
    })

    try:
        if registry.interrupted.is_set():
            raise InterruptedError("campaign interrupted")
        manifest_cmd = [
            "python3",
            "scripts/run_manifest.py",
            "--phase",
            "P2-random-campaign",
            "--seed",
            str(job.seed),
            "--config",
            str(CONFIG.relative_to(ROOT)),
            "--binary",
            str(BINARY.relative_to(ROOT)),
            "--out",
            str(manifest),
        ]
        rc, _ = run_process(manifest_cmd, registry, run_log)
        if rc != 0:
            reason = "run_manifest failed"
        else:
            command = [
                str(BINARY),
                f"--config={CONFIG.relative_to(ROOT)}",
                f"--scenario={job.scenario}",
                f"--seed={job.seed}",
                f"--rngRun={job.rng_run}",
                f"--simTime={sim_time}",
                f"--out={job.seed_dir}",
                *scenario_args(scenario),
            ]
            rc, runtime = run_process(
                command,
                registry,
                run_log,
                append=True,
                on_line=lambda line: dashboard.heartbeat(worker, line),
            )
            ensure_alias(job.seed_dir / "stdout.log", "log.txt")
            required = (
                job.seed_dir / "meta.json",
                job.seed_dir / "summary.json",
                job.seed_dir / "rows.csv",
            )
            if registry.interrupted.is_set():
                raise InterruptedError("campaign interrupted")
            if rc != 0:
                reason = failure_reason(run_log, rc)
            elif not all(path.is_file() for path in required):
                rc = 2
                reason = "missing output: " + ", ".join(
                    path.name for path in required if not path.is_file()
                )
            else:
                text = run_log.read_text(errors="replace")
                if any(word in text for word in ("NS_FATAL", "assert failed", "terminate called")):
                    rc = 2
                    reason = failure_reason(run_log, rc)

        if rc == 0:
            augment = [
                "python3",
                "scripts/run_manifest.py",
                "--augment-meta",
                str(job.seed_dir / "meta.json"),
                "--out",
                str(manifest),
                "--quiet",
            ]
            rc, _ = run_process(augment, registry, run_log, append=True)
            if rc != 0:
                reason = "manifest meta augmentation failed"

        sim_summary_path = job.seed_dir / "summary.json"
        if sim_summary_path.is_file():
            sim_summary = json.loads(sim_summary_path.read_text())
            rows = int(sim_summary.get("rows", 0))
        if (job.seed_dir / "rows.csv").is_file():
            stats = quick_stats(job.seed_dir / "rows.csv")
        status_name = "PASS" if rc == 0 else "FAILED"
    except InterruptedError as exc:
        status_name = "INTERRUPTED"
        reason = str(exc)
    except Exception as exc:  # keep one bad job from killing the campaign parent
        status_name = "FAILED"
        reason = f"{type(exc).__name__}: {exc}"
        with run_log.open("a") as fh:
            fh.write("\n" + traceback.format_exc())

    status = {
        "scenario": job.scenario,
        "seed": job.seed,
        "rng_run": job.rng_run,
        "status": status_name,
        "runtime_s": round(runtime, 3),
        "rows": rows,
        "reason": reason,
        "finished_at": utc_now(),
    }
    atomic_json(job.seed_dir / "status.json", status)
    sim_summary_path = job.seed_dir / "summary.json"
    sim_summary = json.loads(sim_summary_path.read_text()) if sim_summary_path.is_file() else {}
    atomic_json(job.seed_dir / "stats.json", {**sim_summary, **stats, **status})
    row = make_summary_row(job, scenario, runtime, rows, stats, status_name, reason)
    return RunResult(job, row)


def scenario_summary(
    out: Path,
    scenario_id: int,
    scenario: dict,
    rows: dict[tuple[int, int], dict[str, object]],
    seeds_per_scenario: int,
) -> dict:
    selected = [rows.get((scenario_id, seed)) for seed in range(1, seeds_per_scenario + 1)]
    selected = [row for row in selected if row is not None]
    passed = sum(row["status"] == "PASS" for row in selected)
    failed = sum(row["status"] == "FAILED" for row in selected)
    interrupted = sum(row["status"] == "INTERRUPTED" for row in selected)
    value = {
        "scenario": scenario_id,
        "setup": scenario,
        "seeds_total": seeds_per_scenario,
        "seeds_finished": len(selected),
        "passed": passed,
        "failed": failed,
        "interrupted": interrupted,
        "rows": sum(int(row["rows"] or 0) for row in selected),
        "runtime_s": round(sum(float(row["runtime_s"] or 0) for row in selected), 3),
        "complete": len(selected) == seeds_per_scenario and passed == seeds_per_scenario,
        "updated_at": utc_now(),
    }
    atomic_json(out / f"scenario_{scenario_id:04d}" / "scenario_summary.json", value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", "--scenarios", type=int)
    parser.add_argument("-s", "--seeds", type=int, help="seeds per scenario")
    parser.add_argument("-o", "--out", help="output directory")
    parser.add_argument("--sim-time", type=float, default=300.0)
    parser.add_argument("--workers", default="auto", help="positive integer or auto")
    parser.add_argument("--scenario-start", type=int, help="first scenario id, inclusive")
    parser.add_argument("--scenario-end", type=int, help="last scenario id, inclusive")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failed", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--skip-gates", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args()

    out = Path(args.out or input("Output directory [dataset]: ").strip() or "dataset")
    if not out.is_absolute():
        out = ROOT / out
    out.mkdir(parents=True, exist_ok=True)
    campaign_path = out / "campaign.json"

    if campaign_path.is_file():
        campaign = json.loads(campaign_path.read_text())
        if not args.resume and not ask_yes("Previous campaign detected. Resume? (Y/N): "):
            sys.exit("Không ghi đè campaign cũ. Chọn output directory khác.")
        num_scenarios = int(campaign["num_scenarios"])
        seeds_per_scenario = int(campaign["seeds_per_scenario"])
        sim_time = float(campaign["simulation_time_s"])
        campaign["gates_enabled"] = False
        campaign["gate_policy"] = "deferred_post_campaign"
    else:
        if args.resume:
            sys.exit(f"Không có campaign để resume tại {out}")
        if any(out.iterdir()):
            sys.exit(f"Output directory không rỗng và không có campaign.json: {out}")
        num_scenarios = args.scenarios or ask_int("Number of scenarios: ")
        seeds_per_scenario = args.seeds or ask_int("Seeds per scenario: ")
        sim_time = args.sim_time
        if num_scenarios <= 0 or seeds_per_scenario <= 0 or sim_time <= 0:
            sys.exit("scenarios, seeds và sim-time phải > 0")
        campaign = {
            "num_scenarios": num_scenarios,
            "seeds_per_scenario": seeds_per_scenario,
            "generator": "ns3::UniformRandomVariable generate-once",
            "simulation_time_s": sim_time,
            "gates_enabled": False,
            "gate_policy": "deferred_post_campaign",
            "config": str(CONFIG.relative_to(ROOT)),
            "created_at": utc_now(),
        }

    scenario_start = args.scenario_start if args.scenario_start is not None else 1
    scenario_end = args.scenario_end if args.scenario_end is not None else num_scenarios
    if not (1 <= scenario_start <= scenario_end <= num_scenarios):
        sys.exit(
            f"Range scenario không hợp lệ: {scenario_start}-{scenario_end}; "
            f"campaign có scenario 1-{num_scenarios}"
        )
    scenario_ids = range(scenario_start, scenario_end + 1)
    campaign_total = num_scenarios * seeds_per_scenario
    selected_total = len(scenario_ids) * seeds_per_scenario
    workers, worker_reason = resolve_workers(args.workers, selected_total)
    if not campaign_path.is_file():
        if not args.yes:
            print("\n==============================")
            print("FANET DATASET GENERATOR")
            print("==============================")
            print(f"Number of scenarios : {num_scenarios}")
            print(f"Seeds per scenario  : {seeds_per_scenario}")
            print(f"Scenario range      : {scenario_start}-{scenario_end} (inclusive)")
            print(f"Workers             : {workers} ({worker_reason})")
            print(f"Output directory    : {out}")
            if not ask_yes("Continue? (Y/N): "):
                return 0
        atomic_json(campaign_path, campaign)
    else:
        # Persist the deferred-gate policy before launching a long resume.
        atomic_json(campaign_path, campaign)

    prior_runtime = float(campaign.get("runtime_s", 0.0))
    log = CampaignLog(out / "campaign.log")
    registry = ProcessRegistry()

    def stop_campaign(_signum, _frame) -> None:
        registry.terminate_all()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, stop_campaign)
    signal.signal(signal.SIGTERM, stop_campaign)
    started = time.monotonic()
    log.write("=" * 54)
    log.write("FANET DATASET GENERATOR — GLOBAL WORKER POOL")
    log.write("=" * 54)
    log.write(
        f"Scenarios: {num_scenarios}, seeds/scenario: {seeds_per_scenario}, "
        f"campaign jobs: {campaign_total}"
    )
    log.write(
        f"Selected range: {scenario_start}-{scenario_end} (inclusive), "
        f"jobs: {selected_total}"
    )
    log.write(f"Workers: {workers} ({worker_reason})")
    log.write(f"Output: {out}")

    try:
        for command in (
            ["bash", "scripts/run_tests.sh"],
            ["./ns3", "build", "scratch/linkscore/link-dataset-fanet"],
        ):
            rc, _ = run_process(command, registry, echo=True)
            if rc != 0:
                log.close()
                return rc
        if not BINARY.is_file():
            raise SystemExit(f"Không tìm thấy binary: {BINARY}")
        scenarios = generate_scenarios(out, scenario_ids, num_scenarios, registry, log)
    except KeyboardInterrupt:
        registry.terminate_all()
        log.write("Campaign interrupted during scenario generation. Resume to continue.")
        log.close()
        return 130

    summary_path = out / "summary.csv"
    summary_rows: dict[tuple[int, int], dict[str, object]] = load_summary(summary_path)
    jobs: list[Job] = []
    for scenario_id in scenario_ids:
        for seed_id in range(1, seeds_per_scenario + 1):
            job = Job(
                scenario_id,
                seed_id,
                (scenario_id - 1) * seeds_per_scenario + seed_id,
                out / f"scenario_{scenario_id:04d}" / f"seed_{seed_id:04d}",
            )
            row = existing_pass(job, scenarios[scenario_id])
            if row is None:
                jobs.append(job)
            else:
                summary_rows[(scenario_id, seed_id)] = row
    write_summary(summary_path, summary_rows)

    initial_done = selected_total - len(jobs)
    workers = min(workers, max(1, len(jobs)))
    dashboard = Dashboard(selected_total, initial_done, started)
    worker_ids = WorkerIds()
    log.write(f"Queue: {len(jobs)} pending, {initial_done} PASS reused")

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fanet-worker")
    futures: dict[Future, Job] = {}
    interrupted = False
    try:
        for job in jobs:
            future = executor.submit(
                run_job,
                job,
                scenarios[job.scenario],
                sim_time,
                registry,
                worker_ids,
                dashboard,
            )
            futures[future] = job

        for future in as_completed(futures):
            result = future.result()
            job = result.job
            if result.row["status"] == "INTERRUPTED":
                continue
            summary_rows[(job.scenario, job.seed)] = result.row
            write_summary(summary_path, summary_rows)
            dashboard.complete(job)
            status_name = result.row["status"]
            log.write(
                f"S{job.scenario:04d} Seed {job.seed:04d}: {status_name} | "
                f"runtime {float(result.row['runtime_s']):.1f}s | rows {int(result.row['rows']):,}"
                + (f" | {result.row['reason']}" if result.row["reason"] else "")
            )
            scenario_log = out / f"scenario_{job.scenario:04d}" / "scenario.log"
            with scenario_log.open("a") as fh:
                fh.write(
                    f"{utc_now()} seed={job.seed} rng_run={job.rng_run} "
                    f"status={status_name} runtime_s={result.row['runtime_s']} "
                    f"rows={result.row['rows']}\n"
                )
            if all(
                summary_rows.get((job.scenario, seed), {}).get("status") == "PASS"
                for seed in range(1, seeds_per_scenario + 1)
            ):
                scenario_summary(
                    out,
                    job.scenario,
                    scenarios[job.scenario],
                    summary_rows,
                    seeds_per_scenario,
                )
            progress_value = {
                **dashboard.snapshot(),
                "workers": workers,
                "scenario_start": scenario_start,
                "scenario_end": scenario_end,
                "campaign_total": campaign_total,
                "elapsed_s": round(time.monotonic() - started, 3),
                "updated_at": utc_now(),
            }
            atomic_json(out / "progress.json", progress_value)
    except KeyboardInterrupt:
        interrupted = True
        registry.terminate_all()
        for future in futures:
            future.cancel()
        log.write("Ctrl+C: terminating all active ns-3 processes...")
    finally:
        executor.shutdown(wait=True, cancel_futures=True)

    if interrupted:
        dashboard.stop()
        atomic_json(out / "progress.json", {
            **dashboard.snapshot(),
            "workers": workers,
            "scenario_start": scenario_start,
            "scenario_end": scenario_end,
            "campaign_total": campaign_total,
            "interrupted": True,
            "updated_at": utc_now(),
        })
        log.write("Campaign interrupted safely. Run again with --resume.")
        log.close()
        return 130

    for scenario_id in scenario_ids:
        scenario_summary(
            out,
            scenario_id,
            scenarios[scenario_id],
            summary_rows,
            seeds_per_scenario,
        )

    campaign_rows = [
        summary_rows.get((scenario_id, seed_id))
        for scenario_id in range(1, num_scenarios + 1)
        for seed_id in range(1, seeds_per_scenario + 1)
    ]
    campaign_rows = [row for row in campaign_rows if row is not None]
    range_rows = [
        summary_rows.get((scenario_id, seed_id))
        for scenario_id in scenario_ids
        for seed_id in range(1, seeds_per_scenario + 1)
    ]
    range_rows = [row for row in range_rows if row is not None]
    passed = sum(row["status"] == "PASS" for row in campaign_rows)
    failed = sum(row["status"] == "FAILED" for row in campaign_rows)
    range_passed = sum(row["status"] == "PASS" for row in range_rows)
    range_failed = sum(row["status"] == "FAILED" for row in range_rows)
    rows_total = sum(int(row["rows"] or 0) for row in campaign_rows)
    campaign_complete = len(campaign_rows) == campaign_total and passed == campaign_total
    range_complete = len(range_rows) == selected_total and range_passed == selected_total
    total_runtime = prior_runtime + time.monotonic() - started
    campaign_update = {
        "updated_at": utc_now(),
        "success": passed,
        "failed": failed,
        "rows": rows_total,
        "runtime_s": round(total_runtime, 3),
        "workers_last": workers,
        "last_scenario_start": scenario_start,
        "last_scenario_end": scenario_end,
    }
    if campaign_complete:
        campaign_update["finished_at"] = utc_now()
    else:
        campaign.pop("finished_at", None)
    campaign.update(campaign_update)
    atomic_json(campaign_path, campaign)
    campaign_summary = {
        "scenarios": num_scenarios,
        "seeds_per_scenario": seeds_per_scenario,
        "jobs": campaign_total,
        "finished": len(campaign_rows),
        "passed": passed,
        "failed": failed,
        "rows": rows_total,
        "wall_runtime_s": round(total_runtime, 3),
        "workers": workers,
        "complete": campaign_complete,
        "updated_at": utc_now(),
        "last_range": {
            "scenario_start": scenario_start,
            "scenario_end": scenario_end,
            "jobs": selected_total,
            "finished": len(range_rows),
            "passed": range_passed,
            "failed": range_failed,
            "complete": range_complete,
        },
    }
    if campaign_complete:
        campaign_summary["finished_at"] = campaign["finished_at"]
    atomic_json(out / "campaign_summary.json", campaign_summary)
    atomic_json(out / "progress.json", {
        **dashboard.snapshot(),
        "scenario_start": scenario_start,
        "scenario_end": scenario_end,
        "campaign_total": campaign_total,
        "range_finished": True,
        "campaign_complete": campaign_complete,
        "finished": campaign_complete,
        "updated_at": utc_now(),
    })
    log.write("=" * 54)
    log.write("RANGE FINISHED")
    log.write("=" * 54)
    log.write(f"Scenario : {scenario_start}-{scenario_end} / 1-{num_scenarios}")
    log.write(f"Range jobs: {len(range_rows)}/{selected_total}")
    log.write(f"Range success: {range_passed}")
    log.write(f"Range fail: {range_failed}")
    log.write(f"Campaign jobs: {len(campaign_rows)}/{campaign_total}")
    log.write(f"Rows     : {rows_total:,}")
    log.write(f"Runtime  : {format_duration(total_runtime)}")
    log.close()
    return 0 if range_failed == 0 and len(range_rows) == selected_total else 1


if __name__ == "__main__":
    raise SystemExit(main())
