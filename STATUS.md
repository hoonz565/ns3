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
  - Cổng 3 — residual σ theo tier Nakagami: m=8 → **1.573** (dự kiến 1.585);
    m=5 → **1.961** (dự kiến 2.043); m=3 → **2.716** (dự kiến 2.729).
    Tất cả trong ±0.25 dB.

## Đang vướng

Không có gì chặn. Hai câu hỏi P1 phải trả lời, phát sinh từ số liệu P0:

1. **Sàn kiểm duyệt RSSI −82 dBm.** `ThresholdPreambleDetectionModel` mặc định
   có `MinimumRssi = −82 dBm`: frame yếu hơn thế không bao giờ được detect, cao
   hơn giới hạn do nhiễu 7 dB. Vị trí điểm link chết do hằng số này quyết định,
   không do mô hình sai số bit. Là **attribute**, sửa bằng config, không cần
   patch — nhưng phải khai báo trong paper nếu đổi.
2. **Cặp (TxPower, diện tích) trong PLAN.md không nhất quán.** Tầm phủ đo được
   là **114 m**, không phải ~500 m như PLAN ghi → degree ≈ **0.30** ở
   2000×2000 m với 30 node, không phải 6. Vá bằng TxPower ≈ 24 dBm (giữ diện
   tích) hoặc thu diện tích về ~444×444 m (giữ 10 dBm).

Chi tiết và số liệu: `reports/P0-instrumentation.md`.

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
