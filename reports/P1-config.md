# P1 — Đóng băng cấu hình

Ngày 2026-07-26 | Git SHA `e750edaea` | Config đã đóng băng: `txPowerDbm = 19`, `minRssiDbm = -101`

**Kết luận: config đã đóng băng và xác nhận bằng run đọc thẳng từ file, không flag.** Degree đo lại được **6.14**, đúng bằng lúc truyền bằng flag, và provenance in ra cho thấy cả bốn key (`txPowerDbm`, `minRssiDbm`, `channelNumber`, `dataMode`) đến từ `sim-config/fanet-tier2.conf`.

## Đã làm

- **`scratch/linkscore/sim-config.h`** — parser dùng chung cho mọi scenario. Precedence `default < config < flag` (quét `--config` trong argv trước `CommandLine::Parse`, nạp file, rồi `Parse` ghi đè bằng flag tường minh). Nhiều `--config` ghép được, file sau ghi đè file trước.
- **Registry key hai tầng.** Key ngoài `KnownKeys()` → `NS_FATAL_ERROR` (typo); key trong registry mà scenario không đọc → cảnh báo liệt kê ra. Một tầng thì config phân lớp gãy vì `topology-probe` không biết key của `link-probe`. Đã kiểm cả hai đường, kèm lối thoát `--allowUnknownKeys`.
- Mỗi run in **provenance từng key**: `default` / tên file config / `cmdline (ghi đè <file>)`.
- **`sim-config/p0-link-probe.conf`, `sim-config/p1-topology.conf`** — overlay, chỉ ghi chỗ lệch so với nominal. Khối physics định nghĩa **một lần** trong `fanet-tier2.conf`; khối lặp lại là khối sẽ trôi.
- **`fanet-tier2.conf`: thêm `gmDirMin`/`gmDirMax`** (key còn thiếu, không đổi key đã có — attribute default của ns-3 vốn là `Uniform[0, 2π]` nên run cũ vẫn so sánh được).
- **`run_manifest.py`: `--config` lặp lại được**, hash gộp theo thứ tự nạp + hash từng file. (`config_sha256` vốn đã có sẵn; P0 không dùng chỉ vì tôi tưởng chưa có file config.)
- **Chạy lại toàn bộ P0 ở cây sạch** — 11 run, tất cả `git_dirty: false`, SHA `294c481df`, ép bằng `--fail-on-dirty`.
- **`scratch/linkscore/topology-probe.cc`** + **`analysis/validate/p1_topology.py`** — 3 run đo topology.

## Cổng nghiệm thu

| Chỉ số | Ngưỡng | Đo được | Đạt |
|---|---|---|---|
| P0 chạy lại: σ mỗi tier khớp số cũ | ±0.02 dB | **0.000 dB** cả ba tier (1.594 / 2.026 / 2.755) | ✓ |
| P0 chạy lại: ba cổng P0 | đều đạt | đều đạt, số liệu trùng đến 3 chữ số | ✓ |
| Config: key sai chính tả | phải dừng | `NS_FATAL_ERROR`, chỉ đúng file:dòng | ✓ |
| Degree trung bình ở config **cũ** (20 dBm / sàn −82) | [4.0, 8.0] | 1.06 | ✗ |
| Tỉ lệ thời gian cô lập ở config **cũ** | ≤ 10% | 34.5% | ✗ |
| Mật độ lớp biên | ≤ 2× kỳ vọng đều | 1.36× (z, xấu nhất) | ✓ |
| **Degree ở config đã đóng băng (19 dBm / −101)** | [4.5, 6.5] | **6.14**, cô lập 0.6% | ✓ |
| **Đọc từ config thay vì flag cho cùng kết quả** | trùng khít | 6.14, beacon nhận 582 010 — trùng | ✓ |
| **P0 không bị rò rỉ thay đổi nominal** | trùng khít | 5990 / 1032 / 1032, trùng bản đã lưu | ✓ |

Hai cổng đầu là số của config **trước khi sửa**, giữ lại để thấy vì sao phải sửa. Sau khi đóng băng, mọi cổng đạt.

## Số liệu chính

### a) Degree — và số 5.28 của conf không tái lập được

Ba run dùng **cùng một seed và `positions.csv` byte-identical** (stream RNG của mobility độc lập với radio), nên đây là so sánh có đối chứng: cùng hình học, chỉ khác ngân sách link.

| TxPower / sàn | ngân sách | R(0.9) | R(0.5) | R(0.1) | degree chặt | degree lỏng | cô lập | 2 chiều |
|---|---|---|---|---|---|---|---|---|
| 20 dBm / −82 *(conf hiện tại)* | 102 dB | 182 m | **294 m** | 424 m | **1.06** | 3.99 | 34.5% | 0.99 |
| **19 dBm / −101** | **109 dB** | 391 m | **625 m** | 875 m | **6.14** | 14.39 | 0.6% | 5.81 |
| 27 dBm / −101 | 117 dB | 945 m | 1458 m | 2015 m | 22.33 | 28.91 | 0.0% | 21.60 |

*chặt* = tỉ lệ nhận beacon ≥ 0.5 trong cửa sổ 5 s; *lỏng* = nhận được ≥ 1 beacon trong cửa sổ (gần với luật `neighborTtl` "vừa nghe thấy").

**`fanet-tier2.conf` ghi degree 5.28 ở 20 dBm. Đo lại được 1.06 (chặt) hoặc 3.99 (lỏng) ở đúng công suất và đúng sàn đó.** Không định nghĩa link nào cho ra 5.28. Con số của conf đến từ `link-dataset-fanet.cc`, **không có trong cây này**, nên không truy được nguyên nhân. Coi nó là **giá trị tham chiếu tiên nghiệm, không phải kết quả đã xác lập** (theo đúng chỉ đạo).

Phép đo mới có một kiểm chứng nội tại mà con số kia không có: `p1_topology.py` tính **degree kỳ vọng từ phân bố khoảng cách thật trong `positions.csv`**, hoàn toàn độc lập với beacon.

| R (m) | degree hình học | so với đo bằng beacon |
|---|---|---|
| 300 | 0.92 | 1.06 ở R(0.5) = 294 m |
| 600 | 5.40 | — |
| 625 | ~6.0 | **6.14 ở R(0.5) = 625 m** |
| 900 | 11.05 | — |

Hai đường tính độc lập khớp trong ~15%. Đó là lý do tôi tin 1.06/6.14 hơn 5.28.

**`12 dBm / −101` bị loại bằng số học, không cần chạy:** ngân sách của nó là 12 − (−90) = 102 dB, **đúng bằng** 20 − (−82) = 102 dB của cấu hình hiện tại. Cùng ngân sách thì cùng R, cùng degree 1.06. Lựa chọn ưu tiên số một trong khung quyết định rơi ngay ở điều kiện cần.

### b) Phân bố vị trí — không dồn biên, nhưng độ cao gần như đóng băng

| trục | min | max | mean | mean nếu đều | lớp biên 5% | / kỳ vọng |
|---|---|---|---|---|---|---|
| x | 0 | 1998 | 960 | 1000 | 10.9% | 1.09 |
| y | 3 | 2000 | 1008 | 1000 | 9.0% | 0.90 |
| z | 100 | 599 | 314 | 350 | 13.6% | 1.36 |

Không có hiện tượng dán trần: `GaussMarkovMobilityModel::DoWalk` phản xạ (đảo dấu vận tốc **và** lật `m_meanDirection`/`m_meanPitch`), và số liệu xác nhận. Histogram z hai đỉnh ở 100/600 mà kịch bản lo — **không xảy ra**.

**Nhưng z-span từng node kể một chuyện khác:**

| | |
|---|---|
| z-span trung bình mỗi node | **107 m** / dải 500 m |
| median | 106 m |
| min – max | 20 – 250 m |
| tỉ lệ node quét dưới nửa dải cao | **100%** |

**Không node nào quét quá một nửa dải độ cao trong 300 s. Mỗi node ở nguyên một lát ~100 m suốt run.** Histogram gộp trông gần đều chỉ vì các lát nằm rải rác — đúng chỗ mà histogram gộp không phân biệt được, nên mới phải báo z-span từng node.

Số học khớp: `MeanPitch ~ U[−0.05, +0.05]` nên một node điển hình có |pitch| ≈ 0.025 rad; ở 22 m/s cho vận tốc dọc ≈ 0.55 m/s, và Gauss-Markov dao động quanh giá trị đó chứ không đi một chiều. 270 s × 0.55 m/s ≈ 150 m là cận trên; đo được 107 m.

Hệ quả: **kịch bản là vị trí 3D nhưng động lực học gần như 2D.** Độ cao hoạt động như một độ lệch tĩnh mỗi node, không phải một chiều chuyển động. RSSI slope vẫn tồn tại (do chuyển động ngang) nên P5 không hỏng, nhưng phải khai báo — không được viết "3D mobility" mà ngụ ý độ cao biến thiên.

### c) Cảnh báo "degree > 11 làm abort" của conf đã lỗi thời

Conf ghi `NS_ASSERT(!m_currentEvent)` ở `phy-entity.cc:490` làm abort run khi degree vượt ~11, và ngay cả ở degree ~5 thì "1 run trong 10" cũng chết.

**Đo lại: run ở degree 22.33 (27 dBm) chạy hết 300 s, exit sạch.** Cả ba run topology (30 node × 300 s) đều không hit assert. Cảnh báo đó có **trước** patch trong cây hiện tại. Không gian lựa chọn ở mục (a) vì thế rộng hơn conf mô tả.

Đây cũng là lần đầu patch `phy-entity` bị thử thật — báo cáo P0 ghi nó "chưa được kiểm vì mọi run đều 2 node". **Mục Bất thường 5 của P0 đóng.**

### d) Vận động dọc đóng góp bao nhiêu — con số thay cho phát biểu định tính

Với mỗi lần link đổi trạng thái (3424 / 3494 lần dùng được), lấy 5 s trước đó và tách thay đổi ly cách thành phần dọc và phần ngang:

| Đại lượng | Trung vị | IQR |
|---|---|---|
| Δz / (Δz + Δxy) | **0.032** | [0.015, 0.066] |
| Chiếu lên khoảng cách 3D: (dz/d)·Δdz / [(dz/d)·Δdz + (dxy/d)·Δdxy] | **0.007** | — |

Số thứ hai mới là số phải viết vào paper: cái quyết định RSSI là thay đổi của **khoảng cách 3D**, và ở ly cách ngang lớn hơn nhiều thì `dz/d` nhỏ nên đóng góp thật của chiều dọc còn nhỏ hơn tỉ số thô. **Biến động topology 99.3% do chuyển động ngang.**

Cách phát biểu đúng trong paper: *vị trí 3D, node phân tầng theo độ cao, động lực học do chuyển động ngang* — không phải "3D mobility" ngụ ý độ cao biến thiên.

### e) Vì sao giữ −101 dù nó không mua thêm tầm phủ

`12 dBm / −101` và `20 dBm / −82` cùng ngân sách 102 dB, nên **trong phép đo cô lập này chúng cho cùng R và cùng degree**. Nhưng chúng **không tương đương ở P2**, vì hai lý do:

1. **Sàn −82 kiểm duyệt chính feature RSSI.** Dưới sàn không có mẫu nào, nên ở khoảng cách biên chỉ nửa trên của dao động fading được quan sát. Phân bố RSSI bị cắt cụt và p20 của P3 bị kéo về phía mép kiểm duyệt.
2. **Với `Threshold` SNR, mép link dịch theo can nhiễu.** Kênh bận hơn thì tầm phủ ngắn lại — đó là hành vi vật lý. Hằng số tuyệt đối −82 dBm không nhúc nhích dưới tải. Ở P0 (2 node) hai thứ không phân biệt được; ở P2 với 30 node cùng probe thì có.

Đây là lý do chọn `19 dBm / −101` chứ không phải `27 dBm / −82` (cũng cho degree ~6).

## Quyết định đã chốt

- **`txPowerDbm = 19`, `minRssiDbm = -101` — đã ghi vào `fanet-tier2.conf`.** `txPowerDbm` là **sửa giá trị đã có** (20 → 19); `minRssiDbm` là key mới nhưng **đổi hành vi** (trước đó mọi run chạy ở mặc định −82 của ns-3). Cả hai làm run trước đó không so sánh được, đúng như cảnh báo ở đầu file.
- **`channelNumber` và `dataMode` thành key**, giá trị đúng bằng default cũ nên không run nào đổi hành vi. Trước đó chúng chỉ nằm trong comment, tức hai dòng của bảng Simulation Setup không được `config_sha256` ghim.
- **Gỡ ghi đè `minRssiDbm` trong `p1-topology.conf`.** topology-probe phải thừa kế sàn đã đóng băng, nếu không nó đo một mạng khác mạng mà P2 chạy — và trông như nó chạy đúng.
- **`p0-link-probe.conf` giữ nguyên 10 dBm / −82.** Đã kiểm sau khi đổi nominal: P0 chạy lại vẫn ra 5990 sends / 1032 delivered / 1032 phy_rx_ok, trùng khít bản đã lưu. Overlay đã cách ly đúng.
- **Precedence và registry hai tầng** như trên. P2 thêm key mới thì phải thêm vào `KnownKeys()` — đó chính là cơ chế bắt typo.
- **Overlay thay vì lặp khối physics.** `p0-link-probe.conf` giữ sàn ở −82 **có chủ ý**: bảng σ của paper đo ở sàn mặc định, đổi sàn ở đó là âm thầm phá cổng tái lập ±0.02 dB.
- **Dữ liệu P0 cũ đã bị ghi đè**, và `data/smoke/p0-sigma/` (trùng lặp với `p0-sigma-seeds/seed-1`) đã xoá để không ai trích nhầm bản có provenance chết.
- **`--fail-on-dirty` cho mọi run có số vào paper.** Manifest sinh khi cây dirty là cái bẫy tôi đã sập hai lần; cưỡng chế bằng cờ, không bằng trí nhớ.

## KHÔNG làm

- **Không sửa `MeanPitch` và không thu dải cao** dù độ cao gần như đóng băng. Chọn phương án *chấp nhận và khai báo*: đã ghi vào CLAUDE.md và PLAN.md kèm con số 0.7%. Nới `MeanPitch` sẽ làm mọi run trước không so sánh được, và ở đây độ cao phân tầng vẫn có tác dụng — nó tạo ly cách 3D tĩnh giữa các node, chỉ không đóng góp vào *biến động*.
- **Không chạy nhiều seed cho topology.** 1 seed, 8100 mẫu node×thời điểm. Đủ để loại 5.28 và để chọn công suất; chưa đủ để công bố phân bố degree trong paper.
- **Không viết `link-dataset.cc`, không chạy 30 node có traffic, không fit gì.**

## Bất thường / nghi ngờ

1. **Không giải thích được 5.28.** Scenario sinh ra nó không có trong cây. Ba khả năng chưa loại trừ được: luật nạp neighbor khác, diện tích khác lúc đo, hoặc degree ở đó đếm neighbor tích luỹ chứ không phải tức thời. Nếu tìm lại được `link-dataset-fanet.cc` thì nên đối chiếu.
2. **Định nghĩa link đổi degree gấp gần 4 lần** (1.06 chặt so với 3.99 lỏng ở cùng dữ liệu). Đây không phải chi tiết kỹ thuật — nó nói rằng phần lớn cặp node nằm ở vùng biên, nghe thấy nhau *một phần*. Với P2 thì đó là tin tốt (nhiều dòng ở vùng gradient), nhưng nó cũng có nghĩa **mọi con số degree phải đi kèm định nghĩa**, và `neighborTtl` của conf là một knob mạnh hơn vẻ ngoài.
3. **`dataMode` và `channelNumber` hiện ra là `default` trong provenance**, không phải từ config. Conf cố ý không đặt key cho tốc độ ("not configurable here on purpose") nhưng vẫn ghi giá trị trong comment. Nghĩa là hai tham số vật lý của bảng Simulation Setup không được `config_sha256` ghim. Cân nhắc thêm chúng như key read-only ở P2.
4. **Beacon 100 ms có thể tự gây nhiễu ở degree cao.** Ở 27 dBm, 300 beacon/s với ~21 người nghe mỗi beacon; tỉ lệ nhận beacon lúc đó phản ánh cả collision chứ không chỉ kênh. Không ảnh hưởng kết luận ở 19 dBm (degree 6), nhưng đừng dùng run 27 dBm để nói về chất lượng link.
5. **Cửa sổ 5 s ở 15–30 m/s là 75–150 m di chuyển.** Tỉ lệ nhận beacon vì thế là trung bình trên một đoạn đường chứ không phải một điểm. Với ngưỡng degree thì chấp nhận được; với feature của P2 thì `featureWin = 4 s` cũng chịu đúng hiệu ứng này — đã ghi trong conf như một Limitations.

## Đầu vào cho phase sau

| Đường dẫn | Nội dung |
|---|---|
| `scratch/linkscore/sim-config.h` | Parser + registry. **P2 thêm key phải sửa `KnownKeys()`.** |
| `sim-config/{fanet-tier2,p0-link-probe,p1-topology}.conf` | Config phân lớp |
| `scratch/linkscore/topology-probe.cc` | Scenario đo hình học |
| `data/smoke/p1-topology{,-19dbm-floor101,-27dbm-floor101}/` | `neighbors.csv`, `positions.csv`, `meta.json`, `summary.json`, `run_manifest.json` |
| `figures/P1-degree.png`, `figures/P1-positions.png` | Hình |
| `data/smoke/p0-*/` | P0 chạy lại ở cây sạch, provenance resolve được |

### Hai việc đã chốt (P1 đóng)

**1. `txPowerDbm = 19`, `minRssiDbm = -101`** — đã ghi vào `fanet-tier2.conf`, xác nhận bằng run đọc thẳng từ config.

**2. Độ cao quasi-tĩnh: chấp nhận và khai báo.** Đã ghi vào CLAUDE.md và PLAN.md kèm số đo (0.7% đóng góp của chiều dọc). Không nới `MeanPitch`, không thu dải cao.

### Cảnh báo cho P2

- **Thêm key mới phải sửa `KnownKeys()`** trong `sim-config.h`, nếu không parser sẽ dừng — đó là cơ chế, không phải lỗi.
- **`neighborTtl` là knob mạnh hơn vẻ ngoài.** Định nghĩa link đổi degree gấp gần 4 lần trên cùng dữ liệu (1.06 so với 3.99). Mọi con số degree phải đi kèm định nghĩa.
- **Đừng dùng run 27 dBm để nói về chất lượng link** — ở degree 22 thì tỉ lệ nhận beacon phản ánh cả collision chứ không chỉ kênh.
- **`--fail-on-dirty` cho mọi run có số vào paper.**
