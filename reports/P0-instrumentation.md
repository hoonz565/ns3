# P0 — Môi trường và kiểm chứng thiết bị đo

Ngày 2026-07-26 | Git SHA `415beabf5` (**dirty** — xem Bất thường) | Config SHA: chưa có, `config/nominal.yaml` là việc của P1

## Đã làm

- Dựng ns-3.45 trên filesystem native Linux (`/home/hung/workspace/ns3`), `./ns3 configure --enable-examples` + build. Patch `phy-entity.cc` đã có sẵn trong cây, không sửa gì thêm.
- Kiểm chứng 4 callback signature bằng cách đọc source thật trước khi viết code: `MonitorSnifferRx` (6 tham số, `SignalNoiseDbm`), `MonitorSnifferTx` (5 tham số, không có `SignalNoiseDbm`), `MacTxDataFailed` / `MacTxFinalDataFailed` (`TracedCallback<Mac48Address>`).
- Viết `scratch/linkscore/link-probe.cc`: 2 node, node 0 đứng yên, node 1 bay thẳng ra xa 10 m/s. Probe unicast L2 qua `NetDevice::Send` (Ethertype 0x88b5), không IP, không routing.
- Ba lần chạy, mỗi lần kèm `run_manifest.json`:

  | Run | Cấu hình | Dùng cho |
  |---|---|---|
  | `data/smoke/p0-nofading` | 10 dBm, fading off, 10→620 m | cổng 1 |
  | `data/smoke/p0-fading` | 10 dBm, fading on, 10→620 m | cổng 2 |
  | `data/smoke/p0-sigma` | **40 dBm**, fading on, 10→820 m | cổng 3 |

  Run thứ ba là bổ sung: ở công suất nominal, sàn detect −82 dBm (xem dưới) chặn hết mẫu ở tier m=3 nên cổng 3 không kiểm được. σ tính theo dB **không phụ thuộc công suất phát** (Nakagami nhân với biến gamma trung bình 1), nên nâng TxPower chỉ dịch sàn ra khỏi vùng đo, không làm thay đổi đại lượng đang đo.
- Viết `analysis/validate/p0_check.py`: tính lại đường lý thuyết từ đầu trong Python (không dùng lại số C++ đã tính), đo σ residual theo từng tier m, sinh 3 hình.

## Cổng nghiệm thu

| Chỉ số | Ngưỡng | Đo được | Đạt |
|---|---|---|---|
| \|residual\| lớn nhất, fading off | ≤ 0.5 dB | **0.0066 dB** | ✓ |
| Residual trung bình, fading off | ≈ 0 | +0.0016 dB | ✓ |
| Spearman(dist, RSSI), fading off | ≤ −0.999 | **−1.000000** (0 lần RSSI tăng) | ✓ |
| MAC retry khác 0 | > 0 | 19 973 retry / 21 072 attempt | ✓ |
| MAC retry không phải toàn bộ | có cả bin sạch | 6 bin sạch (11–70 m) / 55 bin có retry | ✓ |
| σ residual tier m=8 | 1.585 ± 0.25 dB | **1.573** (SE 0.037) | ✓ |
| σ residual tier m=5 | 2.043 ± 0.25 dB | **1.961** (SE 0.031) | ✓ |
| σ residual tier m=3 | 2.729 ± 0.25 dB | **2.716** (SE 0.027) | ✓ |

**Ba cổng đều đạt.** Câu hỏi trực tiếp của lượt này — residual σ có ra ~2.0 dB không — trả lời: **1.96 dB đo được ở tier m=5, dự kiến 2.04 dB.**

σ dự kiến không lấy từ tài liệu mà suy từ chính hiện thực ns-3 (`propagation-loss-model.cc`: độ lợi công suất ~ Gamma(m, 1/m)), nên sang dB thì σ = √ψ₁(m)·10/ln10 và **E[dB] = (ψ(m) − ln m)·10/ln10, âm chứ không phải 0** — fading giữ nguyên công suất trung bình nhưng hạ dBm trung bình (Jensen). ψ và ψ₁ tự viết trong script, đã đối chiếu với chuỗi giải tích tới 7e-13 (scipy 1.8 của hệ thống không tương thích ABI với numpy 2.x).

| tier | mean residual dự kiến | đo được |
|---|---|---|
| m=8 | −0.277 dB | −0.168 dB |
| m=5 | −0.449 dB | −0.380 dB |
| m=3 | −0.764 dB | −0.685 dB |

## Số liệu chính

- `figures/P0-rssi-vs-distance.png` — RSSI đo chồng lên đường lý thuyết, 3 run. Ở panel fading-off đường đỏ bị điểm đo phủ kín hoàn toàn.
- `figures/P0-residual-sigma.png` — residual theo khoảng cách + histogram theo tier m.
- `figures/P0-retry-vs-distance.png` — retry_rate và tỉ lệ giải mã theo khoảng cách.
- `data/smoke/p0-gates.json` — toàn bộ số liệu ba cổng ở dạng máy đọc.

### Phát hiện quan trọng nhất: sàn kiểm duyệt RSSI −82 dBm

`WifiPhyHelper` mặc định gắn `ThresholdPreambleDetectionModel` với **`MinimumRssi = −82 dBm`**: frame yếu hơn thế **không bao giờ được detect**, bất kể SNR. Frame cuối cùng nhận được trong run fading-off nằm đúng ở −82.0 dBm.

Sàn này cao hơn giới hạn do nhiễu tới 7 dB (noise đo được −93.97 dBm, 6 Mbps cần SNR ≈ 5 dB → −89 dBm). **Nghĩa là điểm link chết do một tham số của mô hình detect quyết định, không do mô hình sai số bit.** Hệ quả đo được:

| | fading off | fading on |
|---|---|---|
| Khoảng cách xa nhất còn nhận được | 114 m | 187 m |
| Vùng chuyển tiếp (0 < tỉ lệ giải mã < 1) | ~110–120 m (gần như bậc thang) | **~60–180 m** |

Có vùng waterfall thật, rộng ~120 m, nhưng nó do **fading làm RSSI dao động quanh sàn** tạo ra, chứ không do đường cong PER. Vị trí của nó là hệ quả của một hằng số trong mô hình detect.

### Hệ quả: cặp (TxPower, diện tích) trong PLAN.md không nhất quán

PLAN.md/CLAUDE.md ghi "TxPower 10 dBm cho tầm phủ ≈ 500 m" và "2000×2000 m, 30 node → ~6 neighbor". Đo được tầm phủ **114 m**. Bậc trung bình thực tế:

    degree = (N−1)·πR²/A = 29·π·114²/(2000·2000) ≈ 0.30

Tức mạng gần như rời rạc hoàn toàn, không phải 6 neighbor. Hai cách vá, **là quyết định của P1 chứ không phải của P0**:

- Giữ diện tích 2000×2000 m → cần **TxPower ≈ 24 dBm** để R = 500 m (từ 46.73 + 22·log₁₀500 − 82 = 24.1). Cho degree ≈ 5.7.
- Giữ TxPower 10 dBm → phải thu diện tích về **~444×444 m** mới có degree 6.

Và độc lập với hai cách trên: cân nhắc **hạ `MinimumRssi` về −101 dBm** (bằng `RxSensitivity`) để vùng chuyển tiếp do mô hình sai số quyết định thay vì do hằng số detect. Đây là **attribute, sửa bằng config, không cần patch** — nhưng phải khai báo trong paper.

## Quyết định đã chốt

Ba lựa chọn đo dưới đây dùng lại **y hệt** ở P2 (PLAN.md mục 3: train và deploy phải tính feature giống nhau):

1. **RSSI đọc từ `MonitorSnifferRx`, trường `signalNoise.signal`.** Đã kiểm: khớp lý thuyết trong 0.0066 dB.
2. **retry_rate = (số lần `MacTxDataFailed`) / (số PPDU data trong `MonitorSnifferTx`).** Mẫu số lấy ở tầng MAC, **không** suy từ số lần gọi `Send()` — một lần phát lại là một attempt mới nhưng không có `Send` tương ứng, và queue có thể drop trước khi phát. Cách này cũng tránh hẳn `PeekHeader` ở điểm trace Tx (chế độ hỏng `txFirst = 0` mà PLAN.md P0 dự đoán không thể xảy ra).
3. **Probe unicast L2 bằng `NetDevice::Send`, Ethertype 0x88b5, cùng kích thước frame data.**

Ngoài ra: scenario C++ ở `scratch/linkscore/`, mỗi `.cc` một target qua `build_exec` với `EXECNAME_PREFIX scratch_linkscore_` — bắt buộc đúng prefix này, nếu không `./ns3 run` báo "Target to build does not exist" dù ninja build được.

## KHÔNG làm

- **Không tạo `config/nominal.yaml`.** Đó là P1. Tham số nominal hiện nằm ở giá trị mặc định trong `link-probe.cc`; P1 phải chuyển sang file config và `link-probe.cc` phải đọc từ đó.
- **Không sửa `MinimumRssi`.** Phát hiện ra nó ở P0, nhưng đổi cấu hình mô phỏng là việc của P1. Ba run trên đều để mặc định.
- **Không kiểm tier m=3 ở công suất nominal.** Không thể — sàn detect chặn hết. Đã kiểm ở 40 dBm và ghi rõ lý do tại sao phép đo vẫn hợp lệ.
- **Không chạy nhiều seed.** 1 seed; SE của σ đã xuống 0.03 dB nên thêm seed không đổi kết luận cổng 3.
- **Không xác minh độc lập `MacTxFinalDataFailed`** — chỉ đếm, chưa đối chiếu với trace drop của queue (xem Bất thường).
- **Không chạy 30 node, không có OLSR, không có mobility Gauss-Markov.** P2.
- **Không commit.** Ba manifest đều ghi `git_dirty: true`.

## Bất thường / nghi ngờ

1. **`retry_rate` toàn run 0.948 là hiện vật, không phải đặc tính kênh.** Scenario bơm 100 probe/s trong 60 s nhưng link chết từ giây thứ 10, nên 50 s cuối là queue backlog liên tục retry vào khoảng không. Con số dùng được là **retry_rate theo bin khoảng cách** (0 dưới 70 m, →1 sau 150 m), không phải con số tổng. P2 phải giãn nhịp probe để queue không dồn, và theo CLAUDE.md quy tắc 13 thì vùng bão hoà không được dùng để fit.
2. **`final_fails` (478) nhỏ hơn nhiều số frame không tới (5990 − 1238 = 4752).** Nghĩa là phần lớn frame bị drop **ở queue** chứ không phải do hết số lần retry. Chưa hook trace drop của queue nên chưa xác nhận. Đây là lý do thứ hai không tin con số retry tổng.
3. **Mean residual lệch nhất quán +0.09 dB so với dự đoán Jensen ở cả ba tier** (−0.168 vs −0.277; −0.380 vs −0.449; −0.685 vs −0.764), mỗi tier khoảng 2 SE, cùng dấu. Đã loại trừ: kiểm duyệt do sàn (run 40 dBm giao 7990/7990 frame, không mất frame nào), lệch khoảng cách giữa lúc phát và lúc trace (< 0.001 dB). Chưa giải thích được. Nhỏ hơn σ đang đo 20–30 lần nên chưa đuổi tiếp, nhưng nếu P3 thấy percentile RSSI lệch nhẹ so với dự đoán thì đây là nghi phạm.
4. **σ tier m=5 lệch −0.082 dB = 2.6 SE** — lệch có ý nghĩa thống kê dù nằm trong ngưỡng 0.25 dB. Cùng dấu với ba mục trên.
5. **Patch `phy-entity.cc` không được kiểm thật.** Ba run đều 2 node, 60–80 s, không dày đặc — không đụng tới race mà patch xử lý. Chỉ có thể kiểm ở P2.
6. **`./ns3 build <target-sai>` trả về exit code 0** dù in "Target to build does not exist". Bất kỳ script tự động nào bọc `./ns3 build` phải grep output, không được tin exit code.

## Đầu vào cho phase sau

| Đường dẫn | Nội dung |
|---|---|
| `scratch/linkscore/link-probe.cc` | Scenario P0. Ba cách đo ở mục "Quyết định đã chốt" copy sang `link-dataset.cc` ở P2. |
| `data/smoke/p0-{nofading,fading,sigma}/` | `rx.csv` (t, dist, rssi, noise, size, freq), `tx.csv` (t, dist, event ∈ {send, attempt, retry, final_fail}), `meta.json`, `run_manifest.json` |
| `data/smoke/p0-gates.json` | Số liệu ba cổng, máy đọc |
| `analysis/validate/p0_check.py` | ψ/ψ₁ và σ dự kiến theo Nakagami m — P3 dùng lại khi kiểm phân bố RSSI |
| `figures/P0-*.png` | 3 hình |

**Việc P1 phải chốt trước khi tiêu seed:** (a) `MinimumRssi` để mặc định −82 dBm hay hạ về −101 dBm; (b) cặp (TxPower, diện tích) cho degree ≈ 6 — 24 dBm ở 2000×2000 m, hay 10 dBm ở ~444×444 m. Cả hai đều đổi vị trí vùng waterfall, tức đổi phân bố nhãn của P2.
