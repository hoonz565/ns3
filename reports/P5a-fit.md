# P5a — PCA, GLM thô và kiểm chứng attenuation

Ngày 2026-07-27 | Git SHA làm việc: `f09d10855` | Dữ liệu: seeds 6–29,
`git_sha c90310d86`, binary `15198a5fc9…`, `config_sim_sha256
3e4481e7c04f…`, `sim_params_sha256 0c94836c1d77…`

**Phạm vi dừng:** chỉ P5a lõi. Không đọc dữ liệu holdout seeds 30–35,
không làm bảng so mô hình, không fit AR/LET/raw-vs-clip — tất cả là P5b
sau duyệt.

## Đã làm

- Đọc `frozen/split.json`, cưỡng chế tập fit đúng seeds 6–29 và kiểm bộ ba
  hồ sơ mô phỏng đồng nhất trên cả 24 seed.
- PCA trên ba feature thô sau z-score, dùng đúng các dòng GLM dùng.
- Fit binomial GLM tự do có intercept trên
  `(rssi_level, rssi_slope, retry_rate)`, nhãn per-attempt
  `successes = trials_future - fails_future`, `failures = fails_future`;
  covariance cluster-robust theo seed.
- Bootstrap 200 lần bằng resample nguyên seed; kiểm dấu vật lý và tỉ số
  `beta_slope / beta_RSSI`.
- Fit bốn tầng `rssi_n` phủ trọn tập dùng, không lọc dòng; áp đúng quy tắc
  dừng trước reliability-ratio khi beta_slope không tăng đơn điệu.
- Ghi hệ số chạy thật trên thang logit thô và `(a,b,c)` chỉ-trình-bày vào
  `frozen/weights.json`.
- Làm cứng `config_sim_sha256`: tập key quy tắc loại khỏi hash phải trùng
  khít tập key binary khai là có trong registry nhưng scenario không đọc.
  Thiếu stdout, thiếu dòng registry, sai số lượng hoặc lệch tập đều là lỗi
  cứng; runner dừng ngay thay vì đếm như một seed trượt thống kê.

## Cổng nghiệm thu

| Chỉ số | Tiêu chí | Đo được | Kết luận |
|---|---:|---:|---|
| Tập fit | seeds 6–29, không holdout | 24 seed | đạt |
| Hồ sơ mô phỏng | một bộ ba hash | đúng một bộ | đạt |
| Dòng usable | không lọc nhãn/trials/`rssi_n` | 519.968 / 523.371; thiếu retry 3.403 (0,65%) | đạt |
| PCA, PC1+PC2 | `>95%` thì thừa một số hạng | **93,14%** | không kích hoạt tiêu chí thừa |
| GLM | feature thô, intercept tự do, cluster theo seed | 24 cluster | đạt |
| Dấu beta | level `+`, slope `+`, retry `−` | `+`, `+`, `−` | đúng vật lý |
| Bootstrap | dấu và độ lớn ổn định | mọi CI95 bootstrap giữ nguyên dấu | đạt |
| Kiểm chứng `beta_slope/beta_RSSI` | xấp xỉ `tau = 4 s` | **2,150 s** | **không đạt dự đoán 4 s** |
| Attenuation trực tiếp | beta_slope tăng đơn điệu theo `rssi_n` | 0,199 → 0,811 → 0,915 → 0,808 | không kích hoạt hiệu chỉnh |
| Gương config hash | tập loại trừ = tập binary không đọc | cùng 10 key, 24/24 seed fit | đạt |

## Số liệu chính

### Bước 0 — PCA / phổ giá trị riêng

PCA dùng ma trận tương quan của ba feature thô, tức z-score chỉ cho phân
tích chiều; các hằng số z-score này không đi vào GLM hay artifact triển
khai. Dấu của eigenvector là tuỳ quy ước; quan hệ tương đối giữa các loading
mới có ý nghĩa.

| Thành phần | Giá trị riêng | Phương sai | `rssi_level` | `rssi_slope` | `retry_rate` |
|---|---:|---:|---:|---:|---:|
| PC1 | 1,7941 | 59,803% | +0,7071 | −0,0008 | −0,7071 |
| PC2 | 1,0000 | 33,334% | +0,0027 | +1,0000 | +0,0015 |
| PC3 | 0,2059 | 6,864% | −0,7071 | +0,0029 | −0,7071 |

PC1 là trục level–retry; PC2 gần như thuần slope. Câu dùng trong Results:
**hai thành phần đầu giải thích 93,14%, dưới ngưỡng 95%; PC3 = 6,86%.**
P5a chưa có căn cứ tuyên bố công thức ba số hạng thừa một số hạng.

### GLM nhị thức trên thang thô

Mô hình:

```text
z = 29.052258
    + 0.334722 * rssi_level
    + 0.719591 * rssi_slope
    - 1.851676 * retry_rate
p_hat = logistic(z)
```

| Hệ số | beta | SE cluster | CI95 cluster | z |
|---|---:|---:|---:|---:|
| intercept | +29,052258 | 0,402037 | [28,264281; 29,840236] | +72,26 |
| `rssi_level` [1/dB] | +0,334722 | 0,004734 | [0,325443; 0,344001] | +70,70 |
| `rssi_slope` [s/dB] | +0,719591 | 0,008150 | [0,703617; 0,735565] | +88,29 |
| `retry_rate` | −1,851676 | 0,022662 | [−1,896092; −1,807259] | −81,71 |

Statsmodels trả p-value bằng 0 theo số học dấu phẩy động cho cả bốn hệ số
(`p < 10^-300`); z và CI được báo để tránh diễn giải số 0 là p-value chính
xác. Cả ba dấu đúng chiều vật lý. Beta retry âm là kết quả mong đợi trên
feature `retry_rate` (retry cao làm giảm xác suất thành công), không bị clip.

Theo cấu tạo kênh đã chốt, beta level đáng kể chủ yếu mã hoá khoảng cách;
không được trình bày như thông tin channel vượt-hình-học.

### Hai dạng xuất

Dạng P8 chạy thật là đầy đủ bộ `(b0,b1,b2,b3)` ở thang thô trong
`frozen/weights.json`, dùng logit `z` ở trên. TTT không chạy trên LinkScore
đã clip: ở 0–200 m, `s_rssi` bị ghim tại 1 trên 100% dòng, khiến đạo hàm
theo thời gian bằng 0 chính xác và có thể tạo TTT vô hạn.

Dạng chỉ để trình bày paper, sau khi đổi ba feature về cùng chiều tốt và
cùng thang p20/p80:

```text
(a, b, c) = (0.348960, 0.147762, 0.503278)
```

Đây không phải hệ số controller và không thay thế intercept.

### Kiểm chứng vật lý và bootstrap theo seed

`beta_slope / beta_RSSI = 2,1498 s`, SE delta-method 0,0352 s, CI95 xấp xỉ
[2,0809; 2,2188] s. Bootstrap theo seed cho CI95 [2,0793; 2,2126] s. Hai
cách khớp nhau nhưng đều nằm xa `tau = 4 s`: slope có đóng góp thống kê
rất mạnh, song hệ số không hành xử như bộ ngoại suy tuyến tính sạch đúng
một horizon 4 s trong mô hình đầy đủ. Đây là phát hiện cần giữ nguyên, không
được đổi scale hay chọn mô hình phụ để ép tỉ số về 4.

| Hệ số | SD bootstrap | CI95 bootstrap |
|---|---:|---:|
| intercept | 0,380566 | [28,380700; 29,780158] |
| `rssi_level` | 0,004474 | [0,326691; 0,343242] |
| `rssi_slope` | 0,008775 | [0,702472; 0,732920] |
| `retry_rate` | 0,021035 | [−1,894261; −1,814658] |

Bootstrap cho thấy dấu và độ lớn hệ số ổn định giữa seed. Nó không cứu được
kiểm chứng `tau`: tỉ số ổn định quanh 2,15 s, không quanh 4 s.

### Thang attenuation

| Tầng `rssi_n` | Số dòng | beta_slope | SE cluster | CI95 xấp xỉ | beta_RSSI | beta_retry |
|---|---:|---:|---:|---:|---:|---:|
| 3–9 | 153.577 | +0,1987 | 0,0104 | [0,1783; 0,2190] | +0,5652 | −2,0664 |
| 10–19 | 128.183 | +0,8114 | 0,0120 | [0,7879; 0,8349] | +0,4642 | −1,1440 |
| 20–29 | 108.421 | +0,9152 | 0,0164 | [0,8829; 0,9474] | +0,2928 | −0,9878 |
| >=30 | 129.787 | +0,8079 | 0,0141 | [0,7803; 0,8355] | +0,2071 | −1,4957 |

Bốn tầng phủ đúng 519.968/519.968 dòng. Beta slope dương và có ý nghĩa ở
mọi tầng: luận điểm slope không rơi vào trường hợp “vô nghĩa ở mọi tầng”.
Tuy nhiên đường không tăng đơn điệu vì tầng `>=30` giảm rõ so với 20–29;
các CI95 cũng không có giao chung, nên cũng không thể gọi là ổn định.
Kết luận P5a là **mẫu hỗn hợp, attenuation chưa được xác nhận theo tiêu chí
trực tiếp đã chốt**. Do bước (b) không kích hoạt, P5a không tính và không áp
reliability-ratio; beta quan sát 0,719591 được giữ nguyên.

## Quyết định đã chốt

- `frozen/weights.json` chạy trên logit thô có intercept; `(a,b,c)` chỉ là
  bản trình bày.
- Không hiệu chỉnh reliability-ratio trong P5a vì thiếu bằng chứng đơn điệu
  theo tiêu chí đã công bố trước.
- Kết luận khoa học hiện tại phải giữ cả hai vế: slope rất có ý nghĩa và ổn
  định theo bootstrap, nhưng không đạt kiểm chứng hệ số/horizon 4 s.
- Gate `config_sim_sha256` fail-closed theo chính danh sách “known but
  unused” binary in ra; không còn cho phép bỏ qua khi stdout/registry thiếu.

## KHÔNG làm

- Không đọc `rows.csv`/`rows_norm.csv` của seeds 30–35.
- Không làm bảng so mô hình, AIC/BIC, AR baseline, RSSI+slope-only, LET,
  tương tác, raw-vs-clip hay scatter/R2 holdout. Đây là P5b và phải chờ duyệt.
- Không lọc theo `rssi_n`, trials hay giá trị nhãn.
- Không clip beta âm và không ép tổng beta bằng 1 khi fit.
- Không sửa `frozen/normalization.json` hay `frozen/split.json`.

## Bất thường / nghi ngờ

1. Tỉ số vật lý 2,15 s khác 4 s rất xa dù beta slope có z = 88,29. Slope
   dự đoán thật, nhưng cơ chế không khớp mô hình ngoại suy tuyến tính đơn
   giản trong GLM đầy đủ; P5b mới được phép kiểm tra phần sức dự đoán vượt AR.
2. Mẫu tầng tăng mạnh từ `n=3–9` tới `20–29` rồi giảm ở `>=30`. Nó tương
   thích với attenuation ở vùng n thấp nhưng vi phạm tiêu chí đơn điệu toàn
   dải; cũng có thể phản ánh thay đổi hỗn hợp khoảng cách/contention giữa
   tầng. Không được chọn riêng ba tầng đầu để tuyên bố attenuation.
3. 3.403 dòng (0,65%) thiếu retry không thể vào mô hình ba feature; đây là
   missing feature do harness đã biết, không phải lọc hậu nghiệm.
4. p-value numerically zero không đồng nghĩa các attempt độc lập. Cluster
   theo 24 seed xử lý tương quan theo run, nhưng retry trong cùng frame vẫn
   là limitation đã ghi trong CLAUDE.md.

## Addendum trước P5b — trung điểm cửa sổ và attenuation tại 400–600 m

Addendum chỉ đọc `rows_norm.csv`, `summary.json` và manifest của seeds
6–29. Holdout 30–35 không được đọc.

### A. Kiểm giả thuyết trung điểm cửa sổ nhãn

Rows không lưu timestamp từng attempt, nên dùng lịch phát đã đóng băng để
ước lượng theo từng dòng:

```text
mean_time_i =
    (trials_probe_i * 2.0000 + trials_cbr_i * 1.9375)
    / trials_future_i
```

Probe có phase độc lập và chu kỳ 1 s jitter đối xứng ±5%, nên kỳ vọng trong
`[t,t+4)` là 2,0 s. CBR chạy 8 packet/s trên lưới 0,125 s; 32 phase
`0, 0.125, ..., 3.875` có trung bình 1,9375 s. Cho phase CBR dịch tự do cả
một chu kỳ tạo khoảng bảo thủ 1,9375–2,0625 s.

| Đại lượng | Đo/ước lượng |
|---|---:|
| Dòng GLM | 519.968 |
| Attempt probe | 3.332.278 (86,31%) |
| Attempt CBR | 528.517 (13,69%) |
| Dòng probe-only / CBR-only | 495.743 / 92 |
| Trung bình estimator theo dòng, không trọng số | 1,99825 s |
| p05 / p50 / p95 theo dòng | 2,000 / 2,000 / 2,000 s |
| Trung điểm trọng số theo attempt | **1,99144 s** |
| Khoảng do phase CBR | **[1,99144; 2,00856] s** |
| Queue-delay p99 median / max giữa seed | 3,92 / 4,47 ms |
| Queue-delay max lớn nhất | 18,66 ms |

Tỉ số GLM 2,1498 s cao hơn trung điểm trọng số 0,1584 s; CI95 bootstrap
của tỉ số `[2,0793; 2,2126]` không giao khoảng phase `[1,9914; 2,0086]`.
Ngay cả cộng queue-delay max 18,66 ms cho mọi attempt — một chặn trên quá
bảo thủ — vẫn không chạm cận dưới bootstrap.

Quan trọng hơn, `rssi_level` của row là mean trên `[t−4,t)`, đặt tại tâm
`t−2`, không phải RSSI tức thời tại `t`. Tâm nhãn ước lượng là `t+1,991`;
khoảng tâm-feature tới tâm-label vì thế là **3,991 s**, vẫn xấp xỉ 4 s.
Do đó phép ước lượng từ scheduler **không ủng hộ** giả thuyết “2,15 s chỉ
là trung điểm cửa sổ nhãn”; điều kiện để viết lại Bất thường 1 thành lỗi
phép kiểm ban đầu không đạt. Bất thường được làm rõ hơn: trung điểm nhãn
đúng là khoảng 2 s so với anchor, nhưng đại lượng cần so với beta ratio là
khoảng cách tâm-đến-tâm gần 4 s.

Giới hạn của phép suy: row không giữ timestamp/pcap nên estimator không
thấy phase thật của từng link, thời điểm retry hay các đoạn probe vừa
stop/restart. Phase CBR và queue delay đo được không đủ giải thích chênh
0,158 s; riêng bias do admission stop/restart là state-dependent và không
thể định lượng từ count alone. Vì vậy đây là kiểm bằng kỳ vọng scheduler,
không phải phép đo timestamp trực tiếp; nó không cung cấp bằng chứng để
đổi diễn giải cũ, nhưng cũng không tuyên bố loại hết mọi bias timing.

### B. Kiểm attenuation trong dải khoảng cách cố định

Giữ `400 <= dist_m < 600` cho 158.538 dòng, rồi chia theo quartile
`rssi_n` nội-dải: Q25/Q50/Q75 = 20/24/28. Mỗi GLM vẫn có đủ 24 seed,
feature thô, intercept tự do và covariance cluster-robust theo seed.

| `rssi_n` | Dòng | beta_slope | SE cluster | CI95 | beta_RSSI | beta_retry |
|---|---:|---:|---:|---:|---:|---:|
| 4–19 | 39.218 | +0,4455 | 0,0118 | [0,4224; 0,4687] | −0,0378 | −0,6744 |
| 20–23 | 34.660 | +0,7484 | 0,0227 | [0,7039; 0,7929] | +0,0916 | −0,7630 |
| 24–27 | 37.364 | +0,7947 | 0,0219 | [0,7518; 0,8377] | +0,1090 | −0,8711 |
| 28–41 | 47.296 | +0,7161 | 0,0191 | [0,6788; 0,7535] | +0,0988 | −0,9770 |

Đường `0,4455 → 0,7484 → 0,7947 → 0,7161` vẫn không tăng đơn điệu:
tầng cao nhất giảm so với tầng 24–27. Kiểm nhạy với đúng ranh giới P5a cũ
cho `0,0712 → 0,4629 → 0,7651 → 0,6906`, cũng không đơn điệu (tầng 3–9
chỉ có 1.013 dòng trong dải này, là lý do bảng chính dùng quartile).

Kết luận điều kiện: **P5a đứng vững và mạnh hơn sau khi cố định vùng vật
lý**. Có mức tăng rõ từ n thấp lên n trung bình, nhưng tiêu chí trực tiếp
đã chốt đòi tăng đơn điệu trên bốn tầng và vẫn không đạt. Không tính/apply
reliability-ratio, kể cả riêng vùng 400–600 m; không chọn ba tầng đầu để
tuyên bố attenuation.

### C. Trạng thái sau addendum

Hai kiểm bổ sung hoàn tất mà không mở holdout. P5b theo kế hoạch đã duyệt
có thể bắt đầu ở lượt tiếp theo; addendum này không chạy AR/RSSI+slope/LET,
raw-vs-clip hay scatter holdout.

## Đầu vào cho phase sau

| Artifact | Nghĩa |
|---|---|
| `analysis/fit/p5a_fit.py` | pipeline P5a, hash `b532e545c37f…` |
| `data/p5a_fit.json` | output máy đọc được, hash `d1f96bf096e9…` |
| `analysis/fit/p5a_addendum.py` | hai kiểm train-only, hash `3bbf18638340…` |
| `data/p5a_addendum.json` | output addendum, hash `34bc5facf482…` |
| `frozen/weights.json` | logit thô + bản `(a,b,c)` trình bày, hash `d4218c8482cf…` |
| `frozen/split.json` | P5b chỉ được đọc holdout sau duyệt, hash `ac70dabb866b…` |

**DỪNG addendum tại đây; P5b chưa được chạy trong phạm vi lượt này.**
