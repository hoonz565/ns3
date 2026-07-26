# STATUS — vị trí hiện tại của dự án

> File này là nguồn chân lý về **đang ở đâu**. Đọc đầu tiên mỗi session,
> cập nhật cuối mỗi phase (WORKFLOW.md mục 1).

Cập nhật lần cuối: 2026-07-27

## Phase hiện tại

**P2 ĐANG DỞ — harness viết xong và chạy đúng, smoke seed 1 TRƯỢT 2/6 cổng
(degree 1.79 < 4.0; MAC loss 92.9% > 75%). Nguyên nhân đã chẩn đoán định
lượng: bão hoà kênh do probe (airtime probe 228.8% simTime toàn mạng,
đo-lường/ứng-dụng = 48.5×). ĐANG CHỜ quyết định mức tải probe — ba đòn bẩy
kèm số trong `reports/P2-harness.md` mục cuối. Không chạy batch, không chỉnh
tham số cho tới khi duyệt.**

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
- **P2 — smoke seed 1** (SHA `ba27233c5`, dirty=False, manifest chuẩn):
  14 273 dòng, kết quả và chẩn đoán trong `reports/P2-harness.md`.

## Đang vướng

**Một việc duy nhất: chọn đòn bẩy hạ tải probe.** Chuỗi nhân quả đo được:
ước lượng thiết kế sai 7.8× vì (a) admission TTL-lỏng nhận ~9 neighbor/node
chứ không phải degree chặt 6.14, (b) khuếch đại ARQ ×5.37 (866 573 attempt /
161 475 probe gửi). Bão hoà đè beacon (degree đo sập còn 1.79) và đè OLSR
(route tồn tại ~19% thời gian → 98.8% dòng là probe-only). Ba phương án kèm
số ở cuối `reports/P2-harness.md`; đề xuất: trần retry MaxSsrc 7→1-2 toàn
mạng + probe 1 Hz. Sau khi chọn: chạy lại đúng 1 seed smoke, qua cổng rồi mới
bàn batch.

## Quyết định đã chốt

- **Ba tầng mô phỏng** (CLAUDE.md): Tier 1 kiểm chứng / Tier 2 thu dữ liệu
  (OLSR-tải + CBR + beacon + probe) / Tier 3 đánh giá (không beacon, không
  probe). Kết quả không bao giờ vượt tầng.
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
