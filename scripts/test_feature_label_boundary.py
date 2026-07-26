#!/usr/bin/env python3
"""Test ranh giới features/labels — WORKFLOW.md mục 2.

Quy tắc phương pháp luận số 1: feature từ quá khứ [t−Δ, t), nhãn từ tương lai
[t, t+τ). Ranh giới đó hiện lên trong cây thư mục:

    analysis/features/   KHÔNG được import từ analysis/labels/
    analysis/labels/     KHÔNG được import từ analysis/features/

Vi phạm nghĩa là code tính feature có thể nhìn thấy nhãn (hoặc ngược lại) —
đường tắt dẫn tới fit contemporaneous và R² giả trên 0.9.

Kiểm tra bằng AST chứ không grep, để bắt được cả:

    import labels
    import analysis.labels as al
    from labels import pdr
    from analysis.labels.pdr import compute
    from ..labels import pdr          (relative import vượt ranh giới)

Chạy trực tiếp:  python3 scripts/test_feature_label_boundary.py
Hoặc qua pytest: pytest scripts/test_feature_label_boundary.py
Exit 0 = sạch, exit 1 = có vi phạm hoặc file không parse được.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = REPO_ROOT / "analysis"

# (thư mục bị soi, tên module cấm)
RULES = [
    (ANALYSIS / "features", "labels"),
    (ANALYSIS / "labels", "features"),
]


def _module_hits(module: str | None, forbidden: str) -> bool:
    """True nếu tên module đụng vào module cấm.

    Bắt 'labels', 'labels.pdr', 'analysis.labels', 'analysis.labels.pdr' —
    nhưng không bắt 'labelstore' (so khớp theo thành phần, không theo chuỗi).
    """
    if not module:
        return False
    parts = module.split(".")
    return forbidden in parts


def _violations_in_file(path: Path, forbidden: str) -> list[tuple[int, str]]:
    """[(số dòng, mô tả)] cho mọi import cấm trong một file."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _module_hits(alias.name, forbidden):
                    found.append((node.lineno, f"import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            # from X import Y — X có thể None với 'from . import Y',
            # khi đó tên bị cấm nằm ở Y.
            if _module_hits(node.module, forbidden):
                found.append((node.lineno, f"from {node.module} import ..."))
            elif node.level > 0:  # relative import: from .. import labels
                for alias in node.names:
                    if alias.name == forbidden:
                        found.append(
                            (node.lineno, f"from {'.' * node.level} import {alias.name}")
                        )
    return found


def find_violations() -> list[str]:
    """Quét cả hai chiều, trả về danh sách thông báo vi phạm (rỗng = sạch)."""
    problems = []
    for directory, forbidden in RULES:
        if not directory.is_dir():
            problems.append(f"thiếu thư mục {directory.relative_to(REPO_ROOT)}")
            continue
        for path in sorted(directory.rglob("*.py")):
            rel = path.relative_to(REPO_ROOT)
            try:
                hits = _violations_in_file(path, forbidden)
            except SyntaxError as exc:
                # File không parse được thì không kiểm tra được — coi là lỗi,
                # đừng im lặng cho qua.
                problems.append(f"{rel}:{exc.lineno}: không parse được ({exc.msg})")
                continue
            for lineno, desc in hits:
                problems.append(
                    f"{rel}:{lineno}: VI PHẠM ranh giới feature/label — '{desc}' "
                    f"(cấm import '{forbidden}' từ đây)"
                )
    return problems


def test_feature_label_boundary():
    """Entry point cho pytest."""
    problems = find_violations()
    assert not problems, "\n".join(problems)


def main() -> int:
    problems = find_violations()
    if problems:
        print("VI PHẠM ranh giới features/labels:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    checked = sum(
        len(list(d.rglob("*.py"))) for d, _ in RULES if d.is_dir()
    )
    print(f"OK — ranh giới features/labels sạch ({checked} file Python đã quét).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
