# P6 — Scientific Interpretation & Mechanistic Analysis

**Ngày:** 2026-07-27  
**Phạm vi:** diễn giải các kết quả đã đóng ở P2, P5a và P5b. Không fit,
không inference thêm, không chọn mô hình, không thay đổi pipeline hoặc
frozen artifact.

## 1. Executive Summary

Mô hình logistic được hiểu phù hợp nhất như một **conditional predictor**
kết hợp ba mô tả của cùng trạng thái link ở các góc nhìn khác nhau:

- `rssi_level` mô tả mức tín hiệu trung bình gần đây;
- `rssi_slope` mô tả hướng và tốc độ biến đổi gần đây của mức tín hiệu;
- `retry_rate` tóm tắt lịch sử giao nhận MAC gần đây, bao gồm phần trạng
  thái kênh và contention đã biểu hiện thành retransmission.

Ba đại lượng được cộng trên thang log-odds, sau đó sigmoid chuyển linear
predictor thành xác suất thành công per-attempt trong cửa sổ tương lai.
Dấu hệ số `(+,+,−)` phù hợp với diễn giải cơ học này: tín hiệu mạnh hơn và
xu hướng RSSI tăng đi cùng xác suất giao nhận cao hơn, trong khi retry gần
đây cao đi cùng xác suất giao nhận thấp hơn. Đây là các **conditional
associations**, không phải ước lượng tác động vật lý riêng rẽ.

P5a cho thấy hệ số slope dương, rất ổn định giữa seed, nhưng tỉ số
\(\beta_{slope}/\beta_{RSSI}=2.1498\) s không thể được đọc trực tiếp như
một horizon hình học 4 s. Tỉ số này là một **effective conditional scale**:
nó phụ thuộc hệ tọa độ thời gian của level, persistence của slope,
conditioning qua retry và phép tổng hợp phi tuyến của nhiều attempts.
Kiểm midpoint và kiểm attenuation đơn giản đã khép lại mà không giải thích
được chênh lệch; P6 không mở lại hai giả thuyết đó.

P5b bổ sung bằng chứng ngoài mẫu theo đúng frozen model. Full raw tốt hơn AR
persistence trên mọi point metric được báo cáo. Tuy nhiên, do không có
frozen reduced model, kết quả này chỉ hỗ trợ giá trị dự đoán **chung** của
RSSI, slope và retry so với AR; nó không cô lập đóng góp ngoài mẫu của từng
feature. Raw tốt hơn clipped chủ yếu vì clipping xoá biên độ và đạo hàm:
trong 0–200 m, `s_RSSI=1` trên 100% dòng nên RSSI-level channel mất hoàn
toàn sensitivity, trong khi raw logit vẫn giữ
\(\partial z/\partial RSSI=0.334722\).

Mọi nhận định trong báo cáo tuân theo ranh giới sau:

| Loại nhận định | Nguồn |
|---|---|
| Cấu tạo kênh, lấy mẫu, mobility, probe/CBR và retry | P2 |
| Hệ số, bootstrap, effective-horizon discrepancy và hai giả thuyết đã bác bỏ | P5a |
| Hiệu năng ngoài mẫu, calibration và raw-versus-clipped | P5b |
| Persistence, nonlinearity và vai trò phối hợp của feature | Mechanistic interpretation dựa trên ba nguồn trên |

## 2. Physical Meaning of Features

### 2.1 RSSI level

`rssi_level` không phải mẫu RSSI tức thời tại anchor \(t\). Nó là trung
bình của các mẫu RSSI thô trong cửa sổ \([t-4,t)\), có tâm thời gian gần
\(t-2\) s. Đại lượng này mô tả **trạng thái mức tín hiệu gần đây** của link.
Giá trị lớn hơn, tức ít âm hơn trên thang dBm, tương ứng với signal margin
tốt hơn trong cấu hình thu đã mô phỏng.

P2 cho thấy trong channel model hiện tại, level chủ yếu đi cùng hình học
log-distance và fading tức thời; không có per-link shadowing cố định để
mean RSSI mang một “chữ ký” riêng cho từng cặp node. Trong từng distance
bin, độ biến thiên mean giữa link nhỏ hơn độ biến thiên theo thời gian của
chính link. Vì vậy, ý nghĩa khoa học thận trọng của RSSI level là vị trí
gần đây của link trên dải chất lượng vật lý, không phải một nguồn thông tin
hoàn toàn tách khỏi khoảng cách.

Hệ số đóng băng là:

\[
\beta_{RSSI}=0.334722\ {\rm dB}^{-1}.
\]

Giữ slope và retry không đổi, tăng 1 dB đi cùng mức tăng 0.334722 trên
log-odds, tương đương odds ratio xấp xỉ 1.40. Diễn giải này có điều kiện
trên hai feature còn lại. Nó không có nghĩa rằng can thiệp làm RSSI tăng
1 dB sẽ tự động tạo đúng mức thay đổi đó trong packet delivery.

Intercept 29.052258 không có diễn giải vật lý độc lập: điểm
`RSSI = slope = retry = 0` nằm ngoài miền RSSI quan sát. Vai trò của
intercept là đặt mặt logit vào đúng miền dữ liệu.

### 2.2 RSSI slope

`rssi_slope` là hệ số OLS của RSSI thô theo thời gian trong cùng cửa sổ
\([t-4,t)\), đơn vị dB/s. Nó mô tả **chiều và tốc độ biến đổi gần đây**:
slope dương đi cùng link đang cải thiện theo thang RSSI; slope âm đi cùng
link đang suy giảm. Slope không phải một phép đo RSSI tương lai và cũng
không mang cam kết rằng xu hướng quá khứ tiếp tục tuyến tính trong bốn giây
tiếp theo.

P5a cho thấy slope gần trực giao với level ở mức toàn tập
(`corr ≈ 0`) và PC2 gần như thuần slope. Do đó mô hình có thể dùng slope
như một mô tả động học bổ sung cho mức RSSI. Hệ số đóng băng là:

\[
\beta_{slope}=0.719591\ {\rm s/dB}.
\]

Giữ level và retry không đổi, tăng 1 dB/s đi cùng mức tăng 0.719591 trên
log-odds, tương đương odds ratio xấp xỉ 2.05. Giá trị này là association
có điều kiện của trend đã quan sát với delivery tương lai. Bootstrap theo
seed giữ dấu và độ lớn ổn định; bằng chứng đó hỗ trợ tính lặp lại của
association trong simulation design, không biến hệ số thành một tham số
động học phổ quát.

### 2.3 MAC retry

`retry_rate` là tỉ lệ retry MAC trong cửa sổ feature quá khứ. Nó là
**lagged delivery-state summary**: retransmission gần đây phản ánh phần
chất lượng propagation, interference, contention và trạng thái nhận đã
biểu hiện tại MAC. Vì thế retry không phải nguồn thông tin độc lập hoàn
toàn với RSSI. P2 đo `corr(level,retry) = -0.793`, tương ứng khoảng 63%
phương sai tuyến tính chia sẻ, còn P5a xử lý retry như một predictor có
điều kiện chứ không như nhãn hiện tại.

Hệ số đóng băng là:

\[
\beta_{retry}=-1.851676.
\]

Giữ RSSI level và slope không đổi, thay đổi retry rate từ 0 lên 1 đi cùng
odds ratio xấp xỉ 0.157; tăng 0.1 retry rate đi cùng odds ratio xấp xỉ
0.831. Đây là cách đọc trên thang log-odds trong miền model. Không nên đọc
nó như hiệu ứng riêng của một retry, vì retry là kết quả tổng hợp của
nhiều trạng thái MAC/channel và còn liên hệ mạnh với RSSI.

## 3. Mechanistic Interpretation

Frozen inference có cấu trúc:

```text
recent physical/MAC observations
    RSSI level, RSSI slope, retry rate
                    ↓
conditional linear predictor
    z = b0 + bL·level + bS·slope + bR·retry
                    ↓
logistic transform
    p_hat = 1 / (1 + exp(-z))
                    ↓
expected per-attempt delivery in the future label window
```

Đây là sơ đồ tính toán và diễn giải cơ học, không phải sơ đồ
nguyên nhân-kết quả.

Trên thang log-odds, ba association được cộng tuyến tính. Trên thang xác
suất, chúng không còn cộng tuyến tính vì:

\[
\frac{\partial \hat p}{\partial x_j}
  = \hat p(1-\hat p)\beta_j.
\]

Cùng một thay đổi RSSI hoặc slope tạo thay đổi xác suất lớn nhất ở vùng
giữa của sigmoid và nhỏ hơn khi \(\hat p\) đã gần 0 hoặc 1. Vì vậy,
coefficient mô tả thay đổi log-odds có điều kiện; nó không phải số điểm
phần trăm PDR cố định trên mọi link.

Mechanistic interpretation phù hợp với các kết quả đã có là:

1. **Level định vị trạng thái gần đây.** Nó cho biết link đang ở vùng tín
   hiệu mạnh, waterfall hay gần sàn thu trong simulation channel.
2. **Slope cung cấp chiều chuyển động của trạng thái.** Hai link có level
   giống nhau nhưng trend ngược dấu không có cùng mô tả động học.
3. **Retry cung cấp persistence của delivery/MAC state.** Hai link có RSSI
   và slope gần nhau vẫn có thể khác về contention hoặc lịch sử thất bại;
   retry tóm tắt phần khác biệt gần đây đã xuất hiện tại MAC.
4. **Logit hợp nhất ba mô tả có điều kiện.** Mô hình không cần ba feature
   độc lập thống kê hoàn toàn; nó phân bổ hệ số cho association còn lại
   của mỗi feature sau khi giữ hai feature kia cố định.

P5a hỗ trợ bước 2 bằng dấu, z-score và bootstrap của slope. P5b hỗ trợ
cơ chế phối hợp bằng việc Full raw vượt AR persistence trên holdout:
LogLoss 0.420494 so với 1.807126, Brier 0.132486 so với 0.152691, ROC AUC
0.830396 so với 0.803451 và PR AUC 0.666080 so với 0.576340. Vì
RSSI-only và RSSI+slope reduced models không có frozen implementation,
P5b không cho phép quy phần cải thiện này cho riêng level hoặc riêng slope.

## 4. Raw versus Clipped Interpretation

Clipping thay đổi thông tin đầu vào trước khi logit được tính:

\[
s(x)=\operatorname{clip}
\left(\frac{x-p_{20}}{p_{80}-p_{20}},0,1\right).
\]

Trong vùng nội suy \(p_{20}<x<p_{80}\), phép biến đổi còn giữ thứ tự và có
đạo hàm khác 0. Ngoài vùng đó, mọi giá trị được ánh xạ về cùng 0 hoặc 1;
biên độ chênh lệch và đạo hàm theo \(x\) bị xoá. Đây là saturation do phép
biến đổi, khác với saturation tự nhiên của sigmoid ở xác suất gần 0/1.

### 4.1 Information loss và derivative

P5b đo trực tiếp rằng trong 0–200 m:

- 4.564/4.564 dòng có `s_RSSI=1`;
- raw giữ \(\partial z/\partial RSSI=0.334722\) log-odds/dB;
- clipped RSSI-level channel có đạo hàm bằng 0 trên 100% dòng;
- raw RSSI contribution có SD 1.240 và range 10.707 log-odds;
- clipped RSSI contribution có SD số học xấp xỉ 0 và range đúng 0.

Vì vậy, clipped representation không chỉ nén scale; nó làm nhiều trạng
thái RSSI khác nhau trở nên không phân biệt được trong vùng gần. Toàn score
vẫn có thể thay đổi qua slope và retry, nên kết luận đúng là RSSI-level
channel mất sensitivity, không phải toàn bộ LinkScore trở thành hằng số.

### 4.2 Calibration và discrimination

Trên toàn holdout:

| Variant | LogLoss | Brier | ROC AUC | PR AUC | ECE-10 |
|---|---:|---:|---:|---:|---:|
| Raw logit | 0.420494 | 0.132486 | 0.830396 | 0.666080 | 0.021919 |
| Clipped-input equivalent | 0.429713 | 0.136479 | 0.829628 | 0.650273 | 0.040041 |

ROC AUC chỉ giảm 0.000767, nên phần lớn thứ hạng toàn cục còn được giữ.
Ngược lại, PR AUC giảm 0.015807, LogLoss và Brier xấu hơn, còn ECE gần
gấp đôi. Mẫu này phù hợp với việc clipping vẫn phân hạng được nhiều link
nhưng làm mất biên độ cần cho xác suất và calibration.

Hậu quả tập trung rõ ở 0–200 m: observed success là 0.9116, mean raw
prediction là 0.9646, còn mean clipped prediction chỉ 0.6541. Mean
\(|p_{raw}-p_{clip}|\) trong vùng này là 30.395 điểm phần trăm. P5b cũng
ghi nhận clipped tốt hơn nhẹ ở một vài metric trong 600–800 m hoặc
\(\ge 800\) m; do đó bằng chứng không hỗ trợ phát biểu raw ưu thế ở mọi
distance band.

### 4.3 Controller sensitivity

Controller cần sự biến đổi của state, không chỉ thứ hạng tĩnh. Khi
RSSI-level channel bị ghim, đạo hàm của channel này theo thời gian bằng 0
cho tới khi RSSI quay lại miền nội suy. Raw logit giữ biên độ và đạo hàm
của level trên toàn miền số thực. Kết quả P5b vì thế hỗ trợ lựa chọn P8
dùng raw logit cho state/TTT, còn clipped LinkScore chỉ phù hợp với vai trò
điểm bị chặn để trình bày hoặc xếp hạng. Nhận định này dựa trên sensitivity
đã đo; nó không khẳng định raw luôn có error nhỏ hơn trong mọi vùng.

## 5. Why Effective Horizon ≠ 4 s

Tỉ số:

\[
H_{\rm eff} =
\frac{\beta_{slope}}{\beta_{RSSI}}
= 2.1498\ {\rm s}
\]

có đơn vị giây, nhưng chỉ bằng horizon vật lý 4 s dưới một cấu trúc hẹp:
level có timestamp đại diện cố định, slope quá khứ tiếp tục không đổi,
RSSI trajectory tuyến tính, logit delivery tuyến tính theo RSSI tại một
thời điểm đại diện, và conditioning qua retry không đổi estimand. P5a
không thiết lập đầy đủ các điều kiện đó.

### 5.1 Effective horizon

`2.1498 s` nên được gọi là effective horizon trên thang logit có điều
kiện. Nó cho biết model đánh đổi bao nhiêu đơn vị coefficient level cho
một đơn vị coefficient slope. Nó không phải timestamp quan sát được của
attempt, cũng không phải thời gian sống còn lại của link.

### 5.2 Timestamp correction

Level là mean trên \([t-4,t)\), tâm gần \(t-2\), trong khi tâm attempts của
nhãn được ước lượng tại \(t+1.991\). Khoảng tâm-đến-tâm là 3.991 s, gần
horizon thiết kế 4 s. Do đó midpoint của label không giải thích tỉ số
2.15 s; giả thuyết này đã được bác bỏ ở P5a.

Cùng lúc, phép đổi tọa độ về endpoint \(t\) cho:

\[
L_t \approx L_{mean}+2S,
\]

\[
\beta_L L_{mean}+\beta_S S
=\beta_L L_t+(\beta_S-2\beta_L)S.
\]

Với frozen coefficients,
\(\beta_S-2\beta_L\approx0.05015\), tương ứng phần ratio còn lại khoảng
0.15 s sau khi recenter level. Đây là đồng nhất thức đại số của cùng
linear predictor, không phải phép đo mới về slope persistence. Nó cho
thấy ratio gốc trộn hai vai trò: đưa mean level từ tâm cửa sổ về anchor và
mô tả association còn lại của trend với nhãn tương lai.

### 5.3 Retry conditioning

Full model ước lượng:

\[
\operatorname{logit}(p_{future})
=b_0+b_L L+b_S S+b_R R.
\]

Vì retry là lagged outcome và tương quan mạnh với level, \(b_L\) và \(b_S\)
là partial coefficients sau khi giữ retry cố định. Chúng không còn là cặp
hệ số của mô hình cấu trúc chỉ có `RSSI_future`. Logistic coefficients còn
không collapsible: conditional coefficient có thể khác coefficient khi
không conditioning, ngay cả khi prediction tổng vẫn phù hợp. Vì vậy không
có đẳng thức bắt buộc \(b_S=4b_L\) trong Full model.

### 5.4 Persistence

**Mechanistic interpretation:** dưới Gauss–Markov mobility, vận tốc và
hướng có thể đổi theo thời gian. OLS slope trong cửa sổ quá khứ vì thế có
thể chỉ còn association một phần với trajectory trong cửa sổ tương lai.
Một persistence kernel ngắn hơn horizon thiết kế sẽ làm effective horizon
nhỏ hơn 4 s mà slope vẫn là predictor ổn định.

P5a chưa đo slope autocorrelation giữa hai cửa sổ hoặc timestamp trajectory
chi tiết. Vì vậy persistence là lời giải cơ học phù hợp, không phải kết quả
đã được phân biệt thực nghiệm khỏi các cơ chế thống kê khác.

### 5.5 Nonlinear aggregation

Nhãn là số successes/failures của nhiều attempts trải trên bốn giây. Nếu
xác suất tức thời là \(p(u)=\operatorname{logistic}(\eta(u))\), model quan
sát trung bình theo attempts. Nói chung:

\[
\operatorname{logit}\{\operatorname{mean}_u[p(u)]\}
\ne \operatorname{mean}_u[\eta(u)].
\]

Do sigmoid phi tuyến, aggregate binomial mean không tương đương delivery
tại đúng midpoint, kể cả khi attempts phân bố đều. Mixture probe/CBR làm
phép tổng hợp còn dị thể hơn. Vì thế coefficient ratio của một GLM gộp là
pseudo-true conditional summary của toàn cửa sổ, không phải phép ngoại suy
RSSI tại một thời điểm duy nhất.

Tổng hợp P5a: midpoint-only và simple attenuation không phù hợp bằng chứng;
những cơ chế còn lại có thể cùng tồn tại. Không có căn cứ để chọn duy nhất
một cơ chế hoặc ép ratio về 4 s.

## 6. Relationship Between Prediction and FANET Dynamics

Trong FANET mô phỏng, link state biến đổi bởi hình học tương đối, fading,
contention và route/load state. Ba feature quan sát các phần khác nhau của
trạng thái đó trên cùng cửa sổ quá khứ:

```text
current operating region     → RSSI level
recent direction of change   → RSSI slope
recent delivery persistence  → MAC retry
```

Logit chuyển bộ mô tả này thành một conditional estimate của success rate
per-attempt trong cửa sổ kế tiếp. Cơ chế này phù hợp với một mạng động:
level phân biệt vùng mạnh/yếu, slope phân biệt hai trajectory có cùng
level hiện tại, còn retry mang trạng thái MAC gần đây mà RSSI không mô tả
hết.

P2 cho thấy traffic regime không đồng nhất. Min-hop OLSR dồn phần lớn CBR
attempts vào 400–800 m, và `q_cbr` cao hơn `q_probe` trong các distance
bin đã báo cáo. Do đó future delivery trong dataset phản ánh cả propagation
và load/route regime. Retry là proxy một phần cho trạng thái này; RSSI và
slope giữ mô tả vật lý trực tiếp hơn. Full model hoạt động như một
conditional compromise surface cho mixture đó.

P5b cho thấy compromise surface đóng băng vẫn mang thông tin trên sáu seed
tách khỏi fit: Full raw vượt AR và calibration tổng thể gần prevalence.
Điều này hỗ trợ diễn giải rằng physical-state descriptors bổ sung thông tin
cho lagged delivery state. Nó không phân tách riêng propagation,
contention và mobility contribution, và không thiết lập một quan hệ
nguyên nhân-kết quả giữa từng feature và packet delivery.

## 7. Scientific Limitations

### 7.1 Conditional prediction

Hệ số là conditional associations của một GLM ba feature. Level và retry
chia sẻ thông tin đáng kể; slope coefficient được đọc sau khi giữ cả hai
feature kia cố định. Không nên chuyển các hệ số thành tác động độc lập của
radio power, mobility hoặc retry policy.

### 7.2 Simulation assumptions

Diễn giải gắn với cấu hình P2: LogDistance + Nakagami, receiver floor và
không có per-link shadowing cố định. Trong mô hình này, RSSI level chủ yếu
mã hoá geometry cùng fading tức thời. Một channel model có shadowing,
obstruction hoặc interference process khác có thể tạo association khác.
P2 cũng cho thấy observation gần receiver floor bị selection bởi khả năng
decode beacon; đây là giới hạn đã biết của miền link quan sát.

### 7.3 Mobility model

Slope được tạo dưới Gauss–Markov mobility của simulation. Persistence của
trend phụ thuộc vận tốc, hướng và cách chúng đổi theo model này. P6 không
có bằng chứng rằng effective horizon 2.15 s chuyển nguyên vẹn sang mobility
trace hoặc flight-control regime khác.

### 7.4 Probe/CBR mixture

P5a gộp per-attempt label từ probe và CBR; 86.31% attempts dùng trong GLM
là probe và 13.69% là CBR, trong khi phần lớn rows là probe-only. P2 đã ghi
nhận probe và on-path CBR có loss regime khác nhau. Full model vì thế mô tả
mixture đã thu, không phải hai response surfaces riêng. Kết quả không cho
phép giả định mixture weight khác vẫn giữ nguyên mapping.

### 7.5 Retry mediation and persistence

Retry là lagged delivery summary, đồng thời liên hệ với RSSI và contention.
Conditioning trên retry có thể hấp thụ một phần association mà level hoặc
slope sẽ mang trong mô hình khác. Full-versus-AR ở P5b hỗ trợ giá trị chung
của bộ feature nhưng không phân rã pathway qua retry.

### 7.6 Six holdout seeds

P5b dùng đúng sáu holdout seeds 30–35 và báo point metrics, không có
confidence interval theo seed cho chênh lệch model. Kết luận predictive
nên giới hạn ở hướng và độ lớn quan sát được, không diễn giải chênh lệch
nhỏ như một kiểm định thống kê.

### 7.7 External validity

Train và holdout dùng cùng simulator family, scenario và frozen
configuration. Kết quả chưa bao phủ hardware radio, environment thực,
khác density/speed/load, hay Tier-C evaluation. P5b cũng thiếu frozen
RSSI-only, RSSI+slope và LET implementations; vì vậy P6 không tuyên bố
Full vượt các comparator đó.

## 8. Conclusion

Diễn giải khoa học gọn nhất là: model logistic kết hợp **mức trạng thái**,
**trend gần đây** và **persistence của delivery/MAC state** trên thang
log-odds để ước lượng conditional future packet-delivery probability.
Dấu và độ ổn định của coefficients phù hợp với diễn giải đó, còn P5b cho
thấy tổ hợp frozen raw giữ giá trị dự đoán ngoài mẫu so với AR persistence.

Raw representation giữ biên độ và derivative mà clipped representation
xoá tại các saturation boundaries. Bằng chứng 0–200 m và degradation của
LogLoss, Brier, PR AUC và calibration hỗ trợ raw logit cho controller
sensitivity, nhưng không hàm ý raw ưu thế ở mọi distance band.

Cuối cùng, \(2.1498\) s là effective conditional scale, không phải
four-second physical horizon. Timestamp correction, conditioning qua
retry, finite trend persistence và nonlinear attempt aggregation giải
thích vì sao đẳng thức 4 s không bắt buộc. Chỉ timestamp midpoint và simple
attenuation đã được kiểm trực tiếp rồi bác bỏ; các cơ chế còn lại phải giữ
đúng nhãn mechanistic interpretation. P6 vì thế giải thích cách model tổ
chức thông tin đã quan sát mà không nâng predictive association thành
phát biểu nguyên nhân-kết quả.
