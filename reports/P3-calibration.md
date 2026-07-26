# P3 — Hiệu chuẩn ngưỡng: đóng băng normalization + hiệu chuẩn lại near-q + ba mục chuẩn bị P5

Ngày 2026-07-27 | Dữ liệu vào: batch calibration seeds 1–5 (git `2e3e45828`,
binary `15198a5fc9…`, config-digest `5e90070cdf…`, cây sạch cả 5 manifest) |
Tạo phẩm: `frozen/normalization.json` (sha256 `ff3bc97ee9ca…`)

**Kết luận: `frozen/normalization.json` đã đóng băng từ 105 869 dòng của
đúng 5 seed calibration — p20/p80 cho `rssi_level` và `rssi_slope` là bộ
triển khai, p5/p95 ghi kèm chỉ để P5 so bản clip rộng, `retry_rate` dùng
ngưỡng vật lý [0, 1] không percentile. `gateNearQMax` 0.35 → 0.38 theo
phân bố 35 điểm. PLAN.md P5 nhận ba mục chuẩn bị (PCA trước fit; β_RSSI
mã hoá khoảng cách theo cấu tạo kênh; thang hiệu chỉnh attenuation thay
cho lọc). KHÔNG fit gì — đó là việc của P5.**

## Đã làm

- `sim-config/fanet-tier2.conf`: `gateNearQMax` 0.35 → 0.38, ghi chú hiệu
  chuẩn từ phân bố 35 seed ở 19 dBm/−101 và vai trò cổng (sức khoẻ vận
  hành, không phải chất lượng dữ liệu — vai trò đó thuộc degree; giữ
  nguyên ghi chú cổng-liên-hợp).
- `analysis/features/p3_normalization.py`: gộp 5 seed calib → percentile
  type-7 → `frozen/normalization.json`. Bất biến cưỡng chế trong code:
  từ chối ghi đè file frozen đã có, từ chối root chứa "eval", đòi đúng
  seeds 1–5, manifest sạch và đồng nhất (1 git_sha, 1 binary, 1 config).
- `frozen/normalization.json`: p5/p20/p80/p95 hai feature liên tục +
  ngưỡng vật lý retry + công thức triển khai + provenance + per-seed
  stability. **Từ đây là hằng số; đổi = tạo `-v2` kèm lý do.**
- PLAN.md P5: thêm "Bước 0 — phân tích chiều TRƯỚC khi fit" (PCA, tiêu
  chí >95%/2 thành phần); thêm "Diễn giải β_RSSI: level không mang tin
  vượt khoảng cách — theo cấu tạo kênh" (Results, không phải Limitations;
  Future Work shadowing per-link); thêm "Attenuation của β_slope: hiệu
  chỉnh, KHÔNG lọc" (thang 3 bước: fit thô → fit phân tầng theo `rssi_n`
  → reliability-ratio với phương sai nhiễu đã biết); sửa Limitations cũ —
  **gỡ chỉ dẫn "fit riêng tập `rssi_n ≥ 20`"** (lọc theo `rssi_n` là kiểm
  duyệt link biên, cùng loại lỗi với lọc theo trials).
- CLAUDE.md, hai chỗ: quy tắc 11 bổ sung đoạn "level ≡ f(khoảng cách) theo
  cấu tạo kênh" (bản tiếng Anh, cho paper); mục Acceptance gate bổ sung
  **lệnh cấm lọc theo `rssi_n`** cạnh lệnh cấm lọc theo trials — cùng cơ
  chế kiểm duyệt (link biên mất beacon → `rssi_n` tương quan nhãn), để
  session sau không hồi sinh bộ lọc từ ghi chú lịch sử trong P2-batch.md.
- Kiểm chứng: `check_gates.py` seed-1/seed-2 đọc 0.38 từ conf và PASS;
  `run_tests.sh` sạch (data/eval rỗng, ranh giới features/labels).
- Kiểm chứng độc lập (4 agent, không đọc script gốc): (i) tính lại toàn
  bộ percentile bằng cài đặt riêng + numpy đối chiếu — khớp frozen tới
  ≤1.4e−14, bảng báo cáo khớp ở 4 chữ số; (ii) tính lại phân bố near-q từ
  35 `gates.json` — mọi con số trích dẫn tái lập được (một chỗ "4.4 SD"
  đã sửa thành ~4.5 — xem Bất thường 5); (iii) quét nhất quán 6 tài liệu;
  (iv) đối chiếu ngược 6 điểm chỉ định + kiểm phạm vi (git status đúng
  tập file, data/eval rỗng, không fit/PCA nào đã chạy).

## Cổng nghiệm thu

P3 không chạy mô phỏng; cổng là cổng provenance và bất biến.

| Chỉ số | Ngưỡng | Đo được | Đạt |
|---|---|---|---|
| Batch calibration đúng seeds | {1..5}, không thêm bớt | seeds [1,2,3,4,5] | ✓ |
| Số dòng khớp sổ sách P2 | 105 869 | 105 869 (0 dòng thiếu feature) | ✓ |
| Manifest sạch, đồng nhất | dirty=false; 1 git/binary/config | 5/5, `2e3e45828`/`15198a5fc9…`/`5e90070cdf…` | ✓ |
| `frozen/` trước khi ghi | rỗng | rỗng (STATUS xác nhận); script từ chối ghi đè | ✓ |
| `data/eval/` | rỗng tới P10 | `run_tests.sh` PASS | ✓ |
| Cổng mới không phá seed cũ | calib PASS ở 0.38 | seed-1: near-q 0.265 ≤ 0.38, 7/7 cổng | ✓ |

## Số liệu chính

Percentile gộp 105 869 dòng (5 seed), nội suy tuyến tính type-7:

| Feature | p5 | p20 | **p80** | p95 | p80−p20 |
|---|---|---|---|---|---|
| `rssi_level` (dBm) | −89.2040 | **−88.6141** | **−84.7784** | −79.9009 | 3.8357 |
| `rssi_slope` (dB/s) | −0.8484 | **−0.3794** | **+0.3761** | +0.8448 | 0.7555 |

Độ ổn định giữa 5 seed (SD của từng percentile):

| | p5 | p20 | p80 | p95 |
|---|---|---|---|---|
| `rssi_level` | 0.019 | **0.022** | **0.162** | 0.077 |
| `rssi_slope` | 0.027 | 0.006 | 0.005 | 0.025 |

Đọc ba cảnh báo P2 bằng số đóng băng:

- **(a) p20 tựa sàn detect — xác nhận:** p20 = −88.61 dBm cách sàn hiệu
  dụng −90 dBm đúng 1.4 dB, SD 0.022 dB (so 0.162 của p80) — đầu dưới do
  máy thu ghim, đầu trên do topology. p5 còn sát hơn (−89.20, SD 0.019):
  **bản clip-rộng p5/p95 hầu như chỉ mở rộng dải VỀ PHÍA TRÊN** (p95
  −79.90); phía dưới không có chỗ mở vì mẫu dưới sàn không tồn tại
  (kiểm duyệt vật lý — Limitations P5 đã khai).
- **(b) dải p80−p20 hẹp — xác nhận:** 3.84 dB. Đây là số phải khai khi
  P5 so raw vs clip: dải chuẩn hoá hẹp nghĩa là clip p20/p80 nén phần lớn
  phân bố về hai đầu (theo định nghĩa percentile: ~40% dữ liệu calib nằm
  ngoài dải).
- **(c) đuôi slope một phần là nhiễu đo link xa:** p5/p95 = ±0.85 dB/s
  trong khi SE(slope) ở bin ≥800 m là ~1.19 dB/s — đuôi phân bố slope có
  thành phần nhiễu đo lớn. Dải triển khai p20/p80 (±0.38) không phụ
  thuộc đuôi; bản p5/p95 thì có — P5 nhớ điều này khi so hai bản.
- Slope ra **gần đối xứng** (−0.379/+0.376): percentile không tự sinh dải
  bất đối xứng. Nếu P8 muốn dải bất đối xứng (slope âm quan trọng hơn),
  đó là lựa chọn thiết kế phải khai riêng (PLAN.md P3 đã dặn), không được
  trình bày như percentile.

Hiệu chuẩn near-q, phân bố 35 điểm từ `gates.json` (kiểm chứng lại trực
tiếp): mean 0.2811, SD 0.0221, min 0.2394, max 0.3263; riêng 5 seed calib
mean 0.2658, SD 0.0078. Ngưỡng mới **0.38 = mean-calib + 5 SD-toàn-tập =
mean-toàn-tập + ~4.5 SD** (chính xác 4.475), cách seed xấu nhất quan sát
được ~2.4 SD;
ngưỡng cũ 0.35 nằm ở mean + 3.1 SD — một seed đen-nhưng-khoẻ nữa là trượt
oan.

## Quyết định đã chốt

- **`frozen/normalization.json` bất biến.** Bộ triển khai là (p20, p80);
  (p5, p95) tồn tại **chỉ** cho phép so của P5 — không phải "bộ triển
  khai thứ hai" (một nguồn chân lý cho P8).
- **`retry_rate` không percentile:** ngưỡng vật lý [0, 1], triển khai đảo
  chiều `s_mac = 1 − clip(retry, 0, 1)` (đúng PLAN.md P3).
- **`gateNearQMax` = 0.38** áp cho mọi run từ nay; batch duy nhất còn lại
  là eval 36–40 ở P10.
- **`config_sha256` của batch eval sẽ khác batch train** vì conf đổi một
  hằng số cổng. Khai trước: khác biệt duy nhất là tham số phía phân tích
  (binary liệt kê `gate*` là "của Python" — trơ với mô phỏng; xác nhận
  trong `stdout.log` dòng 51–52 của mọi seed), tham số mô phỏng không
  đổi. P10 không được coi đây là lệch provenance.
- Ba mục chuẩn bị P5 nằm trong PLAN.md — **thứ tự làm việc của P5: PCA
  trước, fit sau, rồi thang attenuation**; chỉ dẫn lọc `rssi_n ≥ 20` đã
  bị thay thế ở mọi tài liệu chỉ-đường (còn nguyên trong P2-batch.md như
  vết lịch sử, đã đánh dấu bên dưới).

## KHÔNG làm

- **Không fit gì, không chạy PCA** — P5 làm trên train; P3 chỉ ghi kế
  hoạch. Không đọc `data/train` cho percentile (chỉ calib — rule 15).
- **Không chạy mô phỏng nào**; không sinh seeds 36–40; không đụng
  `data/eval/`.
- **Không làm tròn hằng số** trong frozen (PLAN.md P3: làm tròn cho đẹp
  âm thầm đổi kết quả).
- **Không chọn dải bất đối xứng cho slope** dù có gợi ý trong PLAN.md P3
  — số đo ra gần đối xứng, chọn bất đối xứng lúc này là quyết định thiết
  kế không có dữ liệu chống lưng; để P5 so hai bản đã định nghĩa trước.
- Không sửa `reports/P2-batch.md` (nhật ký lịch sử — chỉ dẫn `rssi_n ≥
  20` trong đó là vết của thời điểm viết, báo cáo này ghi đè về mặt
  chỉ-đường).

## Bất thường / nghi ngờ

1. **Tuyên bố "toàn batch một SHA `c90310d86`" của P2-batch.md không
   chính xác về git_sha:** manifest calib (1–5) ghi `2e3e45828`, train
   (6–35) ghi `c90310d86` — hai commit chỉ khác tài liệu, còn
   `binary_sha256` và `config_sha256` **đồng nhất trên cả 35 seed** (kiểm
   trực tiếp). Kết luận provenance của P2 vẫn đứng; frozen ghi SHA chính
   xác của calib.
2. **Số "mean 0.266" trong chỉ định hiệu chuẩn là mean calib-5, không
   phải mean 35 điểm (0.281).** Công thức 0.266 + 5×0.022 trộn mean calib
   với SD toàn tập; quy về phân bố 35 điểm, 0.38 ≈ mean + 4.5 SD. Hai
   cách đọc cho cùng ngưỡng sau làm tròn 2 chữ số; ghi chú conf khai cả
   hai để không ai phải suy lại.
3. **5 seed là mẫu mỏng cho percentile đuôi** (p5/p95): SD per-seed của
   p95-level là 0.077 dB, chấp nhận được, nhưng p80-level dao động 0.41 dB
   giữa min–max seed. Đây là hệ quả thiết kế rule 15 (calib tách riêng,
   5 seed); độ nhạy này là một lý do nữa để P5 so raw-vs-clip trên test
   thay vì tin một bộ ngưỡng.
4. Percentile của script này (type-7) khác phép lấy hạng thô của
   `p2_batch_stats.py` (int index) — hai script không hoán đổi được; đã
   ghi trong docstring cả hai chiều. Số P2-batch không đổi vì nó chỉ báo
   p10/p50/p90 mô tả.
5. Bản nháp đầu ghi "batch mean + 4.4 SD"; kiểm chứng độc lập chỉ ra
   (0.38 − 0.2811)/0.0221 = 4.475 → làm tròn là 4.5, "4.4" chỉ đúng khi
   cắt cụt. Đã sửa thành ~4.5 ở conf, báo cáo này và STATUS.
6. Chạy `check_gates.py` để kiểm chứng ngưỡng mới **ghi lại `gates.json`
   của seed-1 và seed-2 tại chỗ** (mtime mới, cột ngưỡng đổi 0.35→0.38;
   giá trị đo không đổi — seed-1 near-q 0.265, seed-2 0.276). Dữ liệu
   nằm ngoài git (`data/` gitignore), `gates.txt` thời-P2 còn nguyên làm
   vết gốc. Là output kiểm chứng, không phải mô phỏng mới; khai để không
   ai ngạc nhiên vì mtime.

## Đầu vào cho phase sau

| Đường dẫn | Nội dung |
|---|---|
| `frozen/normalization.json` | (p20, p80) triển khai + (p5, p95) cho so sánh P5 + provenance + per-seed. BẤT BIẾN. |
| `analysis/features/p3_normalization.py` | Chạy lại được: `python3 analysis/features/p3_normalization.py data/calib --out frozen/normalization.json` (sẽ từ chối vì file đã tồn tại — đúng thiết kế) |
| `sim-config/fanet-tier2.conf` | `gateNearQMax = 0.38` — check_gates đọc từ đây |
| PLAN.md P5 | Bước 0 PCA → fit → thang attenuation; mục diễn giải β_RSSI |
| P4 kế tiếp | Áp normalization đóng băng lên train, VIF, chia 30/5 theo seed — cần duyệt trước khi làm |
