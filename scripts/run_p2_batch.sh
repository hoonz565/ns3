#!/usr/bin/env bash
# Runner batch P2 — WORKFLOW.md mục 3: mỗi run một manifest, fail to và sớm.
#
#   scripts/run_p2_batch.sh <seed_đầu> <seed_cuối> <thư_mục_gốc>
#   vd: scripts/run_p2_batch.sh 1 5 data/calib
#
# Điều kiện dừng (chỉ định của batch P2, 2026-07-27):
#   - run_tests.sh fail (bất biến repo vỡ)                    -> không chạy gì
#   - manifest fail (cây dirty / binary cũ hơn source)        -> dừng NGAY;
#     sửa gì giữa chừng thì batch không đồng nhất, chạy lại từ đầu
#   - seed abort (exit != 0, FATAL trong log, thiếu summary)  -> dừng NGAY
#   - từ 3 seed trở lên trượt BẤT KỲ cổng nào                 -> dừng;
#     một seed trượt là đuôi phân bố, ba seed là chế độ hỏng
set -u
cd "$(dirname "$0")/.."

BIN=build/scratch/linkscore/ns3.45-link-dataset-fanet-default
CONF=sim-config/fanet-tier2.conf
START=$1
END=$2
OUTROOT=$3
gatefails=0

scripts/run_tests.sh || { echo "DỪNG: run_tests.sh fail — bất biến repo vỡ"; exit 1; }

for seed in $(seq "$START" "$END"); do
    out="$OUTROOT/seed-$seed"
    mkdir -p "$out"

    if ! python3 scripts/run_manifest.py --phase P2 --seed "$seed" \
            --config "$CONF" --binary "$BIN" --fail-on-dirty --quiet \
            --out "$out/run_manifest.json"; then
        echo "DỪNG: manifest seed $seed fail (dirty hoặc binary cũ hơn source)"
        exit 1
    fi

    if ! ./ns3 run "scratch/linkscore/link-dataset-fanet --config=$CONF --seed=$seed --out=$out" \
            > "$out/stdout.log" 2>&1; then
        echo "DỪNG: seed $seed abort — xem $out/stdout.log"
        exit 1
    fi
    # ./ns3 có tiền sử exit 0 dù lỗi (P0 bất thường 6) — soi log, đừng tin mã thoát.
    if grep -qE "NS_FATAL|terminate called|assert failed" "$out/stdout.log"; then
        echo "DỪNG: seed $seed có FATAL trong log dù exit 0 — xem $out/stdout.log"
        exit 1
    fi
    if [ ! -f "$out/summary.json" ]; then
        echo "DỪNG: seed $seed không sinh summary.json"
        exit 1
    fi

    if python3 scripts/check_gates.py "$out" > "$out/gates.txt" 2>&1; then
        echo "seed $seed: PASS"
    else
        gatefails=$((gatefails + 1))
        echo "seed $seed: TRƯỢT CỔNG ($gatefails; dừng khi đủ 3) — xem $out/gates.txt"
    fi
    if [ "$gatefails" -ge 3 ]; then
        echo "DỪNG: $gatefails seed trượt cổng — một seed là đuôi phân bố, ba là chế độ hỏng"
        exit 1
    fi
done

echo "BATCH XONG: seeds $START-$END vào $OUTROOT, $gatefails seed trượt cổng"
