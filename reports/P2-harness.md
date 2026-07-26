# P2 — Harness thu dữ liệu Tier 2

Ngày 2026-07-27 | Git SHA `ba27233c5` | Config SHA `0a83692226f5…` (`sim-config/fanet-tier2.conf`)

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
