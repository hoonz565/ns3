# Hướng dẫn chia nhau chạy dataset FANET

Tài liệu này dành cho hai hoặc nhiều máy cùng chạy campaign
**1.000 scenario × 10 seed**. Mỗi máy nhận một khoảng scenario không giao
nhau, dùng output riêng, sau đó chuyển kết quả về máy chính để ghép.

## 1. Cấu hình phải giữ nguyên

| Mục | Giá trị |
|---|---|
| Tổng scenario | 1.000 |
| Seed mỗi scenario | 10 |
| Simulation time | 300 giây |
| Worker | `--workers auto` |
| Node | Uniform integer 15–90 |
| X, Y | Uniform 1.000–3.000 m |
| Độ cao mỗi node | Uniform 100–600 m |
| Tốc độ mỗi node | Uniform 15–30 m/s |
| Gauss–Markov alpha | Uniform 0,4–0,95 |
| Tx power | Uniform 15–23 dBm |
| Packet rate | Uniform integer 4–20 pkt/s |
| Startup delay | Đã bỏ |
| Acceptance gate | Hoãn tới hậu kiểm sau khi có đủ dataset |

Mỗi `scenario.json` được random đúng một lần. Mười seed trong cùng scenario
dùng chung setup; `RngRun` vẫn khác nhau. Không sửa source, config hoặc tham
số trong lúc campaign đang chạy.

## 2. Chia việc

Ví dụ hai máy:

| Máy | Scenario, tính cả hai đầu | Output |
|---|---:|---|
| Máy chính | 1–500 | `dataset_1000x10` |
| Máy phụ | 501–1000 | `dataset_friend_0501_1000` |

Nếu máy chính đã chạy một phần, hãy giao cho máy phụ một range chưa chạy.
Không để hai người chạy trùng scenario và không cho hai runner cùng ghi vào
một output, kể cả output đặt trên thư mục mạng.

Nếu máy chính đang chạy lệnh cũ không giới hạn range, nhấn `Ctrl+C` và resume
lại với range đã nhận. Với cách chia trong bảng:

```bash
./scripts/run_campaign.sh \
  --out dataset_1000x10 \
  --resume \
  --scenario-start 1 \
  --scenario-end 500 \
  --workers auto
```

Chỉ cho máy phụ bắt đầu range 501–1000 sau khi máy chính đã dừng lệnh toàn
campaign và chuyển sang lệnh giới hạn 1–500.

## 3. Chuẩn bị máy Ubuntu hoặc WSL

Máy phụ phải nhận **đúng snapshot project hiện tại** từ máy chính, không dùng
một bản ns-3 khác. Nên commit thay đổi trước khi gửi project.

Trên Ubuntu/WSL:

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build python3 ccache
```

Đặt project và dataset trong filesystem Linux, ví dụ:

```bash
cd ~/workspace/ns3
```

Trên WSL không đặt chúng trong `/mnt/c` hoặc `/mnt/d`. Kiểm tra tài nguyên:

```bash
nproc
free -h
df -h .
```

Hai bên so sánh phiên bản trước khi chạy:

```bash
git rev-parse HEAD
sha256sum \
  scripts/run_campaign.py \
  scratch/linkscore/link-dataset-fanet.cc \
  sim-config/fanet-tier2.conf
```

Các hash phải giống nhau giữa hai máy.

## 4. Build và kiểm tra

Chỉ cần thực hiện lần đầu trên máy phụ:

```bash
./ns3 configure --build-profile=default
./ns3 build link-dataset-fanet
bash scripts/run_tests.sh
```

Không bắt đầu campaign nếu build hoặc test trả về lỗi.

## 5. Chạy range được giao

Ví dụ máy phụ nhận scenario 501–1000:

```bash
./scripts/run_campaign.sh \
  --scenarios 1000 \
  --seeds 10 \
  --scenario-start 501 \
  --scenario-end 1000 \
  --workers auto \
  --sim-time 300 \
  --out dataset_friend_0501_1000 \
  --yes
```

`--scenario-start` và `--scenario-end` đều được tính. Lệnh trên tạo
500 × 10 = 5.000 job. `--workers auto` tự giới hạn theo CPU, RAM và số job.

Muốn giữ phiên chạy khi đóng terminal, có thể dùng `tmux`:

```bash
sudo apt install -y tmux
tmux new -s fanet
```

Chạy lệnh campaign bên trong `tmux`. Nhấn `Ctrl+B`, rồi `D` để tách phiên;
kết nối lại bằng:

```bash
tmux attach -t fanet
```

Máy Windows không được sleep, restart hoặc shutdown trong lúc WSL đang chạy.

## 6. Theo dõi

Xem log chung:

```bash
tail -f dataset_friend_0501_1000/campaign.log
```

Xem trạng thái tổng:

```bash
cat dataset_friend_0501_1000/progress.json
cat dataset_friend_0501_1000/campaign_summary.json
```

Heartbeat chi tiết của một seed nằm trong:

```text
dataset_friend_0501_1000/scenario_0501/seed_0001/log.txt
```

Simulation time 300 giây là thời gian mô phỏng, không phải 300 giây thời gian
thật. Một seed có thể chạy lâu hơn đáng kể.

## 7. Dừng và resume

Nhấn `Ctrl+C` một lần. Parent sẽ terminate các process ns-3 đang chạy; không
đóng cưỡng bức terminal trước khi runner báo đã dừng.

Resume đúng output và đúng range:

```bash
./scripts/run_campaign.sh \
  --out dataset_friend_0501_1000 \
  --resume \
  --scenario-start 501 \
  --scenario-end 1000 \
  --workers auto
```

Seed đã `PASS` và còn đủ output sẽ được bỏ qua. Seed thiếu output,
`FAILED` hoặc `INTERRUPTED` sẽ được đưa lại vào queue.

## 8. Đóng gói kết quả ở máy phụ

Chỉ đóng gói khi `campaign_summary.json` cho biết `last_range.complete` là
`true`, `failed` của range bằng 0.

```bash
(
  cd dataset_friend_0501_1000
  tar -czf ../fanet_s0501_s1000.tar.gz scenario_*
)
sha256sum fanet_s0501_s1000.tar.gz > fanet_s0501_s1000.tar.gz.sha256
```

Gửi cả file `.tar.gz` và `.sha256` cho máy chính. Không gửi các file top-level
như `campaign.json`, `summary.csv`, `progress.json` vì chúng chỉ mô tả phần
campaign trên máy phụ.

## 9. Ghép vào dataset trên máy chính

Đặt hai file nhận được ngoài thư mục dataset rồi kiểm tra:

```bash
sha256sum -c fanet_s0501_s1000.tar.gz.sha256
tar -tzf fanet_s0501_s1000.tar.gz | head
```

Chờ runner của máy chính dừng hoặc hoàn tất range trước khi ghép. Không mở
thêm một runner khác vào `dataset_1000x10` trong lúc runner cũ còn chạy.

Giải nén với chế độ không ghi đè:

```bash
tar -xzf fanet_s0501_s1000.tar.gz \
  -C dataset_1000x10 \
  --keep-old-files
```

Sau đó cho runner quét range vừa nhập và cập nhật summary chung:

```bash
./scripts/run_campaign.sh \
  --out dataset_1000x10 \
  --resume \
  --scenario-start 501 \
  --scenario-end 1000 \
  --workers auto
```

Nếu toàn bộ seed nhận về hợp lệ, log sẽ báo queue có `0 pending`; runner
không mô phỏng lại. Nếu có seed thiếu, chỉ các seed đó được chạy bổ sung trên
máy chính.

## 10. Checklist bàn giao

- [ ] Hai máy có cùng Git SHA và ba SHA-256 ở mục 3.
- [ ] Range của các máy không giao nhau.
- [ ] Mỗi máy dùng output riêng.
- [ ] Build và `scripts/run_tests.sh` thành công.
- [ ] `last_range.complete = true`, range không có seed failed.
- [ ] SHA-256 của archive hợp lệ sau khi truyền.
- [ ] Chỉ ghép `scenario_*`, không ghi đè file top-level của dataset chính.
- [ ] Runner trên máy chính đã quét lại range và cập nhật summary.
