# P0 — Môi trường và kiểm chứng thiết bị đo

Ngày 2026-07-26 | Git SHA `dfe0788a4` | Config SHA: chưa có, `config/nominal.yaml` là việc của P1

> **Lưu ý provenance.** Các `run_manifest.json` của P0 ghi SHA `f9b3554c9` /
> `415beabf5`, là SHA **trước** khi sửa git author. Sau khi rewrite, những SHA
> đó không còn tồn tại. Dữ liệu P0 là smoke nên chấp nhận được, nhưng quy tắc
> rút ra: **rewrite lịch sử trước khi sinh manifest, không bao giờ sau.** Từ P1
> trở đi không rewrite nữa.

## Đã làm

- Dựng ns-3.45 trên filesystem native Linux (`/home/hung/workspace/ns3`), `./ns3 configure --enable-examples` + build. Patch `phy-entity.cc` đã có sẵn trong cây, không sửa gì thêm.
- Kiểm chứng 4 callback signature bằng cách đọc source thật trước khi viết code: `MonitorSnifferRx` (6 tham số, `SignalNoiseDbm`), `MonitorSnifferTx` (5 tham số, không có `SignalNoiseDbm`), `MacTxDataFailed` / `MacTxFinalDataFailed` (`TracedCallback<Mac48Address>`).
- Viết `scratch/linkscore/link-probe.cc`: 2 node, node 0 đứng yên, node 1 bay thẳng ra xa 10 m/s. Probe unicast L2 qua `NetDevice::Send` (Ethertype 0x88b5), không IP, không routing.
- **11 lần chạy**, mỗi lần kèm `run_manifest.json`:

  | Run | Cấu hình | Dùng cho |
  |---|---|---|
  | `data/smoke/p0-nofading` | 10 dBm, fading off | cổng 1 |
  | `data/smoke/p0-fading` | 10 dBm, fading on | cổng 2 |
  | `data/smoke/p0-sigma-seeds/seed-{1..6}` | **40 dBm**, fading on, 6 seed | cổng 3 + phép thử bất thường |
  | `data/smoke/p0-range/ctrl-10dbm-floor82` | 10 dBm, `MinimumRssi` −82 (mặc định) | đối chứng |
  | `data/smoke/p0-range/new-10dbm-floor101` | 10 dBm, `MinimumRssi` **−101** | cô lập tác động của sàn |
  | `data/smoke/p0-range/new-17dbm-floor101` | **17 dBm**, `MinimumRssi` −101 | kiểm dự đoán R = 500 m |

  Run 40 dBm là bổ sung: ở công suất nominal, sàn detect −82 dBm chặn hết mẫu ở tier m=3 nên cổng 3 không kiểm được. σ theo dB **không phụ thuộc công suất phát** (Nakagami nhân với biến gamma trung bình 1), nên nâng TxPower chỉ dịch sàn ra khỏi vùng đo. Ba run `p0-range` dùng nhịp probe 50 ms thay vì 10 ms, và cặp `ctrl` / `new-10dbm` khác nhau **đúng một tham số** để tác động của sàn không lẫn với thứ khác.
- Viết `analysis/validate/p0_check.py`: tính lại đường lý thuyết từ đầu trong Python (không dùng lại số C++ đã tính), gộp nhiều seed, đo σ residual theo từng tier m, đo tầm phủ, sinh 3 hình.

## Cổng nghiệm thu

| Chỉ số | Ngưỡng | Đo được | Đạt |
|---|---|---|---|
| \|residual\| lớn nhất, fading off | ≤ 0.5 dB | **0.0066 dB** | ✓ |
| Residual trung bình, fading off | ≈ 0 | +0.0016 dB | ✓ |
| Spearman(dist, RSSI), fading off | ≤ −0.999 | **−1.000000** (0 lần RSSI tăng) | ✓ |
| MAC retry khác 0 | > 0 | 19 973 retry / 21 072 attempt | ✓ |
| MAC retry không phải toàn bộ | có cả bin sạch | 6 bin sạch (11–70 m) / 55 bin có retry | ✓ |
| σ residual tier m=8 | 1.585 ± 0.25 dB | **1.594** (SE 0.015) | ✓ |
| σ residual tier m=5 | 2.043 ± 0.25 dB | **2.026** (SE 0.013) | ✓ |
| σ residual tier m=3 | 2.729 ± 0.25 dB | **2.755** (SE 0.011) | ✓ |

**Ba cổng đều đạt** (σ trên 6 seed, 47 947 mẫu). Residual σ ở tier m=5 là **2.026 dB**, dự kiến 2.043 dB.

σ dự kiến không lấy từ tài liệu mà suy từ chính hiện thực ns-3 (`propagation-loss-model.cc`: độ lợi công suất ~ Gamma(m, 1/m)), nên sang dB thì σ = √ψ₁(m)·10/ln10 và **E[dB] = (ψ(m) − ln m)·10/ln10, âm chứ không phải 0** — fading giữ nguyên công suất trung bình nhưng hạ dBm trung bình (Jensen). **Cả hai mô men khớp đồng thời**, mạnh hơn nhiều so với chỉ khớp σ:

| tier | mean residual dự kiến | đo được (6 seed) |
|---|---|---|
| m=8 | −0.277 dB | −0.253 dB |
| m=5 | −0.449 dB | −0.409 dB |
| m=3 | −0.764 dB | −0.767 dB |

ψ và ψ₁ tự viết trong script, đã đối chiếu với chuỗi giải tích tới 7e-13 (scipy 1.8 của hệ thống không tương thích ABI với numpy 2.x).

### Bất thường +0.09 dB: đã loại trừ

Ở 1 seed, mean residual lệch +0.09 dB so với dự đoán Jensen ở cả ba tier. Gộp 6 seed, đại lượng `offset = residual − E[dB](m)` (đã trừ kỳ vọng của từng tier nên gộp được các tier khác m):

| seed | n | offset | SE | z |
|---|---|---|---|---|
| 1 | 7991 | **+0.0795** | 0.0273 | +2.91 |
| 2 | 7991 | +0.0222 | 0.0281 | +0.79 |
| 3 | 7991 | +0.0379 | 0.0278 | +1.36 |
| 4 | 7991 | −0.0154 | 0.0280 | −0.55 |
| 5 | 7993 | −0.0322 | 0.0278 | −1.16 |
| 6 | 7990 | −0.0291 | 0.0275 | −1.06 |
| **gộp** | **47 947** | **+0.0105** | **0.0113** | **+0.93** |

**Tan về 0. Hiện vật RNG của seed 1** (bản thân seed 1 là +2.91 SE, một lượt bốc thăm xấu). Lệch σ −0.082 dB ở tier m=5 cũng tan theo: 6 seed cho −0.017 dB (1.3 SE). Đóng lại. Bảng này đồng thời là bằng chứng seed có tác dụng thật — offset khác nhau rõ giữa các seed.

## Số liệu chính

- `figures/P0-rssi-vs-distance.png`, `figures/P0-residual-sigma.png`, `figures/P0-retry-vs-distance.png`
- `data/smoke/p0-gates.json` — toàn bộ số liệu ba cổng + bảng tầm phủ, máy đọc

### Phát hiện 1: sàn kiểm duyệt RSSI −82 dBm

`WifiPhyHelper` mặc định gắn `ThresholdPreambleDetectionModel` với **`MinimumRssi = −82 dBm`**: frame yếu hơn thế **không bao giờ được detect**, bất kể SNR. Frame cuối cùng nhận được trong run fading-off nằm đúng ở −82.0 dBm.

Sàn này cao hơn giới hạn do nhiễu tới 7 dB (noise đo được −93.97 dBm, 6 Mbps cần SNR ≈ 5 dB → −89 dBm). Hạ `MinimumRssi` về −101 dBm thì ràng buộc chuyển sang `Threshold` (mặc định 4 dB SNR) → **sàn hiệu dụng −90 dBm, dựa trên SNR tức dựa trên vật lý** thay vì một hằng số tuyệt đối. Là attribute, sửa bằng config, không cần patch.

### Phát hiện 2: hạ sàn mua được TẦM PHỦ, không mua được bề rộng waterfall

Đo trực tiếp, `d(x)` = khoảng cách nơi tỉ lệ giải mã tụt xuống `x`:

| TxPower | MinimumRssi | sàn hiệu dụng | d(0.9) | d(0.5) | d(0.1) | rộng (m) | **rộng (dB)** |
|---|---|---|---|---|---|---|---|
| 10 dBm | −82 (mặc định) | −82.0 dBm | 82 m | **107 m** | 144 m | 62 m | **5.38** |
| 10 dBm | −101 | −90.0 dBm | 183 m | **250 m** | 329 m | 146 m | **5.60** |
| 17 dBm | −101 | −90.0 dBm | 355 m | **501 m** | 678 m | 323 m | **6.18** |

**Bề rộng theo dB gần như không đổi (5.38 → 5.60 → 6.18) dù sàn dịch 8 dB.** Kỳ vọng rằng hạ sàn sẽ để đường cong PER chi phối và làm vùng chuyển tiếp rộng ra **không xảy ra**. Lý do định lượng: vùng chuyển tiếp là **bề rộng của phân bố fading**, không phải của đường cong PER. Đi từ 90% xuống 10% cần ≈ 2·1.28·σ = 2.56σ; với σ = 1.6–2.7 dB thì ra 4.1–7.0 dB, khớp cả ba số đo. Bằng chứng nội tại: bề rộng dB **tăng dần** theo tầm phủ (5.38 → 6.18) đúng vì tier m đổi từ m=8 (σ 1.59) sang m=3 (σ 2.76). Cả hai ràng buộc gần nhau tới mức PER không kịp chi phối: preamble cần 4 dB SNR, 6 Mbps cần ~5 dB.

**Nhưng hạ sàn vẫn nên làm**, vì lý do khác lý do ban đầu: cùng một bề rộng ~5.5 dB, ở xa hơn thì trải ra **nhiều mét hơn** (62 → 146 → 323 m), tức nhiều cặp node nằm trong vùng biên hơn. Đó chính là thứ cổng "phân bố `pdr_future` có đuôi thấp" cần. Muốn waterfall rộng hơn *theo dB* thì chỉ có cách tăng fading, mà CLAUDE.md quy tắc 11 cấm.

### Phát hiện 3: TxPower cho R = 500 m

Ước lượng ban đầu 10 dBm → 500 m dùng ngưỡng −96 dBm, quá lạc quan. Với sàn hiệu dụng thật:

| Cấu hình | TxPower cho R = 500 m | Kiểm bằng đo |
|---|---|---|
| `MinimumRssi` = −82 | 24.1 dBm | — |
| `MinimumRssi` = −101 (sàn −90) | **16.1 dBm** | run 17 dBm cho d(0.5) = **501 m** ✓ |

Dự đoán 16.1 dBm được xác nhận thực nghiệm. **Đề xuất P1: `MinimumRssi` = −101 dBm, TxPower ≈ 17 dBm, giữ 2000×2000×500 m.**

Không dùng công thức degree để chốt: chiều cao hộp (500 m) xấp xỉ bằng R nên công thức 2D cho 5.7, 3D cho 7.6, đáp số thật nằm giữa vì cầu bị biên cắt. **Đo degree thực nghiệm trong smoke test của P2.**

## Quyết định đã chốt

Ba lựa chọn đo dưới đây dùng lại **y hệt** ở P2 (PLAN.md mục 3: train và deploy phải tính feature giống nhau):

1. **RSSI đọc từ `MonitorSnifferRx`, trường `signalNoise.signal`.** Đã kiểm: khớp lý thuyết trong 0.0066 dB.
2. **Mẫu số của mọi tỉ lệ MAC lấy từ `MonitorSnifferTx` (số PPDU data thực sự lên sóng), không từ số lần gọi `Send()`.** Một lần phát lại là một attempt mới nhưng không có `Send` tương ứng, và queue có thể drop trước khi phát. Cách này cũng tránh hẳn `PeekHeader` ở điểm trace Tx (chế độ hỏng `txFirst = 0` mà PLAN.md P0 dự đoán không thể xảy ra). **Hệ quả quan trọng: gói bị queue drop tự động nằm ngoài mọi tỉ lệ** — queue đầy là tính chất của node, không phải của link, và trộn nó vào nhãn là trộn hai đại lượng khác nhau.
3. **Probe unicast L2 bằng `NetDevice::Send`, Ethertype 0x88b5, cùng kích thước frame data.**

Ngoài ra: scenario C++ ở `scratch/linkscore/`, mỗi `.cc` một target qua `build_exec` với `EXECNAME_PREFIX scratch_linkscore_` — bắt buộc đúng prefix này, nếu không `./ns3 run` báo "Target to build does not exist" dù ninja build được.

## KHÔNG làm

- **Không tạo `config/nominal.yaml`** và **không sửa `MinimumRssi` làm mặc định.** Đó là P1. Cờ `--minRssi` đã có, mặc định vẫn là −82 (mặc định ns-3); ba run `p0-range` truyền tường minh.
- **Không kiểm tier m=3 ở công suất nominal.** Không thể — sàn detect chặn hết. Đã kiểm ở 40 dBm và ghi rõ lý do phép đo vẫn hợp lệ.
- **Không hook trace drop của queue.** Biết là phần lớn frame mất do queue chứ không do hết lượt retry, nhưng chưa đếm được bao nhiêu. Việc của P2 (xem Đầu vào cho phase sau).
- **Không chạy 30 node, không OLSR, không Gauss-Markov.** P2.
- **Không đo degree.** Công thức không tin được ở hình học này; phải đo, và chỗ đo là smoke test P2.

## Bất thường / nghi ngờ

1. **`retry_rate` tổng vẫn là hiện vật, và giãn nhịp probe KHÔNG chữa được.** Nhịp 10 ms cho 0.9478; nhịp 50 ms cho **0.9475** — gần như y nguyên. Lý do: khi link chết hẳn, probe vẫn tiếp tục xếp hàng bất kể nhịp, nên vùng chết chi phối con số tổng. Kết luận cho P2: **giãn nhịp là không đủ, phải ngừng probe những neighbor không còn nghe thấy** (thiết kế P2 vốn đã nói "probe tới mọi node vừa nghe thấy" — điều kiện "vừa nghe thấy" chính là cơ chế cắt, cần hiện thực đúng). Con số dùng được vẫn là retry_rate **theo bin khoảng cách**.
2. **Nhãn post-ARQ vừa bão hoà vừa không đếm được vững.** So hai định nghĩa trên run 17 dBm, bin 25 m:

   | bin | attempts | per-attempt | post-ARQ |
   |---|---|---|---|
   | 275 m | 51 | 0.980 | 1.000 |
   | 400 m | 90 | 0.556 | 1.000 |
   | 475 m | 125 | 0.392 | 0.980 |
   | 550 m | 224 | 0.161 | 0.611 |
   | 675 m | 349 | 0.006 | **−23.0** |

   `1 − final_fails/first_attempts` bằng đúng 1.000 suốt từ 0 đến 400 m trong khi per-attempt đã tụt về 0.556 — vì với 7 lần retry thì xác suất trượt hẳn là (1−p)⁷, tức nhãn chỉ rời 1.0 khi p đã rất thấp. **Đó đúng là chế độ hỏng "pdr_future dồn hết ở 1.0" trong cổng nghiệm thu.** Tệ hơn, `first_attempts = attempts − retries` cho giá trị âm ở vùng chết (−23.0): đếm per-frame cần theo dõi từng MPDU từ lần thử đầu tới lúc kết thúc, không suy được từ bộ đếm cộng dồn, nhất là khi một frame trải qua nhiều bin. Per-attempt không cần theo dõi gì: mỗi attempt là một phép thử Bernoulli độc lập, cả tử và mẫu đều là bộ đếm đơn giản.
3. **Per-attempt đo khứ hồi, không phải một chiều.** Một attempt thất bại có thể do mất data hoặc mất ACK, nên `1 − retries/attempts` ≈ p_data·p_ack. Với một metric chất lượng link dùng cho unicast thì đó là đại lượng đúng, nhưng phải khai báo — đây cũng chính là lý do ETX nhân xác suất hai chiều.
4. **`git_dirty` là cờ toàn repo, không riêng scenario.** Các run mới ghi `dirty: true` chỉ vì `p0_check.py` chưa commit lúc chạy; scenario thì đã sạch. Thứ ghim đúng scenario đã biên dịch là `binary_sha256`, độc lập với cờ dirty. Không phải lỗi, nhưng khi đọc manifest thì phải biết.
5. **Patch `phy-entity.cc` chưa được kiểm thật.** 11 run đều 2 node, 40–80 s, không dày đặc — không đụng tới race mà patch xử lý. Chỉ kiểm được ở P2.
6. **`./ns3 build <target-sai>` trả exit code 0** dù in "Target to build does not exist". Script tự động phải grep output, không được tin exit code.
7. **Định danh git — đã sửa, còn một chỗ lệch.** 7 commit của P0 đã đổi từ `Your Name` sang `Nguyen Minh Hung` (giữ nguyên author date). Nhưng hai commit trước đó của tác giả (`b62e163f1`, `415beabf5`) mang tên **`Minh Hưng`**, nên git đếm thành hai author khác nhau. Muốn thống nhất thì chọn một trong hai và chạy `git rebase --exec 'git commit --amend --no-edit --author="<tên> <email>"' b62e163f1^`.

   **Cảnh báo đã trả giá:** `git rebase --root` ở repo này đi tới commit đầu tiên của ns-3 năm 2006, không phải commit đầu của dự án — nó bắt đầu gán author của mình lên hàng nghìn commit upstream trước khi tôi abort. Luôn giới hạn phạm vi bằng SHA (`git rebase ... 415beabf5`), không dùng `--root`.

## Đầu vào cho phase sau

| Đường dẫn | Nội dung |
|---|---|
| `scratch/linkscore/link-probe.cc` | Scenario P0. Ba cách đo ở "Quyết định đã chốt" copy sang `link-dataset.cc`. |
| `data/smoke/p0-{nofading,fading}/`, `p0-sigma-seeds/seed-{1..6}/`, `p0-range/{3 run}/` | `rx.csv`, `tx.csv`, `meta.json`, `run_manifest.json` |
| `data/smoke/p0-gates.json` | Ba cổng + bảng tầm phủ, máy đọc |
| `analysis/validate/p0_check.py` | ψ/ψ₁, σ dự kiến theo Nakagami m, đo tầm phủ — P3 dùng lại khi kiểm phân bố RSSI |
| `figures/P0-*.png` | 3 hình |

**P1 phải chốt:** (a) `MinimumRssi` — đề xuất **−101 dBm** kèm khai báo trong paper; (b) TxPower — đề xuất **17 dBm** (đo được d(0.5) = 501 m), giữ 2000×2000×500 m. Cả hai đổi vị trí vùng waterfall, tức đổi phân bố nhãn của P2.

**P2 phải làm, phát sinh từ P0:**
1. **Nhãn per-attempt, không post-ARQ:** `trials_future` = số attempt trong `[t, t+τ)`, `fails_future` = số `MacTxDataFailed` trong cùng cửa sổ, `pdr_future = 1 − fails/trials`. Khớp đúng dạng nhị thức mà CLAUDE.md quy tắc 3 yêu cầu, không bão hoà, và queue drop tự động nằm ngoài vì mẫu số ở tầng MAC.
2. **Ngừng probe neighbor không còn nghe thấy** — giãn nhịp một mình không chặn được backlog (mục 1 phần Bất thường). Nhịp 50–100 ms mỗi neighbor: với τ = 4 s thì 40–80 attempt mỗi cửa sổ nhãn, dư cho ngưỡng `trials ≥ 5`.
3. **Hook trace drop của WifiMacQueue** — không để đưa vào nhãn mà để **đếm**: queue drop nhiều nghĩa là tải quá cao. Cân nhắc đặt `MaxSize` thấp cho interface probe để backlog không tích luỹ được về mặt vật lý.
