# P4 — Dataset huấn luyện: holdout đóng băng, normalization áp toàn tập, VIF, đồng nhất hồ sơ

Ngày 2026-07-27 | Git SHA đầu phase: `7d7f17534` (commit split, đứng trước
mọi việc khác; các commit còn lại của P4 liền sau) | Dữ liệu: 35 seed P2
(binary `15198a5fc9…`, config-digest `5e90070cdf…`; sau P4 mọi manifest
mang thêm `sim_params_sha256 0c94836c1d77…` và `config_sim_sha256
3e4481e7c04f…`, đồng nhất cả 35) | Tạo phẩm mới: `frozen/split.json`

**Kết luận: holdout chốt TRƯỚC khi nhìn dữ liệu (seeds 6–29 fit / 30–35
holdout, commit `7d7f17534` đứng trước mọi việc khác của phase). Normalization
đóng băng đã áp lên toàn bộ 758 301 dòng — cột thô giữ nguyên, ghim biên đo
được cho cả hai bản clip. Cổng VIF ĐẠT (2.707 / 1.000 / 2.707 < 5). Hồ sơ
cổng 35 seed đồng nhất ở ngưỡng 0.38, giá trị đo trùng khít. Ngoại lệ
"config hash của eval sẽ khác" bị gỡ hẳn bằng khoá so sánh ba thành phần.
KHÔNG fit gì, KHÔNG PCA — đó là P5.**

## Đã làm

- **`frozen/split.json` — việc đầu tiên, commit riêng trước khi đọc bất kỳ
  dòng dữ liệu nào**: quy tắc cố định theo số seed (6–29 fit = 24, 30–35
  holdout = 6), lý do ghi trong file (eval khoá tới P10 nên P5 cần tập
  held-out riêng cho scatter/R² ngoài mẫu); bất biến cùng cơ chế
  normalization (đổi = `-v2` + lý do).
- `analysis/features/p4_apply_normalization.py`: mỗi seed sinh
  `rows_norm.csv` = nguyên vẹn cột thô + `s_rssi, s_slope, s_mac` từ **cặp
  triển khai (p20, p80)**; `s_mac` rỗng giữ rỗng (rỗng ≠ 0 — known trap).
  Bản clip-rộng (p5, p95) **không sinh cột** (tránh hai bộ triển khai song
  song) nhưng ghim biên báo cho cả hai bản → `data/p4_norm_stats.json`.
- `analysis/validate/p4_vif.py`: VIF ba feature **thô**, đúng 24 seed fit
  đọc từ `frozen/split.json`; đếm tường minh 3 403 dòng (0.65%) bị loại vì
  thiếu retry (GLM sẽ loại lặng lẽ — ở đây thành số nhìn thấy).
- **Đồng nhất hồ sơ cổng**: chạy lại `check_gates.py` cho cả 35 seed ở
  0.38 (ghi cả `gates.json` lẫn `gates.txt` như runner); đối chiếu tự động:
  **giá trị đo trùng khít cả 35 seed**, chỉ cột ngưỡng đổi. Kiểm luôn câu
  hỏi chỉ định: `git diff 2e3e45828 c90310d86` trên `check_gates.py`,
  `run_manifest.py`, conf, `scratch/`, `src/` — **rỗng toàn bộ**: calib và
  train được chấm bằng đúng một phiên bản. Tới HEAD, `check_gates.py` vẫn
  rỗng; riêng conf khác đúng khối `gateNearQMax` 0.35→0.38 của P3 — bất
  biến mô phỏng được `config_sim_sha256` chứng nhận (hai bản conf cùng
  hash).
- Conf: đoạn "WHAT NEAR-Q ACTUALLY DETECTS AT 0.38" — run 2 (0.343) giờ
  PASS near-q; near-q chỉ còn bắt bão hoà NẶNG (run 1: 0.680); bộ dò chính
  là DEGREE (calib 4.895 ± 0.093 → cổng 4.0 cách 9.7 SD; toàn tập 4.92 ±
  0.19 → 5.0 SD; bắt cả run 1 degree 1.79 lẫn run 2 degree 3.82). "near-q
  PASS" chỉ được phép đọc là "không bão hoà nặng", không phải "kênh khoẻ".
- PLAN.md P5 Limitations: bản p5/p95 nới **0.59 dB phía dưới / 4.88 dB
  phía trên** — phép so raw-vs-clip của quy tắc 5 chủ yếu kiểm tra đuôi
  TRÊN; đuôi dưới không nới được vì mẫu dưới sàn không tồn tại. Kèm số ghim
  đo được (bảng dưới).
- `run_manifest.py`: (a) **`sim_params_sha256`** — hash chính tắc các giá
  trị hiệu dụng binary tự khai trong `meta.json` (loại `seed`, `flows`,
  `phase`, `config_files`), chế độ `--augment-meta` sau-run, móc vào
  `run_p2_batch.sh`, backfill 35 manifest → **một hash duy nhất
  `0c94836c1d77…`**, idempotent; (b) **`config_sim_sha256`** — hash phần
  key MÔ PHỎNG của conf (loại `gate*`/`seeds*`/`rHalfM`, gương với registry
  "của Python" binary in ở stdout.log) — kiểm chứng bất biến then chốt:
  **conf 0.35 và conf 0.38 cho CÙNG hash `fe2dc414…`/composite
  `3e4481e7…`**. `config_sha256` giữ nguyên để so lịch sử.

## Cổng nghiệm thu

| Chỉ số | Ngưỡng | Đo được | Đạt |
|---|---|---|---|
| VIF `rssi_level` / `rssi_slope` / `retry_rate` (thô, 24 seed fit) | < 5 | 2.707 / 1.000 / 2.707 | ✓ |
| Phương sai ba feature "đáng kể" (PLAN P4) | ≠ suy biến | SD 3.06 dBm / 0.582 dB/s / 0.344 | ✓ |
| Hồ sơ cổng 35 seed ở ngưỡng 0.38 | 35/35 PASS | 35/35, 0 trượt | ✓ |
| Giá trị đo sau khi chạy lại cổng | trùng khít | trùng cả 35 (bỏ cột threshold) | ✓ |
| Một phiên bản check_gates chấm cả hai batch | diff rỗng | diff 2e3e45828↔c90310d86↔HEAD rỗng | ✓ |
| `sim_params_sha256` trên 35 manifest | duy nhất | 1 hash, idempotent | ✓ |
| `config_sim_sha256` bất biến qua đổi gate | bằng nhau | 0.35-conf = 0.38-conf | ✓ |
| `data/eval/` | rỗng tới P10 | `run_tests.sh` PASS | ✓ |

## Số liệu chính

**Ghim biên clip, % dòng theo bin** (toàn tập 758 301 dòng; đầy đủ trong
`data/p4_norm_stats.json`):

| bin | s_rssi ghim-0/ghim-1 (p20/p80) | (p5/p95) | s_slope (p20/p80) | s_mac ghim-0/ghim-1 |
|---|---|---|---|---|
| 0–200 m | 0 / **100** | 0 / 90.5 | 19.7 / 56.1 | 0 / 78.4 |
| 200–400 m | 0 / **82.1** | 0 / 9.3 | 24.3 / 30.3 | 0.1 / 42.6 |
| 400–600 m | 0.2 / 4.9 | 0 / 0 | 19.6 / 17.4 | 6.4 / 5.0 |
| 600–800 m | 27.3 / 0 | 3.6 / 0 | 17.6 / 15.0 | 53.4 / 0.1 |
| ≥800 m | **74.1** / 0 | 25.9 / 0 | 21.0 / 17.1 | **90.6** / 0 |
| TOÀN TẬP | 20.1 / 19.3 | 4.9 / 4.7 | 20.0 / 20.1 | 33.0 / 11.8 |

Đọc: (a) `s_rssi` triển khai chỉ còn phân biệt trong dải 400–800 m — ngoài
dải đó nó ghim gần hết về 0 hoặc 1; đây là tính chất của **triển khai P8**
(P5 fit trên thô nên không bị ảnh hưởng), phải nhớ khi thiết kế MPC. (b)
Bản p5/p95 gỡ ghim chủ yếu ở biên TRÊN (200–400 m: 82% → 9%) đúng như phân
tích bất đối xứng; biên dưới ≥800 m vẫn 26%. (c) `s_mac`: 33% cửa sổ có
retry = 1 (mất trắng), dồn 90.6% ở ≥800 m — feature retry bão hoà ở đuôi
xa; ghi chú `1 − sqrt(retry)` của PLAN P3 sẽ có đất dụng võ ở P5. (d)
`s_slope` ghim ~20/20 rải đều hơn theo bin; riêng 0–200 m lệch về ghim-1
(56%) — hiệu ứng chọn lọc (link vào được bin gần thường vừa tiến lại).

**VIF & tương quan tập fit** (519 968 dòng dùng được / 523 371): VIF level
2.707 = 1/(1−0.794²) — toàn bộ từ corr(level, retry); slope 1.000 (trực
giao). corr tập fit (−0.794 / +0.001 / +0.002) trùng toàn tập 35 seed
(−0.793 / 0.000 / +0.002) — phân bố feature ổn định giữa fit và phần còn
lại.

## Quyết định đã chốt

- **`frozen/split.json` bất biến**: fit = seeds 6–29, holdout = 30–35. P5
  fit và chọn mô hình trên fit; scatter/R² ngoài mẫu trên holdout;
  `data/eval` không ai chạm tới P10.
- **Chỉ vật chất hoá cột chuẩn hoá theo cặp triển khai (p20, p80)** trong
  `rows_norm.csv`; bản p5/p95 chỉ tồn tại dưới dạng thống kê + hằng số
  trong frozen — một nguồn chân lý cho P8.
- **Khoá so sánh giữa các batch từ nay là BỘ BA
  (`binary_sha256`, `config_sim_sha256`, `sim_params_sha256`)**; ngoại lệ
  P3 "config_sha256 của eval sẽ khác vì key gate" **bị gỡ hẳn** — eval hợp
  lệ ⟺ bộ ba trùng với train, không cần soi diff conf bằng mắt.
  `config_sha256` cũ giữ nguyên vai trò hash file để đối chiếu lịch sử.
- **Hồ sơ cổng thống nhất một ngưỡng 0.38** trên cả 35 seed; vết 0.35 nằm
  trong git history của reports và trong khai báo ở đây, không còn trong
  `data/`.

## KHÔNG làm

- **Không fit, không PCA, không đụng `data/eval/`, không mô phỏng mới.**
- **Không mở rộng meta.json của binary** dù nó thiếu key (xem Bất thường
  1): sửa `.cc` là đổi `binary_sha256`, phá so sánh binary train↔eval —
  đúng thứ bộ ba hash tồn tại để bảo vệ. Ghi thành yêu cầu cho scenario
  Tier 3 (P8): in đủ tham số hiệu dụng vào meta.json ngay từ đầu.
- Không sửa mục P4 của PLAN.md (chỉ định không yêu cầu; quy tắc split nằm
  trong frozen/split.json + STATUS).
- Không xoá `rows.csv` gốc hay gộp cột vào nó — `rows_norm.csv` là file
  dẫn xuất, tách bạch thô/chuẩn hoá.

## Bất thường / nghi ngờ

1. **`meta.json` chỉ in ~20 tham số** — thiếu `gm*`, `nakagami*`,
   `exponent`, `frameRetryLimit`, `dataMode`, `channelNumber`, `area*`,
   `alt*`. Một mình `sim_params_sha256` vì thế KHÔNG bắt được ví dụ đổi
   exponent trong conf. Đây là lý do có **`config_sim_sha256` — phần vượt
   chỉ định điểm 7**, khai ở đây để anh/chị bác được: không có nó, ngoại lệ
   "diff conf chỉ chạm gate*" phải kiểm bằng mắt, và ngoại lệ nào cũng sẽ
   bị viện dẫn. Một trường, một hàm, xoá dễ nếu không muốn.
2. **Manifest 35 seed bị sửa tại chỗ** (backfill): chỉ THÊM trường mới
   (`sim_params_sha256`, `config_sim_sha256`, cờ `config_sim_backfilled`
   ghi rõ nguồn), không trường nào có sẵn bị đổi. `config_sim_sha256`
   backfill tính từ blob conf tại đúng git SHA của run (cây sạch nên blob
   là conf thật lúc chạy), bằng chính hàm dùng cho tương lai.
3. **`gates.txt` thời-0.35 không còn trong `data/`** — P3 từng ghi "gates.txt
   còn nguyên làm vết gốc"; sau đồng nhất hoá P4 câu đó hết hiệu lực. Vết
   0.35: bảng phân bố trong `reports/P2-batch.md` + khai báo này.
4. **`s_rssi` triển khai gần như nhị phân ngoài dải 400–800 m** (bảng
   trên). Không ảnh hưởng P5 (fit thô) nhưng là input thật của MPC ở P8 —
   nếu LinkScore triển khai cần phân giải ở bin gần, cặp (p20, p80) không
   cho. Để ngỏ cho P8, KHÔNG đổi frozen bây giờ.
5. **Điểm treo cho P5**: retry bão hoà đuôi xa (90.6% cửa sổ ≥800 m có
   retry = 1) nghĩa là trong vùng chết, feature retry hết phương sai —
   AR baseline sẽ yếu đúng ở đó, còn slope thì ồn đúng ở đó (SE ~1.2 dB/s).
   Vùng 400–800 m là chiến trường thật của mọi mô hình.

## Đầu vào cho phase sau

| Đường dẫn | Nội dung |
|---|---|
| `frozen/split.json` | fit 6–29 / holdout 30–35, BẤT BIẾN, chốt trước dữ liệu |
| `data/*/seed-*/rows_norm.csv` | cột thô nguyên vẹn + `s_rssi,s_slope,s_mac` (cặp triển khai) |
| `data/p4_norm_stats.json` | ghim biên hai bản clip, theo feature × bin |
| `data/p4_vif.json` | VIF, phương sai, tương quan tập fit |
| `data/*/seed-*/run_manifest.json` | thêm bộ ba khoá so sánh (`sim_params_sha256`, `config_sim_sha256`) |
| P5 kế tiếp | thứ tự đã chốt trong PLAN.md: **PCA (Bước 0) → GLM trên THÔ, tập fit → thang attenuation**; scatter/R² trên holdout; so raw vs clip(p20/p80) vs clip(p5/p95) — cần duyệt trước khi làm |
