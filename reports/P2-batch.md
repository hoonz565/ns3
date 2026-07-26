# P2 — Batch dữ liệu Tier 2 (35 seed) và ba phân tích tiền-P5

Ngày 2026-07-27 | Git SHA `c90310d86` (toàn batch, cây sạch suốt — mọi manifest cùng SHA, cùng `binary_sha256`) | Config `sim-config/fanet-tier2.conf`

**Kết luận: 35/35 seed PASS cả 7 cổng. `data/calib/` = seeds 1–5 (105 869
dòng), `data/train/` = seeds 6–35 (652 432 dòng), tổng 758 301 dòng.
`data/eval/` rỗng — bất biến `run_tests.sh` giữ nguyên. Ba phân tích
tiền-P5 xong trên dữ liệu đã có, không chạy thêm mô phỏng nào. P2 HOÀN
TẤT — chờ duyệt sang P3.**

## Đã làm

- Batch calibration 5 seed (báo cáo ở `reports/P2-harness.md` mục cuối) rồi
  batch training 30 seed sau khi được duyệt, qua `scripts/run_p2_batch.sh`
  (manifest `--fail-on-dirty` → sim → check_gates từng seed; `run_tests.sh`
  trước seed đầu). 0 abort, 0 dirty, 0 seed trượt — không điều kiện dừng
  nào kích hoạt.
- `analysis/validate/p2_batch_stats.py`: ba phân tích trên `rows.csv` gộp
  35 seed; kết quả máy-đọc-được ở `data/train/batch_stats.json`.
- PLAN.md P5 thêm Limitations: kiểm duyệt vật lý tại sàn detect (chi tiết
  bên dưới).

## Cổng nghiệm thu — phân bố theo 35 seed

| Đại lượng | mean ± SD | min … max | Ngưỡng |
|---|---|---|---|
| near-q | 0.281 ± 0.022 | 0.239 … **0.326** | ≤ 0.35 |
| degree | 4.92 ± 0.19 | 4.45 … 5.21 | ≥ 4.0 |
| MAC loss % | 78.8 ± 1.0 | 76.7 … 80.4 | ≤ 85 (lưới sập) |
| rows/seed | 21 666 ± 796 | 19 740 … 22 927 | — |
| median trials | 7 (mọi seed) | 7 … 7 | — |
| route availability % | 75.0 ± 5.9 | 61.5 … 91.4 | — |
| % dòng thiếu retry | 0.65 ± 0.05 | 0.53 … 0.73 | — |

**Ghi chú hiệu chuẩn near-q (cho lần xem lại đã hẹn):** SD toàn tập là
**0.022, gấp ~3× SD của 5 seed calib (0.008)**, và seed cực đại chạm 0.326 —
cách ngưỡng 0.35 chỉ ~1 SD nữa. 35/35 vẫn qua, nhưng biên mỏng hơn calib gợi
ý; khi hiệu chuẩn lại 0.35 dùng phân bố này (mean + 3SD ≈ 0.35 — ngưỡng hiện
tại hoá ra nằm đúng mép 3-sigma), và nhớ quy tắc conf: cổng đọc liên hợp với
degree.

## Phân tích 1 — `rssi_n` theo bin: slope ồn nhất đúng vùng quan trọng nhất

| bin | p10 | p50 | p90 | SE(slope) minh hoạ* |
|---|---|---|---|---|
| 0–200 m | 36 | 38 | 40 | ~0.22 dB/s |
| 200–400 m | 29 | 35 | 39 | ~0.30 dB/s |
| 400–600 m | 16 | 24 | 32 | ~0.49 dB/s |
| 600–800 m | 5 | **10** | 18 | ~0.75 dB/s |
| ≥800 m | 3 | **4** | 7 | ~1.19 dB/s |

\* SE = σ_fading/(s_t·√n) với s_t ≈ 4/√12 s, σ theo tier Nakagami tại bin
(1.59 dB gần, 2.76 dB xa), n = p50 của bin. Cùng cửa sổ 4 s, **sai số đo
slope ở 600–800 m gấp ~3.4× vùng gần** (mất beacon → n từ 38 tụt còn 10) —
trong khi slope thật ở đó ~0.6 dB/s, tức t-stat mỗi cửa sổ chỉ ~0.8.

**Hệ quả P5 phải dùng khi diễn giải β_slope:** nhiễu đo của feature slope
là errors-in-variables → **attenuation bias kéo β_slope về 0, mạnh nhất ở
link biên** — đúng vùng công thức cần phân biệt. Nếu β_slope yếu, phải tách
"slope không mang tin" khỏi "slope bị đo ồn ở nơi nó đáng lẽ mang tin nhất"
(ví dụ: fit riêng tập n ≥ 20 để so — dữ liệu có sẵn cột `rssi_n`).

## Phân tích 2 — SD liên-link vs trong-link: RSSI không phân biệt link trong cùng bin

Nhóm = (seed, src, dst, bin) với ≥ 3 dòng; trong-link = SD của `rssi_level`
trong nhóm theo thời gian; liên-link = SD giữa các mean nhóm cùng bin.

| bin | liên-link SD | trong-link SD (median) | tỉ số | nhóm |
|---|---|---|---|---|
| 0–200 m | 1.96 dB | 2.91 dB | 0.68 | 3 592 |
| 200–400 m | 0.98 dB | 1.85 dB | 0.53 | 18 206 |
| 400–600 m | 0.38 dB | 0.95 dB | 0.40 | 25 510 |
| 600–800 m | 0.21 dB | 0.55 dB | **0.39** | 27 933 |
| ≥800 m | 0.22 dB | 0.40 dB | 0.54 | 18 549 |

**Tỉ số < 1 ở mọi bin**: trong một bin khoảng cách, dải mean-RSSI giữa các
link hẹp hơn nhiễu thời gian của chính một link — mean RSSI không nhận diện
được link nào tốt hơn link nào khi đã biết khoảng cách. Điều này **đúng theo
cấu tạo kênh**: chuỗi loss LogDistance + Nakagami của ns-3 không có shadowing
per-link (không hằng số riêng từng cặp), nên `rssi_level` ≈ f(d) + nhiễu
fading. Không phải lỗi đo — là tính chất mô hình kênh phải khai báo: trong
mô phỏng này, phần "kênh thật khác hình học" mà RSSI mang được nằm ở **mức
fading tức thời và slope**, không nằm ở mean-level-vượt-trên-khoảng-cách.
(Ăn khớp với CLAUDE.md quy tắc 11: kiểm tra LinkScore-hơn-distance bằng
t-stat của β_slope, không phải bằng σ fading.)

Lưu ý định nghĩa: trong-link SD bao gồm cả trôi khoảng cách trong bin suốt
run (không chỉ fading), nên 2.91 dB ở bin gần > σ fading 1.59 dB là dự kiến.

## Phân tích 3 — ma trận tương quan ba feature (753 366 dòng có retry)

Toàn tập 35 seed (Pearson; cặp chứa retry chỉ tính trên dòng có retry):

| | level~slope | level~retry | slope~retry |
|---|---|---|---|
| **toàn tập** | **+0.000** | **−0.793** | +0.002 |
| 0–200 m | −0.256 | −0.136 | +0.079 |
| 200–400 m | −0.440 | −0.461 | +0.200 |
| 400–600 m | −0.345 | −0.522 | +0.202 |
| 600–800 m | −0.123 | −0.366 | +0.089 |
| ≥800 m | −0.050 | −0.088 | +0.016 |

- **corr(level, retry) = −0.793 giữ nguyên mức một-seed trên toàn tập** —
  hai feature chia **r² ≈ 63%** thông tin. Cùng với việc retry là nhãn trễ
  (CLAUDE.md quy tắc 3), điều này chốt cứng yêu cầu: **P5 phải trả lời "RSSI
  thêm gì vượt trên retry" bằng số** (AR baseline trong bảng đối chứng),
  không được kể ba feature như ba nguồn tin độc lập.
- level~slope = 0.000 toàn cục → không cộng tuyến, VIF ≈ 1 (mối lo "known
  trap" của CLAUDE.md không thành hiện thực ở mức toàn cục); trong bin có
  tương quan âm nhẹ (−0.05…−0.44) do động học (link đang ở mép trên của bin
  thường vừa đi vào từ xa/đang tiến lại) — mức này không đe doạ VIF.
- slope~retry ≈ 0 toàn cục nhưng **+0.20 trong bin giữa** — dấu dương (slope
  dương ↔ retry cao hơn một chút trong cùng bin) là bất ngờ nhỏ, xem mục
  Bất thường.

## Quyết định đã chốt

- Dataset P2 đóng: 35 seed, 758 301 dòng, provenance đồng nhất (một SHA,
  một binary hash). Mọi phân tích P3–P5 chạy trên dữ liệu này, không sinh
  thêm.
- Limitations "kiểm duyệt tại sàn" vào PLAN.md P5 (điểm 4 của chỉ định):
  quy tắc 5 (fit thô, không clip) tránh được kiểm duyệt do *chuẩn hoá*,
  nhưng mẫu dưới sàn detect **chưa bao giờ tồn tại trong dataset** — trần
  cứng do phần cứng đặt về lượng vùng-link-xấu quan sát được. Bằng chứng:
  p20 = −88.6 dBm cách sàn hiệu dụng −90 dBm đúng 1.4 dB, SD giữa seed
  0.022 dB so với 0.16 dB của p80 — **đầu dưới do máy thu ghim, đầu trên do
  topology quyết định.**

## KHÔNG làm

- Không chạy thêm mô phỏng nào cho ba phân tích — tất cả từ rows.csv đã có.
- Không sinh seeds 36–40 (`data/eval/` rỗng, `run_tests.sh` cưỡng chế).
- Không hiệu chuẩn lại `gateNearQMax = 0.35` dù đã có phân bố 35 điểm —
  ghi số liệu vào mục cổng ở trên; đổi ngưỡng là việc có tác động sang P3+
  nên để anh/chị quyết cùng lúc duyệt P3.
- Không bắt đầu bất kỳ việc gì của P3 (percentile/normalization.json).

## Bất thường / nghi ngờ

1. **SD near-q toàn tập (0.022) gấp ~3× SD calib (0.008), max 0.326.** 5
   seed calib tình cờ đồng đều hơn tổng thể; nếu chỉ nhìn calib sẽ tưởng
   ngưỡng 0.35 cách 10 SD, thật ra ~3 SD. Không seed nào trượt, nhưng đây
   là minh hoạ vì sao hoãn hiệu chuẩn tới khi có 35 điểm là đúng.
2. **slope~retry dương (+0.20) trong bin giữa.** Giả thuyết: thành phần
   trong-bin — link vừa được admit (đi từ xa vào, slope dương) còn mang
   lịch sử retry cao ở cửa sổ feature; và link đang rời đi (slope âm) từng
   ở gần nên retry quá khứ thấp. Chưa kiểm chứng — P5 sẽ thấy nó qua dấu
   tương tác; ghi để không ngạc nhiên.
3. **route availability trải 61.5–91.4% giữa các seed** — phụ thuộc cách
   rút cặp CBR; như đã khai báo ở phân tích hop, con số per-seed dao động.
4. Phân tích 2 dùng median của within-SD (phân bố lệch phải); mean sẽ cao
   hơn. Kết luận tỉ-số-nhỏ-hơn-1 không đổi với mean.

## Đầu vào cho phase sau

| Đường dẫn | Nội dung |
|---|---|
| `data/calib/seed-{1..5}/` | 105 869 dòng — P3 tính percentile → `frozen/normalization.json` |
| `data/train/seed-{6..35}/` | 652 432 dòng — P4/P5 fit |
| `data/train/batch_stats.json` | Ba phân tích, máy đọc |
| `analysis/validate/p2_batch_stats.py` | Chạy lại được: `python3 analysis/validate/p2_batch_stats.py data/calib data/train` |
| Mỗi seed | `rows.csv`, `positions.csv`, `meta.json`, `summary.json`, `gates.{json,txt}`, `stdout.log`, `run_manifest.json` |

**P3 nhận ba cảnh báo từ P2:** (a) p20 tựa sàn — báo thêm p5/p95 khi so hai
bản chuẩn hoá; (b) dải p80−p20 chỉ ~3.8 dB; (c) slope có nhiễu đo dị phương
sai theo khoảng cách — nếu P3/P5 chuẩn hoá slope bằng percentile toàn cục,
phần đuôi phân bố slope một phần là nhiễu đo của link xa, không phải động
học thật.
