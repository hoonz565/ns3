#!/usr/bin/env python3
"""Cổng nghiệm thu P2 — chạy trên output của link-dataset-fanet (CLAUDE.md
"Acceptance gate", ngưỡng đọc từ sim-config, không hardcode).

    python3 scripts/check_gates.py data/smoke/p2-harness/seed-1 \
        [--config sim-config/fanet-tier2.conf]

Exit 0 nếu mọi cổng đạt, 1 nếu có cổng trượt, 2 nếu thiếu file hoặc vỡ bất
biến registry/config. Một run trượt cổng là run KHÔNG DÙNG ĐƯỢC, không phải
run yếu — dừng và báo cáo, đừng nới ngưỡng (WORKFLOW.md quy tắc vận hành 7).

Ngoài các cổng, in thêm những con số P2 phải nhìn trước khi duyệt batch:
  - degree so với 6.14 của P1 (cùng định nghĩa: tỉ lệ nhận beacon >= 0.5 / 5 s)
  - bảng airtime tách nguồn beacon/probe/cbr/olsr — con số quyết định mức tải
  - queue drop theo nguyên nhân + phân bố trễ queue (MaxDelay có đang nắn
    traffic không: p99 gần cap là confound)
  - corr(retry_rate, rssi_level) toàn cục và theo bin khoảng cách (quy tắc 13:
    gần 0 khi thiếu tải lẫn khi bão hoà, âm sâu ở điểm vận hành đúng)
  - các dòng có nhãn nhưng thiếu feature retry (GLM sẽ âm thầm bỏ)

Thuần Python có chủ ý: scipy của hệ thống lệch ABI với numpy 2.x (đã ghi ở
P0), và cổng nghiệm thu không được phép chết vì môi trường.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

P1_DEGREE_REF = 6.14  # reports/P1-config.md, cùng định nghĩa link


def read_conf(paths: list[str]) -> dict[str, str]:
    """key = value, '#' là comment; file sau ghi đè file trước (như sim-config.h)."""
    values: dict[str, str] = {}
    for raw in paths:
        path = Path(raw) if Path(raw).is_absolute() else REPO_ROOT / raw
        if not path.is_file():
            sys.exit(f"[check_gates] không mở được config: {raw}")
        for line in path.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if "=" not in line:
                sys.exit(f"[check_gates] dòng không phải key = value trong {raw}: {line}")
            key, val = (part.strip() for part in line.split("=", 1))
            values[key] = val
    return values


def parse_unused_keys(stdout_text: str) -> set[str] | None:
    """Tập key binary khai 'co trong registry nhung scenario nay KHONG doc'.

    Định dạng trong stdout.log (link-dataset-fanet):
        sim-config: CANH BAO 10 key ... KHONG doc:
           gateDegreeMin, gateLossMax, ..., seedsTrain
    Trả về None nếu không thấy dòng cảnh báo (scenario đọc hết mọi key).
    """
    lines = stdout_text.splitlines()
    for i, line in enumerate(lines):
        if "KHONG doc" in line and "registry" in line:
            match = re.search(r"CANH BAO (\d+) key", line)
            if match is None or i + 1 >= len(lines):
                raise ValueError("dòng registry của binary sai định dạng")
            keys = {k.strip() for k in lines[i + 1].split(",") if k.strip()}
            if len(keys) != int(match.group(1)):
                raise ValueError(
                    f"binary khai {match.group(1)} key nhưng in {len(keys)} key"
                )
            return keys
    return None


def median(xs: list[float]) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def percentile(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    return s[int(q * (len(s) - 1))]


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def ranks(xs: list[float]) -> list[float]:
    """Hạng trung bình khi hoà — cần cho Spearman vì retry_rate đầy giá trị 0."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = 0.5 * (i + j) + 1.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return float("nan")
    return pearson(ranks(xs), ranks(ys))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir", help="thư mục chứa rows.csv + summary.json")
    ap.add_argument(
        "--config",
        action="append",
        default=[],
        help="file sim-config chứa ngưỡng gate* (lặp lại được; mặc định "
        "sim-config/fanet-tier2.conf)",
    )
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = REPO_ROOT / run_dir
    rows_path = run_dir / "rows.csv"
    summary_path = run_dir / "summary.json"
    if not rows_path.is_file() or not summary_path.is_file():
        print(f"[check_gates] thiếu {rows_path} hoặc {summary_path}", file=sys.stderr)
        return 2

    conf = read_conf(args.config or ["sim-config/fanet-tier2.conf"])
    gate_degree_min = float(conf["gateDegreeMin"])
    gate_retry_min = float(conf["gateRetryMin"])
    gate_mid_min = float(conf["gateMidMin"])
    gate_loss_max = float(conf["gateLossMax"])
    gate_pinned_max = float(conf["gatePinnedMax"])
    # Cổng bão hoà chính (P2 run 3): q gộp trên link GẦN. Vùng gần suy từ
    # R(0.5) đo được chứ không phải hằng số — ngưỡng 75% cũ sai chính vì nó
    # là hằng số thừa kế từ cấu hình radio khác. 0.64·R½ = 400 m tại 625 m.
    near_max_m = 0.64 * float(conf["rHalfM"])
    gate_near_q_max = float(conf["gateNearQMax"])

    # --- Gương registry (P5a) — bảo vệ config_sim_sha256 khỏi bảo trì tay.
    # Quy tắc loại trừ của hash mô phỏng (run_manifest._conf_is_analysis_key:
    # gate*/seeds*/rHalfM) phải chọn ra từ conf ĐÚNG tập key mà binary khai
    # "không đọc" trong stdout.log. Lệch chiều nào cũng phải DỪNG:
    #   - key phân tích mới không khớp quy tắc -> lọt vào hash mô phỏng,
    #     eval bị kết luận "khác tham số" oan;
    #   - key khớp quy tắc nhưng binary THỰC RA có đọc -> tham số mô phỏng
    #     bị loại khỏi hash, đổi nó mà hash không đổi;
    #   - tham số vật lý nằm trong danh sách "không đọc" -> scenario đang
    #     chạy bằng default, không bằng config (cảnh báo sẵn của binary,
    #     nay thành lỗi cứng).
    from run_manifest import _conf_is_analysis_key  # scripts/ cùng thư mục

    stdout_path = run_dir / "stdout.log"
    if not stdout_path.is_file():
        print("[check_gates] thiếu stdout.log — không thể assert gương registry "
              "của config_sim_sha256, DỪNG", file=sys.stderr)
        return 2
    else:
        try:
            printed = parse_unused_keys(stdout_path.read_text())
        except ValueError as exc:
            print(f"[check_gates] {exc}; DỪNG", file=sys.stderr)
            return 2
        expected = {k for k in conf if _conf_is_analysis_key(k)}
        if printed is None:
            print("[check_gates] stdout.log không có danh sách registry mà "
                  "binary không đọc — không thể assert config_sim_sha256, DỪNG",
                  file=sys.stderr)
            return 2
        elif printed != expected:
            only_bin = sorted(printed - expected)
            only_rule = sorted(expected - printed)
            print("[check_gates] LỆCH GƯƠNG REGISTRY — config_sim_sha256 sẽ "
                  "lệch oan, DỪNG.\n"
                  f"  binary khai không đọc mà quy tắc không loại: {only_bin}\n"
                  f"  quy tắc loại mà binary lại có đọc:           {only_rule}\n"
                  "  Sửa _conf_is_analysis_key trong run_manifest.py hoặc đặt "
                  "lại tên key cho khớp quy ước gate*/seeds*.", file=sys.stderr)
            return 2

    summary = json.loads(summary_path.read_text())

    # ---------------- đọc rows.csv ----------------
    n_rows = 0
    n_retry_pos = 0       # retry_rate > 0
    n_retry_empty = 0     # có nhãn nhưng không có feature retry (GLM bỏ âm thầm)
    n_mid = 0             # 0 < pdr < 1
    n_pinned_hi = 0       # pdr == 1
    n_pinned_lo = 0       # pdr == 0
    n_fails_pos = 0       # fails_future > 0
    n_probe_only = 0      # trials_cbr == 0 (link off-path thuần probe)
    trials_all: list[float] = []
    rssi_all: list[float] = []
    corr_rssi: list[float] = []
    corr_retry: list[float] = []
    by_bin: dict[str, tuple[list[float], list[float]]] = {}
    # q theo bin, TÁCH lớp: [trials_probe, fails_probe, trials_cbr, fails_cbr]
    # — off-path (probe) so với on-path (CBR). Trả lời "link CBR đi qua có
    # tập trung ở bin xa không" (cơ chế min-hop chọn link dài).
    q_bin: dict[str, list[float]] = {}
    near_trials = 0.0
    near_fails = 0.0
    bin_edges = [0, 200, 400, 600, 800, float("inf")]

    def bin_name(dist: float) -> str:
        for lo, hi in zip(bin_edges, bin_edges[1:]):
            if lo <= dist < hi:
                return f"{lo:.0f}-{hi:.0f} m" if hi != float("inf") else f">={lo:.0f} m"
        return "?"

    with rows_path.open() as fh:
        for row in csv.DictReader(fh):
            n_rows += 1
            pdr = float(row["pdr_future"])
            trials_all.append(float(row["trials_future"]))
            rssi_all.append(float(row["rssi_level"]))
            if float(row["trials_cbr"]) == 0:
                n_probe_only += 1
            qb = q_bin.setdefault(bin_name(float(row["dist_m"])), [0.0, 0.0, 0.0, 0.0])
            qb[0] += float(row["trials_probe"])
            qb[1] += float(row["fails_probe"])
            qb[2] += float(row["trials_cbr"])
            qb[3] += float(row["fails_cbr"])
            if float(row["dist_m"]) < near_max_m:
                near_trials += float(row["trials_future"])
                near_fails += float(row["fails_future"])
            if float(row["fails_future"]) > 0:
                n_fails_pos += 1
            if pdr >= 1.0:
                n_pinned_hi += 1
            elif pdr <= 0.0:
                n_pinned_lo += 1
            else:
                n_mid += 1
            retry = row["retry_rate"]
            if retry == "":
                n_retry_empty += 1
            else:
                r = float(retry)
                if r > 0:
                    n_retry_pos += 1
                corr_retry.append(r)
                corr_rssi.append(float(row["rssi_level"]))
                dist = float(row["dist_m"])
                for lo, hi in zip(bin_edges, bin_edges[1:]):
                    if lo <= dist < hi:
                        name = f"{lo:.0f}-{hi:.0f} m" if hi != float("inf") else f">={lo:.0f} m"
                        by_bin.setdefault(name, ([], []))[0].append(r)
                        by_bin[name][1].append(float(row["rssi_level"]))
                        break

    if n_rows == 0:
        print("[check_gates] rows.csv rỗng — harness không sinh dòng nào", file=sys.stderr)
        return 1

    pct = lambda k: 100.0 * k / n_rows
    degree = float(summary["degree_mean"])
    mac_loss = 100.0 * float(summary["mac_loss"])
    pinned = pct(n_pinned_hi + n_pinned_lo)

    # ---------------- bảng cổng ----------------
    near_q = near_fails / near_trials if near_trials else float("nan")
    gates = [
        ("degree trung bình", f">= {gate_degree_min}", f"{degree:.2f}", degree >= gate_degree_min),
        ("% dòng retry_rate > 0", f">= {gate_retry_min}%", f"{pct(n_retry_pos):.1f}%",
         pct(n_retry_pos) >= gate_retry_min),
        ("% dòng 0 < pdr < 1", f">= {gate_mid_min}%", f"{pct(n_mid):.1f}%",
         pct(n_mid) >= gate_mid_min),
        # Cổng bão hoà chính: sập nâng q vùng gần, đuôi cố ý đo không đụng nó.
        (f"q vùng gần (< {near_max_m:.0f} m)", f"<= {gate_near_q_max}", f"{near_q:.3f}",
         near_q <= gate_near_q_max),
        # Lưới sau — chỉ báo SẬP KÊNH, không phải chất lượng dữ liệu: harness
        # không-kiểm-duyệt phải có loss tổng cao (78.3% ở kênh khoẻ).
        ("MAC loss tổng (lưới sập)", f"<= {gate_loss_max}%", f"{mac_loss:.1f}%",
         mac_loss <= gate_loss_max),
        ("% dòng pdr ghim 0/1", f"<= {gate_pinned_max}%", f"{pinned:.1f}%",
         pinned <= gate_pinned_max),
        ("dòng có fails > 0", "> 0", str(n_fails_pos), n_fails_pos > 0),
    ]

    print(f"=== check_gates: {run_dir.relative_to(REPO_ROOT)} ===")
    print(f"{'Chỉ số':<28}{'Ngưỡng':<14}{'Đo được':<12}Đạt")
    ok = True
    for name, thresh, value, passed in gates:
        ok &= passed
        print(f"{name:<28}{thresh:<14}{value:<12}{'✓' if passed else '✗ TRƯỢT'}")

    # ---------------- số phải nhìn, không phải cổng ----------------
    print("\n--- số phải nhìn trước khi duyệt batch ---")
    print(f"rows                      : {n_rows}  (probe-only {pct(n_probe_only):.1f}%)")
    print(f"degree so với P1          : {degree:.2f} / {P1_DEGREE_REF}  "
          f"(lệch {100.0 * (degree - P1_DEGREE_REF) / P1_DEGREE_REF:+.1f}%), "
          f"cô lập {100.0 * float(summary['isolated_frac']):.1f}% node-thời-gian")
    print(f"dòng thiếu retry feature  : {n_retry_empty}  ({pct(n_retry_empty):.1f}% — GLM sẽ bỏ âm thầm)")
    n_low_trials = sum(1 for t in trials_all if t < 5)
    print(f"trials_future p10/p25/p50/p90: {percentile(trials_all, 0.10):.0f} / "
          f"{percentile(trials_all, 0.25):.0f} / {percentile(trials_all, 0.50):.0f} / "
          f"{percentile(trials_all, 0.90):.0f}   (% dòng trials < 5: {pct(n_low_trials):.1f}%)")
    print(f"fails_slipped (cửa sổ)    : {summary['fails_slipped_windows']}  "
          f"({100.0 * float(summary['fails_slipped_windows']) / n_rows:.2f}% dòng — "
          f"L nhỏ hơn thì frame kết thúc nhanh hơn, số này phải giảm theo L)")
    print(f"pdr ghim tại 1.0 / 0.0    : {pct(n_pinned_hi):.1f}% / {pct(n_pinned_lo):.1f}%")
    print(f"rssi_level median         : {median(rssi_all):.1f} dBm")
    print(f"fails không quy được lớp  : {summary['fails_unattributed']}")
    print(f"frame ARP trên sóng       : {summary['airtime_frames']['arp']}  (phải là 0 — ARP tĩnh)")
    print(f"PSDU probe / cbr          : {summary['psdu_bytes_probe']} / {summary['psdu_bytes_cbr']} B")

    q_deq = int(summary["queue_dequeued"])
    q_exp = int(summary["queue_expired"])
    q_ovf = int(summary["queue_drop_before_enqueue"])
    q_all = q_deq + q_exp + q_ovf
    print(f"\nqueue: dequeued {q_deq}, expired {q_exp} ({100.0 * q_exp / max(q_all, 1):.2f}%), "
          f"tràn {q_ovf} ({100.0 * q_ovf / max(q_all, 1):.2f}%)")
    print(f"queue delay ms            : p50 {summary['queue_delay_ms_p50']:.1f}  "
          f"p90 {summary['queue_delay_ms_p90']:.1f}  p99 {summary['queue_delay_ms_p99']:.1f}  "
          f"max {summary['queue_delay_ms_max']:.1f}  "
          f"(MaxDelay đang nắn traffic nếu p99 gần cap)")

    sim_time = None
    meta_path = run_dir / "meta.json"
    if meta_path.is_file():
        sim_time = float(json.loads(meta_path.read_text()).get("sim_time_s", 0)) or None
    print("\nairtime theo nguồn (toàn mạng, chưa chia miền tranh chấp):")
    airtime = summary["airtime_s"]
    frames = summary["airtime_frames"]
    for name in ("beacon", "probe", "cbr", "olsr", "arp", "ctrl", "mgmt", "other"):
        secs = float(airtime[name])
        share = f"{100.0 * secs / sim_time:6.2f} %" if sim_time else "     ? %"
        print(f"  {name:<8}{secs:10.2f} s  {share}   ({frames[name]} frame)")
    meas = float(airtime["beacon"]) + float(airtime["probe"])
    app = float(airtime["cbr"]) + float(airtime["olsr"])
    print(f"  đo lường (beacon+probe) / ứng dụng (cbr+olsr): "
          f"{meas:.1f} / {app:.1f} s = {meas / app if app else float('inf'):.2f}×")

    print("\nq per-attempt theo bin, tách off-path (probe) / on-path (CBR) — và CBR")
    print("dồn trials vào bin nào (bằng chứng cơ chế min-hop chọn link dài):")
    tot_tp = sum(v[0] for v in q_bin.values()) or 1.0
    tot_tc = sum(v[2] for v in q_bin.values()) or 1.0
    print(f"  {'bin':<12}{'q_probe':>9}{'q_cbr':>9}{'%trials_probe':>15}{'%trials_cbr':>13}")
    for name in sorted(q_bin):
        tp, fp, tc, fc = q_bin[name]
        qp = f"{fp / tp:.3f}" if tp else "—"
        qc = f"{fc / tc:.3f}" if tc else "—"
        print(f"  {name:<12}{qp:>9}{qc:>9}{100.0 * tp / tot_tp:>14.1f}%{100.0 * tc / tot_tc:>12.1f}%")

    print("\ncorr(retry_rate, rssi_level) — quy tắc 13, kỳ vọng âm sâu:")
    print(f"  toàn cục: Pearson {pearson(corr_retry, corr_rssi):+.3f}  "
          f"Spearman {spearman(corr_retry, corr_rssi):+.3f}  (n={len(corr_retry)})")
    for name, (rs, ss) in sorted(by_bin.items()):
        print(f"  {name:<12} Pearson {pearson(rs, ss):+.3f}  Spearman {spearman(rs, ss):+.3f}  "
              f"(n={len(rs)})")

    (run_dir / "gates.json").write_text(json.dumps({
        "rows": n_rows,
        "gates": {name: {"threshold": thresh, "value": value, "pass": passed}
                  for name, thresh, value, passed in gates},
        "retry_empty_pct": pct(n_retry_empty),
        "probe_only_pct": pct(n_probe_only),
        "median_trials": median(trials_all),
        "trials_p10_p25_p50_p90": [percentile(trials_all, q) for q in (0.10, 0.25, 0.50, 0.90)],
        "trials_below_5_pct": pct(n_low_trials),
        "fails_slipped_windows": summary["fails_slipped_windows"],
        "q_by_bin_probe_cbr": {
            name: {
                "q_probe": (v[1] / v[0]) if v[0] else None,
                "q_cbr": (v[3] / v[2]) if v[2] else None,
                "trials_probe": v[0],
                "trials_cbr": v[2],
            }
            for name, v in sorted(q_bin.items())
        },
        "pinned_hi_pct": pct(n_pinned_hi),
        "pinned_lo_pct": pct(n_pinned_lo),
        "degree_vs_p1": {"measured": degree, "p1": P1_DEGREE_REF},
        "near_q": {"value": near_q, "max_dist_m": near_max_m, "trials": near_trials},
        "corr_retry_rssi_pearson": pearson(corr_retry, corr_rssi),
        "corr_retry_rssi_spearman": spearman(corr_retry, corr_rssi),
        "all_pass": ok,
    }, indent=2, ensure_ascii=False) + "\n")

    print(f"\n{'MỌI CỔNG ĐẠT' if ok else 'CÓ CỔNG TRƯỢT — DỪNG, BÁO CÁO, KHÔNG NỚI NGƯỠNG'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
