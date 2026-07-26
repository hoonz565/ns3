# STATUS — vị trí hiện tại của dự án

> File này là nguồn chân lý về **đang ở đâu**. Đọc đầu tiên mỗi session,
> cập nhật cuối mỗi phase (WORKFLOW.md mục 1).

Cập nhật lần cuối: 2026-07-27

## Phase hiện tại

**P3 HOÀN TẤT — CHỜ DUYỆT SANG P4. `frozen/normalization.json` đã đóng
băng từ 105 869 dòng của đúng 5 seed calib (p20/p80 `rssi_level` =
−88.6141/−84.7784 dBm, `rssi_slope` = −0.3794/+0.3761 dB/s; p5/p95 ghi kèm
chỉ để P5 so bản clip rộng; `retry_rate` ngưỡng vật lý [0,1], không
percentile). `gateNearQMax` hiệu chuẩn lại 0.35 → 0.38 từ phân bố 35 điểm.
Ba mục chuẩn bị P5 đã vào PLAN.md. KHÔNG fit gì. Báo cáo:
`reports/P3-calibration.md`.**

P4 kế tiếp (cần duyệt): áp normalization đóng băng lên `data/train`, kiểm
VIF, chia 30/5 theo seed. P5 sau đó làm theo thứ tự mới trong PLAN.md:
**PCA trước, fit sau, rồi thang hiệu chỉnh attenuation.**

## Đã hoàn thành

- **P0 — thiết bị đo, ba cổng đạt** (11 run, cây sạch, SHA `294c481df`):
  |residual| max 0.0066 dB; σ 6 seed: m=8→1.594, m=5→2.026, m=3→2.755.
- **P1 — config đóng băng**: `txPowerDbm = 19`, `minRssiDbm = -101` →
  degree **6.14**, cô lập 0.6%, R(0.5) = 625 m (kiểm chứng hình học độc lập
  ~6.0). Độ cao quasi-tĩnh: chấp nhận và khai báo (dọc góp 0.7%).
- **P2 — thiết kế + harness + dataset đóng** (chi tiết:
  `reports/P2-harness.md`, `reports/P2-batch.md`): Tier 2 = OLSR chuẩn
  (chỉ tạo tải) + CBR đa chặng + beacon L2 10 Hz (nguồn duy nhất RSSI) +
  probe L2 mỗi-neighbor; nhãn per-attempt tách cột probe/CBR;
  `FrameRetryLimit = 2` toàn hệ thống. **35/35 seed PASS cả 7 cổng:
  `data/calib/` = seeds 1–5 (105 869 dòng), `data/train/` = seeds 6–35
  (652 432 dòng), tổng 758 301 dòng.** Binary + config digest đồng nhất
  cả 35 manifest (calib chạy ở git `2e3e45828`, train ở `c90310d86` — hai
  commit chỉ khác tài liệu; xem Bất thường của P3-calibration.md).
  Ba phân tích tiền-P5: (1) `rssi_n` 38 → 4 theo bin → SE(slope) ~0.22 →
  ~1.2 dB/s — attenuation bias mạnh nhất ở link biên; (2) SD
  liên-link/trong-link 0.39–0.68 mọi bin — mean RSSI không phân biệt link
  cùng bin; (3) corr(level, retry) = −0.793, level~slope = 0.000.
- **P3 — hiệu chuẩn ngưỡng, đóng băng** (`reports/P3-calibration.md`):
  `frozen/normalization.json` (bất biến; provenance + per-seed stability
  trong file); `analysis/features/p3_normalization.py` (từ chối ghi đè
  frozen, từ chối "eval", đòi manifest sạch đồng nhất); `gateNearQMax`
  0.35 → 0.38; PLAN.md P5 nhận ba mục: Bước 0 PCA, "β_RSSI mã hoá khoảng
  cách theo cấu tạo kênh" (Results, không phải Limitations), thang
  attenuation 3 bước (**hiệu chỉnh, không lọc** — chỉ dẫn cũ "fit riêng
  `rssi_n ≥ 20`" đã gỡ); CLAUDE.md nhận đoạn cấu tạo kênh (quy tắc 11) và
  lệnh cấm lọc theo `rssi_n` (mục Acceptance gate, cạnh lệnh cấm lọc theo
  trials).

## Đang vướng

**Chờ duyệt sang P4.** Không có việc để ngỏ trong phạm vi P3.

## Quyết định đã chốt

- **Ba tầng mô phỏng** (CLAUDE.md): Tier 1 kiểm chứng / Tier 2 thu dữ liệu
  (OLSR-tải + CBR + beacon + probe) / Tier 3 đánh giá (không beacon, không
  probe). Kết quả không bao giờ vượt tầng.
- **`frozen/normalization.json` bất biến**; bộ triển khai là (p20, p80),
  (p5, p95) chỉ cho phép so của P5 — không phải bộ triển khai thứ hai.
  `retry_rate` không percentile: [0,1] vật lý, `s_mac = 1 − clip(retry)`.
- **`gateNearQMax` = 0.38** (= mean-calib + 5 SD-toàn-tập = mean-35-seed
  + ~4.5 SD, cách max quan sát 0.326 ~2.4 SD). Vai trò: cổng SỨC KHOẺ VẬN
  HÀNH — cùng chế độ tranh chấp với batch đã duyệt — không phải cổng chất
  lượng dữ liệu (vai trò đó thuộc degree); vẫn đọc liên hợp với degree.
  Hệ quả khai trước: `config_sha256` của batch eval (P10) sẽ khác batch
  train vì đổi hằng số cổng — khác biệt chỉ ở phía phân tích (`gate*` là
  "của Python", trơ với binary), không phải lệch provenance.
- **P5 mở màn bằng phân tích chiều (PCA)** trên ba feature z-score, toàn
  tập 35 seed, trước mọi GLM; >95% phương sai ở 2 thành phần đầu = công
  thức thừa một số hạng, phải nói thẳng trong paper.
- **`rssi_level` không mang tin vượt khoảng cách THEO CẤU TẠO KÊNH**
  (LogDistance + Nakagami, không shadowing per-link → E[RSSI] = f(d) tất
  định). Vào **Results**, không phải Limitations: giá trị vượt-hình-học
  nằm ở slope + retry; β_RSSI đáng kể = mã hoá khoảng cách, nói thẳng.
  Future Work: shadowing log-normal per-link (không làm trong paper này).
- **Attenuation của β_slope xử lý bằng hiệu chỉnh, không lọc**: fit thô →
  fit phân tầng theo `rssi_n` (β_slope tăng đơn điệu theo n = bằng chứng
  trực tiếp) → reliability-ratio với phương sai nhiễu ĐÃ BIẾT (SE(slope)
  dạng đóng từ `rssi_n` + σ tier Nakagami), báo cả β quan sát lẫn β hiệu
  chỉnh. Đường β_slope theo `rssi_n` dùng lại cho P7 (dual control,
  n = Δ/H). KHÔNG lọc `rssi_n ≥ 20` — kiểm duyệt link biên.
- **`FrameRetryLimit = 2` toàn hệ thống** (Tier 2 lẫn Tier 3, vào bảng
  Simulation Setup): chuỗi retry tương quan làm GLM khai quá thông tin
  ~√5 ở L=7, chặn ở ~√2; đo được khuếch đại 5.37 → 1.76.
- **`retry_rate` là NHÃN TRỄ** — câu hỏi P5 là "RSSI + slope có vượt AR
  baseline không"; bảng đối chứng P5 có chỉ-retry và chỉ-RSSI+slope.
- **Tiêu chí tải Tier 2: TỔNG airtime mọi nguồn 50–70% toàn mạng**
  (~20–28%/miền). Limitations: probe rải đều, CBR dồn dọc tuyến.
- **Nhãn tách cột probe/CBR**; gộp hay không quyết ở P5 (fit ba bản).
- **RSSI chỉ từ beacon**; fail quy lớp theo attempt gần nhất cùng địa
  chỉ; ARP tĩnh; gỡ root qdisc TrafficControl; ba cách đo P0 dùng lại y
  hệt; per-attempt, không post-ARQ; `--fail-on-dirty` mọi run có số.

## Sự thật đã đo, ghi để khỏi suy lại

- **Percentile đóng băng** (105 869 dòng calib): level p5/p20/p80/p95 =
  −89.20/−88.61/−84.78/−79.90 dBm (dải p80−p20 = 3.84 dB); slope =
  −0.848/−0.379/+0.376/+0.845 dB/s (gần đối xứng — dải bất đối xứng nếu
  muốn là quyết định thiết kế, không phải percentile). SD per-seed: p20
  level 0.022 dB (ghim sàn detect −90 dBm, cách 1.4 dB) so p80 0.162 dB
  (topology quyết định). Bản p5/p95 chỉ mở dải VỀ PHÍA TRÊN — phía dưới
  không có mẫu (kiểm duyệt vật lý tại sàn).
- **near-q 35 điểm**: mean 0.2811, SD 0.0221, min 0.2394, max 0.3263;
  calib-5: mean 0.2658, SD 0.0078 (SD toàn tập gấp ~3× calib).
- **Đuôi slope ±0.85 dB/s (p5/p95) so SE(slope) ~1.19 dB/s ở bin ≥800 m**
  — đuôi phân bố slope có thành phần nhiễu đo lớn; dải p20/p80 không phụ
  thuộc đuôi, bản p5/p95 thì có.
- **`MaxSsrc`/`MaxSlrc` OBSOLETE từ ns-3.44** — knob là
  `WifiMac::FrameRetryLimit`, nghĩa "số ATTEMPT tối đa mỗi frame"; L=2 →
  E[attempts] = 1 + q; đo 1.76 tại q = 0.814, khớp.
- **Phản hồi dương admission ↔ độ thoáng kênh**: kênh thoáng → beacon
  decode nhiều → TTL admit thêm neighbor (9.0 → 11.5) → probe +28%.
- **q_cbr ≥ q_probe, hiệu nới khi route tăng** (48% → 70%: +0.009 →
  +0.065); min-hop dồn 72.4% trials on-path vào 400–800 m; cùng bin
  200–400 m on-path fail ×2.3 (tự tranh chấp dọc tuyến).
- **Aggregate MAC loss là trung bình theo trọng số vị-trí-đặt-probe**,
  không phải chỉ báo sức khoẻ kênh (78.3% trên kênh khoẻ). Chỉ báo sập là
  near-q + degree đọc liên hợp.
- **Đường CBR: trung bình 2.15 hop, 71.3% flow-giây ≥2 hop, route
  availability ~70–75% (trải 61.5–91.4% giữa seed)**.
- **q̄ per-attempt là trung bình trọng số theo attempt** — link xấu sinh
  nhiều attempt nên kéo q̄ lên.
- **MaxDelay 100 ms trơ khi hết bão hoà** (expired 0, p99 4.7 ms); không
  phải thủ phạm bão hoà run 1 (airtime đốt trên sóng, không backlog).
- **ns-3.45 tự cài root qdisc FqCoDel lên WifiNetDevice khi gán địa chỉ
  IP**; trace `Tx` của OnOffApplication chỉ bắn khi `Send` thành công.
- **Ước lượng airtime probe phải nhân hai hệ số** (TTL lỏng ~9 neighbor +
  ARQ ×5.4 khi có link chết); thiếu cả hai → sai 7.8×.
- **corr(retry, rssi) âm sâu (−0.86) NGAY TRONG bão hoà** — corr một mình
  không chẩn đoán bão hoà; nhìn bảng airtime tách nguồn.
- Phân bố nhãn KHÔNG ceiling: ghim-1.0 2.6%, 75.2% dòng 0<pdr<1, median
  trials 39 (smoke); batch: median trials 7, %dòng thiếu retry 0.65%.

## Chưa chạm

`frozen/weights.json` (việc của P5). `data/eval/` (RỖNG, cưỡng chế bằng
`run_tests.sh` tới P10). Chưa fit gì, chưa PCA gì — P5 làm cả hai theo thứ
tự mới. Dataset P2 đóng: `data/calib/` (P3 đã dùng xong), `data/train/`
(P4/P5 dùng).
