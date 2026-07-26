# STATUS — vị trí hiện tại của dự án

> File này là nguồn chân lý về **đang ở đâu**. Đọc đầu tiên mỗi session,
> cập nhật cuối mỗi phase (WORKFLOW.md mục 1).

Cập nhật lần cuối: 2026-07-27

## Phase hiện tại

**P2 ĐANG DỞ — hai lần smoke seed 1, cùng trượt 2/6 cổng (degree, MAC loss),
cả hai cổng đều cải thiện mạnh sau `FrameRetryLimit = 2` nhưng tổng airtime
run 2 là 105.6% toàn mạng (~47%/miền) — vẫn trên tiêu chí 50–70%, nên DỪNG
theo đúng điều kiện đã giao, chưa kết luận được cổng nào "trượt thật".
ĐANG CHỜ duyệt đề xuất: `probeInterval` 0.5 → 1.0 s/neighbor (dự phóng tổng
~55–60% mạng, giữa vùng mục tiêu). Chi tiết + bảng so run 1/run 2 ở mục cuối
`reports/P2-harness.md`. Không batch.**

Run 1 (L=7): degree 1.79, loss 92.9%, airtime probe 228.8%. Run 2 (L=2):
degree 3.82, loss 81.4%, probe 96.1%, khuếch đại ARQ 5.37 → 1.76 (dự đoán
1+q = 1.81 — khớp), route OLSR 19% → 48%, queue trơ hoàn toàn (p99 4.7 ms).

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
  `af306952b`) và **smoke run 2** cùng seed: 19 752 dòng, bảng so hai run ở
  mục cuối báo cáo. Dữ liệu hai run giữ song song:
  `data/smoke/p2-harness/seed-1{,-retry2}/`.

## Đang vướng

**Một việc duy nhất: duyệt hạ nhịp probe 2 Hz → 1 Hz/neighbor.** Trần retry
đã cắt khuếch đại đúng dự đoán (5.37 → 1.76), nhưng kênh thoáng làm beacon
decode tốt hơn → TTL admit thêm neighbor (9.0 → 11.5/node) → probe gửi tăng
28%, nuốt một phần lợi ích (giảm ×2.38 thay vì ×3.05). Số học còn lại: cần
giảm ~36% số lần gửi để tổng vào ≤ 70% mạng, và phải chừa chỗ cho admission
nở tiếp về ~14. Ở 1 Hz: attempt probe/dòng ≈ 7 ≥ sàn 5, median trials ~7–8.
Dự phòng nếu chưa đủ: TTL 2 → 1 s (đổi bias lấy variance — để sau cùng).
Sau khi duyệt: đổi đúng một tham số, chạy lại 1 seed, so ba điểm dữ liệu.

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
- **q_cbr ≈ q_probe (0.82)** — min-hop chọn link dài/biên nên CBR fail
  per-attempt cao ngang probe trên link biên. Đúng bệnh lý đề tài nhắm vào;
  cũng nghĩa là CBR không tự động "sạch" hơn probe.
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
