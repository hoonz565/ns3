# P2 — Harness thu dữ liệu Tier 2

Ngày 2026-07-27 | Git SHA `ba27233c5` (run 1) / `af306952b` (run 2) / `f2d7c5d02` (run 3) | Config: `sim-config/fanet-tier2.conf`

> **Trạng thái mới nhất — sau run 3** (`FrameRetryLimit = 2`, probe 1 Hz):
> tổng airtime **60.9%** toàn mạng — vào vùng mục tiêu 50–70; **5/6 cổng
> đạt** (degree 4.97 ✓). Còn cổng MAC loss 78.3% > 75% — phân tích ở mục
> run 3 cho thấy đây là tín hiệu **ngưỡng sai, không phải tải sai**; hai
> phương án ngưỡng chờ duyệt ở đó. Kèm mục riêng: q_cbr ≥ q_probe — bằng
> chứng thực nghiệm min-hop chọn link biên. Ba lần chạy là ba điểm dữ liệu,
> giữ nguyên tuần tự bên dưới.

**Kết luận: harness chạy đúng và đo được chính nó — smoke test seed 1 TRƯỢT
2/6 cổng (degree 1.79 < 4.0; MAC loss 92.9% > 75%). Nguyên nhân định lượng
được: bão hoà kênh do probe, đúng rủi ro "tải do thiết bị đo chi phối" đã ghi
trước trong PLAN.md P2. Theo quy tắc vận hành: DỪNG, không nới ngưỡng, không
tự chỉnh tham số, không chạy batch. Chờ quyết định về mức tải probe.**

Trượt cổng ở đây là *thông tin*, không phải thất bại của phase: chính bảng
airtime tách nguồn — thứ được thêm vào smoke test để quyết định mức tải — là
cái bắt được chế độ hỏng này trước khi nó ăn 25 seed.

## Đã làm

- Sửa thiết kế trong tài liệu **trước** khi viết code (commit riêng): PLAN.md
  P2 bỏ "không chạy giao thức định tuyến" → bốn loại phát; CLAUDE.md thêm mục
  "Three simulation tiers" + "sampling constraint / dual control"
  (SE(slope) ∝ √H; P7 đo suy giảm bằng lấy mẫu thưa dữ liệu beacon 10 Hz;
  PLAN.md P8e sửa lập luận "H không ảnh hưởng LinkScore" — sai một nửa).
- `fanet-tier2.conf`: `labelWin` 2→4 (τ = 4 s theo CLAUDE.md — giá trị 2.0
  thừa kế từ scenario ngoài cây), `beaconInterval` 1.0→0.1 (4 mẫu RSSI/cửa sổ
  thì slope chìm trong nhiễu; 10 Hz = nhịp P1 đo degree 6.14), `probeBytes`
  64→540 (quy tắc 12: PPDU bằng CBR đúng từng byte), `probeInterval` đổi ngữ
  nghĩa thành mỗi-neighbor; key mới `cbrFlows/cbrBytes/cbrPps/maxQueueDelayMs/
  warmupTime`.
- `scratch/linkscore/link-dataset-fanet.cc` (30 node): kế thừa nguyên vẹn ba
  cách đo P0. Nhãn per-attempt **tách cột** `trials_probe/fails_probe` và
  `trials_cbr/fails_cbr` (gộp hay không là quyết định của P5). Tách thời gian
  cưỡng chế bằng xoay bucket: dòng chỉ ghi tại t+τ, `featureWin != labelWin`
  → NS_FATAL. Fail quy lớp theo attempt gần nhất cùng địa chỉ (MAC non-QoS
  serial hoá; sai lệch biên cửa sổ đếm ở `fails_slipped` = 26/14 273 dòng).
- ARP tĩnh (ARP reply lọt vào tử số `MacTxDataFailed` mà không vào mẫu số lọc
  size — thổi phồng fails một chiều); đo được 0 frame ARP trên sóng.
- Assert PSDU probe == PSDU CBR **đo trên sóng**, không tin số học +28: cả
  hai 576 B. Guard NS_FATAL nếu có root qdisc TrafficControl.
- `scripts/check_gates.py` (trước đó chưa tồn tại): 6 cổng đọc ngưỡng từ
  conf, exit 1 khi trượt, kèm degree-so-P1, bảng airtime tách nguồn, queue
  drop/delay, corr(retry, rssi) theo bin khoảng cách; ghi `gates.json`.
- Smoke đúng 1 seed, cây sạch, manifest `--fail-on-dirty`, binary khớp source.

## Cổng nghiệm thu (seed 1, 14 273 dòng)

| Chỉ số | Ngưỡng | Đo được | Đạt |
|---|---|---|---|
| Degree trung bình (định nghĩa P1) | ≥ 4.0 | **1.79** | ✗ |
| % dòng `retry_rate` > 0 | ≥ 10% | 96.1% | ✓ |
| % dòng 0 < pdr < 1 | ≥ 10% | 75.2% | ✓ |
| MAC loss per-attempt | ≤ 75% | **92.9%** | ✗ |
| % dòng pdr ghim 0/1 | ≤ 90% | 24.8% | ✓ |
| Dòng có fails > 0 | > 0 | 13 898 | ✓ |

## Số liệu chính — chẩn đoán bão hoà, mọi con số đo được

**Bảng airtime tách nguồn (toàn mạng / 300 s, chưa chia miền tranh chấp):**

| Nguồn | Airtime | % simTime | Frame |
|---|---|---|---|
| **probe** | **686.3 s** | **228.8%** | 866 573 |
| cbr | 13.3 s | 4.4% | 16 811 |
| beacon | 10.4 s | 3.5% | 89 950 |
| olsr | 1.1 s | 0.4% | 5 566 |
| ctrl (ACK) | 5.5 s | 1.8% | 124 973 |
| **đo lường / ứng dụng** | | **48.5×** | |

Với ~2–2.5 miền tranh chấp độc lập (R = 625 m trong hộp 2000 m), 229% toàn
mạng nghĩa là **mỗi miền ~90–115% — kênh bão hoà bởi chính thiết bị đo.**

**Chuỗi nhân quả, từng mắt xích có số:**

1. Ước lượng thiết kế 369 probe-frame/s (degree 6.14 × 2 Hz) sai **7.8×**
   vì thiếu hai hệ số nhân:
   - **Admission theo TTL nghe-≥1-beacon/2 s nhận ~9 neighbor/node** (đo:
     161 475 probe gửi / 300 s / 30 node / 2 Hz = 8.97), không phải 6.14 —
     degree chặt và tập được-probe là hai định nghĩa khác nhau, đúng cảnh báo
     "neighborTtl là knob mạnh hơn vẻ ngoài" của P1.
   - **Khuếch đại ARQ ×5.37**: 866 573 attempt / 161 475 lần gửi. Link biên
     và link chết đốt tới 7 lần thử/probe; 792 µs/attempt (= 576 B @ 6 Mbps,
     khớp lý thuyết).
2. Bão hoà đè beacon: 2.56 người nhận/beacon so với 6.47 của P1 cùng nhịp
   10 Hz cùng công suất → degree(định nghĩa P1) đo trong harness sập còn
   **1.79**, cô lập 17.0% node-thời-gian. 7 967 dòng-ứng-viên mất vì < 3 mẫu
   RSSI trong cửa sổ 4 s.
3. Bão hoà đè OLSR: HELLO/TC bị collision → **route tồn tại ~19% thời gian**
   (CBR gửi được 2 591/13 620 gói theo lịch; trace `Tx` của OnOff chỉ bắn khi
   `Send` có route — kiểm chứng trong source ns-3.45). Vì thế 98.8% dòng là
   probe-only, tức CBR gần như không đóng vai trò tạo tranh chấp giống Tier 3
   như thiết kế muốn.
4. MAC loss per-attempt 92.9% — phần lớn attempt là retry trên link không bao
   giờ giao được, đúng nghĩa "harness tự tạo loss".

**Những phần hoạt động đúng thiết kế (đáng giữ nguyên):**

- Cưỡng chế cấu trúc: 0 fail không quy được lớp; PSDU 576 = 576; 0 ARP;
  chỉ 26 cửa sổ có fail trượt biên (0.18%).
- Queue lành mạnh — **MaxDelay không phải thủ phạm**: expired 0.38%, tràn 0,
  trễ p50 13.2 ms / p99 85.1 ms / max 124.8 ms. Airtime đốt trên sóng (retry),
  không phải backlog trong queue. p99 gần cap 100 ms là hệ quả của bão hoà,
  không phải nguyên nhân.
- Median trials/dòng = 39 (sàn 5 dư); phân bố nhãn có đuôi thật: 75.2% dòng
  ở 0 < pdr < 1, ghim-1.0 chỉ 2.6% — **không có ceiling effect**.
- corr(retry_rate, rssi_mean): toàn cục −0.86; theo bin: −0.43 / −0.66 /
  −0.44 / −0.23 / −0.03 (0→800+ m). Âm sâu, nhưng đo trong môi trường tranh
  chấp do probe tạo ra nên **không dùng được để kết luận điểm vận hành** —
  β_mac fit ở đây đo tranh chấp probe, thứ không tồn tại ở Tier 3.

## Quyết định đã chốt (trong phạm vi được duyệt)

- Bốn loại phát + nhãn tách cột probe/CBR — đã vào PLAN.md/CLAUDE.md/conf.
- RSSI chỉ từ beacon; probe admission theo beacon TTL; MaxDelay 100 ms trên
  queue chung; ARP tĩnh; gỡ root qdisc (ns-3.45 tự cài FqCoDel khi gán địa
  chỉ — guard bắt được ở lần chạy đầu, đã gỡ và giữ guard).
- Dual control + ràng buộc lấy mẫu 1/H ghi vào CLAUDE.md; việc lấy mẫu thưa
  ghi vào P7.

## KHÔNG làm

- **Không chạy batch, không chạy thêm seed nào** — cổng trượt.
- **Không chỉnh bất kỳ tham số kịch bản nào để cổng đạt** (không đổi
  probeInterval/neighborTtl/cbrPps/TxPower…). Các phương án ở mục cuối là đề
  xuất kèm số, chưa thực hiện.
- **Không đo OLSR** ngoài một con số phụ (route ~19%) dùng làm bằng chứng bão
  hoà — OLSR vẫn là máy tạo tải, không phải đối tượng đo.
- Không viết analysis/fit gì (P5), không hiệu chuẩn ngưỡng (P3).

## Bất thường / nghi ngờ

1. **corr(retry, rssi) âm sâu ngay trong bão hoà (−0.86)** — quy tắc 13 dự
   đoán gần 0 khi bão hoà. Lý giải: bão hoà ở đây không đối xứng — gánh retry
   dồn lên link yếu (thử nhiều lần hơn), nên tương quan với RSSI vẫn âm.
   Không mâu thuẫn với kết luận trượt cổng; chỉ có nghĩa là chỉ số corr một
   mình không đủ chẩn đoán bão hoà — bảng airtime mới đủ.
2. **Tx trace của OnOff chỉ đếm gói có route** — `cbr_app_tx` là "gói đã rời
   node nguồn", không phải "gói theo lịch". Số 19% suy ra từ đó; nếu sau này
   cần chính xác thì đếm cả `Send` thất bại.
3. **Ước lượng airtime trong kế hoạch sai 7.8×.** Ghi lại làm bài học: mọi
   ước lượng tải probe phải nhân (tập admission theo TTL lỏng, không phải
   degree chặt) × (khuếch đại ARQ ~5× khi có link chết trong tập).
4. Degree 1.79 là **degree đo trong bão hoà**, không phải hình học thay đổi —
   `positions.csv` cùng phân bố với P1. Không dùng con số này nói về topology.

## Đầu vào cho phase sau (và cho quyết định mức tải)

| Đường dẫn | Nội dung |
|---|---|
| `data/smoke/p2-harness/seed-1/` | `rows.csv` (14 273 dòng), `positions.csv`, `meta.json`, `summary.json`, `gates.json`, `run_manifest.json` |
| `scratch/linkscore/link-dataset-fanet.cc` | Harness — logic đo đã kiểm, chỉ mức tải là sai |
| `scripts/check_gates.py` | Cổng + chẩn đoán, dùng lại nguyên vẹn cho mọi run P2 |

**Ba đòn bẩy khả dĩ, kèm số để chọn (chưa thực hiện — chờ duyệt):**

1. **Hạ trần retry của ARQ** (`MaxSsrc` 7 → 1–2, toàn mạng). Đòn bẩy lớn
   nhất: khuếch đại ×5.37 → ~×1.5–2, riêng nó đưa probe từ ~229% về ~65–85%
   toàn mạng (~26–34%/miền). Nhãn per-attempt **không đổi định nghĩa** — mỗi
   attempt vẫn là một phép thử Bernoulli, chỉ bớt phép thử lãng phí trên link
   chết; ETX cũng đo xác suất một-lần-thử. Tác dụng phụ phải khai báo: CBR
   chịu cùng trần retry (loss ứng dụng tăng — chấp nhận được vì CBR chỉ tạo
   tải), và phân bố "trials/dòng" giữa link tốt–xấu đều hơn.
2. **Giảm nhịp probe 2 Hz → 1 Hz/neighbor**: trials/dòng 8 → 4 (vẫn ≥
   minTrials = 2, nhưng dưới sàn phân tích `trials ≥ 5` — bù được vì CBR và
   nhiều cửa sổ gộp; hoặc τ giữ 4 s và chấp nhận hàng thưa hơn). Tuyến tính:
   probe còn ~115% toàn mạng — không đủ một mình.
3. **Thắt admission** (TTL 2 → 1 s hoặc yêu cầu ≥ 2 beacon): tập probe ~9 →
   gần 6; nhưng chính conf đã cảnh báo TTL ngắn tái-kiểm-duyệt tương quan với
   nhãn — đòn bẩy này đổi bias lấy variance, nên để sau cùng.

Đề xuất của tôi (chỉ là đề xuất): **1 + 2** — trần retry thấp cho cả mạng và
probe 1 Hz, dự kiến đưa tổng đo-lường về ~50–60% toàn mạng (~20–25%/miền),
CBR/OLSR khi đó mới thở được và tỉ lệ đo-lường/ứng-dụng tụt từ 48× về ~5×.
Sau khi anh/chị chọn, chạy lại đúng 1 seed smoke rồi mới bàn tiếp.

---

# Lần chạy 2 — `FrameRetryLimit = 2`, giữ probe 2 Hz (2026-07-27)

Git SHA `af306952b` | manifest `data/smoke/p2-harness/seed-1-retry2/run_manifest.json`, dirty=False | cùng seed 1

Thay đổi so với run 1 đúng một tham số: `frameRetryLimit = 2` (=
dot11ShortRetryLimit — **`MaxSsrc`/`MaxSlrc` đã OBSOLETE từ ns-3.44**, knob
còn hoạt động là `WifiMac::FrameRetryLimit`, kiểm trong source: nghĩa là số
*attempt* tối đa mỗi frame, drop khi retry count chạm limit). Quyết định toàn
hệ thống, đã vào bảng Simulation Setup của CLAUDE.md/PLAN.md cùng hai lý do
(chuỗi retry tương quan ~√5; retry dai dẳng phản tác dụng ở tốc độ FANET).

## Cổng nghiệm thu (seed 1, 19 752 dòng)

| Chỉ số | Ngưỡng | Run 1 | **Run 2** | Đạt |
|---|---|---|---|---|
| Degree trung bình (định nghĩa P1) | ≥ 4.0 | 1.79 | **3.82** | ✗ (sát) |
| % dòng `retry_rate` > 0 | ≥ 10% | 96.1% | 94.9% | ✓ |
| % dòng 0 < pdr < 1 | ≥ 10% | 75.2% | 68.0% | ✓ |
| MAC loss per-attempt | ≤ 75% | 92.9% | **81.4%** | ✗ |
| % dòng pdr ghim 0/1 | ≤ 90% | 24.8% | 32.0% | ✓ |
| Dòng có fails > 0 | > 0 | 13 898 | 18 892 | ✓ |

**Vẫn trượt 2/6, cả hai đều cải thiện mạnh và đều còn bị bão hoà đè** — tổng
airtime chưa vào vùng mục tiêu nên chưa kết luận được cổng nào là "trượt
thật" (tiêu chí dừng thứ hai của lượt này chưa kích hoạt: chưa vào 50–70%).

## Bộ số so sánh yêu cầu

| Đại lượng | Run 1 (L=7) | **Run 2 (L=2)** | Tham chiếu |
|---|---|---|---|
| **Tổng airtime mọi nguồn** | 716.6 s = **238.9%** mạng (~106%/miền) | 316.9 s = **105.6%** mạng (~**47%**/miền) | mục tiêu 50–70% mạng |
| — probe | 686.3 s (228.8%) | 288.3 s (96.1%) | |
| — beacon / cbr / olsr / ctrl | 10.4 / 13.3 / 1.1 / 5.5 s | 10.4 / 12.0 / 1.4 / 4.8 s | |
| Khuếch đại ARQ (attempts/sends) | ×5.37 | **×1.76** | dự đoán 1.93 tại q=0.929; tại q đo được 0.814 thì 1+q = 1.81 — khớp |
| Probe gửi | 161 475 | **207 075 (+28%)** | tập admission nở ra khi kênh thoáng |
| Neighbor được probe TB/node | 8.97 | **11.50** | degree chặt 6.14; loose P1 ~14.4 |
| Degree (định nghĩa P1) | 1.79 | **3.82** | P1: 6.14; cô lập 17.0% → **1.9%** (P1: 0.6%) |
| Route OLSR tồn tại | 19.0% | **48.0%** | lịch 13 620 gói, gửi được 6 536 |
| Dòng probe-only | 98.8% | **97.1%** | CBR vẫn gần như vắng trong nhãn |
| Median trials/dòng | 39 | **14** | sàn phân tích 5 |
| corr(retry, rssi) toàn cục | −0.858 | **−0.859** | theo bin: −0.26/−0.60/−0.58/−0.37/−0.09 (0→800+ m); sâu nhất ở 200–600 m |
| Queue | p99 85 ms, expired 0.38% | **p99 4.7 ms, expired 0, tràn 0** | MaxDelay giờ hoàn toàn trơ — đúng "setting trơ và an toàn" |
| q per-attempt (probe / cbr) | 0.931 / 0.813 | 0.814 / **0.823** | q_cbr ≈ q_probe: min-hop chọn link dài/biên — đúng bệnh lý mà đề tài nhắm vào |

Kiểm chứng phụ giữ nguyên chất lượng: 0 ARP, 0 fail không quy được lớp, PSDU
576 = 576, 22 cửa sổ fail trượt biên (0.11%).

## Chẩn đoán: vì sao ×2.9 dự kiến chỉ thành ×2.4

Trần retry cắt khuếch đại đúng như dự đoán (5.37 → 1.76, lý thuyết 1.81),
nhưng **kênh thoáng hơn làm beacon decode tốt hơn (230 k → 391 k lần nhận),
TTL 2 s admit thêm neighbor (~9.0 → ~11.5/node), probe gửi tăng 28%** — phản
hồi dương giữa độ thoáng kênh và kích thước tập admission nuốt mất một phần
lợi ích. Airtime probe giảm ×2.38 thay vì ×3.05. Nếu tải giảm tiếp, admission
còn nở về phía loose-degree ~14 — phải tính hệ số này vào mọi dự đoán tải
probe từ nay về sau (cùng bài học với hệ số ×5.37 của run 1).

Degree 3.82 vẫn thấp hơn 6.14 vì kênh vẫn mất ~33% beacon so với kênh sạch
(391 k nhận so với 582 k của P1 cùng nhịp, cùng công suất) — nhất quán với
~47%/miền còn quá cao, chưa phải nguyên nhân nào khác ngoài bão hoà.

## Trạng thái theo tiêu chí đã giao

Tổng airtime 105.6% toàn mạng > 70% → **DỪNG theo đúng điều kiện 4, không tự
hạ probe.** Chưa vào được vùng 50–70% nên chưa trả lời được câu hỏi "vào vùng
mà degree vẫn trượt thì nguyên nhân khác bão hoà" — bước tiếp theo phải đưa
tải vào vùng trước đã.

## Đề xuất bước tiếp (chưa thực hiện)

Số học từ run 2: airtime probe = sends × amp × 792 µs. Muốn tổng ≤ 70% mạng
(probe ≤ ~186 s) cần sends ≤ ~133 k, tức **giảm ~36% số lần gửi**, và phải
chừa chỗ cho admission nở tiếp khi kênh thoáng (11.5 → ~14 neighbor).

1. **`probeInterval` 0.5 → 1.0 s/neighbor** (đề xuất chính). Sends ~×0.5 kể
   cả khi admission nở đầy (~14 neighbor × 1 Hz = 14 gửi/s/node so với 23
   hiện tại): probe ≈ 130–150 s ≈ 43–50% mạng, tổng ≈ **55–60% mạng
   (~24–27%/miền) — giữa vùng mục tiêu**, còn dư biên. Chi phí: attempt
   probe/dòng ≈ 4 gửi × 1.8 ≈ 7 — vẫn trên sàn `trials ≥ 5`; median trials
   ~7–8 (run 2: 14). Cái giá này giờ rẻ hơn lúc trước vì amp đã bị chặn ở
   ≤2 — lập luận "giữ 2 Hz để giữ độ chính xác nhãn" đúng ở thời điểm quyết
   nhưng bị phản hồi admission (+28% sends) ăn mất phần dự phòng.
2. *(dự phòng nếu 1 chưa đủ)* TTL 2 → 1 s — thắt admission, nhưng đổi bias
   lấy variance như conf đã cảnh báo; chỉ dùng nếu sau bước 1 tổng vẫn > 70%.

Sau khi anh/chị duyệt: đổi đúng một tham số, chạy lại 1 seed, so ba điểm dữ
liệu rồi mới bàn cổng degree/loss.

---

# Lần chạy 3 — `probeInterval` 1.0 s/neighbor (2026-07-27)

Git SHA `f2d7c5d02` | manifest `data/smoke/p2-harness/seed-1-probe1hz/run_manifest.json`, dirty=False | cùng seed 1

Thay đổi so với run 2 đúng một tham số: `probeInterval` 0.5 → 1.0 s.

## Cổng nghiệm thu (seed 1, 21 427 dòng) — 5/6 đạt

| Chỉ số | Ngưỡng | Run 1 | Run 2 | **Run 3** | Đạt |
|---|---|---|---|---|---|
| Degree trung bình (định nghĩa P1) | ≥ 4.0 | 1.79 | 3.82 | **4.97** | **✓** |
| % dòng `retry_rate` > 0 | ≥ 10% | 96.1% | 94.9% | 87.5% | ✓ |
| % dòng 0 < pdr < 1 | ≥ 10% | 75.2% | 68.0% | 54.6% | ✓ |
| MAC loss per-attempt | ≤ 75% | 92.9% | 81.4% | **78.3%** | **✗** |
| % dòng pdr ghim 0/1 | ≤ 90% | 24.8% | 32.0% | 45.4% | ✓ |
| Dòng có fails > 0 | > 0 | 13 898 | 18 892 | 18 916 | ✓ |

## Tải: VÀO vùng mục tiêu, dự phóng trúng

| Đại lượng | Run 1 | Run 2 | **Run 3** |
|---|---|---|---|
| **Tổng airtime mọi nguồn** | 238.9% | 105.6% | **60.9% mạng (~27%/miền)** — mục tiêu 50–70% ✓ |
| — probe / beacon / cbr / olsr / ctrl | 228.8 / 3.5 / 4.4 / 0.4 / 1.8 % | 96.1 / 3.5 / 4.0 / 0.5 / 1.6 % | **49.9** / 3.5 / 6.0 / 0.5 / 1.0 % |
| Probe gửi | 161 475 | 207 075 | **110 403** (= 207k × 0.5 × 1.07 — admission nở tiếp 11.5 → 12.3 neighbor, đã dự phòng) |
| Khuếch đại ARQ | 5.37 | 1.76 | **1.71** (1 + q̄ = 1.78 tại q_probe 0.776 — khớp) |
| Degree (P1: 6.14) | 1.79 | 3.82 | **4.97**, cô lập 0.87% (P1: 0.6%) |
| Route OLSR tồn tại | 19.0% | 48.0% | **70.1%** |
| Dòng probe-only | 98.8% | 97.1% | 96.0% |
| Queue p50 / p99 ms | 13.2 / 85.1 | 1.8 / 4.7 | **0.9 / 4.1**, 0 drop |
| fails_slipped | 26 (0.18%) | 22 (0.11%) | **13 (0.06%)** — giảm đơn điệu theo L rồi theo tải, đúng chiều bắt buộc; logic quy lớp không có vấn đề |

Dự phóng ~60–68% trong commit `076b439bf` (gộp độ lợi admission 0.28): đo được
60.9%. Admission thực tế +7% thay vì +28% vì đã gần trần loose (~12.3/14).

**Chi phí đã lường trước của 1 Hz — biên mỏng thật:** `trials_future`
p10/p25/p50/p90 = **4 / 5 / 7 / 8**, tức **16.2% dòng có trials < 5** (run 2:
1.2%). Với GLM nhị thức thì dòng ít trial là quan sát hợp lệ trọng số thấp
(conf, chú thích `minTrials`), nhưng nếu P5 lọc cứng `trials ≥ 5` theo
CLAUDE.md thì mất 16.2% dòng — mâu thuẫn nhỏ giữa hai tài liệu, cần chốt ở
P4/P5, ghi ở đây để không quên. Ghim 0/1 tăng 32.0% → 45.4% (artifact n nhỏ
đã ghi trong conf), vẫn xa cổng 90%.

## Cổng MAC loss 78.3%: tín hiệu ngưỡng sai, không phải tải sai

Đối chiếu đúng lập luận đã dùng cho degree: **mọi chỉ báo sức khoẻ kênh khác
đều nói "không sập"** — degree 4.97 (qua cổng), cô lập 0.87% ≈ 0.6% của P1,
queue rỗng (p99 4.1 ms, 0 drop), route 70%, chiếm dụng 60.9% trong vùng. Con
số 78.3% được **phân rã trọn vẹn bằng vị trí đặt trial trên trục khoảng
cách** (bảng bin bên dưới): 53.5% trials probe nằm ở ≥ 600 m, nơi q =
0.91–0.99 **do vật lý** (R(0.5) = 625 m — quá mép waterfall thì per-attempt
phải tiến về 1). Đó là thiết kế đang làm đúng việc: quy tắc 12 bắt probe theo
beacon để giữ đuôi rất-xấu neo đáy sigmoid; sàn −101 dBm làm beacon nghe được
xa hơn hẳn tầm unicast hữu dụng, nên tập admission chứa cái đuôi ấy.

Chữ ký phân biệt với sập kênh: sập nâng q **mọi bin kể cả gần** (run 1→3, bin
0–200 m: q_probe 0.098 → 0.055; bin 200–400 m: 0.370 → 0.244 — bin gần sạch
dần khi kênh thoáng, bin xa đứng im ở trần vật lý). Ngưỡng 75% thừa kế từ
scenario ngoài cây đo ở 20 dBm/−82 (R(0.5) = 294 m, đuôi bị sàn −82 cắt cụt)
— chưa bao giờ được hiệu chuẩn cho cấu hình 19/−101 vốn cố ý đo đuôi dài hơn.

**Đề xuất (chưa sửa, chờ duyệt):**

1. *Tối thiểu:* `gateLossMax` 75 → **85** — bắt sập thật (run 1 bão hoà:
   92.9%) và tha cho thiết kế không-kiểm-duyệt (78.3% ở kênh khoẻ).
2. *Tách bạch hơn (khuyến nghị):* thêm cổng **q vùng gần** — q per-attempt
   gộp trên link < 400 m ≤ **0.30**. Sập nâng bin gần, đuôi cố ý đo không
   đụng bin gần: run 3 = 0.216 ✓, run 2 = 0.33 ✗, run 1 tệ hơn nữa — chỉ số
   bám đúng bão hoà mà không phạt việc đo đuôi. Giữ `gateLossMax = 85` làm
   lưới sau. Chỉ đổi check_gates.py + conf, không đụng scenario.

---

# q_cbr ≥ q_probe — bằng chứng thực nghiệm cho tiền đề đề tài (mục riêng)

**Phát biểu:** trên cùng một mạng, cùng cỡ frame, cùng ARQ, các link mà OLSR
min-hop *chọn để chở dữ liệu* giao gói per-attempt **kém hơn** tập link được
probe rải đều: run 3 (kênh khoẻ) q_cbr = **0.841** so với q_probe = **0.776**
— và khoảng cách này **nới ra khi OLSR có nhiều route hơn** (run 2 → run 3:
route 48% → 70%, hiệu q_cbr − q_probe từ +0.009 lên **+0.065**). Càng được
định tuyến nhiều, chất lượng link trên đường càng tệ đi — vì metric là hop
count: ít hop nhất = link dài nhất = link vùng biên.

Phân rã theo bin tách được **hai cơ chế riêng biệt**, cả hai đều vào
Motivation:

| bin | q_probe | q_cbr | % trials probe | % trials CBR |
|---|---|---|---|---|
| 0–200 m | 0.055 | 0.117 | 2.3% | 3.2% |
| 200–400 m | 0.244 | **0.570** | 13.0% | 18.3% |
| 400–600 m | 0.630 | **0.870** | 31.2% | **40.5%** |
| 600–800 m | 0.913 | 0.980 | 39.9% | 31.9% |
| ≥800 m | 0.991 | 0.999 | 13.6% | 6.1% |

1. **Cơ chế đặt-link (placement):** min-hop dồn **72.4%** trials on-path vào
   400–800 m — tại và quá mép waterfall (R(0.5) = 625 m). Không phải quan sát
   hệ quả nữa mà thấy thẳng cơ chế: chọn ít hop là chọn link dài.
2. **Cơ chế cùng-khoảng-cách (excess):** ở *cùng bin*, q_cbr vẫn cao hơn
   q_probe ở mọi bin — nổi nhất 200–400 m: 0.570 so với 0.244, gấp **2.3×**.
   Link đang chở dữ liệu chịu tự tranh chấp và hidden-terminal dọc tuyến —
   đúng cái confound "không nằm trong feature" đã là lý do tách cột
   `*_probe`/`*_cbr` (quyết định C4): tính khả hoán giữa on-path và off-path
   là câu hỏi thật, P5 phải kiểm như kế hoạch.

Hệ quả đã ghi vào PLAN.md P6 (commit `458a59920`): so regret ba chiều
**oracle / LinkScore / min-hop** — regret của min-hop là con số Motivation,
miễn phí từ dữ liệu đã thu.

*Caveat trung thực:* q_cbr đo trên tập link OLSR chọn, vốn phải qua điều kiện
HELLO hai chiều — có kiểm duyệt riêng của nó; và CBR chỉ chiếm 10.7% tổng
attempt nên SE của q_cbr theo bin rộng hơn q_probe. Kết luận định tính (dồn
vào bin xa; excess cùng-bin) vững qua cả ba run; con số chính xác để trích
vào paper nên lấy từ batch nhiều seed, không phải smoke 1 seed.

## Trạng thái sau run 3

Tải ĐÃ vào vùng (60.9%), 5/6 cổng đạt, harness sạch về mọi kiểm chứng nội
tại (0 ARP, 0 fail không quy lớp, PSDU 576=576, slipped giảm đơn điệu). Còn
đúng một quyết định: **ngưỡng cổng loss** (hai phương án ở trên). Nếu duyệt
phương án ngưỡng: chạy lại check_gates trên chính dữ liệu run 3 (không cần
mô phỏng lại), qua cổng thì xin duyệt batch 25 seed theo `seedsCalibration/
Train/Test` của conf.

---

# Chốt cổng + chuẩn bị batch (2026-07-27, sau duyệt phương án b)

Git SHA `92102bfff`…`cb337bb9c` | run 4: `data/smoke/p2-harness/seed-1-hops/`, dirty=False

## Cổng đã chốt — 7 cổng, run 3 qua tất cả

Theo phương án (b) với ba điều chỉnh đã duyệt:

- **Cổng bão hoà chính: q gộp (probe+CBR) trên link < 0.64·`rHalfM`** ≤
  `gateNearQMax` = 0.35. `rHalfM = 625` là key conf (R(0.5) đo ở P1) — vùng
  gần **suy từ tầm đo được, không phải hằng số 400** (ngưỡng 75 cũ sai chính
  vì là hằng số thừa kế; không lặp lại lỗi đó).
- **`gateLossMax` 75 → 85, đổi vai trò thành lưới SẬP KÊNH** — không phải chỉ
  báo chất lượng dữ liệu; harness không-kiểm-duyệt ở 19/−101 buộc phải có
  loss tổng cao. Hai vai trò, hai cổng, ghi rõ trong conf.
- Ngưỡng 0.35 hiệu chuẩn từ đúng **hai điểm** (run 2 bão hoà nhẹ / run 3
  khoẻ), mỗi điểm một seed → cố ý dễ dãi, **xem lại sau batch đầu** (ghi
  trong conf).

Kiểm chéo cả ba run với bộ cổng mới:

| Run | q vùng gần | Loss tổng (lưới 85) | Degree | Kết quả |
|---|---|---|---|---|
| 1 (bão hoà nặng) | **0.680 ✗** | **92.9% ✗** | **1.79 ✗** | trượt 3 cổng sức khoẻ |
| 2 (bão hoà nhẹ) | 0.343 ✓ *(sát)* | 81.4% ✓ | **3.82 ✗** | vẫn bị chặn (degree) |
| 3 (khoẻ) | 0.265 ✓ | 78.3% ✓ | 4.97 ✓ | **7/7 ✓** |

*Ghi chú trung thực:* near-q gộp của run 2 là **0.343**, không phải 0.33 (số
cũ là probe-only) — ngưỡng 0.35 tha run 2 ở cổng này, run 2 bị bắt nhờ cổng
degree. Biên hẹp đúng như đã lường khi chọn 0.35 thay 0.30; sau batch đầu có
phân bố per-seed thì hiệu chuẩn lại.

## Bỏ ngưỡng trials (CLAUDE.md + PLAN.md đã sửa)

Giữ mọi dòng harness phát ra — GLM nhị thức trọng số theo n, đó chính là
điều phân biệt nó với hồi quy trên tỉ lệ. Ngưỡng `trials ≥ 5` là di sản của
tư duy tỉ-lệ-liên-tục và **có hại**: link biên chết sớm → ít attempt → trials
tương quan với nhãn → lọc theo trials là kiểm duyệt đúng loại đã tránh ở mọi
chỗ khác. `minTrials = 2` giữ làm bộ lọc vệ sinh của harness. Phân bố trials
(run 3: p10/p25/p50/p90 = 4/5/7/8) vào Limitations — mâu thuẫn conf/CLAUDE.md
ghi ở mục run 3 đóng lại.

## Run 4 — đo hop CBR, kèm phép kiểm determinism miễn phí

Thêm phép đo thuần quan sát (tra bảng OLSR của node nguồn mỗi giây/flow,
không RNG, không phát gì). **`rows.csv` của run 4 trùng md5 từng byte với
run 3** — xác nhận phép đo không nhiễu vào mô phỏng, và harness tái lập
deterministic. `seed-1-hops/` thành dữ liệu smoke chuẩn (= run 3 + hop).

**Histogram hop (1 710 flow-giây):** no_route 508 (29.7%) · 1 hop 345 · 2 hop
514 · 3 hop 215 · 4 hop 88 · ≥5 hop 40. Trong flow-giây có route: **71.3% ≥
2 hop, trung bình 2.15 hop** → tiền đề "CBR tạo tranh chấp chuyển tiếp giống
Tier 3" **đứng vững**. Route availability từ bảng định tuyến = 70.3%, khớp
độc lập với 70.1% ước từ app (hai đường đo, một con số).

**Lệch 9× (21.3% đo vs 2.4% dự đoán 3-hop) phân rã trọn, không còn bí ẩn:**

    dự đoán 3-hop:            (1−q²)³ = 2.5%          [giả định sai: 3 hop]
    × hop-mix thật (2.15 hop): → 12.6%                 [×5.0]
    × dị biệt q (Jensen):      → 21.3% đo được         [×1.69]

q̄ = 0.841 trọng số theo **attempt** nên bị link xấu (sinh nhiều attempt) kéo
lên; gói giao thành công dồn về đường tốt hơn trung bình. Không có drop IP
trước MAC đáng kể, không lỗi đếm.

*Limitations ghi thêm:* 28.7% flow-giây có route là 1-hop và 29.7% không có
route — CBR đa chặng nhưng không phải luôn luôn; con số này phụ thuộc cách
rút cặp (src, dst) ngẫu nhiên và sẽ dao động theo seed.

## Seed: 40 = 5 / 30 / 5 (đã ghi vào conf: 1-5 / 6-35 / 36-40)

Mâu thuẫn conf (15 train) vs CLAUDE.md quy tắc 6 (30–40) chốt nghiêng về quy
tắc 6: cluster-robust SE cần 30–50 cluster, cluster là seed. **Thời gian chạy
thực run 3: ~2.9 phút** (manifest → summary.json) → 40 seed ≈ 2 h tuần tự,
ngắn hơn nếu chạy song song vài process. Dưới ngưỡng 10 phút/run của tiêu
chí "chạy qua đêm" rất xa.

## Sẵn sàng batch — một câu hỏi vận hành chờ quyết

Mọi thứ đã chốt: cổng (7/7 trên smoke chuẩn), tham số (conf), phương pháp
(tài liệu). Đề xuất kế hoạch batch khi được duyệt:

- Chạy **seeds 1–35** (5 calibration → `data/calib/`, 30 training →
  `data/train/`), mỗi run manifest riêng `--fail-on-dirty`, check_gates từng
  seed, bảng tổng hợp cổng theo seed trước khi sang P3.
- **Câu hỏi cần anh/chị quyết: sinh 5 seed evaluation (36–40) bây giờ hay để
  P10?** Sinh ngay = trọn bộ cùng binary/config, nhưng `data/eval/` nằm đó
  ba phase liền với rủi ro chạm nhầm; để P10 = sinh sau từ đúng binary+config
  đã ghim hash trong manifest (tái lập kiểm chứng được), đổi lại phải giữ
  binary không trôi. Tôi nghiêng về **để P10** — manifest tồn tại chính để
  bảo đảm điều đó, và vùng cấm rỗng thì không ai chạm nhầm được.
