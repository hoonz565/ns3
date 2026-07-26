# Kế hoạch nghiên cứu — MPC điều khiển HELLO trong OLSR/FANET

Phạm vi: **chỉ LinkScore.** NodeScore để future work.
Trạng thái: **P0**

---

## 0. Chuỗi nhân quả

Mọi phase tồn tại để chứng minh một mắt xích trong chuỗi này:

```
RSSI (mức) + RSSI slope + MAC retry
        │  P5 — fit bằng binomial GLM
        ▼
   LinkScore  →  xác suất giao gói của link
        │  P7 — ngoại suy theo slope
        ▼
   TTT = thời gian còn lại trước khi link vượt ngưỡng
        │  min trên các neighbor (HELLO là broadcast)
        ▼
   Độ cấp bách của node i
        │  P8 — MPC tối ưu trên horizon
        ▼
   Chu kỳ HELLO H_i  +  thời điểm urgent HELLO
        ▼
   OLSR phát hiện đổi topology nhanh/chậm hơn
        ▼
   Bảng định tuyến chính xác hơn  →  PDR ↑, overhead ↓
```

**Điểm can thiệp duy nhất là chu kỳ HELLO.** LinkScore không tham gia Dijkstra, không đổi MPR selection, không đổi TC. Lõi OLSR giữ nguyên RFC 3626. Đây là ràng buộc khiến kết quả quy được về đúng một nguyên nhân.

---

## 1. Ba tạo phẩm đông lạnh — ba nguồn độc lập

| Tạo phẩm | Sinh ra ở | Từ batch | Sau đó là hằng số |
|---|---|---|---|
| `normalization.json` (p20/p80) | P3 | **calibration** (5 seed) | ✓ |
| `(a, b, c)` | P5 | **training** (15 seed) | ✓ |
| Mọi con số báo cáo | P10 | **test / evaluation** (5 seed) | — |

Ba batch **rời nhau hoàn toàn**, chia **theo seed** chứ không theo dòng (các dòng trong một lần chạy tương quan mạnh).

Tuyệt đối cấm: tính percentile trên toàn bộ dữ liệu gộp rồi mới chia train/test. Đó là rò rỉ lặng lẽ — kết quả đẹp hơn thực tế mà không có dấu hiệu nào.

## 2. Ba tầng bằng chứng

| Tầng | Chứng minh | Phase | Cần chạy sim? |
|---|---|---|---|
| **A** — thống kê | LinkScore dự đoán đúng chất lượng link | P5 | Không |
| **B** — hệ thống, offline | LinkScore chọn đúng đường tốt | P6 | Không |
| **C** — end-to-end | MPC HELLO cải thiện mạng thật | P10 | Có |

Không vòng lặp vào nhau: A dùng nhãn per-link, B dùng nhãn per-path, C dùng kết quả end-to-end. Reviewer bác một tầng thì hai tầng còn lại vẫn đứng. Các paper hiện có chỉ có tầng C.

## 3. Quy tắc bao trùm: train và deploy phải tính feature giống hệt nhau

Nếu dataset huấn luyện tính RSSI bằng trung bình cửa sổ mà node thật dùng EWMA, phân bố feature ở hai nơi khác nhau — trọng số fit trên phân bố này bị áp lên phân bố kia. Đó là **train/deploy skew**, âm thầm và khó phát hiện.

**Nhất quán quan trọng hơn tối ưu.** Chốt định nghĩa feature một lần ở P2, dùng y hệt ở P8.

---

## P0 — Môi trường và kiểm chứng thiết bị đo

**Ý tưởng.** Không debug được callback trên 30 node. Hai node, một đứng yên, một bay thẳng ra xa — quét toàn dải RSSI trong một lần chạy, đối chiếu được với path loss tính tay.

**Việc.** Dựng ns-3.45 trên filesystem native Linux (không bao giờ `/mnt/c`, `/mnt/d`). Chạy `link-probe.cc` hai chế độ `--fading=false` và `--fading=true`. Vẽ RSSI theo khoảng cách chồng lên đường lý thuyết.

**Cổng.**
- RSSI giảm đơn điệu, bám đường lý thuyết ở chế độ không fading
- MAC retry khác 0 nhưng không phải toàn bộ (bằng 0 tuyệt đối → callback câm)
- Residual σ ở chế độ fading khớp giá trị dự kiến từ Nakagami m đã chọn (**m = 5 → σ ≈ 2.0 dB**)

**Nếu hỏng.** Lệch RSSI lớn → callback đọc nhầm trường. `txFirst = 0` → `PeekHeader` thất bại ở điểm trace Tx. σ ≈ 5–7 dB → Nakagami vẫn ở mặc định m = 0.75, chưa cấu hình lại.

---

## P1 — Đóng băng cấu hình

**Ý tưởng.** Một file duy nhất, mọi script đọc từ đó. Mỗi tham số kèm một dòng "tại sao giá trị này" và nguồn trích dẫn. File này chính là bảng Simulation Setup trong paper. Tham số để mặc định mà không kiểm tra là tham số sẽ cắn bạn — Nakagami `m = 0.75` là bài học đã trả giá.

| Nhóm | Tham số | Giá trị | Căn cứ |
|---|---|---|---|
| Không gian | Diện tích | 2000×2000×500 m (cao 100–600) | Khớp paper FANET 2026; bậc TB ~6 neighbor |
| | Số node | 30 | |
| Di động | Model | `GaussMarkovMobilityModel` | Chuẩn de-facto FANET |
| | Alpha | 0.85 | Template FANET ns-3 |
| | MeanVelocity | Uniform[15, 30] m/s | Giữa dải các paper (5–60) |
| | **MeanPitch** | **Uniform[−0.05, +0.05]** | Template phổ biến để `Min=Max=0.05` → mọi UAV leo mãi rồi dán vào trần |
| | NormalVelocity | Normal[0, var 2.0, bound 4.0] | Template để var = 0 → tốc độ không dao động |
| | TimeStep | 0.5 s | |
| PHY | Chuẩn | 802.11a, 5.18 GHz | |
| | Rate manager | `ConstantRateWifiManager`, 6 Mbps | Rate adaptation che mất tín hiệu cần đo |
| | **TxPower** | **19 dBm** | Chọn theo **degree đo được**, không theo công thức link budget. Cho d(PDR 0.5) = **625 m**, degree **6.14** — cả hai đo ở P1 |
| | **`MinimumRssi`** | **−101 dBm** | Mặc định −82 dBm là **sàn cứng trên RSSI**, cao hơn giới hạn do nhiễu 7 dB. Hạ về −101 thì ràng buộc chuyển sang `Threshold` (4 dB SNR). Ở degree cố định nó **không mua thêm tầm phủ** — lý do là (a) gỡ kiểm duyệt trên chính feature RSSI, (b) mép link dịch theo can nhiễu thay vì đứng yên. **Khai báo trong paper** |
| | **Degree trung bình** | **6.14** | **Đo được** (P1, tỉ lệ nhận beacon ≥ 0.5 trong 5 s), cô lập 0.6%. Kiểm chứng bằng đếm hình học từ vị trí ghi được, không dùng beacon: ~6.0. Đừng tính bằng công thức mật độ — hộp cao 500 m so với tầm phủ 625 m nên công thức 2D và 3D lệch gần 2× |
| | **Động lực học độ cao** | quasi-2D | Mỗi node ở nguyên lát cao ~107 m suốt run 300 s (trung vị z-span; **100%** node quét dưới nửa dải 500 m). Vận động dọc đóng góp trung vị **0.7%** vào thay đổi khoảng cách làm link đổi trạng thái (3.2% trước khi chiếu). Tức: **vị trí** 3D phân tầng giữa các node, động lực học do chuyển động ngang |
| | `WifiMacQueue::MaxDelay` | 100 ms (interface probe) | Giãn nhịp probe không chặn được backlog: 10 ms → retry_rate 0.9478, 50 ms → 0.9475. Chặn bằng thời gian sống của gói |
| | Path loss exponent | 2.2 | Đo đạc A2A ≈ free-space |
| | **Nakagami m₀/m₁/m₂** | **8 / 5 / 3** | LoS trên không; 0.75 là kênh đô thị |
| | **Distance1 / Distance2** | **100 m / 300 m** | Mặc định 80/200 m là thang mặt đất |
| Thời gian | Sim time | 300 s | |
| | Seed | 25 (5 calib / 15 train / 5 test) | |
| Cửa sổ | Δ (feature) | 4 s | Xem P7 — 2 s thì slope chìm trong nhiễu |
| | τ (nhãn) | 4 s | |

---

## P2 — Harness thu dữ liệu (Tier 2)

**Ý tưởng — phase quan trọng nhất về phương pháp.** Mỗi link có hướng đều có mẫu, không phụ thuộc đường đi nào, và phân bố MAC retry phải giống môi trường mà bộ điều khiển sẽ gặp ở Tier 3.

**Tier 2 chạy đồng thời ba thứ** (sửa 2026-07-26; bản cũ ghi "không chạy giao thức định tuyến" — không còn đúng):

1. **OLSR chuẩn, HELLO cố định 2 s — chỉ đóng vai máy tạo tải.** Không sửa nó, không đo nó, không báo cáo về nó. Nó định tuyến bằng hop count nên mù về LinkScore → không có endogeneity (lựa chọn đường không phụ thuộc đại lượng đang được fit).
2. **Luồng CBR đa chặng qua UDP/OLSR** — tạo tranh chấp và chuyển tiếp thật, để phân bố MAC retry ở Tier 2 giống Tier 3. Nếu chỉ có probe thì trọng số fit trên một phân bố rồi bị áp lên phân bố khác (train/deploy skew, quy tắc bao trùm mục 3).
3. **Probe unicast L2 tới mọi hàng xóm còn nghe được beacon** — lấp phần link mà routing không dùng. Không có nó, retry và nhãn bị kiểm duyệt về link on-path, trong khi RSSI (đi nhờ broadcast) thì không → kiểm duyệt **bất đối xứng**, không thấy được bằng kiểm tra nhanh.

**Bốn loại phát:**

| Loại | Kiểu | Cho ta | Vào dataset? |
|---|---|---|---|
| OLSR HELLO/TC | Broadcast (UDP) | Tải nền + định tuyến cho CBR | Không |
| CBR đa chặng | Unicast UDP | Tranh chấp thật; attempt trên link on-path | Nhãn (cột `_cbr`) |
| Beacon L2 | Broadcast định kỳ | RSSI mọi link, phát hiện hàng xóm, degree | Feature RSSI |
| Probe L2 | Unicast 0x88b5 tới từng hàng xóm | MAC retry, nhãn PDR cả link off-path | Retry + nhãn (cột `_probe`) |

Broadcast không có ACK → không retry, không nhãn. Chỉ probe thì không phát hiện được hàng xóm ban đầu (vòng lặp chết). Chỉ CBR thì nhãn bị kiểm duyệt về on-path. Cần cả bốn.

**Nhãn ghi tách cột: `trials_probe/fails_probe` và `trials_cbr/fails_cbr`.** Link on-path có n ≈ hàng trăm attempt CBR mỗi cửa sổ, link off-path chỉ có ~8 probe; binomial GLM trọng số theo n nên bản gộp bị link on-path chi phối — và link mang CBR có thêm tự tranh chấp (self-contention) không nằm trong feature, tức các quan sát có thể không khả hoán khi đã cho feature. Gộp hay không là quyết định của **P5** (fit ba bản: probe-only, gộp, gộp + chỉ báo on-path, so β); P2 chỉ thu đủ dữ liệu để P5 quyết được.

**Probe là thiết bị đo, không phải một phần hệ thống triển khai.** Như hầm gió: dùng để đặc trưng hoá rồi tháo ra. Overhead của nó không tính vào kết quả paper vì nó không tồn tại ở P10.

**Rủi ro phải đo ngay ở smoke test: tải do chính thiết bị đo chi phối.** Ước lượng thô cho thấy probe chiếm airtime gấp ~3 lần CBR — nếu đúng, môi trường tranh chấp mà retry được đo trong đó do traffic đo lường tạo ra, còn Tier 3 không có probe/beacon (quy tắc 13: không fit ở mức tải khác mức bộ điều khiển sẽ thấy). Smoke test **phải in bảng airtime tách theo nguồn** (beacon / probe / CBR / OLSR / ack) — con số đó quyết định mức CBR, hệ số tái sử dụng không gian không đoán được. Ba hướng nếu xấu: nâng CBR cho traffic ứng dụng chi phối; probe thích ứng (chỉ probe neighbor chưa đủ attempt từ traffic thật); hoặc chấp nhận và định lượng β_mac theo mức tải (quy tắc 14).

### Định nghĩa feature — chốt một lần, dùng ở cả P2 và P8

| Feature | Cách tính | Lý do |
|---|---|---|
| `rssi_level` | EWMA **hoặc** trung bình cửa sổ — chọn một, dùng ở cả hai nơi | Cả hai đều ổn cho ước lượng mức |
| `rssi_slope` | **OLS trên mẫu RSSI thô**, không qua EWMA | Xem dưới |
| `retry_rate` | `retries / (first_attempts + retries)`, chỉ unicast | Broadcast không có ARQ, sẽ làm bẩn mẫu số |

**Vì sao không EWMA trước rồi OLS.** EWMA không làm lệch slope — với tín hiệu dốc tuyến tính, EWMA cho cùng đường dốc tịnh tiến một hằng số, đạo hàm không đổi. Nhưng:

- Theo Gauss–Markov, OLS trên dữ liệu thô **đã là** ước lượng tuyến tính không chệch tốt nhất cho hệ số dốc. Không tiền xử lý nào vượt qua được.
- EWMA tạo tương quan giữa các điểm liền kề. OLS giả định sai số độc lập. Với sai số tương quan dương, **sai số chuẩn bị đánh giá thấp** — bạn tưởng có nhiều thông tin hơn thực có. Với đề tài dựa vào p-value của β_slope, đây là lỗi nghiêm trọng.
- EWMA cần ~1/α mẫu để hội tụ; cửa sổ ngắn thì đang đo giai đoạn quá độ.

Ở node thật, giữ ring buffer ~20 mẫu cho slope là khả thi (vài trăm byte mỗi neighbor). Không cần EWMA để tiết kiệm bộ nhớ.

**Nếu vẫn dùng EWMA cho mức RSSI:** đừng chọn α, hãy chọn hằng số thời gian rồi suy ra. `α ≈ Δt / τ_desired`. Ghi vào paper là "τ_eff = 1 s", không phải "α = 0.3" — con số thứ nhất có nghĩa vật lý và không đổi khi đổi tần suất beacon.

### Cấu trúc dữ liệu ra

Một dòng cho mỗi (link có hướng, cửa sổ):

```
seed, t, src, dst, dist_m,
rssi_level, rssi_slope, rssi_n,          ← features, cửa sổ [t−Δ, t)
retry_rate, tx_attempts,                  ← features, cùng cửa sổ
trials_future, fails_future, pdr_future   ← nhãn, cửa sổ [t, t+τ)
```

**Tách thời gian cưỡng chế bằng cấu trúc.** Dòng chỉ được ghi tại thời điểm mô phỏng `t+τ`, khi cửa sổ nhãn đã đóng. Không thể vô tình fit contemporaneous ngay cả khi cố ý.

Vì sao sống còn: MAC retry và PDR gần như cùng một đại lượng vật lý. Fit trong cùng cửa sổ cho R² giả tạo trên 0.9 và reviewer bắt được ngay.

**Giữ phân biệt rỗng với bằng 0.** `retry_rate = 0` nghĩa là "truyền 500 frame không lỗi"; rỗng nghĩa là "chưa truyền gì". Hai sự thật khác nhau.

### Cổng nghiệm thu — ba con số in ra cuối mỗi lần chạy

| Chỉ số | Ngưỡng | Nếu không đạt |
|---|---|---|
| Tỉ lệ dòng có `retry_rate > 0` | ≥ 10% | Tải quá nhẹ → tăng traffic nền |
| Số link quan sát được | ≈ số cặp trong tầm sóng | Probe chưa chạy đúng |
| Phân bố `pdr_future` | Có đuôi thấp, không dồn hết ở 1.0 | Mạng quá thoáng → giảm TxPower hoặc mở rộng diện tích |

Chỉ số thứ ba dễ bỏ sót nhất. 90% link có PDR = 1.0 thì regression không có gì để học. **Link PDR 30% quý hơn link PDR 100%** — vùng biên là nơi công thức phải phân biệt được.

**Không bao giờ lọc theo giá trị nhãn.** Chỉ lọc theo số mẫu (`trials ≥ 5`). Lọc theo PDR cao là cách chắc chắn nhất để fit ra mô hình vô dụng.

---

## P3 — Hiệu chuẩn ngưỡng

**Ý tưởng.** RSSI là dBm, slope là dB/s, retry là tỉ lệ — phải đưa về [0,1] mới cộng được. Ngưỡng lấy từ percentile của phân bố thật, không đặt tay.

**Việc.** 5 seed calibration → gộp → tính p20/p80 cho `rssi_level` và `rssi_slope` → ghi `normalization.json` → **đóng băng**.

### Hai bản chuẩn hoá — đây là điểm sửa quan trọng

| Dùng ở | Feature | Vì sao |
|---|---|---|
| **Fit** (P5) | **Thô hoặc z-score, KHÔNG clip** | Clip kiểm duyệt biến giải thích, làm β lệch về 0 |
| **Triển khai** (P8) | Chuẩn hoá + clip về [0,1] | MPC cần LinkScore bị chặn để hàm mục tiêu ổn định |

Clip ở p20 nghĩa là link RSSI −95 dBm và −88 dBm **đều thành 0** — nén đúng vùng biên quý nhất thành một điểm.

Sau khi fit cả hai bản, **so khả năng dự đoán trên tập test**. Nếu clip làm tụt đáng kể, nới ra p5/p95.

Điều này không mâu thuẫn với `a+b+c=1`: chuẩn hoá trọng số là biến đổi đơn điệu, thứ tự xếp hạng link không đổi.

### Công thức triển khai

```
s_rssi  = clip((rssi_level − p20) / (p80 − p20), 0, 1)
s_slope = clip((slope − p20) / (p80 − p20), 0, 1)
s_mac   = 1 − clip(retry_rate, 0, 1)          ← chú ý ĐẢO CHIỀU
```

`s_mac` đảo chiều vì retry cao là xấu — cả ba metric phải cùng hướng "cao = tốt".

Lưu ý `retry_rate` đã nằm trong [0,1) theo định nghĩa, nên phép clip ở đó là no-op. **Thử `1 − sqrt(retry_rate)`** rồi so AIC — phân bố retry lệch phải rất nặng (phần lớn cửa sổ bằng 0), biến đổi căn thường cải thiện rõ.

**Nếu chọn dải bất đối xứng cho slope** (ví dụ −2.0 đến +0.5): hợp lý, vì slope âm mạnh rất quan trọng còn slope dương mạnh không tốt hơn dương nhẹ bao nhiêu. Nhưng phải nói rõ đó là **lựa chọn thiết kế có biện minh**, không để nó trông như percentile.

**Ghi chú paper.** Các hằng số này là **dữ liệu**, không phải magic number. Ghi xuất xứ. Làm tròn cho đẹp sẽ âm thầm đổi kết quả khoa học.

---

## P4 — Dataset huấn luyện

20 seed rời hoàn toàn với calibration. Áp `normalization.json` đã đóng băng. Chia train/test **theo seed** (15/5).

**Cổng.**
- VIF giữa `s_rssi` và `s_slope` < 5 — node tiến lại gần có cả RSSI cao lẫn slope dương, cộng tuyến là rủi ro thật
- Cả ba feature đều có phương sai đáng kể

---

## P5 — Fit trọng số (Tầng A)

**Ý tưởng.** Mỗi cửa sổ trên một link có `tx_count` lần thử và một tỉ lệ thành công — đó là quan sát nhị thức. Fit như nhị thức tương đương **chính xác** với logistic regression trên từng frame, không mất chút thông tin nào.

```python
import statsmodels.api as sm, numpy as np

successes = np.round(df.pdr_future * df.trials_future)
failures  = df.trials_future - successes

X = sm.add_constant(df[["rssi_level", "rssi_slope", "retry_rate"]])   # THÔ, không clip
res = sm.GLM(np.c_[successes, failures], X,
             family=sm.families.Binomial()).fit()
print(res.summary())
```

**Bốn quy tắc.**

1. **Không nhị phân hoá nhãn.** Không ngưỡng τ. Cắt ngưỡng vứt khác biệt giữa 0.72 và 0.94, và đẻ ra siêu tham số phải biện minh.
2. **Không ràng buộc `a+b+c=1` trong lúc fit.** Trong logistic, độ lớn β quyết định độ dốc sigmoid — dữ liệu quyết định nó. Ép tổng bằng 1 là ép độ dốc, intercept không bù lại được. Fit tự do có intercept, báo cáo β kèm sai số chuẩn, **chuẩn hoá ở bước xuất cuối**.
3. **β âm là phát hiện, không phải bug.** Đừng clip về 0 — nó nghĩa là metric hoạt động ngược chiều giả định.
4. Bootstrap để kiểm tra ổn định. β dao động mạnh giữa các lần lấy mẫu lại → chưa đủ dữ liệu.

### Kiểm chứng vật lý: β_slope / β_RSSI ≈ τ

Nếu slope thực sự hoạt động như bộ ngoại suy tuyến tính thì

```
logit(p) = γ₀ + γ₁·RSSI(t+τ) = γ₀ + γ₁·RSSI(t) + (γ₁·τ)·slope
                                        └─β_RSSI─┘  └─β_slope─┘
```

Suy ra dự đoán kiểm tra được: **β_slope / β_RSSI ≈ τ**. Đơn vị khớp — β_RSSI là [1/dB], β_slope là [s/dB], tỉ số ra **giây**.

Nếu tỉ số này xấp xỉ đúng horizon nhãn, bạn có bằng chứng trực tiếp rằng slope đang làm đúng việc dự báo, không phải chỉ là biến tương quan ngẫu nhiên. Đây là một kết quả rất mạnh — và nó **chỉ hiện ra khi fit trên feature thô**. Chuẩn hoá từng metric độc lập sẽ phá tỉ số này.

### Mô hình đối chứng — phần quyết định sức nặng của paper

| Mô hình | Câu hỏi |
|---|---|
| Chỉ `rssi_level` | Ba metric có hơn một metric không? |
| Bỏ `rssi_slope` | Slope có đóng góp thống kê không? |
| Thêm tương tác `rssi × slope` | Slope có ý nghĩa khác nhau tuỳ mức RSSI không? |
| **Khoảng cách Euclid** | LinkScore có hơn "khoảng cách trá hình" không? |
| **LET hình học** (vị trí + vận tốc) | **Đối thủ thật — UAV có GPS** |
| Geometric mean có trọng số | `Σ wᵢ·log(xᵢ)` — cùng GLM trên feature log hoá |

So bằng AIC/BIC và khả năng dự đoán trên test.

Mô hình LET là mối đe doạ lớn nhất. Cả nhánh position-based FANET (FORP, POLSR, ML-OLSR, OLSR+) dùng vị trí tính link expiration time. Reviewer sẽ hỏi *"UAV có GPS, sao không dùng?"* — cần trả lời bằng số, không bằng lời.

Thắng hoặc hoà: lập luận là **vị trí cho hình học, RSSI cho kênh thật** — link có thể chết ở 200 m vì nhiễu và sống tốt ở 800 m khi thoáng. Thua đậm: biết sớm còn hơn biết trong phản biện; đổi hướng sang kết hợp cả hai (như OLSR+ đã làm) hoặc nhấn kịch bản GPS-denied.

**Đầu ra.** `(a,b,c)` đông lạnh + bảng β kèm CI và p-value + scatter LinkScore dự đoán so với PDR thực đo trên test + tỉ số β_slope/β_RSSI.

---

## P6 — Kiểm chứng mức đường đi (Tầng B)

**Ý tưởng.** Tầng A chứng minh đúng ở mức link, tầng B chứng minh có ý nghĩa ở mức hệ thống. Hai thang khác nhau, không vòng lặp. **Hoàn toàn offline, không chạy thêm ns-3.**

```
với mỗi cửa sổ t:
    dựng đồ thị từ các link có dữ liệu tại t

    cost cạnh = −log(pdr_future)     → Dijkstra → đường oracle
    cost cạnh = −log(LinkScore)      → Dijkstra → đường dự đoán

    ghi: trùng không, regret = PDR_oracle − PDR_dự_đoán
```

**Vì sao `−log` và Dijkstra.** Xác suất giao gói dọc đường là **tích** các chặng; lấy log thành tổng — đúng dạng Dijkstra cần. Đây là logic của ETX.

Không dùng min hay trung bình: đường 6 chặng mỗi link 0.95 cho tích 0.735; đường 2 chặng mỗi link 0.90 cho 0.810. Đường thứ hai thắng dù **từng link kém hơn** — mỗi chặng là một cơ hội mất gói. Phép nhân phạt số chặng đúng cách mà không cần hằng số hop penalty tuỳ ý.

**Chỉ số.** Tỉ lệ trúng top-1 và phân bố regret. Regret quan trọng hơn: trúng 60% nghe kém, nhưng regret trung bình 2% PDR thì LinkScore vẫn rất tốt — chọn nhầm sang đường gần tương đương.

Quét mọi cặp nguồn–đích và mọi cửa sổ. Vài phút Python thay cho hàng giờ mô phỏng. Dùng luôn để so nhiều bộ trọng số: GLM, đều nhau (1/3,1/3,1/3), chỉ RSSI.

**Giới hạn ghi vào paper.** Tích các xác suất giả định link hỏng độc lập. Không dây thì không — chặng liền kề dùng chung kênh và tự nhiễu nhau, nên PDR thực của đường dài **tệ hơn** tích số. Đây là lý do ETT/WCETT ra đời sau ETX; nói rõ mình kế thừa giới hạn nào.

---

## P7 — Mô hình dự báo

**Ý tưởng.** MPC cần dự báo trạng thái tương lai. Ngoại suy tuyến tính bằng chính RSSI slope — slope làm hai nhiệm vụ: vừa là feature trong LinkScore, vừa là cơ chế dự báo trong MPC.

```
RSSI(t+k) ≈ RSSI(t) + slope × k  →  chuẩn hoá  →  LinkScore(t+k)

TTT = (LinkScore − L_thresh) / max(0, −dLinkScore/dt)
```

**Vì sao Δ = 4 s.** Ở 400 m, tốc độ tương đối 30 m/s, exponent 2.2, m = 5 (σ ≈ 2.0 dB):

| Cửa sổ | Slope thật | Sai số chuẩn | t |
|---|---|---|---|
| 2 s | 0.67 dB/s | 0.68 dB/s | ≈ 1 — **không phân biệt được** |
| 4 s | ~0.63 dB/s | 0.24 dB/s | ≈ 2.6 — **đo được** |

Đánh đổi: feature cũ hơn. Nhưng nếu không thì β_slope vô nghĩa và mất một phần ba công thức.

**Cổng — đừng bỏ qua.** Đo sai số dự báo tại từng bước horizon: dự báo LinkScore ở t+1…t+N, so với thực đo, vẽ RMSE theo k. **Điểm RMSE vượt ngưỡng chấp nhận được chính là N tối đa có nghĩa.** Đặt N lớn hơn thế là tự lừa mình.

**Việc thêm (chốt ở P2, 2026-07-26): đo suy giảm chất lượng slope theo tốc độ lấy mẫu.** Tier 2 ước lượng slope từ beacon 10 Hz (~40 mẫu/cửa sổ Δ = 4 s), nhưng Tier 3 lấy RSSI từ HELLO nên tốc độ lấy mẫu là 1/H và SE(slope) ∝ √H — xem CLAUDE.md mục "Ba tầng mô phỏng" và "cấu trúc dual control". Lấy dữ liệu beacon 10 Hz đã có, lấy mẫu thưa xuống lưới 0.5/1/2/4 s, tính lại slope, vẽ SE và β_slope theo tốc độ lấy mẫu — không cần chạy lại mô phỏng nào. Đường cong đó là đầu vào trực tiếp cho hàm mục tiêu MPC (chi phí của mù tỉ lệ với độ bất định của TTT, mà độ bất định đó tỉ lệ √H).

Đây cũng là hình kết quả tốt: định lượng chính xác "dự đoán được bao xa" thay vì phát biểu mơ hồ.

**Ghi chú.** Ở 200 m slope là 1.25 dB/s — gần gấp đôi so với ở 400 m. Chất lượng đo biến thiên theo khoảng cách. Vào Limitations.

---

## P8 — Bộ điều khiển

### 8a. Sửa OLSR — hai cái bẫy

**Bẫy timer.** `HelloTimerExpire()` schedule lại bằng `m_helloInterval`; đổi attribute chỉ có hiệu lực từ lần expire kế tiếp. Muốn nhanh phải cancel và reschedule — nhưng đã có báo cáo việc này làm lệch throughput ngay cả khi gán lại đúng giá trị cũ.

**Test bắt buộc:** viết `SetHelloInterval()`, gọi với **chính giá trị hiện tại**, khẳng định kết quả trùng khít từng bit. Lệch → có bug âm thầm sẽ làm hỏng mọi kết quả sau.

**Bẫy hold time.** `OLSR_NEIGHB_HOLD_TIME` là macro biên dịch, **không** dẫn xuất từ `m_helloInterval`. Tăng chu kỳ mà hold time đứng yên → link bị coi là mất oan. Phải cho hold time bám theo **và** set trường `HTime` trong gói HELLO (ns-3 có `SetHTime()`).

**Lấy diff EE-Hello để tham khảo — đọc, không build:**

```bash
git clone https://github.com/imtiaztee/EE-Hello-Adaptive-Hello-Interval-for-FANETs ee-hello
wget https://www.nsnam.org/releases/ns-allinone-3.27.tar.bz2 && tar xjf ns-allinone-3.27.tar.bz2
diff -u ns-allinone-3.27/ns-3.27/src/olsr/model/olsr-routing-protocol.cc \
        ee-hello/src/olsr/model/olsr-routing-protocol.cc > ee-hello.diff
```

Tìm bốn thứ: chỗ cancel/reschedule timer, chỗ cập nhật hold time, chỗ set `HTime`, và xử lý phía node nhận khi hold time khác mặc định. Bỏ qua phần công thức tính chu kỳ — phần đó của bạn khác hoàn toàn.

Repo là ns-3.27 dùng waf (đã bị gỡ khỏi ns-3 từ 3.36). Đọc như **tài liệu**, viết lại trên ns-3.45.

### 8b. Hàm mục tiêu

```
J_i = Σ_{k=t}^{t+N−1} [  q_L · H_k / TTT_k                    ← mù bao lâu
                       +        H_nom / H_k                    ← overhead
                       + q_S · ((H_k − H_{k−1}) / H_nom)²  ]   ← chống dao động

ràng buộc:  H_min ≤ H_k ≤ H_max,   |H_k − H_{k−1}| ≤ ΔH_max
```

`H/TTT` = bạn sẽ mù trong bao nhiêu phần trăm quãng đời còn lại của link. Dùng TTT chứ không dùng `(1 − LinkScore)`: link 0.3 nhưng **ổn định** thì HELLO dày cũng vô ích; link 0.8 nhưng **đang lao dốc** mới cần theo sát. Mức không quyết định, tốc độ thay đổi mới quyết định.

Vô thứ nguyên hoá bằng `H_nom` — nếu không, ba số hạng có đơn vị s, 1/s, s² và các q không so sánh được.

**Gộp per-link thành per-node:** `TTT_i = min over j of TTT_ij`. HELLO là broadcast, không gửi riêng cho một neighbor được. Nên có ablation `min` so với `mean`.

### 8c. Trọng số q — quét, không fit

| | `a, b, c` | `q_L, q_S` |
|---|---|---|
| Bản chất | Tham số mô hình dự đoán | Sở thích thiết kế |
| Ground truth | Có (PDR) | **Không** |
| Xử lý | Fit bằng GLM | Quét, báo cáo Pareto |

Phân biệt kinh điển: **system identification** so với **cost tuning**. Không dữ liệu nào nói được q_L nên bằng bao nhiêu — nó chỉ nói bạn coi trọng độ chính xác định tuyến hơn hay overhead hơn.

Luận điểm paper **không** phải "bộ q này tối ưu" mà là: *đường Pareto (PDR theo overhead) của MPC nằm trên đường Pareto của mọi baseline.*

### 8d. Solver

H rời rạc 8 mức (0.25–4 s), N = 3 → 512 nhánh. Duyệt hết bằng C++, không thư viện ngoài. `ΔH_max` cắt bớt nhánh. Deterministic, dễ defend hơn gọi solver ngoài.

### 8e. Biến thể self-triggered (khuyến nghị)

Hỏi *"lần HELLO kế tiếp nên phát lúc nào"* thay vì *"chu kỳ nên là bao nhiêu"*. Đây là **self-triggered control**, nền lý thuyết vững (Heemels/Johansson/Tabuada CDC 2012; dòng self-triggered MPC).

Lai: MPC chu kỳ đặt nhịp nền **+ trigger sự kiện** phát urgent HELLO khi một link vượt ngưỡng cấp bách giữa hai chu kỳ. Bù được điểm yếu broadcast — không cần tăng nhịp nền cho cả node.

**Vì sao quan trọng về lý thuyết — SỬA 2026-07-26.** Bản cũ của mục này lập luận: "H không ảnh hưởng tới LinkScore, nên không có `ΔH_max` thì bài toán tách rời theo k, đây chỉ là MPC với preview nhiễu ngoại sinh." Lập luận đó **sai một nửa**: H không đổi chất lượng vật lý của link, nhưng H **điều khiển tốc độ lấy mẫu của bộ ước lượng trạng thái** — ở Tier 3, RSSI đến từ HELLO nên số mẫu trong cửa sổ Δ là Δ/H và SE(slope) ∝ √H. H nhỏ → slope chính xác hơn → TTT tin cậy hơn → quyết định tốt hơn.

Đó chính xác là **dual control** (Feldbaum 1960): tín hiệu điều khiển vừa điều tiết, vừa thăm dò. Bài toán không tách rời theo k kể cả khi bỏ ràng buộc tốc độ thay đổi, vì hành động hôm nay quyết định bạn biết bao nhiêu ngày mai — horizon có ý nghĩa thật, không phải mượn từ `ΔH_max`. Và hàm mục tiêu có thêm một số hạng có nguồn gốc vật lý thay vì đặt tay: chi phí của mù không chỉ ∝ H/TTT mà còn ∝ độ bất định của chính TTT, tỉ lệ √H (đường cong định lượng đo ở P7).

Khung self-triggered (Heemels/Johansson/Tabuada CDC 2012) vẫn là biến thể khuyến nghị — nó tương thích với dual control, không thay thế. Chi tiết và ràng buộc lấy mẫu Tier 2/Tier 3: CLAUDE.md mục "cấu trúc dual control".

---

## P9 — Baselines

| Baseline | Vai trò |
|---|---|
| OLSR chuẩn, HELLO = 2 s | Mốc RFC |
| OLSR HELLO = 0.5 s / 5 s | Hai cận overhead |
| **Ngưỡng phản ứng đơn giản** | **Quan trọng nhất** — `H = clip(k · TTT)`, không horizon |
| **EE-Hello** | Đối thủ chính, implement lại trên ns-3.45 |
| LET hình học điều khiển HELLO | Đối chứng GPS, nếu P5 cho thấy LET mạnh |

Baseline ngưỡng phản ứng rẻ và quyết định: nếu MPC không thắng nổi nó, độ phức tạp của MPC không được biện minh. Reviewer sẽ hỏi — có sẵn câu trả lời tốt hơn bị hỏi bất ngờ.

**Về baseline hậu-2019.** AI-Hello, DQN-OLSR, MA-IDDPG-OLSR, FBCR đều **không có code công khai**. Implement lại RL từ mô tả rồi báo cáo nó thua bạn là không defend được. Trích trong Related Work, nêu rõ không có implementation công khai nên so sánh trực tiếp ngoài phạm vi.

**Kỳ vọng thực tế.** EE-Hello ghi nhận OLSR không đạt nổi PDR 0.5 trong bất kỳ cấu hình FANET nào của họ. Số của bạn thấp là đặc tính bài toán, không phải lỗi setup.

---

## P10 — Đánh giá (Tầng C)

5 seed evaluation rời hoàn toàn. Quét `(q_L, q_S)` → Pareto PDR–overhead cho MPC và từng baseline. Ablation: LinkScore đầy đủ / bỏ slope / chỉ RSSI / trọng số đều nhau. Quét độ nhạy: tốc độ, mật độ, mức tải.

| Nhóm chỉ số | Nội dung |
|---|---|
| Hiệu năng | PDR, delay p50/p95, throughput |
| Chi phí | Byte control/giây, số HELLO/node/giây |
| Định tuyến | Số lần đổi route, thời gian không có route |
| **Điều khiển** | **Phân bố H theo thời gian, tần suất urgent trigger** |

Nhóm cuối là thứ các paper khác không báo cáo và nó thuyết phục: cho thấy bộ điều khiển **thực sự làm gì**. Một biểu đồ H theo thời gian chồng lên TTT của link cấp bách nhất cho thấy trực quan rằng MPC phản ứng đúng chỗ.

**Khung thống kê.** Nếu MPC ngang bằng chứ không vượt ở một số cấu hình, đó là **non-inferiority** — cần **công bố biên độ trước** (ví dụ "không kém quá 3 điểm PDR"), ghi vào file đã commit **trước khi** chạy. Chốt sau khi nhìn kết quả thì vô giá trị.

---

## Bảng tóm tắt

| Phase | Đầu ra | Sim | Rủi ro chính |
|---|---|---|---|
| P0 | Instrumentation đã kiểm chứng | 2 | Callback signature lệch phiên bản |
| P1 | Config đóng băng | 0 | Tham số mặc định không kiểm tra |
| P2 | Harness Tier 2 | 1 | Thiếu probe → dataset censored |
| P3 | `normalization.json` | 5 | Clip trước khi fit → β lệch |
| P4 | train/test theo seed | 20 | Chia theo dòng thay vì theo seed |
| P5 | `(a,b,c)` + CI + p-value | 0 | β_slope không có ý nghĩa; LET thắng |
| P6 | Top-1 match, regret | 0 | — |
| P7 | Horizon N có căn cứ | 0 | Đặt N quá lớn |
| P8 | Controller + solver | vài | Hold time không bám chu kỳ |
| P9 | Baselines | — | EE-Hello implement sai |
| P10 | Pareto + ablation | ~5×cấu hình | So một điểm thay vì Pareto |

**Ba phase đắt nhất về trí tuệ (P5, P6, P7) không cần chạy mô phỏng.** Sau khi P2–P4 xong, phần khoa học lặp lại được hàng chục lần trong vài phút. Dataset là tài sản; controller chỉ là hệ quả. Đừng vội viết controller.

---

## Nếu một phase hỏng

| Triệu chứng | Chẩn đoán | Hành động |
|---|---|---|
| `β_slope` không có ý nghĩa | Δ quá ngắn, hoặc tốc độ quá thấp | Tăng Δ lên 6 s; tăng MeanVelocity; nếu vẫn không → **báo cáo đó là kết quả**, LinkScore thành 2 metric |
| β_slope/β_RSSI lệch xa τ | Slope không hoạt động như ngoại suy | Kiểm tra tương tác rssi×slope; có thể quan hệ phi tuyến |
| Retry gần như bằng 0 khắp nơi | Tải quá nhẹ | Tăng traffic nền, quét `numFlows` |
| Retry cao đồng đều bất kể RSSI | Bão hoà | Giảm tải. Điểm ngọt = nơi tương quan retry–RSSI âm sâu nhất |
| `pdr_future` dồn hết ở 1.0 | Mạng quá thoáng | Giảm TxPower hoặc mở rộng diện tích |
| Khoảng cách dự đoán tốt bằng LinkScore | LinkScore = distance trá hình | Kiểm tra β_slope — ở FANET, thông tin ngoài khoảng cách đến từ **slope**, không từ fading |
| LET hình học thắng đậm | GPS mạnh hơn RSSI ở kịch bản này | Kết hợp cả hai (như OLSR+), hoặc nhấn kịch bản GPS-denied |
| MPC không thắng baseline ngưỡng | Horizon không tạo giá trị | Kiểm tra `ΔH_max` đủ chặt chưa; nếu không → dùng khung self-triggered |
