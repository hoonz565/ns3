# STATUS — vị trí hiện tại của dự án

> File này là nguồn chân lý về **đang ở đâu**. Đọc đầu tiên mỗi session,
> cập nhật cuối mỗi phase (WORKFLOW.md mục 1).

Cập nhật lần cuối: 2026-07-26

## Phase hiện tại

**P1 XONG. Config đã đóng băng.** Sẵn sàng cho P2 (harness thu dữ liệu Tier 2)
khi anh/chị duyệt. Báo cáo: `reports/P1-config.md`.

Config đóng băng: `txPowerDbm = 19`, `minRssiDbm = -101`, `channelNumber = 36`,
`dataMode = OfdmRate6Mbps` — tất cả trong `sim-config/fanet-tier2.conf`, xác
nhận bằng run đọc thẳng từ config (không flag): degree **6.14**, provenance in
ra đúng tên file cho cả bốn key.

## Đã hoàn thành

- **Khung repo + provenance** (P0): cây thư mục theo WORKFLOW mục 2,
  `scripts/run_manifest.py` (git_dirty + binary-vs-source mtime),
  `scripts/test_feature_label_boundary.py`.
- **P0 — thiết bị đo, ba cổng đạt**, đã chạy lại ở cây sạch (11 run,
  `dirty: false`, SHA `294c481df`), số liệu trùng bản cũ đến 3 chữ số:
  - |residual| max **0.0066 dB** so với lý thuyết; Spearman **−1.000000**.
  - retry: 19 973 / 21 072 attempt, 6 bin sạch dưới 70 m.
  - σ residual 6 seed: m=8 → **1.594** (dự kiến 1.585); m=5 → **2.026**
    (2.043); m=3 → **2.755** (2.729). Mean residual cũng khớp Jensen.
- **P1 — công cụ config**: `sim-config.h` (precedence default < config < flag,
  registry key hai tầng: ngoài registry → fatal, trong-registry-không-dùng →
  cảnh báo), config phân lớp, `run_manifest.py --config` lặp lại được +
  `config_sha256`.
- **P1 — đo hình học**: `topology-probe.cc` 30 node / 300 s / chỉ beacon.

## Đang vướng

Không có gì chặn. Hai việc của P1 đã chốt:

1. **`txPowerDbm = 19`, `minRssiDbm = -101`** — degree **6.14**, cô lập 0.6%,
   R(0.5) = 625 m. Config cũ (20 dBm / sàn −82) cho degree 1.06 và cô lập
   34.5%, không đạt cổng. `12 dBm/−101` bị loại bằng số học: ngân sách 102 dB
   đúng bằng config cũ nên cùng degree.
2. **Độ cao quasi-tĩnh: chấp nhận và khai báo.** z-span mỗi node trung vị
   **107 m / dải 500 m**, 100% node quét dưới nửa dải. Vận động dọc đóng góp
   trung vị **0.7%** vào thay đổi khoảng cách làm link đổi trạng thái (3.2%
   trước khi chiếu lên khoảng cách 3D). Phát biểu đúng: **vị trí 3D phân tầng
   giữa các node, động lực học do chuyển động ngang** — đã ghi vào CLAUDE.md
   và PLAN.md.

## Quyết định đã chốt

- **Scenario C++ ở `scratch/linkscore/`**, mỗi `.cc` một target qua `build_exec`
  với `EXECNAME_PREFIX scratch_linkscore_`.
- **Ba cách đo của P0, dùng lại y hệt ở P2**: RSSI từ `MonitorSnifferRx`
  (`signalNoise.signal`); mẫu số mọi tỉ lệ MAC từ `MonitorSnifferTx`, không từ
  `Send()`; probe unicast L2 qua `NetDevice::Send`.
- **Nhãn per-attempt, không post-ARQ** (CLAUDE.md quy tắc 3).
- **Config phân lớp, không lặp khối physics.** Khối lặp lại là khối sẽ trôi.
- **`--fail-on-dirty` cho mọi run có số vào paper.**
- **σ dự kiến của fading suy từ hiện thực ns-3**, không từ tài liệu.

## Sự thật đã đo, ghi để khỏi suy lại

- **Sàn detect mặc định của ns-3 là −82 dBm** (`ThresholdPreambleDetectionModel`),
  cao hơn giới hạn do nhiễu 7 dB. Nó kiểm duyệt cả **feature RSSI** chứ không
  chỉ nhãn.
- **Bề rộng vùng chuyển tiếp ≈ 2.56·σ_fading ≈ 5.4 dB**, không phụ thuộc sàn.
  Hạ sàn mua **tầm phủ**, không mua bề rộng waterfall.
- **degree 5.28 của `fanet-tier2.conf` không tái lập được** — đo lại ở đúng
  20 dBm/−82 ra 1.06 (chặt) hoặc 3.99 (lỏng). Scenario sinh ra nó
  (`link-dataset-fanet.cc`) không có trong cây nên **điều kiện đo chưa biết**;
  không tuyên bố con số cũ sai, chỉ là không kiểm chứng được ở đây. Phép đo mới
  có kiểm chứng hình học độc lập (0.92 ở R=300 vs 1.06 đo; ~6.0 ở R=625 vs 6.14
  đo). Đã chú giải ngay trong conf, không xoá bảng cũ.
- **Ngân sách link = TxPower − sàn.** `12 dBm/−101` và `20 dBm/−82` cùng 102 dB
  nên cùng R trong phép đo cô lập, **nhưng không tương đương ở P2**: với sàn
  −101 ràng buộc rơi vào `Threshold` SNR nên mép link dịch theo can nhiễu; sàn
  −82 là hằng số tuyệt đối, không nhúc nhích dưới tải.
- **Cảnh báo "degree > 11 làm abort" của conf đã lỗi thời.** Run ở degree
  22.33 chạy hết 300 s exit sạch. **Patch `phy-entity` lần đầu được kiểm thật
  (30 node × 300 s × 3 run, không hit assert) — mục Bất thường 5 của P0 đóng.**
- **Định nghĩa link đổi degree gấp gần 4 lần** trên cùng dữ liệu. Mọi con số
  degree phải đi kèm định nghĩa.

## Chưa chạm

`frozen/` (rỗng), `data/{calib,train,eval}/` (rỗng). `data/eval/` cấm tới P10.
`config/` rỗng — config thật nằm ở `sim-config/` theo CLAUDE.md; thư mục
`config/` trong WORKFLOW mục 2 hiện không dùng.
