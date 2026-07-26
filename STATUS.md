# STATUS — vị trí hiện tại của dự án

> File này là nguồn chân lý về **đang ở đâu**. Đọc đầu tiên mỗi session,
> cập nhật cuối mỗi phase (WORKFLOW.md mục 1).

Cập nhật lần cuối: 2026-07-27

## Phase hiện tại

**P2 SẴN SÀNG BATCH — CHỜ DUYỆT. Cổng đã chốt (7 cổng, phương án b đã
chỉnh): cổng bão hoà chính = q gộp trên link < 0.64·`rHalfM` ≤ 0.35
(`rHalfM = 625` là key conf, không hardcode); `gateLossMax` 85 làm lưới SẬP
KÊNH (đổi vai trò, không phải chỉ báo chất lượng dữ liệu); ngưỡng 0.35 hiệu
chuẩn từ 2 điểm — xem lại sau batch đầu. Smoke chuẩn (`seed-1-hops`, = run 3
byte-identical + đo hop) qua CẢ 7 CỔNG. Trials bỏ ngưỡng (GLM trọng số theo
n; minTrials=2 là vệ sinh). Seed chốt 40 = 5/30/5, conf đã ghi 1-5 / 6-35 /
36-40; ~2.9 phút/seed → batch 35 seed ≈ 1.7 h.**

**Kế hoạch batch đề xuất (mục cuối `reports/P2-harness.md`): chạy seeds 1–35
(calib → `data/calib/`, train → `data/train/`), manifest + check_gates từng
seed, bảng cổng theo seed trước khi sang P3. MỘT CÂU HỎI CHỜ QUYẾT: sinh 5
seed eval (36–40) ngay bây giờ hay để P10 — tôi nghiêng về để P10 (manifest
ghim binary+config để tái lập; vùng cấm rỗng thì không chạm nhầm được).**

Tiến trình bốn run (cùng seed 1): tổng airtime 238.9% → 105.6% → 60.9%;
degree 1.79 → 3.82 → 4.97; route OLSR 19% → 48% → 70%; khuếch đại ARQ 5.37
→ 1.76 → 1.71; run 4 = run 3 + đo hop, rows.csv trùng md5 (determinism ✓).

Thiết kế Tier 2 đã đổi và đã ghi vào tài liệu TRƯỚC khi viết code: OLSR chuẩn
(chỉ tạo tải, mù LinkScore) + CBR đa chặng + beacon L2 10 Hz (nguồn duy nhất
của RSSI) + probe L2 mỗi-neighbor. Nhãn per-attempt tách cột probe/CBR, gộp
hay không quyết ở P5. Xem CLAUDE.md "Three simulation tiers".

## Đã hoàn thành

- **P0 — thiết bị đo, ba cổng đạt** (11 run, cây sạch, SHA `294c481df`):
  |residual| max 0.0066 dB; σ 6 seed: m=8→1.594, m=5→2.026, m=3→2.755.
- **P1 — config đóng băng**: `txPowerDbm = 19`, `minRssiDbm = -101` →
  degree **6.14**, cô lập 0.6%, R(0.5) = 625 m (kiểm chứng hình học độc lập
  ~6.0). Độ cao quasi-tĩnh: chấp nhận và khai báo (dọc góp 0.7%).
- **P2 — tài liệu**: PLAN.md P2 viết lại (bốn loại phát); CLAUDE.md thêm
  "Three simulation tiers" + **"sampling constraint / dual control"** — Tier 3
  lấy RSSI từ HELLO nên tốc độ lấy mẫu là 1/H, SE(slope) ∝ √H, H vừa điều
  tiết vừa thăm dò (Feldbaum); P7 phải đo suy giảm slope bằng lấy mẫu thưa
  dữ liệu beacon 10 Hz (không cần mô phỏng thêm); P8e sửa lập luận cũ.
- **P2 — code**: `scratch/linkscore/link-dataset-fanet.cc` (kế thừa nguyên ba
  cách đo P0; xoay bucket cưỡng chế ghi dòng tại t+τ; ARP tĩnh; assert PSDU
  probe==CBR đo trên sóng: 576=576; guard qdisc), `scripts/check_gates.py`
  (ngưỡng đọc từ conf, exit 1 khi trượt, bảng airtime tách nguồn),
  `fanet-tier2.conf` khối harness mới (labelWin 4, beacon 0.1 s, probeBytes
  540, key CBR/warmup/MaxDelay).
- **P2 — smoke seed 1, run 1** (SHA `ba27233c5`, L=7): 14 273 dòng — bão hoà
  do probe, chẩn đoán trong `reports/P2-harness.md`.
- **P2 — `FrameRetryLimit = 2`** (tài liệu + conf + code, SHA `64eacc733` /
  `af306952b`) và **smoke run 2** cùng seed: 19 752 dòng.
- **P2 — probe 1 Hz + smoke run 3** (SHA `076b439bf` / `f2d7c5d02`): 21 427
  dòng, tải vào vùng, 5/6 cổng. check_gates mở rộng: phân bố trials,
  fails_slipped, q theo bin tách probe/CBR. Ba run giữ song song:
  `data/smoke/p2-harness/seed-1{,-retry2,-probe1hz}/`.
- **Phát hiện cho Motivation: q_cbr ≥ q_probe** — mục riêng trong báo cáo.
  Run 3: 0.841 so 0.776, hiệu nới ra khi route tăng 48%→70%; min-hop dồn
  72.4% trials on-path vào 400–800 m (mép waterfall); cùng bin 200–400 m thì
  on-path fail gấp 2.3× off-path (tự tranh chấp dọc tuyến). PLAN.md P6 đã
  thêm min-hop làm baseline regret thứ ba (`458a59920`).

## Đang vướng

**Chờ duyệt batch** (kế hoạch ở trên) + một câu hỏi vận hành: sinh seed eval
36–40 ngay hay để P10. Không còn vấn đề kỹ thuật mở nào — mâu thuẫn trials
đã đóng (bỏ ngưỡng, CLAUDE.md/PLAN.md sửa), mâu thuẫn số seed đã đóng
(40 = 5/30/5), lệch 9× của CBR end-to-end đã phân rã trọn (×5.0 hop-mix,
×1.69 Jensen — không có bug đếm).

## Quyết định đã chốt

- **Ba tầng mô phỏng** (CLAUDE.md): Tier 1 kiểm chứng / Tier 2 thu dữ liệu
  (OLSR-tải + CBR + beacon + probe) / Tier 3 đánh giá (không beacon, không
  probe). Kết quả không bao giờ vượt tầng.
- **`FrameRetryLimit = 2` toàn hệ thống** (= dot11ShortRetryLimit; áp cả
  Tier 2 lẫn Tier 3, vào bảng Simulation Setup): chuỗi retry tương quan làm
  GLM khai quá thông tin ~√5 ở L=7, chặn ở ~√2; retry dai dẳng phản tác dụng
  ở tốc độ FANET. Đo được: khuếch đại 5.37 → 1.76.
- **`retry_rate` là NHÃN TRỄ** (cùng đại lượng với `pdr_future`, lệch τ) —
  câu hỏi P5 là "RSSI + slope có vượt AR baseline không"; bảng đối chứng P5
  đã thêm chỉ-retry và chỉ-RSSI+slope.
- **Tiêu chí tải Tier 2: TỔNG airtime mọi nguồn 50–70% toàn mạng**
  (~20–28%/miền), không dùng tỉ số đo-lường/ứng-dụng. Limitations: probe rải
  đều, CBR dồn dọc tuyến — mẫu hình tranh chấp không gian khác Tier 3.
- **Nhãn tách cột `trials_probe/fails_probe` và `trials_cbr/fails_cbr`** —
  link on-path có n gấp ~10× và tự tranh chấp không nằm trong feature; gộp
  hay không là quyết định của P5 (fit ba bản, so β), không phải của P2.
- **RSSI chỉ từ beacon** (mật độ mẫu đồng đều, không tương quan routing;
  khớp Tier 3 nơi RSSI đi trên broadcast HELLO).
- **Fail quy lớp theo attempt gần nhất cùng địa chỉ** (MacTxDataFailed chỉ có
  địa chỉ; MAC non-QoS serial hoá nên phép quy chính xác; sai biên đếm ở
  `fails_slipped`).
- **ARP tĩnh, khai báo trong paper** — ARP reply lọt tử số mà không vào mẫu
  số lọc size, thổi phồng fails một chiều.
- **Gỡ root qdisc TrafficControl** (ns-3.45 tự cài FqCoDel khi gán địa chỉ):
  không gỡ thì CBR đệm hai tầng còn probe L2 một tầng. Guard NS_FATAL giữ
  trong code.
- **Ba cách đo của P0 dùng lại y hệt**; per-attempt, không post-ARQ;
  `--fail-on-dirty` cho mọi run có số.

## Sự thật đã đo, ghi để khỏi suy lại

- **`MaxSsrc`/`MaxSlrc` là OBSOLETE từ ns-3.44** — knob còn hoạt động là
  `WifiMac::FrameRetryLimit`, nghĩa "số ATTEMPT tối đa mỗi frame" (drop khi
  retry count chạm limit, min 1). L=2 → E[attempts] = 1 + q; đo 1.76 tại
  q = 0.814, khớp.
- **Phản hồi dương admission ↔ độ thoáng kênh**: kênh thoáng hơn → beacon
  decode nhiều hơn → TTL admit thêm neighbor (9.0 → 11.5, trần loose ~14) →
  probe gửi tăng 28%. Mọi dự đoán tải probe phải tính hệ số này.
- **q_cbr ≥ q_probe, và hiệu nới ra khi OLSR có nhiều route hơn** (run 2 →
  run 3: +0.009 → +0.065 khi route 48% → 70%) — càng được định tuyến nhiều,
  link trên đường càng tệ. Hai cơ chế tách được bằng bin: placement (72.4%
  trials on-path ở 400–800 m) + excess cùng-bin (×2.3 ở 200–400 m, tự tranh
  chấp dọc tuyến). CBR không tự động "sạch" hơn probe.
- **Aggregate MAC loss là trung bình theo trọng số vị-trí-đặt-probe**, không
  phải chỉ báo sức khoẻ kênh: 78.3% ở kênh khoẻ (run 3) vì 53.5% trials ở
  ≥600 m nơi q do vật lý là 0.91–0.99. Chỉ báo sập thật là q vùng gần
  (< 0.64·R½): run 3 = 0.265 ✓, run 2 = 0.343 (lọt sát dưới 0.35 — run 2 bị
  cổng degree chặn thay), run 1 = 0.680 ✗. Số gộp probe+CBR, khác số
  probe-only (0.216/0.33) từng trích trước đó.
- **Đường CBR: trung bình 2.15 hop, 71.3% flow-giây có route là ≥2 hop,
  route availability 70.3% (bảng định tuyến) = 70.1% (app)** — tiền đề CBR
  đa chặng đứng vững. Lệch 9× giữa end-to-end 21.3% và dự đoán 3-hop 2.4%
  phân rã = ×5.0 (hop-mix thật) × 1.69 (q̄ trọng số theo attempt bị link xấu
  kéo lên — Jensen). Đo hop chỉ-đọc không đổi mô phỏng: rows.csv trùng md5.
- **q̄ per-attempt là trung bình trọng số theo attempt, không phải theo gói**
  — link xấu sinh nhiều attempt nên kéo q̄ lên; mọi suy diễn end-to-end từ q̄
  phải nhớ điều này.
- **MaxDelay 100 ms trơ hoàn toàn khi hết bão hoà**: run 2 expired 0, tràn 0,
  p50 1.8 ms / p99 4.7 ms (run 1 bão hoà: p99 85 ms, expired 0.38%).
- **ns-3.45 tự cài root qdisc (FqCoDel) lên WifiNetDevice khi gán địa chỉ
  IP.** Không tin tài liệu cũ nói "không còn default qdisc".
- **Trace `Tx` của OnOffApplication chỉ bắn khi `Send` thành công** — với
  UDP + OLSR, gói không có route không được đếm. `cbr_app_tx` là "đã rời
  node", không phải "theo lịch".
- **Ước lượng airtime probe phải nhân hai hệ số**: tập admission theo TTL
  lỏng (~9 neighbor ở TTL 2 s, không phải degree chặt 6.14) và khuếch đại
  ARQ (~×5.4 khi trong tập có link chết). Thiếu cả hai → sai 7.8×.
- **corr(retry, rssi) âm sâu (−0.86) NGAY TRONG bão hoà** — gánh retry dồn
  lên link yếu nên corr một mình không chẩn đoán được bão hoà; phải nhìn
  bảng airtime tách nguồn.
- **MaxDelay 100 ms không phải thủ phạm bão hoà**: queue expired 0.38%,
  tràn 0, p50 13 ms. Airtime đốt trên sóng (retry), không phải backlog.
- Degree đo trong bão hoà (1.79) là con số về kênh, không phải về hình học —
  positions cùng phân bố với P1.
- Phân bố nhãn ở điểm này KHÔNG bị ceiling: ghim-1.0 chỉ 2.6%, 75.2% dòng ở
  0 < pdr < 1, median trials 39.

## Chưa chạm

`frozen/` (rỗng), `data/{calib,train,eval}/` (rỗng). `data/eval/` cấm tới
P10. Chưa fit gì, chưa hiệu chuẩn gì (P3/P5 chưa bắt đầu).
