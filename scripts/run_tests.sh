#!/usr/bin/env bash
# Các bất biến KIỂM TRA ĐƯỢC của repo — chạy trước mỗi batch (run_p2_batch.sh
# gọi file này trước seed đầu tiên) và bất cứ lúc nào nghi ngờ.
# Exit khác 0 = có bất biến bị vi phạm; đừng chạy tiếp.
set -u
cd "$(dirname "$0")/.."
fail=0

# 1. Ranh giới features/labels (WORKFLOW.md mục 2) — AST, không grep.
python3 scripts/test_feature_label_boundary.py || fail=1

# 2. data/eval/ RỖNG cho tới P10 (CLAUDE.md quy tắc 15). Bất biến kiểm tra
#    được mạnh hơn ràng buộc bằng câu chữ: chạm data/eval sớm làm mọi con số
#    báo cáo mất giá trị, và cách chắc nhất để không chạm là giữ nó rỗng.
if [ -d data/eval ] && [ -n "$(ls -A data/eval 2>/dev/null)" ]; then
    echo "VI PHẠM: data/eval/ không rỗng — vùng cấm tới P10 (CLAUDE.md quy tắc 15)" >&2
    fail=1
fi

exit $fail
