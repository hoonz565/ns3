# Hướng dẫn chạy campaign dataset LinkScore v2

Tài liệu này hướng dẫn chạy dataset theo cấu hình v2 trong
`Thiet_ke_LinkScore_OLSR_UAV (2).docx` bằng `scripts/run_campaign.py`.

## 1. Cấu hình đang được dùng

Runner sử dụng `sim-config/fanet-tier2.conf` và binary
`scratch/linkscore/link-dataset-fanet` với các điểm chính:

- Cửa sổ feature và target tương lai đều dài 1 giây.
- Mỗi cửa sổ feature gồm 10 bin RSSI, mỗi bin 100 ms.
- Target là final-delivery PDR trên các packet gốc duy nhất; retransmission
  không làm tăng số trial.
- RSSI trung bình, RSSI slope và MAC retry ratio là ba feature đầu vào.
- Acceptance gate được hoãn tới bước hậu kiểm sau khi campaign hoàn tất.

Không sửa source hoặc `sim-config/fanet-tier2.conf` giữa các lần resume của
cùng một campaign. Nếu cấu hình thay đổi, phải tạo output mới.

## 2. Kiểm tra trước khi chạy

Chạy từ thư mục gốc của repository:

```bash
bash scripts/run_tests.sh
./ns3 build scratch/linkscore/link-dataset-fanet
```

Không tiếp tục nếu một trong hai lệnh trả về lỗi. Runner cũng tự chạy lại hai
bước này trước khi đưa các job vào hàng đợi.

## 3. Tạo campaign mới

Lần đầu tiên, output phải là thư mục mới hoặc thư mục rỗng và **không dùng**
`--resume`:

```bash
python3 scripts/run_campaign.py \
    --scenarios 1000 \
    --scenario-start 500 \
    --scenario-end 600 \
    --seeds 10 \
    --workers auto \
    --out ./dataset_windowdelta_500_600 \
    --yes
```

`--scenario-start` và `--scenario-end` đều được tính. Vì vậy range `500–600`
có 101 scenario, tương ứng `101 × 10 = 1.010` job. Nếu cần đúng 100 scenario,
dùng range `500–599`.

## 4. Resume campaign hiện có

Khi output đã có `campaign.json`, chạy:

```bash
python3 scripts/run_campaign.py \
    --scenarios 1000 \
    --scenario-start 500 \
    --scenario-end 600 \
    --resume \
    --seeds 10 \
    --workers auto \
    --out ./dataset_windowdelta_500_600 \
    --yes
```

Khi resume, runner lấy tổng số scenario, số seed và simulation time từ
`campaign.json`; các giá trị `--scenarios`, `--seeds` và `--sim-time` trên
command line không thay đổi metadata đã lưu. Phải giữ đúng output và range
được giao.

Runner tái sử dụng seed đã `PASS` và còn đủ `meta.json`, `summary.json`,
`rows.csv`. Seed thiếu output, `FAILED` hoặc `INTERRUPTED` sẽ được chạy lại.

## 5. Ý nghĩa các tham số

| Tham số | Ý nghĩa |
|---|---|
| `--scenarios 1000` | Tổng không gian scenario của campaign là 1–1000. |
| `--scenario-start 500` | Scenario đầu tiên của phần đang chạy, inclusive. |
| `--scenario-end 600` | Scenario cuối cùng của phần đang chạy, inclusive. |
| `--seeds 10` | Mỗi scenario chạy 10 seed. |
| `--workers auto` | Tự chọn worker theo CPU khả dụng, RAM và số job. |
| `--out ...` | Thư mục chứa toàn bộ metadata, log và dữ liệu. |
| `--resume` | Tiếp tục campaign đã có `campaign.json`. |
| `--yes` | Bỏ câu hỏi xác nhận khi tạo campaign mới. |

Không chạy hai runner cùng ghi vào một output.

## 6. Theo dõi và dừng an toàn

Xem tiến độ và log:

```bash
cat dataset_windowdelta_500_600/progress.json
tail -f dataset_windowdelta_500_600/campaign.log
```

`simulation_time_s = 300` là thời gian mô phỏng; thời gian thực của một seed
có thể dài hơn nhiều.

Để dừng, nhấn `Ctrl+C` một lần và chờ dòng:

```text
Campaign interrupted safely. Run again with --resume.
```

Sau đó dùng lại lệnh ở mục 4. Không kill riêng các process ns-3 khi runner vẫn
đang hoạt động.

## 7. Kiểm tra kết quả

Sau khi hoàn tất range, kiểm tra:

```bash
cat dataset_windowdelta_500_600/campaign_summary.json
```

Range chỉ hoàn tất khi `last_range.complete` là `true` và không còn seed lỗi.
Acceptance gate của cấu hình v2 chưa được dùng trong lúc sinh dữ liệu; cần
chạy bước hậu kiểm riêng sau khi có đủ dataset.
