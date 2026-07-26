# STATUS — vị trí hiện tại của dự án

> File này là nguồn chân lý về **đang ở đâu**. Đọc đầu tiên mỗi session,
> cập nhật cuối mỗi phase (WORKFLOW.md mục 1).

Cập nhật lần cuối: 2026-07-26

## Phase hiện tại

**P0 xong, ba cổng đều đạt.** Chờ duyệt để sang **P1 — đóng băng cấu hình**.
Báo cáo: `reports/P0-instrumentation.md`.

## Đã hoàn thành

- **Khung repo**: cây thư mục theo WORKFLOW.md mục 2, `.gitignore`,
  `scripts/run_manifest.py` (2 kiểm tra: git_dirty cảnh báo, binary cũ hơn
  source thì exit 2), `scripts/test_feature_label_boundary.py` (kiểm hai chiều
  bằng AST).
- **P0**: ns-3.45 build xong (`./ns3 configure --enable-examples`, ninja, build
  type default, assert ON). `scratch/linkscore/link-probe.cc` chạy 3 run.
  - Cổng 1 — RSSI bám lý thuyết: |residual| max **0.0066 dB**, Spearman
    **−1.000000**, 0 lần RSSI tăng.
  - Cổng 2 — MAC retry: 19 973 retry / 21 072 attempt; 6 bin sạch dưới 70 m,
    55 bin có retry. Callback không câm.
  - Cổng 3 — residual σ theo tier Nakagami, **6 seed / 47 947 mẫu**: m=8 →
    **1.594** (dự kiến 1.585); m=5 → **2.026** (dự kiến 2.043); m=3 →
    **2.755** (dự kiến 2.729). Mean residual cũng khớp dự đoán Jensen ở cả ba
    tier — hai mô men khớp đồng thời.
  - Bất thường +0.09 dB ở 1 seed: **đã loại trừ**, gộp 6 seed cho
    +0.0105 ± 0.0113 dB (z = +0.93). Hiện vật RNG của seed 1.
  - Đo tầm phủ: d(0.5) = **107 m** ở 10 dBm/sàn −82; **250 m** ở 10 dBm/sàn
    −101; **501 m** ở 17 dBm/sàn −101.
- **11 run**, mỗi run một `run_manifest.json`. Đã commit (5 commit).

## Đang vướng

Không có gì chặn. P1 chốt hai tham số, đã có số liệu thật cho cả hai:

1. **`MinimumRssi` — đề xuất hạ về −101 dBm.** Mặc định ns-3 là −82 dBm, một
   **sàn cứng trên RSSI** cao hơn giới hạn do nhiễu 7 dB. Hạ về −101 thì ràng
   buộc chuyển sang `Threshold` (4 dB SNR) → sàn hiệu dụng −90 dBm, dựa trên
   SNR tức dựa trên vật lý. Là attribute, không cần patch, nhưng phải khai báo
   trong paper.
   **Lưu ý ngược trực giác:** hạ sàn KHÔNG làm vùng waterfall rộng ra theo dB
   (5.38 → 5.60 dB). Bề rộng đó là bề rộng phân bố fading (≈ 2.56σ), không
   phải của đường cong PER. Nó mua **tầm phủ**, và nhờ đó vùng biên trải ra
   nhiều mét hơn (62 → 146 m), tức nhiều cặp node ở vùng biên hơn.
2. **TxPower — đề xuất 17 dBm**, giữ 2000×2000×500 m. Đo được d(0.5) = 501 m,
   khớp tính toán 16.1 dBm. (Ước lượng 10 dBm → 500 m trong PLAN.md dùng
   ngưỡng −96 dBm, quá lạc quan.)
   **Không chốt bằng công thức degree**: chiều cao hộp ≈ R nên 2D cho 5.7, 3D
   cho 7.6. Phải đo degree trong smoke test P2.

Chi tiết và số liệu: `reports/P0-instrumentation.md`.

## P2 phải làm, phát sinh từ P0

1. **Nhãn per-attempt, không post-ARQ.** `1 − final_fails/first_attempts` bằng
   đúng 1.000 suốt tới 400 m trong khi per-attempt đã tụt về 0.556 — bão hoà
   đúng kiểu chế độ hỏng "pdr_future dồn hết ở 1.0", và `first_attempts` không
   suy được vững từ bộ đếm cộng dồn (ra giá trị âm ở vùng chết). Dùng
   `trials_future` = số attempt, `fails_future` = số `MacTxDataFailed`.
2. **Ngừng probe neighbor không còn nghe thấy.** Giãn nhịp một mình không chặn
   được backlog: 10 ms cho retry_rate 0.9478, 50 ms cho 0.9475.
3. **Hook trace drop của `WifiMacQueue`** để đếm (không đưa vào nhãn).

## Quyết định đã chốt

- **Scenario C++ nằm ở `scratch/linkscore/`** (WORKFLOW.md mục 2 đã sửa). Mỗi
  scenario một target qua `build_exec` với `EXECNAME_PREFIX scratch_linkscore_`;
  đặt prefix khác thì ninja build được nhưng `./ns3 run` không tìm thấy target.
- **Ba cách đo, dùng lại y hệt ở P2** (PLAN.md mục 3, chống train/deploy skew):
  - RSSI: `MonitorSnifferRx`, trường `signalNoise.signal`.
  - retry_rate: `MacTxDataFailed` / số PPDU data trong `MonitorSnifferTx` —
    mẫu số lấy ở tầng MAC, không suy từ số lần gọi `Send()`, không dùng
    `PeekHeader`.
  - Probe: unicast L2 qua `NetDevice::Send`, Ethertype 0x88b5, cùng kích thước
    frame data.
- **σ dự kiến của fading suy từ hiện thực ns-3, không từ tài liệu**: độ lợi
  công suất ~ Gamma(m, 1/m) → σ_dB = √ψ₁(m)·10/ln10 và mean_dB =
  (ψ(m) − ln m)·10/ln10 (âm, không phải 0). Hàm ψ/ψ₁ tự viết trong
  `analysis/validate/p0_check.py`, khớp chuỗi giải tích tới 7e-13 — scipy 1.8
  của hệ thống không dùng được với numpy 2.x.

## Chưa chạm

`frozen/` (rỗng), `config/` (rỗng — P1), `data/{calib,train,eval}/` (rỗng).
`data/eval/` cấm tới P10.
