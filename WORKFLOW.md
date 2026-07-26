# Quy trình làm việc với Claude Code

Tài liệu này nói **cách vận hành** PLAN.md, không nói nội dung khoa học.

---

## 1. Ba file agent đọc, ba vai trò khác nhau

| File | Vai trò | Ai sửa | Tần suất đọc |
|---|---|---|---|
| `CLAUDE.md` | **Bất biến** — ràng buộc không được vi phạm | Bạn, hiếm khi | Tự động mỗi session |
| `PLAN.md` | **Lộ trình** — phase nào làm gì | Bạn, khi đổi hướng | Đọc phần của phase hiện tại |
| `STATUS.md` | **Vị trí hiện tại** — đã xong gì, đang vướng gì | **Agent, cuối mỗi phase** | Đọc đầu tiên mỗi session |

`STATUS.md` là file quan trọng nhất cho tính liên tục. Session mới không cần đọc lại toàn bộ repo — nó đọc STATUS.md và biết ngay đang ở đâu.

Nguyên tắc: **thứ gì phải đúng ở mọi phase thì vào CLAUDE.md, không vào prompt.** Prompt bị quên khi context đầy; CLAUDE.md nạp lại mỗi session.

---

## 2. Cấu trúc thư mục

```
linkscore/
├── CLAUDE.md               # bất biến, tự động nạp
├── PLAN.md                 # lộ trình 11 phase
├── STATUS.md               # agent cập nhật cuối mỗi phase
├── WORKFLOW.md             # file này
│
├── config/
│   └── nominal.yaml        # ĐÓNG BĂNG sau P1
│
├── scratch/linkscore/      # C++ scenario, copy vào scratch/ khi build
│   ├── link-probe.cc       # P0
│   ├── link-dataset.cc     # P2
│   └── mpc-hello/          # P8
│
├── analysis/
│   ├── features/           # KHÔNG được import từ labels/
│   ├── labels/             # KHÔNG được import từ features/
│   ├── fit/
│   ├── validate/
│   └── plots/
│
├── frozen/                 # BẤT BIẾN sau khi tạo — agent không được sửa
│   ├── normalization.json  # P3
│   └── weights.json        # P5
│
├── data/                   # .gitignore toàn bộ — nặng GB
│   ├── smoke/              # 1 seed, test nhanh
│   ├── calib/              # 5 seed → P3
│   ├── train/              # 30-40 seed → P4, P5
│   └── eval/               # 5 seed → P10, KHÔNG chạm cho tới P10
│
├── reports/                # commit vào git — nhẹ, là nhật ký nghiên cứu
│   ├── P0-instrumentation.md
│   ├── P1-config.md
│   └── ...
│
└── figures/                # hình cho paper
```

**Ranh giới feature/label hiện lên trong cây thư mục.** Không phải trang trí — nó làm việc vi phạm trở nên khó vô tình, thay vì chỉ được ghi trong tài liệu. Thêm một test đơn giản trong CI:

```bash
grep -rn "from labels\|import labels" analysis/features/ && echo "VI PHẠM" && exit 1
```

**`data/eval/` là vùng cấm cho tới P10.** Ghi vào CLAUDE.md. Nếu agent chạm vào nó ở P5, mọi con số báo cáo mất giá trị.

**`frozen/` bất biến.** Một khi `normalization.json` sinh ra ở P3, không phase nào được ghi đè. Nếu cần đổi, tạo `normalization-v2.json` và ghi rõ lý do trong report — như vậy còn dấu vết.

---

## 3. Provenance — mọi output phải tự khai báo nguồn gốc

Đây là thứ phân biệt kết quả nghiên cứu tin được với một đống CSV.

Mỗi lần chạy sinh ra một `run_manifest.json` bên cạnh dữ liệu:

```json
{
  "phase": "P4",
  "timestamp": "2026-07-27T09:14:22Z",
  "git_sha": "a3f9c21",
  "git_dirty": false,
  "config_sha256": "7d2e...",
  "binary_sha256": "9b41...",
  "binary_mtime": "2026-07-27T08:55:01Z",
  "newest_source_mtime": "2026-07-27T08:52:14Z",
  "ns3_version": "3.45",
  "seed": 1007,
  "frozen_artifacts_used": ["frozen/normalization.json@sha256:3c1a..."]
}
```

**Hai trường sống còn:**

- `git_dirty` — nếu `true` thì kết quả không tái lập được. Runner phải **cảnh báo to**.
- `binary_mtime` so với `newest_source_mtime` — nếu binary cũ hơn source, **fail ngay**, đừng chạy.

Bài học đã trả giá: ở dự án trước, mọi profile trỏ tới một binary `-debug` cũ 9 ngày mà ns-3 không còn build. Toàn bộ campaign chạy trên code không khớp source, và không ai biết cho tới khi kiểm toán.

---

## 4. Prompt khởi động (chạy một lần)

```
Đọc CLAUDE.md, PLAN.md, WORKFLOW.md trong repo này.

Nhiệm vụ lượt này: CHỈ dựng khung, không làm nội dung khoa học nào.

1. Tạo cây thư mục theo WORKFLOW.md mục 2.
2. Tạo .gitignore: data/, build/, __pycache__/, *.pcap, *.xml
3. Tạo STATUS.md với nội dung:
   - Phase hiện tại: P0
   - Đã hoàn thành: (chưa có)
   - Đang vướng: (chưa có)
   - Quyết định đã chốt: (chưa có)
4. Viết scripts/run_manifest.py sinh manifest theo WORKFLOW.md mục 3,
   bao gồm cả hai kiểm tra git_dirty và binary vs source mtime.
5. Viết test kiểm tra ranh giới features/labels như WORKFLOW.md mục 2.

KHÔNG viết scenario ns-3, KHÔNG chạy mô phỏng, KHÔNG tạo file nào
ngoài danh sách trên. Xong thì dừng và liệt kê những gì đã tạo.
```

---

## 5. Prompt cho mỗi phase (mẫu dùng lại)

Thay `<PX>` bằng phase đang làm.

```
Đọc theo thứ tự: STATUS.md → CLAUDE.md → phần <PX> trong PLAN.md
→ reports/ của phase liền trước (nếu có).

PHẠM VI: chỉ <PX>. Không làm trước việc của phase sau, không "cải
tiến" phần của phase trước. Nếu thấy vấn đề ngoài phạm vi, GHI VÀO
BÁO CÁO thay vì tự sửa.

QUY TRÌNH:
1. Trình bày kế hoạch cụ thể cho <PX> và ĐỢI tôi xác nhận.
2. Sau khi tôi duyệt: thực hiện, commit từng bước nhỏ, message rõ.
3. Trước mọi batch nhiều seed: chạy SMOKE TEST 1 seed trước, báo cáo
   ba cổng nghiệm thu của phase, ĐỢI tôi duyệt rồi mới chạy batch.
4. Viết reports/<PX>-<tên>.md theo mẫu ở WORKFLOW.md mục 6.
5. Cập nhật STATUS.md.
6. Dừng. KHÔNG tự động sang phase kế tiếp.

RÀNG BUỘC:
- Không sửa file trong frozen/
- Không đụng data/eval/ (chỉ mở ở P10)
- Không sửa config/nominal.yaml sau khi P1 đóng băng
- Mọi lần chạy phải sinh run_manifest.json
- Nếu một cổng nghiệm thu không đạt: DỪNG và báo cáo, đừng tự nới
  ngưỡng cho đạt
```

Câu cuối quan trọng nhất. Agent có xu hướng "giúp" bằng cách hạ tiêu chuẩn cho qua cổng. Ràng buộc rõ để nó báo cáo thất bại thay vì che.

### Prompt sửa lỗi build (dùng thường xuyên)

```
./ns3 build lỗi. Output: <paste>

Chỉ sửa lỗi compile. KHÔNG đổi logic thí nghiệm, KHÔNG thêm tính
năng, KHÔNG đổi tham số. Nếu phải đổi logic mới compile được, dừng
và giải thích trước khi sửa.
```

### Prompt kiểm chứng API (chạy trước khi build lần đầu)

```
Đọc <file>.cc. Với ns-3.45 trong repo này, kiểm tra các callback
signature bằng cách đọc source thật trong src/wifi/model/ — đừng
đoán từ trí nhớ. Nếu lệch, sửa cho khớp và báo cáo chỗ đã đổi.
```

---

## 6. Mẫu báo cáo phase

```markdown
# <PX> — <Tên phase>

Ngày | Git SHA | Config SHA

## Đã làm
Liệt kê gọn, mỗi mục một dòng.

## Cổng nghiệm thu
| Chỉ số | Ngưỡng | Đo được | Đạt |
|---|---|---|---|

## Số liệu chính
Bảng hoặc hình. Đường dẫn tới figures/.

## Quyết định đã chốt
Quyết định nào không thể đảo ngược mà không làm lại phase này.

## KHÔNG làm
Việc trong phạm vi mà tôi bỏ qua, kèm lý do.

## Bất thường / nghi ngờ
Chỗ nào tôi không chắc. Chỗ nào số liệu trông lạ. Chỗ nào tôi đã
đưa ra giả định thay vì kiểm chứng.

## Đầu vào cho phase sau
File nào, ở đâu, nghĩa là gì.
```

Hai mục **"KHÔNG làm"** và **"Bất thường"** là giá trị lớn nhất của mẫu này. Chúng bắt agent tự khai báo phần yếu thay vì trình bày một báo cáo trơn tru che mất vấn đề. Nếu hai mục đó luôn trống, gần như chắc chắn agent đang không tự soi.

---

## 7. Slash command để khỏi paste lại

Claude Code đọc `.claude/commands/*.md` làm lệnh tắt. Tạo `.claude/commands/phase.md` chứa nội dung mục 5, rồi gõ:

```
/phase P2
```

Tương tự `.claude/commands/fixbuild.md` và `.claude/commands/checkapi.md`.

Lợi ích thật: bạn không bao giờ quên một ràng buộc vì paste vội.

---

## 8. Bảy quy tắc vận hành

**1. Một phase một session.** Context dài làm chất lượng tụt, và agent bắt đầu quên ràng buộc từ đầu session. Xong phase thì `/clear` hoặc mở session mới.

**2. Smoke test trước batch, luôn luôn.** 1 seed trước 40 seed. Đây là quy tắc tiết kiệm thời gian lớn nhất trong cả tài liệu. Chạy 40 seed rồi phát hiện config sai là mất một ngày.

**3. Bất biến vào CLAUDE.md, không vào prompt.** Nếu bạn thấy mình nhắc lại một điều ở prompt thứ ba, nó thuộc về CLAUDE.md.

**4. Hỏi có mục tiêu, đừng hỏi mở.** "Đọc toàn bộ module olsr rồi giải thích" đốt context vô ích. "Xem `wifi-remote-station-manager.cc`, signature của trace `MacTxDataFailed` là gì" thì rẻ và chính xác.

**5. Dùng plan mode cho thay đổi rủi ro.** Trước khi agent sửa `olsr-routing-protocol.cc`, bắt nó trình bày kế hoạch. Sửa lõi giao thức là chỗ dễ hỏng âm thầm nhất.

**6. Agent viết báo cáo mà chính nó sẽ đọc lại.** Đây là cách bạn có tính liên tục qua nhiều tuần mà không phải giải thích lại từ đầu.

**7. Không bao giờ để agent tự nới ngưỡng.** Cổng nghiệm thu không đạt là **thông tin**, không phải trở ngại. Nới ngưỡng cho qua là cách chắc chắn nhất để có một paper sai mà không ai biết.

---

## 9. Bốn kiểu drift cần cảnh giác

| Kiểu | Dấu hiệu | Cách chặn |
|---|---|---|
| **Nới ngưỡng** | "Tỉ lệ retry chỉ 7% nhưng vẫn dùng được" | Ràng buộc trong prompt phase |
| **Phình phạm vi** | Sửa lỗi build kèm "tiện thể refactor" | "Chỉ sửa lỗi compile" |
| **Đẻ tài liệu** | Tạo thêm 5 file .md không ai yêu cầu | "Chỉ tạo file trong danh sách" |
| **Ghi đè frozen** | `normalization.json` bị sửa ở P5 | Ràng buộc + kiểm tra hash trong manifest |

Kiểu thứ nhất nguy hiểm nhất vì nó **im lặng**. Ba kiểu kia bạn nhìn `git diff` là thấy.

---

## 10. Nhịp làm việc thực tế

| Nhịp | Việc |
|---|---|
| Mỗi session | Một phase hoặc một phần của phase lớn |
| Mỗi phase | Đọc báo cáo trước khi duyệt cho sang phase sau |
| Mỗi tuần | Đọc lại STATUS.md, xem có trôi khỏi PLAN.md không |
| Khi đổi hướng | Sửa PLAN.md **trước**, rồi mới bảo agent làm |

Điểm cuối quan trọng: nếu bạn đổi ý giữa chừng mà không sửa PLAN.md, agent sẽ tiếp tục đọc bản cũ và làm theo hướng cũ. Plan là nguồn chân lý, không phải trí nhớ của bạn.