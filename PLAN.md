# Kế hoạch nghiên cứu — MPC điều khiển HELLO trong OLSR/FANET

Phạm vi: **chỉ LinkScore.** NodeScore để future work.

---

## Chuỗi nhân quả của đề tài

Trước khi vào từng phase, phải nắm rõ chuỗi lập luận. Mọi phase tồn tại để chứng minh một mắt xích trong chuỗi này:

```
RSSI + slope + MAC retry
        │  (P5: fit bằng binomial GLM)
        ▼
   LinkScore  ──►  dự đoán xác suất giao gói của link
        │  (P7: ngoại suy theo slope)
        ▼
   TTT = thời gian còn lại trước khi link vượt ngưỡng
        │  (min trên các neighbor — vì HELLO là broadcast)
        ▼
   Độ cấp bách của node i
        │  (P8: MPC tối ưu trên horizon)
        ▼
   Chu kỳ HELLO H_i (và thời điểm phát urgent HELLO)
        │
        ▼
   OLSR phát hiện thay đổi topology nhanh/chậm hơn
        │
        ▼
   Bảng định tuyến chính xác hơn  ──►  PDR ↑, overhead ↓
```

**Điểm can thiệp duy nhất là chu kỳ HELLO.** LinkScore **không** tham gia vào Dijkstra, không đổi MPR selection, không đổi TC. Lõi OLSR giữ nguyên RFC 3626. Đây là ràng buộc thiết kế quan trọng nhất — nó là thứ khiến kết quả quy được về đúng một nguyên nhân.

Ba tầng bằng chứng, độc lập nhau:

| Tầng | Câu hỏi | Phase |
|---|---|---|
| A — thống kê | LinkScore có dự đoán đúng chất lượng link không? | P5 |
| B — hệ thống, offline | LinkScore có chọn đúng đường tốt không? | P6 |
| C — end-to-end | MPC HELLO có cải thiện PDR/overhead không? | P10 |

Tầng A và B không cần triển khai gì, chỉ cần dataset. Tầng C mới là kết quả chính của paper.

---

## P0 — Môi trường và kiểm chứng thiết bị đo

**Ý tưởng.** Bạn không debug được callback trên 30 node. Hai node, một đứng yên, một bay thẳng ra xa — quét toàn dải RSSI trong một lần chạy, và bạn đối chiếu được với công thức path loss tính tay.

**Việc làm.**
- Dựng ns-3.45 trên filesystem native Linux (không bao giờ `/mnt/c`, `/mnt/d`).
- Chạy `link-probe.cc`, hai chế độ `--fading=false` và `--fading=true`.
- Vẽ RSSI theo khoảng cách, chồng lên đường path loss lý thuyết.

**Cổng nghiệm thu.**
- RSSI giảm đơn điệu theo khoảng cách, bám đường lý thuyết ở chế độ không fading.
- MAC retry khác 0 nhưng không phải toàn bộ (nếu bằng 0 tuyệt đối → callback câm, không phải mạng tốt).
- Residual σ ở chế độ có fading khớp với giá trị dự kiến từ tham số Nakagami m đã chọn.

**Nếu hỏng.** Sai lệch RSSI lớn → callback đang đọc nhầm trường. `txFirst = 0` → `PeekHeader` thất bại ở điểm trace Tx. Kiểm tra signature với `src/wifi/model/` của đúng bản đang cài, đừng đoán.

---

## P1 — Đóng băng cấu hình thí nghiệm

**Ý tưởng.** Mọi script từ P2 trở đi đọc từ một file duy nhất. Nếu calibration và training chạy trên cấu hình khác nhau dù chỉ một tham số, toàn bộ chuỗi bằng chứng đứt mà không có dấu hiệu nào.

Quan trọng không kém: **mỗi tham số phải có một dòng ghi chú "tại sao giá trị này"** kèm nguồn trích dẫn. File này chính là bảng Simulation Setup trong paper. Tham số nào để mặc định mà không kiểm tra là tham số sẽ cắn bạn — Nakagami `m=0.75` là bài học đã trả giá.

**Cấu hình FANET đề xuất.**

| Nhóm | Tham số | Giá trị | Căn cứ |
|---|---|---|---|
| Không gian | Diện tích | 2000 × 2000 × 500 m (cao 100–600) | Khớp paper FANET 2026; cho bậc trung bình ~6 neighbor với 30 node |
| | Số node | 30 | |
| Di động | Model | `GaussMarkovMobilityModel` | Chuẩn de-facto của FANET |
| | Alpha | 0.85 | Template FANET ns-3 phổ biến |
| | MeanVelocity | Uniform[15, 30] m/s | Giữa dải các paper (5–60 m/s) |
| | **MeanPitch** | **Uniform[−0.05, +0.05]** | Template phổ biến để `Min=Max=0.05` — lỗi, mọi UAV leo mãi rồi dán vào trần |
| | NormalVelocity | Normal[0, var=2.0, bound=4.0] | Template để var=0 → tốc độ không dao động |
| | TimeStep | 0.5 s | |
| PHY | Chuẩn | 802.11a, 5.18 GHz | |
| | Rate manager | `ConstantRateWifiManager`, OfdmRate6Mbps | Rate adaptation che mất tín hiệu cần đo |
| | TxPower | 10 dBm | Cho tầm phủ ≈ 500 m |
| | Path loss exponent | 2.2 | Đo đạc A2A cho thấy xấp xỉ free-space |
| | **Nakagami m₀/m₁/m₂** | **8 / 5 / 3** | LoS chiếm ưu thế trên không; m=0.75 mặc định là kênh đô thị |
| | **Nakagami Distance1/2** | **100 m / 300 m** | Mặc định 80/200 m là thang mặt đất, sai hoàn toàn cho link 500 m |
| Thời gian | Sim time | 300 s | |
| | Seed | 25 (5 calib / 15 train / 5 test) | Batch rời nhau |

**Cổng nghiệm thu.** File config commit vào git, mọi script load từ đó, không hardcode lặp lại ở đâu.

---

## P2 — Harness thu dữ liệu (Tier 2)

**Ý tưởng — đây là phase quan trọng nhất về mặt phương pháp.**

Mục tiêu: mỗi link có hướng trong mạng đều có mẫu, **số mẫu đều nhau**, và không phụ thuộc vào đường đi nào cả.

Vì sao **không chạy giao thức định tuyến** ở phase này: nếu OLSR chọn đường, thì chỉ link nằm trên đường được chọn mới mang unicast, mới có MAC retry và nhãn PDR. 30 node có ~180 link có hướng nhưng chỉ ~25 link mang traffic — mất 85% dữ liệu, và mất theo cách bạn không kiểm soát được.

Vì sao cần **hai loại phát**:

| Loại | Kiểu | Cho ta | Vì sao cần |
|---|---|---|---|
| Beacon | Broadcast định kỳ | RSSI, slope, phát hiện hàng xóm | Tới được cả link quá yếu để unicast thành công |
| Probe | Unicast tới từng hàng xóm | MAC retry, nhãn PDR | Chỉ unicast mới kích hoạt ARQ |

Broadcast không có ACK, không có retransmit — nên nếu chỉ có beacon thì không có retry và không có nhãn. Ngược lại nếu chỉ có probe thì không phát hiện được hàng xóm ban đầu (vòng lặp chết: không biết ai là hàng xóm → không probe → không có frame → không biết ai là hàng xóm).

**Probe là thiết bị đo, không phải một phần của hệ thống triển khai.** Giống hầm gió: dùng để đặc trưng hoá, rồi tháo ra. Overhead của nó không tính vào kết quả paper vì nó không tồn tại ở P10.

**Cấu trúc dữ liệu ra.**

Một dòng cho mỗi (link có hướng, cửa sổ thời gian):

```
seed, t, src, dst, dist_m,
rssi_mean, rssi_slope, rssi_n,          ← features, cửa sổ [t−Δ, t)
retry_rate, tx_attempts,                 ← features, cùng cửa sổ
trials_future, fails_future, pdr_future  ← nhãn, cửa sổ [t, t+τ)
```

**Tách thời gian phải cưỡng chế bằng cấu trúc, không bằng quy ước.** Dòng chỉ được ghi ra tại thời điểm mô phỏng `t+τ`, khi cửa sổ nhãn đã đóng. Như vậy không thể vô tình fit contemporaneous ngay cả khi cố ý.

Vì sao điều này sống còn: MAC retry và PDR gần như là cùng một đại lượng vật lý. Fit chúng trong cùng cửa sổ cho R² giả tạo trên 0.9 và reviewer bắt được ngay.

**Tham số thời gian.** Δ = 4 s cho FANET (xem P7 để hiểu vì sao không phải 2 s), τ = 4 s.

**Cổng nghiệm thu — ba con số phải in ra ở cuối mỗi lần chạy.**

| Chỉ số | Ngưỡng | Nếu không đạt |
|---|---|---|
| Tỉ lệ dòng có `retry_rate > 0` | ≥ 10% | Tải quá nhẹ → tăng traffic nền |
| Số link quan sát được | ≈ số cặp trong tầm sóng | Probe chưa chạy đúng |
| Phân bố `pdr_future` | Phải có đuôi thấp, không dồn hết ở 1.0 | Mạng quá thoáng → giảm TxPower hoặc mở rộng diện tích |

Chỉ số thứ ba quan trọng nhất và dễ bỏ sót. Nếu 90% link có PDR = 1.0, regression không có gì để học — giống hệt vấn đề ceiling effect. **Link có PDR 30% quý hơn link có PDR 100%**, vì vùng biên là nơi công thức phải phân biệt được.

**Không bao giờ lọc theo giá trị nhãn.** Chỉ lọc theo số lượng mẫu (`trials ≥ 5` — phép đo có đủ tin cậy chưa). Lọc theo PDR cao là cách chắc chắn nhất để fit ra một mô hình vô dụng.

---

## P3 — Hiệu chuẩn ngưỡng chuẩn hoá

**Ý tưởng.** RSSI thô là dBm, slope là dB/s, retry là tỉ lệ. Phải đưa cả ba về [0,1] mới cộng được. Ngưỡng dùng percentile của phân bố thực tế, không dùng số tròn tự đặt.

**Việc làm.**
- Chạy 5 seed **calibration** (rời hoàn toàn với train/test).
- Gộp lại, tính p20/p80 cho `rssi_mean` và `rssi_slope`.
- MAC retry dùng ngưỡng vật lý cố định 0 và 1, không cần percentile.
- Ghi ra `normalization.json` và **đóng băng** — mọi phase sau đọc từ đây, không tính lại.

**Vì sao tách batch riêng.** Nếu tính percentile trên chính tập training rồi fit trên đó, ngưỡng đã "nhìn" dữ liệu training — rò rỉ nhẹ nhưng có thật, và khó giải thích khi bị hỏi.

**Ghi chú cho paper.** Các hằng số này là **dữ liệu**, không phải magic number. Ghi lại xuất xứ của chúng. Làm tròn cho đẹp sẽ âm thầm đổi kết quả khoa học.

---

## P4 — Dataset huấn luyện

**Việc làm.**
- 20 seed, rời hoàn toàn với batch calibration.
- Áp `normalization.json` đã đóng băng.
- **Chia train/test theo seed** (15/5), tuyệt đối không chia theo dòng — các dòng trong một lần chạy tương quan với nhau, chia theo dòng cho ước lượng lạc quan giả.

**Cổng nghiệm thu.**
- VIF giữa `s_rssi` và `s_slope` < 5. Node đang tiến lại gần có cả RSSI cao lẫn slope dương → cộng tuyến là rủi ro thật.
- Cả ba feature đều có phương sai đáng kể.

---

## P5 — Fit trọng số (Tầng bằng chứng A)

**Ý tưởng.** Mỗi cửa sổ trên một link có `tx_count` lần thử và một tỉ lệ thành công. Đó là quan sát nhị thức. Fit nó như nhị thức tương đương chính xác với logistic regression trên từng frame, **không mất chút thông tin nào**.

```python
import statsmodels.api as sm, numpy as np

successes = np.round(df.pdr_future * df.trials_future)
failures  = df.trials_future - successes

X = sm.add_constant(df[["s_rssi", "s_slope", "s_mac"]])
res = sm.GLM(np.c_[successes, failures], X,
             family=sm.families.Binomial()).fit()
print(res.summary())
```

**Bốn quy tắc.**

1. **Không nhị phân hoá nhãn.** Không có ngưỡng τ. Cắt ngưỡng vứt đi khác biệt giữa 0.72 và 0.94, và đẻ ra một siêu tham số phải biện minh.

2. **Không ràng buộc `a+b+c=1` trong lúc fit.** Trong mô hình logistic, độ lớn của β quyết định độ dốc sigmoid — dữ liệu quyết định nó. Ép tổng bằng 1 là ép độ dốc, intercept không bù lại được. Fit tự do có intercept, báo cáo β kèm sai số chuẩn, **chuẩn hoá ở bước xuất cuối cùng**. Vì LinkScore chỉ dùng để xếp hạng, phép chia là biến đổi đơn điệu, thứ tự không đổi.

3. **β âm là phát hiện, không phải bug.** Đừng clip về 0. Nó nghĩa là metric hoạt động ngược chiều giả định — đáng báo cáo.

4. Kiểm tra ổn định bằng bootstrap. β dao động mạnh giữa các lần lấy mẫu lại → chưa đủ dữ liệu.

**Bốn mô hình đối chứng — phần này quyết định sức nặng của paper.**

| Mô hình | Vì sao cần |
|---|---|
| Chỉ `s_rssi` | Ba metric có hơn một metric không? |
| Bỏ `s_slope` | Slope có đóng góp thống kê không? |
| **Khoảng cách Euclid** | **LinkScore có hơn được "khoảng cách trá hình" không?** |
| **LET hình học** (từ vị trí + vận tốc) | Đối thủ thật sự — UAV có GPS |

So bằng AIC/BIC và bằng khả năng dự đoán trên tập test.

Mô hình thứ tư là mối đe doạ lớn nhất với đề tài. Cả nhánh FANET position-based (FORP, POLSR, ML-OLSR, OLSR+) dùng vị trí để tính link expiration time. Reviewer sẽ hỏi *"UAV có GPS, sao không dùng?"*. Bạn cần câu trả lời bằng số, không bằng lời.

Nếu LinkScore thắng hoặc hoà LET: đó là kết quả rất mạnh, và lập luận là **vị trí cho hình học, RSSI cho kênh thật** — link có thể chết ở 200 m vì nhiễu và sống tốt ở 800 m khi thoáng. Nếu thua đậm: biết sớm còn hơn biết trong phản biện, và đổi hướng sang kết hợp cả hai (như OLSR+ đã làm).

**Thử thêm dạng geometric mean có trọng số.** `∏ xᵢ^wᵢ` lấy log thành `Σ wᵢ·log(xᵢ)` — fit được bằng đúng GLM trên feature đã log hoá (nhớ clip tránh log 0). So AIC với dạng tuyến tính, báo cáo cái nào khớp hơn. Đây cũng là cách thu hồi giá trị từ thiết kế geometric mean cũ của bạn.

**Đầu ra.** `(a, b, c)` đóng băng + bảng β kèm CI và p-value + biểu đồ scatter LinkScore dự đoán so với PDR thực đo trên tập test.

---

## P6 — Kiểm chứng ở mức đường đi (Tầng bằng chứng B)

**Ý tưởng.** Tầng A chứng minh LinkScore đúng ở mức link. Tầng B chứng minh nó có ý nghĩa ở mức hệ thống. Hai bằng chứng ở hai thang, không vòng lặp.

**Điểm hay: làm hoàn toàn offline, không cần chạy thêm ns-3.**

```
với mỗi cửa sổ thời gian t:
    dựng đồ thị từ các link có dữ liệu tại t

    # đồ thị oracle — dùng nhãn thật
    cost cạnh = −log(pdr_future)
    Dijkstra 0→29  ⇒  đường oracle, PDR oracle

    # đồ thị dự đoán — dùng LinkScore
    cost cạnh = −log(LinkScore)
    Dijkstra 0→29  ⇒  đường dự đoán, tra PDR thật của nó

    ghi: có trùng không, regret = PDR_oracle − PDR_dự_đoán
```

**Vì sao `−log` và Dijkstra.** Xác suất giao gói dọc đường là **tích** các xác suất từng chặng. Lấy log thành tổng — đúng dạng Dijkstra cần. Đây là logic của ETX.

Vì sao không lấy min hay trung bình: đường 6 chặng mỗi link 0.95 cho tích 0.735; đường 2 chặng mỗi link 0.90 cho 0.810. Đường thứ hai thắng dù **từng link kém hơn**, vì mỗi chặng là một cơ hội mất gói. Min và trung bình đều chọn nhầm. Phép nhân phạt số chặng đúng cách mà không cần thêm hằng số hop penalty tuỳ ý.

**Chỉ số báo cáo.** Tỉ lệ trúng top-1 và phân bố regret. Regret quan trọng hơn: trúng 60% nghe kém, nhưng nếu regret trung bình chỉ 2% PDR thì LinkScore vẫn rất tốt — nó chọn nhầm sang đường gần tương đương.

Quét mọi cặp nguồn–đích, không chỉ 0→29, và mọi cửa sổ. Vài phút Python thay cho hàng giờ mô phỏng. Dùng luôn để so nhiều bộ trọng số: bộ fit từ GLM, bộ đều nhau (1/3,1/3,1/3), bộ chỉ RSSI.

**Giới hạn phải ghi trong paper.** Tích các xác suất giả định các link hỏng độc lập. Trong không dây thì không — các chặng liền kề dùng chung kênh và tự nhiễu nhau, nên PDR thực của đường dài **tệ hơn** tích số. Đây chính là lý do ETT/WCETT ra đời sau ETX; nói rõ mình kế thừa giới hạn nào.

---

## P7 — Mô hình dự báo

**Ý tưởng.** MPC cần dự báo trạng thái tương lai. Cách tự nhiên nhất: ngoại suy tuyến tính bằng chính RSSI slope. Slope làm hai nhiệm vụ — vừa là feature trong LinkScore, vừa là cơ chế dự báo trong MPC. Điều đó làm thiết kế mạch lạc.

```
RSSI(t+k) ≈ RSSI(t) + slope × k
      → chuẩn hoá lại → tính LinkScore(t+k)
```

Từ đó ra **thời gian tới ngưỡng**:

```
TTT = (LinkScore − L_thresh) / max(0, −dLinkScore/dt)
```

Ý nghĩa trực tiếp: *link này còn sống bao lâu nữa*.

**Vì sao Δ = 4 s chứ không phải 2 s.** Tính ở khoảng cách 400 m, tốc độ tương đối 30 m/s, exponent 2.2, m=5 (σ ≈ 2.0 dB):

- Cửa sổ 2 s: node đi 60 m → RSSI đổi 1.3 dB → slope 0.67 dB/s. Với ~40 mẫu, sai số chuẩn của slope ≈ 0.68 dB/s. **Tỉ lệ tín hiệu/nhiễu ≈ 1 — không phân biệt được.**
- Cửa sổ 4 s: sai số chuẩn giảm còn ≈ 0.24 dB/s → t ≈ 2.6. **Đo được.**

Đánh đổi: feature cũ hơn. Nhưng nếu không thì β_slope vô nghĩa và bạn mất một phần ba công thức.

**Cổng nghiệm thu — phải làm, đừng bỏ qua.** Đo sai số dự báo tại từng bước horizon: dự báo LinkScore ở t+1, t+2, ..., t+N rồi so với giá trị thực đo. Vẽ RMSE theo k. **Điểm mà RMSE vượt ngưỡng chấp nhận được chính là horizon N tối đa có nghĩa.** Đặt N lớn hơn thế là tự lừa mình.

Đây cũng là một hình kết quả tốt cho paper: nó định lượng chính xác "dự đoán được bao xa", thay vì phát biểu mơ hồ.

**Ghi chú về slope theo khoảng cách.** Ở 200 m, slope là 1.25 dB/s — gần gấp đôi so với ở 400 m. Chất lượng đo của metric này biến thiên theo khoảng cách. Ghi vào Limitations.

---

## P8 — Bộ điều khiển MPC

### 8a. Sửa OLSR cho phép đổi chu kỳ HELLO

Đây là phần code C++ duy nhất chạm vào lõi giao thức, và có hai cái bẫy.

**Bẫy 1 — timer.** `HelloTimerExpire()` schedule lại bằng `m_helloInterval`. Đổi attribute chỉ có hiệu lực từ lần expire kế tiếp. Muốn phản ứng nhanh phải cancel và reschedule — nhưng đã có báo cáo việc này làm lệch throughput ngay cả khi gán lại đúng giá trị cũ.

**Test bắt buộc:** viết hàm `SetHelloInterval()`, gọi nó với **chính giá trị hiện tại**, khẳng định kết quả trùng khít từng bit với khi không gọi. Nếu lệch, bạn có bug âm thầm sẽ làm hỏng mọi kết quả sau.

**Bẫy 2 — hold time.** `OLSR_NEIGHB_HOLD_TIME` là macro biên dịch, **không** dẫn xuất từ `m_helloInterval`. Tăng chu kỳ HELLO mà hold time đứng yên → link bị coi là mất oan. Phải cho hold time bám theo, **và** set trường `HTime` trong gói HELLO để neighbor biết (ns-3 có sẵn `SetHTime()`).

EE-Hello đã giải đúng cả hai. Lấy diff của họ để tham khảo:

```bash
git clone https://github.com/imtiaztee/EE-Hello-Adaptive-Hello-Interval-for-FANETs ee-hello
wget https://www.nsnam.org/releases/ns-allinone-3.27.tar.bz2 && tar xjf ns-allinone-3.27.tar.bz2
diff -u ns-allinone-3.27/ns-3.27/src/olsr/model/olsr-routing-protocol.cc \
        ee-hello/src/olsr/model/olsr-routing-protocol.cc > ee-hello.diff
```

Đọc diff, **viết lại trên ns-3.45**. Đừng build repo đó — nó dùng waf, đã bị gỡ khỏi ns-3 từ bản 3.36.

### 8b. Hàm mục tiêu

```
J_i = Σ_{k=t}^{t+N−1} [  q_L · H_k / TTT_k
                       +        H_nom / H_k
                       + q_S · ((H_k − H_{k−1}) / H_nom)²  ]

ràng buộc:  H_min ≤ H_k ≤ H_max,  |H_k − H_{k−1}| ≤ ΔH_max
```

**Giải thích từng số hạng.**

- **Số hạng 1 — mù bao lâu.** `H/TTT` = bạn sẽ không biết gì về link này trong bao nhiêu phần trăm quãng đời còn lại của nó. Link ổn định → TTT lớn → cost ≈ 0. Link sắp đứt → cost bùng lên. Dùng `TTT` chứ không dùng `(1 − LinkScore)`: link có LinkScore 0.3 nhưng **ổn định** thì HELLO dày cũng vô ích; link 0.8 nhưng **đang lao dốc** mới cần theo sát. Mức không quyết định, tốc độ thay đổi mới quyết định.
- **Số hạng 2 — overhead.** Số HELLO mỗi giây tỉ lệ với `1/H`. Chuẩn hoá hệ số này về 1 để giảm bậc tự do.
- **Số hạng 3 — chống dao động.** Phạt việc đổi H quá mạnh giữa hai chu kỳ (2.0 → 0.5 → 2.0).

Tất cả vô thứ nguyên hoá bằng `H_nom` — nếu không, ba số hạng có đơn vị s, 1/s, s² và các q không so sánh được với nhau.

**Gộp per-link thành per-node.** LinkScore là của từng link, nhưng H là của node — HELLO là broadcast, không gửi riêng cho một neighbor được. Lấy theo link cấp bách nhất:

```
TTT_i = min over j in N(i) of TTT_ij
```

Tần suất HELLO phải đủ nhanh cho link đổi trạng thái nhanh nhất. Nên có ablation `min` so với `mean` — chênh lệch là một kết quả nhỏ nhưng thuyết phục.

### 8c. Trọng số q — không fit, mà quét

`q_L, q_S` khác **về bản chất** với `a, b, c`:

| | `a, b, c` | `q_L, q_S` |
|---|---|---|
| Bản chất | Tham số mô hình dự đoán | Sở thích thiết kế |
| Ground truth | Có (PDR) | **Không** |
| Cách xử lý | Fit bằng GLM | Quét, báo cáo Pareto |

Đây là phân biệt kinh điển: **system identification** so với **cost tuning**. Không dữ liệu nào nói được `q_L` nên bằng bao nhiêu — nó chỉ nói bạn coi trọng độ chính xác định tuyến hơn hay overhead hơn.

Luận điểm của paper **không** phải "bộ q này tối ưu" mà là:

> Đường Pareto (PDR theo overhead) của MPC nằm trên đường Pareto của mọi baseline — ở **mọi** mức overhead, MPC cho PDR cao hơn.

Mạnh hơn hẳn so một điểm với một điểm, và chặn trước câu hỏi "bạn có tune q cho có lợi không?".

### 8d. Solver

H rời rạc hoá 8 mức (0.25–4 s), horizon N=3 → 512 nhánh. Duyệt hết bằng C++, không cần thư viện. Ràng buộc `ΔH_max` cắt bớt nhánh nữa. Deterministic, không phụ thuộc solver ngoài — dễ defend hơn nhiều so với gọi cvxpy.

### 8e. Biến thể self-triggered (khuyến nghị)

Thay vì chỉ hỏi *"chu kỳ nên là bao nhiêu"*, hỏi *"lần HELLO kế tiếp nên phát lúc nào"*. Đây là **self-triggered control**, có nền lý thuyết vững (Heemels/Johansson/Tabuada CDC 2012; dòng self-triggered MPC).

Thiết kế lai: MPC chu kỳ đặt nhịp nền, **cộng trigger sự kiện** phát urgent HELLO khi một link vượt ngưỡng cấp bách giữa hai chu kỳ điều khiển. Điều này bù được điểm yếu của broadcast — không cần tăng nhịp nền cho cả node, chỉ bắn thêm một gói khi thật sự cần.

**Vì sao khung này quan trọng về mặt lý thuyết.** Chú ý rằng H **không** ảnh hưởng tới LinkScore — gửi HELLO dày hơn không làm RSSI mạnh lên. Nên nếu không có ràng buộc `ΔH_max`, bài toán tách rời được theo k và có nghiệm dạng đóng: horizon không làm gì cả. Reviewer biết control theory sẽ thấy ngay.

Cứu bằng hai cách, dùng cả hai: (1) ràng buộc tốc độ thay đổi — nếu dự báo link xấu đi sau 3 giây mà mỗi chu kỳ chỉ đổi được 0.5 s thì phải bắt đầu ngay; (2) khung self-triggered — thời điểm phát kế tiếp **chính là** biến quyết định.

Và gọi đúng tên trong paper: **MPC với preview nhiễu ngoại sinh**. Chất lượng link là nhiễu đo được và dự báo được, không phải trạng thái điều khiển được. Trung thực về điều này biến một điểm yếu tiềm tàng thành bằng chứng bạn hiểu công cụ mình dùng.

---

## P9 — Baselines

| Baseline | Vai trò | Ghi chú |
|---|---|---|
| OLSR chuẩn, HELLO = 2 s | Mốc RFC | |
| OLSR HELLO = 0.5 s | Cận trên overhead | |
| OLSR HELLO = 5 s | Cận dưới overhead | |
| **Ngưỡng phản ứng đơn giản** | **Quan trọng nhất** | Xem bên dưới |
| **EE-Hello** | Đối thủ chính | Implement lại trên ns-3.45 |
| LET hình học điều khiển HELLO | Đối chứng GPS | Nếu P5 cho thấy LET mạnh |

**Baseline ngưỡng phản ứng** rẻ và quan trọng: `H = clip(k · TTT_hiện_tại)`, không horizon, không tối ưu. Nếu MPC không thắng nổi nó, độ phức tạp của MPC không được biện minh. Reviewer sẽ hỏi câu này — có sẵn câu trả lời tốt hơn là bị hỏi bất ngờ.

**Về các baseline hậu-2019.** AI-Hello, DQN-OLSR, MA-IDDPG-OLSR, FBCR đều **không có code công khai**. Implement lại RL từ mô tả paper rồi báo cáo nó thua bạn là không defend được — thiếu hyperparameter, kiến trúc mạng, lịch trình training. Trích trong Related Work và nêu rõ không có implementation công khai nên so sánh trực tiếp nằm ngoài phạm vi. Đó là lý do trung thực và được chấp nhận.

**Kỳ vọng thực tế.** EE-Hello ghi nhận OLSR **không đạt nổi PDR 0.5 trong bất kỳ cấu hình FANET nào** của họ, vì bản chất động cao khiến giao thức chủ động không theo kịp. Nếu số của bạn thấp, đó là đặc tính bài toán, không phải lỗi setup.

---

## P10 — Đánh giá (Tầng bằng chứng C)

**Việc làm.**
- 5 seed evaluation, rời hoàn toàn với calibration và training.
- Quét `(q_L, q_S)` → vẽ đường Pareto PDR theo overhead cho MPC và cho từng baseline.
- Ablation: LinkScore đầy đủ / bỏ slope / chỉ RSSI / trọng số đều nhau.
- Quét độ nhạy: tốc độ node, mật độ, mức tải.

**Chỉ số báo cáo.**

| Nhóm | Chỉ số |
|---|---|
| Hiệu năng | PDR, delay p50/p95, throughput |
| Chi phí | Byte control/giây, số HELLO/node/giây |
| Định tuyến | Số lần đổi route, thời gian không có route |
| Điều khiển | Phân bố H theo thời gian, tần suất urgent trigger |

Nhóm cuối là thứ các paper khác không báo cáo và nó thuyết phục: cho thấy bộ điều khiển **thực sự làm gì**, không chỉ kết quả cuối. Một biểu đồ H theo thời gian chồng lên TTT của link cấp bách nhất sẽ cho thấy trực quan rằng MPC phản ứng đúng chỗ.

**Khung thống kê.** Nếu kết quả cho thấy MPC ngang bằng chứ không vượt ở một số cấu hình, đó là **non-inferiority**, cần **công bố biên độ trước** (ví dụ "không kém quá 3 điểm PDR") và ghi vào file đã commit **trước khi** chạy. Chốt biên độ sau khi nhìn kết quả thì vô giá trị.

---

## Bảng tóm tắt

| Phase | Đầu ra | Số lần chạy sim | Rủi ro chính |
|---|---|---|---|
| P0 | Instrumentation đã kiểm chứng | 2 | Callback signature lệch phiên bản |
| P1 | Config đóng băng | 0 | Tham số mặc định không kiểm tra |
| P2 | Harness Tier 2 | 1 (sanity) | Thiếu probe → dataset censored |
| P3 | `normalization.json` | 5 | Rò rỉ nếu không tách batch |
| P4 | train/test theo seed | 20 | Chia theo dòng thay vì theo seed |
| P5 | `(a,b,c)` + CI + p-value | 0 | β_slope không có ý nghĩa |
| P6 | Top-1 match, regret | 0 | — |
| P7 | Horizon N có căn cứ | 0 | Đặt N quá lớn |
| P8 | Controller + solver | vài lần test | Hold time không bám chu kỳ |
| P9 | Baselines | — | EE-Hello implement sai |
| P10 | Pareto + ablation | ~5 × số cấu hình | So một điểm thay vì Pareto |

**Đang ở: P0.**

---

## Nếu một phase hỏng

| Triệu chứng | Chẩn đoán | Hành động |
|---|---|---|
| `β_slope` không có ý nghĩa thống kê | Cửa sổ Δ quá ngắn, hoặc tốc độ node quá thấp | Tăng Δ lên 6 s; tăng MeanVelocity; nếu vẫn không → **báo cáo đó là kết quả**, LinkScore thành 2 metric |
| Retry gần như bằng 0 khắp nơi | Tải quá nhẹ | Tăng traffic nền, quét `numFlows` |
| Retry cao đồng đều bất kể RSSI | Bão hoà | Giảm tải. Điểm ngọt là nơi tương quan retry–RSSI âm sâu nhất |
| `pdr_future` dồn hết ở 1.0 | Mạng quá thoáng | Giảm TxPower hoặc mở rộng diện tích |
| Khoảng cách dự đoán tốt bằng LinkScore | Fading quá nhẹ, LinkScore = distance trá hình | Kiểm tra `β_slope` — ở FANET, thông tin ngoài khoảng cách đến từ **slope**, không từ fading |
| LET hình học thắng đậm | GPS mạnh hơn RSSI trong kịch bản này | Đổi hướng: kết hợp cả hai (như OLSR+), hoặc nhấn kịch bản GPS-denied |
| MPC không thắng baseline ngưỡng | Horizon không tạo giá trị | Kiểm tra `ΔH_max` có đủ chặt không; nếu không → dùng khung self-triggered |
