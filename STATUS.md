# STATUS — vị trí hiện tại của dự án

> File này là nguồn chân lý về **đang ở đâu**. Đọc đầu tiên mỗi session,
> cập nhật cuối mỗi phase (WORKFLOW.md mục 1).

Cập nhật lần cuối: 2026-07-29

## Phase hiện tại

**P5b HOÀN TẤT TRONG PHẠM VI FROZEN-INFERENCE — đã đọc đúng holdout
seeds 30–35, assert không overlap fit 6–29, không refit và không sửa
artifact P5a. 129.061 dòng holdout được xuất prediction; 128.237 dòng đủ
retry (959.647 attempts) dùng cho metrics, 824 dòng thiếu retry được giữ
với prediction rỗng. Full raw: LogLoss 0,420494, Brier 0,132486, ROC AUC
0,830396, PR AUC 0,666080, weighted R² 0,617227, ECE-10 0,021919; thắng
AR persistence ở mọi point metric. Clipped Full xấu hơn tổng thể và ghim
`s_RSSI=1` ở 100% dòng 0–200 m, làm đạo hàm RSSI-level bằng 0; vùng này
mean |p_raw−p_clip| = 30,395 điểm %. Báo cáo:
`reports/P5b-eval.md`. `data/eval/` vẫn cấm tới P10.**

**THAY ĐỔI THIẾT KẾ TIER 2 (2026-07-29) ĐÃ IMPLEMENT, CHƯA CHẠY BATCH:**
`link-dataset-fanet` lấy mẫu setup mỗi scenario id bằng
`ns3::UniformRandomVariable`: node 15–90, X/Y 1000–3000 m, altitude
100–600 m mỗi node, speed 15–30 m/s mỗi node, alpha 0.4–0.95, TxPower
15–23 dBm và CBR 4–20 pkt/s. Mọi seed trong scenario dùng chung setup và
có `RngRun` độc lập. Đã bỏ warmup/start delay thủ công; metadata ghi setup
thực tế và RNG stream. Target mới là **1.000 scenario × 10 seed**.
`scripts/run_campaign.sh` dùng global dynamic queue + `ThreadPoolExecutor`;
parent gọi ns-3 generate mỗi `scenario.json` đúng một lần và là single writer
cho summary/progress, worker chỉ ghi thư mục seed. Có `--workers auto|N`,
dashboard sạch, resume tự retry run chưa PASS và Ctrl+C terminate process
con. Log seed đã bỏ dump nominal, flush setup thực tế và giữ heartbeat thô.
Build + parallel/resume/interrupt smoke ngắn đạt.
**Chưa duyệt batch lớn:**
smoke scenario 1 lấy 87 node và đo probe
airtime 253% simTime ở giây đầu, cho thấy các setup dày có thể bão hoà.
Dataset/frozen P2–P5 cũ giữ nguyên, không ghi đè.

Giới hạn đã ghi rõ: repo không có frozen inference implementation cho
RSSI-only, RSSI+slope hoặc LET; dưới lệnh cấm refit/tạo baseline mới, ba
hàng đó không được dựng surrogate và chưa thể so hợp lệ. P5b không tuyên
bố Full thắng ba baseline chưa khả dụng này.

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
- **P4 — dataset huấn luyện** (`reports/P4-dataset.md`): `frozen/split.json`
  chốt trước dữ liệu (24 fit / 6 holdout); `rows_norm.csv` toàn 35 seed
  (thô + `s_rssi,s_slope,s_mac` từ cặp p20/p80; s_mac rỗng giữ rỗng);
  VIF ĐẠT; hồ sơ cổng đồng nhất 0.38; `run_manifest.py` thêm
  `sim_params_sha256` (meta.json, augment sau-run, móc vào runner) +
  `config_sim_sha256` (conf bỏ `gate*`/`seeds*`/`rHalfM`), backfill 35
  manifest — mỗi khoá một giá trị duy nhất toàn dataset; conf nhận đoạn
  "near-q ở 0.38 chỉ bắt bão hoà NẶNG, bộ dò chính là degree"; PLAN.md P5
  Limitations nhận mục bất đối xứng p5/p95 (nới 0.59 dB dưới / 4.88 dB
  trên) kèm số ghim đo được.
- **P5a — fit lõi** (`reports/P5a-fit.md`): PCA trên tập fit không vượt
  ngưỡng thừa 95%; GLM nhị thức thô có intercept + cluster theo seed;
  bootstrap theo seed ổn định, mọi dấu đúng vật lý; tỉ số slope/RSSI chỉ
  2,15 s thay vì 4 s; phân tầng rssi_n cho mẫu hỗn hợp nên dừng trước
  reliability-ratio; xuất `frozen/weights.json` dạng logit thô và
  `(a,b,c)` chỉ-trình-bày; chưa đọc holdout/chưa làm bảng P5b.
- **P5a addendum**: từ 3.860.795 attempt trên dòng GLM, midpoint trọng số
  = 1,991 s và không giải thích ratio 2,15 s vì feature/label center cách
  nhau 3,991 s; cố định dist 400–600 m rồi chia quartile rssi_n vẫn cho
  beta_slope không đơn điệu (0,446/0,748/0,795/0,716). Kết luận P5a về
  attenuation đứng vững; không đọc holdout.
- **P5b — holdout frozen inference** (`reports/P5b-eval.md`): seed
  30–35, không overlap fit, không refit; xuất prediction toàn holdout,
  per-attempt LogLoss/Brier/ROC AUC/PR AUC, fixed-bin reliability,
  calibration curve và weighted-R² scatter. Full raw vượt AR ở mọi point
  metric. Clipping làm LogLoss/Brier/ECE tổng thể xấu hơn và xoá
  RSSI-level sensitivity trên toàn bộ dòng 0–200 m. RSSI-only,
  RSSI+slope, LET không có frozen implementation nên không tạo thay thế.

## Đang vướng

Không có lỗi thực thi P5b. Bảng baseline preregistered còn thiếu
RSSI-only, RSSI+slope và LET vì không có frozen implementation; giải quyết
điểm này sẽ cần một quyết định phạm vi riêng, không được tự ý refit sau
khi đã mở holdout.

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
  lượng dữ liệu (vai trò đó thuộc degree). **Ở 0.38 near-q chỉ bắt bão hoà
  NẶNG** (run 1: 0.680; run 2 bão hoà nhẹ 0.343 giờ PASS); bộ dò chính là
  DEGREE (cổng 4.0 cách mean calib 9.7 SD, bắt cả run 1 degree 1.79 lẫn
  run 2 degree 3.82). "near-q PASS" chỉ đọc được là "không bão hoà nặng".
- **`frozen/split.json` bất biến, chốt TRƯỚC khi nhìn dữ liệu**: seeds
  6–29 fit (24) / 30–35 holdout (6), quy tắc cố định theo số seed. P5 fit
  + chọn mô hình trên fit, scatter/R² ngoài mẫu trên holdout; `data/eval`
  vẫn nguyên vẹn tới P10.
- **Khoá so sánh giữa các batch = BỘ BA (`binary_sha256`,
  `config_sim_sha256`, `sim_params_sha256`)** (P4). Ngoại lệ P3
  "config_sha256 của eval sẽ khác vì key gate" ĐÃ GỠ: đổi ngưỡng cổng
  không đổi `config_sim_sha256` (kiểm chứng: conf 0.35 và 0.38 cùng hash).
  Eval hợp lệ ⟺ bộ ba trùng train. `config_sha256` cũ giữ để so lịch sử.
- **P5 mở màn bằng phân tích chiều (PCA)** trên ba feature z-score, tập fit
  seeds 6–29, trước mọi GLM; đo được 93,14% phương sai ở 2 thành phần đầu,
  dưới tiêu chí >95% để kết luận công thức thừa một số hạng.
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

- **VIF tập fit 24 seed (thô): level 2.707 / slope 1.000 / retry 2.707**
  — toàn bộ VIF của level/retry từ corr(level, retry) = −0.794 (trùng
  toàn tập −0.793); slope trực giao. SD: 3.06 dBm / 0.582 dB/s / 0.344.
- **Ghim biên clip (758 301 dòng)**: cặp triển khai p20/p80 ghim `s_rssi`
  100% ở 0–200 m, 82% ở 200–400 m (về 1) và 74% ở ≥800 m (về 0) — chỉ còn
  phân biệt trong 400–800 m; bản p5/p95 gỡ biên trên (82→9%) nhưng biên
  dưới còn 26% (sàn detect). `s_mac`: 33% cửa sổ retry = 1 toàn tập,
  90.6% ở ≥800 m — retry hết phương sai trong vùng chết. Đầy đủ:
  `data/p4_norm_stats.json`.
- **Bộ ba khoá dataset P2**: binary `15198a5fc9…`, config_sim
  `3e4481e7c04f…`, sim_params `0c94836c1d77…` — mỗi khoá đúng một giá trị
  trên cả 35 manifest. `meta.json` chỉ in ~20 tham số (thiếu `gm*`,
  `nakagami*`, `exponent`, `frameRetryLimit`...) — vì thế cần
  `config_sim_sha256` đi kèm; scenario Tier 3 (P8) phải in ĐỦ tham số
  hiệu dụng vào meta.json ngay từ đầu.
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

`data/eval/` vẫn RỖNG và bị `run_tests.sh` cưỡng chế tới P10. Dataset P2
đóng: `data/calib/` (P3 đã dùng xong), `data/train/` (P5a fit seeds 6–29;
P5b chỉ inference holdout seeds 30–35 theo `frozen/split.json`).
