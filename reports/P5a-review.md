# P5a — phản biện khoa học về tỉ số beta_slope / beta_RSSI

Ngày 2026-07-27 | Phạm vi: review P5a trên tài liệu và kết quả train đã
công bố | Không đọc holdout 30–35 | Không mở P5b | Không fit thêm | Không
sửa pipeline, feature hay frozen artifact

## Nhận định điều hành

P5a đã thiết lập chắc ba điều:

1. `beta_slope` dương, có ý nghĩa rất mạnh và ổn định theo bootstrap seed.
2. Tỉ số `beta_slope / beta_RSSI = 2,1498 s`, CI95 bootstrap
   `[2,0793; 2,2126]`, không gần 4 s theo sai số lấy mẫu.
3. Hai giải thích đơn giản đã không đứng được: trung điểm attempt của nhãn
   vẫn cho horizon tâm-đến-tâm khoảng 3,991 s; beta_slope cũng không tăng
   đơn điệu theo `rssi_n`, kể cả khi cố định khoảng cách 400–600 m.

Kết luận reviewer: **tỉ số 4 s không phải hệ quả bắt buộc của một GLM dự
đoán đúng**. Nó chỉ xuất hiện dưới một mô hình cấu trúc hẹp: RSSI biến đổi
tuyến tính với slope không đổi, logit success tuyến tính theo RSSI tại một
thời điểm đại diện, attempt lấy mẫu thời gian theo cách có thể thay bằng
đúng thời điểm đó, và không conditioning qua retry hay biến ẩn. P5a mới
chứng minh slope có conditional association mạnh; chưa chứng minh toàn bộ
association đó là phép ngoại suy RSSI bốn giây.

Ba nhóm cơ chế đáng tin nhất còn lại là:

- slope quá khứ chỉ bền một phần sang cửa sổ tương lai;
- hệ số trong mô hình đầy đủ là hiệu ứng có điều kiện sau khi đã cho
  `retry_rate`, không còn là cặp hệ số của mô hình RSSI cấu trúc;
- logit của PDR tổng hợp và mixture probe/CBR không bằng logit tại RSSI
  trung bình của một link đồng nhất.

## Khi nào tỉ số phải bằng 4 s?

Đặt mốc anchor là `t=0`. Feature level hiện tại là mean RSSI trên
`[-4,0)`, có tâm gần `−2 s`; gọi nó là `L`. Gọi slope quá khứ là `S`.
Nếu đường RSSI tiếp tục tuyến tính không đổi:

```text
RSSI(u) = L + (u + 2) S
```

Tâm attempt của nhãn nằm gần `u=+2 s`, nên:

```text
RSSI_target = L + 4 S
```

Nếu thêm giả định cấu trúc:

```text
logit P(success | RSSI_target) = alpha + gamma RSSI_target
```

thì:

```text
logit P = alpha + gamma L + 4 gamma S
beta_RSSI  = gamma
beta_slope = 4 gamma
beta_slope / beta_RSSI = 4 s
```

Đây là một đẳng thức nhận dạng chỉ khi đồng thời đúng các điều kiện:

1. `L` thực sự có một mốc thời gian cố định;
2. slope quá khứ là slope kỳ vọng của cả cửa sổ tương lai;
3. RSSI trajectory đủ tuyến tính;
4. logit success tuyến tính theo RSSI;
5. tổng hợp attempt trong cửa sổ có thể thay bằng một thời điểm đại diện;
6. không có effect modification;
7. các hệ số không bị đổi estimand bởi retry, traffic class hay biến ẩn;
8. selection/censoring và measurement error không phụ thuộc outcome.

Một GLM có thể đúng theo nghĩa dự đoán conditional mean rất tốt nhưng vẫn
vi phạm một hoặc nhiều điều kiện cấu trúc trên. Khi đó 2,15 s là một
**effective horizon**, không nhất thiết là lỗi ước lượng.

## Danh mục các cơ chế còn lại

Mức khả tín dưới đây đánh giá khả năng giải thích một phần đáng kể khoảng
cách `2,15` so với `4`, dựa trên bằng chứng P5a/P2 hiện có; nó không phải
p-value.

### 1. Slope chỉ bền một phần sang tương lai — khả tín: CAO

**Cơ chế toán học.** Với Gauss–Markov mobility, vận tốc/hướng thay đổi theo
thời gian. Nếu slope tương lai có persistence kernel `rho(u)`:

```text
E[RSSI(t+u) | L,S] =
    RSSI(t) + S * integral_0^u rho(v) dv
```

thì hệ số slope đo tích phân của persistence, không đo thẳng `u`. Từ mean
quá khứ tới anchor đã cần gần 2 s; phần còn lại của ratio quan sát chỉ là:

```text
2,1498 - 2,0 ≈ 0,1498 s
```

theo reparameterization endpoint xấp xỉ. Điều này phù hợp với trường hợp
slope quá khứ chủ yếu đưa mean về hiện tại, còn rất ít persistence sau `t`.

**Dự đoán observable.**

- Trên cùng link ở hai row liên tiếp, thay đổi mean RSSI từ cửa sổ
  `[-4,0)` sang `[0,4)` tăng ít hơn `4*S_past`.
- Hệ số động học `kappa` trong
  `L_next - L_current ~ kappa*S_current` nhỏ hơn 4.
- Autocorrelation của slope giữa hai cửa sổ liên tiếp giảm nhanh.
- Sai lệch mạnh hơn ở UAV đổi hướng/gia tốc lớn.

**Phù hợp P5a?** Có. Slope có ý nghĩa mạnh nhưng ratio ổn định ở 2,15:
đúng hình dạng của một effective horizon có thật nhưng ngắn. Đây cũng là
cơ chế không cần viện dẫn attenuation.

### 2. Level mean và slope đang dùng một hệ tọa độ làm slope gánh phần sửa
lag — khả tín: CAO

**Cơ chế toán học.** Đặt endpoint RSSI tại anchor:

```text
L_t ≈ L_mean + 2 S
```

Mô hình hiện tại:

```text
beta_L L_mean + beta_S S
= beta_L L_t + (beta_S - 2 beta_L) S
```

Với point estimate P5a:

```text
beta_S - 2 beta_L
= 0,719591 - 2*0,334722
≈ 0,05015
```

Tức phần lớn beta slope (`≈0,66944`) tương thích với việc dịch level từ
tâm cửa sổ quá khứ về anchor; phần slope còn lại tương ứng point ratio chỉ
`≈0,15 s`. Đây là đổi tọa độ của cùng mô hình, không thay feature pipeline
và không làm đổi prediction.

**Dự đoán observable.**

- Linear contrast `beta_S - 2 beta_L` nhỏ hơn nhiều beta slope gốc.
- CI cluster/bootstrap của contrast cho biết slope còn thông tin sau khi
  level được recenter về `t` hay không.
- Log-likelihood và prediction phải bất biến dưới phép đổi tọa độ chính
  xác; chỉ cách đọc hệ số đổi.

**Phù hợp P5a?** Rất phù hợp về số học. Nó không tự giải thích vì sao nhãn
tương lai chỉ cần endpoint gần hiện tại, nhưng chỉ ra phép kiểm ratio gốc
đang trộn hai vai trò của slope: sửa lag level và dự báo sau anchor.

### 3. Conditioning/mediation qua `retry_rate` — khả tín: CAO

**Cơ chế toán học.** Đẳng thức 4 s được dẫn xuất cho một cấu trúc chỉ có
RSSI tương lai. Mô hình P5a lại là:

```text
logit P_future = b0 + bL*L + bS*S + bR*retry_past
```

`retry_past` là lagged outcome của cùng quá trình delivery và tương quan
`−0,794` với level. Nếu:

```text
retry_past = dL*L + dS*S + U
```

thì `bL,bS` trong mô hình đầy đủ là **partial/direct coefficients** sau
khi giữ retry cố định. Chúng không còn buộc phải bằng `(gamma,4gamma)`.
Ngoài ra logistic coefficients không collapsible: conditional coefficient
có thể khác marginal coefficient ngay cả khi retry không phải confounder
theo nghĩa tuyến tính.

**Dự đoán observable.**

- Ratio đổi đáng kể giữa mô hình đầy đủ và mô hình RSSI+slope-only.
- Orthogonalizing retry theo level/slope làm rõ phần biến thiên retry nào
  đang hút coefficient level.
- Coefficient level nhạy với việc thêm retry hơn coefficient slope vì
  VIF/correlation tập trung ở cặp level–retry.

**Phù hợp P5a?** Có mạnh. VIF level/retry = 2,707, slope = 1,000; bootstrap
ổn định chỉ bác bỏ numerical instability, không bác bỏ việc estimand đã
đổi. Đây là phép so đã nằm đúng trong P5b, nên không nên chạy lén dưới tên
P5a.

### 4. Multicollinearity làm ratio của partial coefficients khó có nghĩa
cấu trúc — khả tín: TRUNG BÌNH

**Cơ chế toán học.** Khi level và retry cùng mã hóa distance/channel state,
ma trận thông tin có trục yếu. Coefficients riêng lẻ phụ thuộc vào cách
chia tín hiệu chung, dù linear predictor tổng có thể rất ổn định. Ratio của
hai partial coefficients vì thế không còn là một invariant vật lý.

**Dự đoán observable.**

- Covariance `cov(beta_L,beta_R)` lớn; coefficient hai biến dịch ngược nhau
  giữa seed/stratum trong khi prediction ít đổi.
- Condition index của design cao chủ yếu trên trục level–retry.
- Ratio ổn định hơn nếu xét một estimand không conditioning qua retry.

**Phù hợp P5a?** Một phần. Corr `−0,794` và PC1 level–retry ủng hộ, nhưng
VIF 2,707 < 5, beta bootstrap rất ổn định và slope gần trực giao. Do đó
multicollinearity có thể làm đổi diễn giải, nhưng khó giải thích toàn bộ
độ lệch như một lỗi số học.

### 5. Logit của xác suất trung bình khác logit tại RSSI trung bình
— khả tín: CAO/TRUNG BÌNH

**Cơ chế toán học.** Nhãn là nhiều attempt trải trên bốn giây. Nếu xác suất
tại thời điểm `u` là:

```text
p(u) = logistic(alpha + gamma RSSI(u))
```

thì GLM quan sát:

```text
p_bar = average_u p(u)
```

nhưng nói chung:

```text
logit(average logistic(eta(u)))
!= average eta(u)
!= alpha + gamma RSSI(midpoint)
```

do sigmoid phi tuyến (Jensen/non-commutation). Vì thế ngay cả trajectory
tuyến tính hoàn hảo và attempt uniform, coefficient pseudo-true của GLM
aggregate không bắt buộc cho ratio 4.

**Dự đoán observable.**

- Sai lệch ratio lớn nhất khi RSSI quét qua vùng dốc của sigmoid trong một
  cửa sổ, tức `|slope|` lớn và PDR trung gian.
- Calibration/deviance residual có hình cong theo slope và level.
- Ratio cục bộ khác giữa vùng PDR gần 0, vùng waterfall và vùng gần 1.
- Một phép tích phân logistic theo trajectory dự báo aggregate PDR tốt hơn
  phép thay bằng midpoint, dù không thêm feature mới.

**Phù hợp P5a?** Có. 75,2% dòng có `0<PDR<1`, đúng vùng phi tuyến có thể
quan trọng; nhãn không bị ceiling toàn cục. Addendum midpoint chỉ kiểm thời
gian attempt, chưa kiểm phép đổi thứ tự giữa `average` và `logit`.

### 6. Quan hệ logit–RSSI không tuyến tính toàn dải — khả tín: TRUNG BÌNH

**Cơ chế toán học.** Mô hình ratio giả định một `gamma` duy nhất. Thực tế
PDR theo RSSI có waterfall; sau Nakagami, detection floor và interference:

```text
logit p = g(RSSI),  g'(RSSI) không hằng
```

Khi slope làm RSSI đi qua các vùng có `g'` khác nhau, coefficient level là
đạo hàm trung bình tại phân bố level còn coefficient slope là trung bình
có trọng số theo trajectory. Ratio hai trung bình không bằng horizon.

**Dự đoán observable.**

- Partial residual của level có curvature.
- Ratio/cục bộ slope effect thay đổi theo RSSI band dù giữ khoảng cách.
- Score test cho `level^2` hoặc spline basis có tín hiệu.

**Phù hợp P5a?** Có thể. Sàn detect và ghim percentile chứng minh phân bố
không đối xứng; chưa có residual diagnostic để xác nhận độ cong trên raw
feature.

### 7. Interaction `RSSI × slope` hoặc `RSSI × retry` — khả tín:
TRUNG BÌNH/CAO

**Cơ chế toán học.** Nếu:

```text
logit p =
  ... + bS*S + bLS*L*S + bLR*L*retry
```

thì marginal slope effect là:

```text
d logit(p)/dS = bS + bLS*L
```

Không tồn tại một ratio toàn cục duy nhất. GLM không tương tác trả về trung
bình có trọng số của các local effects, không phải horizon.

**Dự đoán observable.**

- Slope có ích nhất ở vùng RSSI boundary, ít ích ở link rất tốt/rất chết.
- Residual mang dấu có hệ thống theo tích `L*S` hoặc `L*retry`.
- Ratio theo RSSI/retry strata đổi nhưng có mẫu vật lý nhất quán.

**Phù hợp P5a?** Khá phù hợp. Beta slope theo `rssi_n`/vùng không ổn định
và retry bão hòa ở đuôi xa. PLAN đã dự kiến interaction model ở P5b, tức
đây là nguy cơ đã được nhận diện trước kết quả.

### 8. Pooled probe/CBR tạo mixture và omitted traffic class — khả tín: CAO

**Cơ chế toán học.** Nhãn gộp:

```text
p_bar =
  (n_probe*p_probe + n_cbr*p_cbr) / (n_probe+n_cbr)
```

nhưng `p_probe != p_cbr` do self-contention/on-path load. Tỷ trọng CBR lại
liên quan distance, route availability và số trial. Nếu không có indicator
traffic class/on-path, ba-feature GLM fit một compromise surface. Omitted
class effect có thể đi vào cả beta level lẫn beta slope và phá ratio.

**Dự đoán observable.**

- Ratio khác giữa probe-only, pooled và pooled+on-path indicator.
- Residual phụ thuộc `trials_cbr/trials_future`.
- Cùng RSSI/slope/retry, row on-path có PDR tương lai khác off-path.

**Phù hợp P5a?** Rất phù hợp với P2: `q_cbr >= q_probe`, độ chênh tăng theo
route load; 72,4% trial on-path dồn vào 400–800 m. Đây là omitted regime
có bằng chứng trực tiếp, không phải giả thuyết chung chung. PLAN đã để
quyết định gộp cho P5/P5b.

### 9. Future contention/channel state là omitted variable — khả tín: CAO

**Cơ chế toán học.** PDR tương lai phụ thuộc:

```text
RSSI trajectory + future interference + future route/load state
```

Retry quá khứ chỉ là proxy không hoàn hảo cho contention tương lai.
Nếu future contention tương quan với level hoặc slope (do topology và
route), omitted-variable bias làm coefficients không còn structural.

**Dự đoán observable.**

- Residual theo seed/time/on-path/source dù đã cho ba feature.
- Slope ratio đổi theo CBR share hoặc route availability.
- Retry-only có predictive power lớn nhưng không hấp thụ hết residual
  traffic-class structure.

**Phù hợp P5a?** Cao. P2 đã chứng minh spatial load khác nhau giữa probe
và CBR, admission feedback và q_cbr/q_probe khác nhau. Mô hình vẫn có thể
dự đoán tốt trong nominal scenario nhưng ratio không còn là horizon thuần.

### 10. Informative trial weighting — khả tín: TRUNG BÌNH

**Cơ chế toán học.** Binomial GLM cho mỗi row trọng số thông tin gần bằng
`n=trials_future`. Nếu mean model đúng tuyệt đối conditional trên X, n
không gây bias. Nhưng khi có mixture/heterogeneity, pseudo-true beta tối ưu:

```text
argmin sum_i n_i * deviance_i(beta)
```

khác beta tối ưu theo link-row. Link xấu sinh retry, link on-path sinh CBR,
boundary link có ít trial; do đó n là informative.

**Dự đoán observable.**

- Equal-row diagnostic hoặc capped-weight diagnostic làm ratio đổi, trong
  khi attempt-weighted calibration có thể vẫn tốt hơn.
- Leverage tập trung ở row có nhiều CBR/retry.
- Ratio theo quantile trials khác nhau.

**Phù hợp P5a?** Có thể. Median trials chỉ 7 và bố trí CBR không đều; P2
đã ghi q trung bình là attempt-weighted. Tuy nhiên không được thay weighting
cho model chính: per-attempt estimand là quyết định phương pháp đúng. Đây
chỉ là sensitivity diagnostic về heterogeneity.

### 11. Correlated retries và overdispersion — khả tín trực tiếp: THẤP;
kết hợp heterogeneity: TRUNG BÌNH

**Cơ chế toán học.** Attempts cùng frame không độc lập nên:

```text
Var(Y|n,p) > n p(1-p)
```

Cluster-robust theo seed sửa covariance của beta, không đổi point estimate.
Nếu conditional mean đúng, overdispersion một mình không làm ratio lệch.
Nó chỉ làm lệch point estimate khi đi cùng informative cluster size,
mixture hoặc state-dependent retry chain.

**Dự đoán observable.**

- Pearson/deviance dispersion > 1.
- Residual variance tăng theo retry share/trials.
- Point beta khá ổn định nhưng naive SE nhỏ hơn cluster/bootstrap SE.

**Phù hợp P5a?** Correlation attempts chắc chắn tồn tại, nhưng
`FrameRetryLimit=2`, cluster/bootstrap ổn định. Vì thế đây không phải ứng
viên chính cho chênh 46%.

### 12. Censoring tại receiver floor và selection theo beacon — khả tín:
TRUNG BÌNH/CAO

**Cơ chế toán học.** RSSI chỉ tồn tại khi beacon giải mã được. Gần floor:

```text
E[RSSI_observed | decoded] > RSSI_latent
```

và thời điểm/mẫu được giữ phụ thuộc fading. Level bị kéo lên, slope của
chuỗi mẫu sống sót không còn slope latent; trong khi probe label vẫn có
thể rất xấu nhờ neighbor TTL. Đây là measurement-selection bias, không
phải clip do normalization.

**Dự đoán observable.**

- Residual/ratio đổi mạnh theo `beacon_ratio` và proximity tới floor.
- Level distribution dẹt ở đáy; beta level/slope khác ở vùng beacon_ratio
  thấp dù cố định distance.
- Approaching và receding link gần floor có selection bất đối xứng.

**Phù hợp P5a?** Cao về cơ chế: p20 level cách sàn hiệu dụng chỉ 1,4 dB và
SD p20 giữa seed cực nhỏ. Kiểm attenuation theo `rssi_n` không bác bỏ
censoring; nó chỉ bác bỏ mẫu đơn điệu cần cho reliability-ratio.

### 13. Measurement error còn lại không có dạng attenuation đơn giản
— khả tín: TRUNG BÌNH

**Cơ chế toán học.** Kiểm `rssi_n` giả định measurement error chủ yếu làm
beta slope tăng đơn điệu khi n tăng. Nhưng mean và slope cùng được ước
lượng từ chuỗi RSSI irregular/censored; errors có thể dị phương sai và
tương quan:

```text
L_obs = L_true + eL
S_obs = S_true + eS
Cov(eL,eS | decoded pattern) != 0
```

Trong multiple regression, correlated errors có thể kéo beta theo bất kỳ
hướng nào, không chỉ attenuation về 0.

**Dự đoán observable.**

- Ratio phụ thuộc sample-time geometry/Sxx và beacon_ratio tốt hơn chỉ n.
- Error pattern khác giữa approaching/receding link.
- Within-row OLS covariance của intercept/slope dự báo coefficient drift.

**Phù hợp P5a?** Có thể, nhưng dữ liệu row không lưu mean sample time/Sxx
hay raw samples nên chưa kiểm trực tiếp được. Non-monotonic `rssi_n` làm
giả thuyết attenuation scalar kém tin, không loại hết errors-in-variables.

### 14. Curvature của LogDistance và gia tốc hình học — khả tín: TRUNG BÌNH

**Cơ chế toán học.** Kênh có:

```text
RSSI(d) = C - 10 n log10(d)
```

Ngay cả UAV chuyển động thẳng đều, RSSI theo thời gian không hoàn toàn
tuyến tính vì `log d(t)`. Với đổi hướng/gia tốc:

```text
RSSI(t+u) =
  RSSI(t) + S*u + 0,5*A*u^2 + ...
```

Nếu curvature `A` tương quan với L/S, bỏ nó làm beta slope trở thành một
average tangent coefficient, không phải horizon.

**Dự đoán observable.**

- Sai số ngoại suy đổi theo distance và dấu slope.
- Consecutive-window `kappa` khác giữa approaching/receding.
- Residual có cấu trúc theo `S^2`, distance hoặc acceleration hình học.

**Phù hợp P5a?** Hợp lý về vật lý FANET/Gauss–Markov. Tuy nhiên fixed
400–600 m vẫn không cho attenuation đơn điệu không trực tiếp kiểm
curvature; cần diagnostic trajectory, không cần đổi model chính.

### 15. Heterogeneity theo link/seed và non-collapsibility — khả tín:
TRUNG BÌNH

**Cơ chế toán học.** Cluster-robust SE không đưa random intercept/slope vào
conditional mean. Nếu:

```text
logit p_ij = a_link + gamma_link*(L + H_link*S) + ...
```

GLM gộp trả một non-collapsible weighted average; ratio của averages không
bằng average horizon. Không cần shadowing per-link để có heterogeneity:
route role, contention domain và mobility encounter đã đủ.

**Dự đoán observable.**

- Seed/link-specific ratio phân tán có cấu trúc dù bootstrap mean ổn định.
- Within-link centered coefficients khác between-link coefficients.
- Random-intercept/conditional diagnostic giảm residual grouping.

**Phù hợp P5a?** Trung bình. Bootstrap seed hẹp bác bỏ drift lớn giữa run,
nhưng không nhìn encounter/link-level heterogeneity bên trong mỗi seed.

### 16. Complete-case selection do thiếu retry và hygiene gates — khả tín:
THẤP/TRUNG BÌNH

**Cơ chế toán học.** Full model loại 3.403 row (0,65%) thiếu retry. Nếu xác
suất có retry feature phụ thuộc việc link mới xuất hiện/biến mất:

```text
P(observed retry | L,S,Y) không hằng
```

thì complete-case beta có selection bias. Harness còn yêu cầu
`minTrials=2`, `minRssiSamples=3`, cũng là selection trước CSV.

**Dự đoán observable.**

- Missing-retry indicator dự đoán được từ level/slope/distance.
- Row sát khi link xuất hiện/biến mất có slope distribution khác.
- Ratio sensitivity tập trung ở encounter boundary.

**Phù hợp P5a?** Có cơ chế nhưng tỷ lệ thiếu retry chỉ 0,65%; khó giải thích
toàn bộ chênh lệch. Selection do sàn RSSI quan trọng hơn.

### 17. Bucket-boundary attribution và fail misclassification — khả tín:
THẤP

**Cơ chế toán học.** ACK timeout của attempt cuối có thể rơi sang bucket
sau; fail bị kẹp bằng attempt theo lớp. Sai số label ở biên thời gian có
thể tương quan với retry và thời điểm attempt.

**Dự đoán observable.**

- Ratio nhạy với row có `fails_slipped`.
- Sai lệch tập trung ở attempt sát boundary.

**Phù hợp P5a?** Không đáng kể: `fails_slipped` khoảng 0,04% row và
FrameRetryLimit=2. Không đủ độ lớn để giải thích 2,15 so với 4.

### 18. Class imbalance/quasi-separation — khả tín: THẤP

**Cơ chế toán học.** Nhiều row PDR 0/1 có thể làm coefficient bị chi phối
bởi vùng separation, ratio không đại diện slope trung tâm.

**Dự đoán observable.**

- Coefficient rất lớn/không hội tụ, bootstrap bất ổn.
- Leverage tập trung ở một đuôi label.

**Phù hợp P5a?** Kém. Dataset không ceiling: 75,2% row có PDR trung gian;
coefficient và bootstrap rất ổn định.

### 19. Feature scaling hoặc sai đơn vị — khả tín: RẤT THẤP, gần như loại

**Cơ chế toán học.** Ratio chỉ có đơn vị giây khi level là dB và slope là
dB/s. Z-score/clip riêng từng biến sẽ phá ratio.

**Dự đoán observable.**

- Ratio đổi theo normalization constants.
- Model matrix không còn raw units.

**Phù hợp P5a?** Không. P5a fit raw feature, có intercept tự do, không clip
và báo đúng đơn vị. `(a,b,c)` normalized chỉ là artifact trình bày.

### 20. Bias của ratio estimator hoặc chỉ 24 cluster — khả tín: RẤT THẤP

**Cơ chế toán học.** Ratio của hai estimator có finite-sample bias, nhất
là khi denominator gần 0.

**Dự đoán observable.**

- Bootstrap ratio lệch/skew rộng; beta_RSSI không ổn định.

**Phù hợp P5a?** Không. Beta_RSSI có z≈70; delta CI và bootstrap CI gần
trùng, rất hẹp quanh 2,15. Sai số lấy mẫu không thể kéo tới 4.

### 21. Hai giả thuyết đã đóng — không dùng lại để giải thích

- **Midpoint nhãn:** scheduler expectation 1,991 s nhưng level ở tâm
  `t−2`, nên center-to-center horizon 3,991 s.
- **Attenuation scalar theo `rssi_n`:** không tăng đơn điệu toàn tập hay
  trong 400–600 m; không được chọn ba tầng đầu hoặc áp reliability-ratio.

Chúng có thể còn limitation đo lường chung, nhưng không còn là lời giải
đơn giản cho ratio.

## Các kiểm chứng train-only hợp lệ, không thay pipeline/P5b

Các kiểm dưới đây chỉ là diagnostic. Không kiểm nào được dùng để chọn
threshold/model bằng holdout, sửa frozen weights hay thay bảng P5b.

### A. Linear contrast recenter level về anchor — không cần fit mới

Kiểm:

```text
H0: beta_S - 2 beta_L = 0
```

Dùng covariance cluster hiện có:

```text
Var(beta_S - 2 beta_L)
= Var(beta_S) + 4 Var(beta_L) - 4 Cov(beta_S,beta_L)
```

và bootstrap seed hiện có để lấy CI. Báo thêm sensitivity khi offset tâm
feature là `2±epsilon` do timestamp mẫu không lưu.

Ý nghĩa:

- contrast ≈ 0: slope chủ yếu sửa lag của mean;
- contrast > 0 nhỏ: còn predictive trend sau anchor nhưng effective horizon
  ngắn;
- contrast tương ứng khoảng 2 s: mới phù hợp dự báo tới tâm nhãn từ anchor.

Đây là reparameterization của cùng fit, không phải model mới.

### B. Kiểm persistence bằng hai cửa sổ RSSI liên tiếp

Ghép cùng `(seed,src,dst)` ở anchor `t` và `t+4`:

```text
D = rssi_level(t+4) - rssi_level(t)
D ~ intercept + kappa * rssi_slope(t)
```

Hai level là mean của hai cửa sổ kề nhau, có tâm cách đúng khoảng 4 s.
Cluster theo seed; báo coverage của link ghép được và sensitivity theo
approaching/receding, không lọc model chính.

Ý nghĩa:

- `kappa ≈ 4`: slope vật lý bền đủ; distortion nằm ở logistic/retry/label;
- `kappa ≈ 2,15`: ratio GLM phản ánh persistence vật lý ngắn;
- `kappa ≈ 2`: slope chủ yếu đưa mean về anchor;
- `kappa ≈ 0`: slope không dự báo window RSSI kế tiếp dù association với
  PDR vẫn mạnh.

Kiểm này không dùng PDR, không fit model P5b và trực tiếp falsify mắt xích
động học của phép kiểm ratio.

### C. Cluster-robust score tests cho functional form

Trên full-model fit hiện có, score-test lần lượt các term chẩn đoán:

```text
level^2
level*slope
level*retry
slope*retry
```

Không chọn model hay xuất weight mới. Observable chính là residual structure
và score statistic theo seed. Nếu interaction mạnh, một ratio toàn cục
không có nghĩa vật lý.

### D. Residual audit theo biến đã có

Không refit; vẽ/bảng deviance residual theo:

- raw RSSI band;
- `beacon_ratio`;
- slope sign/magnitude;
- `trials_cbr/trials_future`;
- trials quantile;
- distance;
- seed/link.

Mẫu residual phân biệt censoring, source mixture, curvature và informative
weighting mà không đụng holdout.

### E. Probe/CBR coefficient sensitivity — để nguyên cho P5b

Fit probe-only, pooled và pooled+on-path indicator là kiểm đúng cho omitted
traffic class, nhưng PLAN đã xếp nó vào quyết định P5. Không nên chạy trước
dưới dạng “review check” nếu nó sẽ tạo thêm một bảng model-selection song
song. Chỉ ghi đây là hypothesis có độ tin cao và để P5b thực hiện một lần.

### F. Retry conditioning sensitivity — để nguyên cho P5b

So full với RSSI+slope-only là phép kiểm trực tiếp mediation/non-collapsibility,
nhưng chính là hàng đối chứng P5b đã đăng ký trước. Không chạy sớm và không
đọc trước kết quả dưới tên khác.

## Hai kiểm đáng làm nhất trước P5b

### Ưu tiên 1 — linear contrast `beta_S - 2 beta_L`

Lý do:

- dùng đúng fit/covariance/bootstrap hiện có, không fit model mới;
- kiểm trực tiếp phát hiện reviewer quan trọng nhất: beta slope có bao nhiêu
  phần chỉ để recenter RSSI mean từ `t−2` về `t`;
- prediction/frozen artifact không đổi;
- point estimate đã cho tín hiệu rất mạnh về mặt độ lớn:
  `0,7196 - 2*0,3347 ≈ 0,0501`.

Đây là phép kiểm rẻ nhất nhưng thay đổi cách diễn giải nhiều nhất. Nếu phần
residual slope nhỏ, paper phải gọi ratio 2,15 là “mean-to-current correction
plus a small forward component”, không gọi toàn bộ beta slope là preview
bốn giây.

### Ưu tiên 2 — persistence trên hai cửa sổ RSSI liên tiếp

Lý do:

- kiểm mắt xích vật lý trước logistic và MAC;
- không dùng label, retry, holdout hay model P5b;
- trả lời duy nhất câu hỏi mà residual/interaction không trả lời được:
  slope quá khứ có thật sự tiếp tục trong cửa sổ tương lai không;
- kết quả `kappa` tạo decision tree rõ: nếu gần 4 thì điều tra
  logistic/retry/mixture; nếu gần 2,15 thì dynamic persistence là lời giải
  chính.

Không chọn score-test interaction vào top 2 vì nó chỉ nói full GLM thiếu
term nào đó, chưa phân biệt được slope vật lý ngắn với distortion thống kê.
Không chọn fit bỏ retry/probe-only vì hai phép đó đã là P5b; chạy trước sẽ
làm mờ ranh giới phase.

## Kết luận reviewer

P5a không thất bại: slope là một predictor conditional rất mạnh và ổn định.
Nhưng bằng chứng hiện tại chưa cho phép câu mạnh hơn rằng slope là phép
ngoại suy bốn giây. Tỉ số 2,15 có nhiều lời giải hợp lý; đáng lo nhất là
slope đang chủ yếu sửa timestamp của mean RSSI, cộng với persistence ngắn
và conditioning qua lagged retry.

Trước P5b, chỉ hai diagnostic thật sự đáng chi phí là contrast recentering
và persistence hai cửa sổ. Sau đó dừng: mediation qua retry, source mixture,
interaction và out-of-sample value phải được trả lời đúng một lần trong
P5b như kế hoạch, không mở một nhánh model-selection ngầm ở P5a.

