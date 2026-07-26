#!/usr/bin/env python3
"""Sinh run_manifest.json cho mỗi lần chạy — WORKFLOW.md mục 3.

Mọi output (dataset, hình, bảng số) phải nằm cạnh một manifest tự khai báo
nguồn gốc: git SHA, cờ dirty, hash config, hash binary, và mtime của binary so
với source mới nhất.

Hai kiểm tra sống còn (WORKFLOW.md mục 3):

  * git_dirty == True   -> CẢNH BÁO TO. Kết quả không tái lập được từ SHA.
  * binary cũ hơn source mới nhất -> DỪNG NGAY, exit 2, không chạy mô phỏng.

Kiểm tra thứ hai **không có cờ bỏ qua**, có chủ ý: ở dự án trước, mọi profile
trỏ tới một binary -debug cũ 9 ngày và toàn bộ campaign chạy trên code không
khớp source mà không ai biết cho tới khi kiểm toán.

Dùng như CLI, trước khi chạy mô phỏng:

    python3 scripts/run_manifest.py \
        --phase P4 --seed 1007 \
        --config config/nominal.yaml \
        --binary build/scratch/ns3.45-link-dataset-fanet-default \
        --frozen frozen/normalization.json \
        --out data/train/seed-1007/run_manifest.json

Hoặc import từ script Python khác:

    from run_manifest import build_manifest, write_manifest, StaleBinaryError
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Source nào ảnh hưởng tới binary. CMake nằm trong danh sách vì đổi flag biên
# dịch cũng đổi binary mà không đổi một dòng .cc nào.
SOURCE_SUFFIXES = {".cc", ".cpp", ".cxx", ".c", ".h", ".hpp", ".cmake"}
SOURCE_NAMES = {"CMakeLists.txt"}

# Không quét: cây build (chứa chính binary), rác của tool, dữ liệu.
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".cache",
    "build",
    "build-dir",
    "testpy-output",
    "data",
    "venv",
}

DEFAULT_SOURCE_DIRS = ("src", "contrib", "scratch")

MAX_DIRTY_FILES_LISTED = 20


class ManifestError(Exception):
    """Lỗi không thể sinh manifest (đường dẫn sai, không phải git repo, ...)."""


class StaleBinaryError(ManifestError):
    """Binary cũ hơn source mới nhất — kết quả sẽ không khớp code trong repo."""


# --------------------------------------------------------------------------- #
# thu thập từng trường
# --------------------------------------------------------------------------- #


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def iso_utc(timestamp: float | None = None) -> str:
    dt = (
        datetime.now(timezone.utc)
        if timestamp is None
        else datetime.fromtimestamp(timestamp, timezone.utc)
    )
    return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise ManifestError(
            f"git {' '.join(args)} thất bại: {proc.stderr.strip() or proc.returncode}"
        )
    return proc.stdout


def git_state() -> dict:
    """SHA + trạng thái dirty.

    File untracked cũng tính là dirty: một `scratch/link-dataset.cc` chưa
    `git add` vẫn được biên dịch vào binary, nên SHA không tái lập được nó.
    File bị .gitignore (data/, build/) không xuất hiện trong --porcelain nên
    không làm dirty.
    """
    porcelain = _git("status", "--porcelain").splitlines()
    return {
        "git_sha": _git("rev-parse", "--short", "HEAD").strip(),
        "git_sha_full": _git("rev-parse", "HEAD").strip(),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD").strip(),
        "git_dirty": bool(porcelain),
        "git_dirty_files": [line[3:] for line in porcelain[:MAX_DIRTY_FILES_LISTED]],
        "git_dirty_file_count": len(porcelain),
    }


def ns3_version() -> str | None:
    version_file = REPO_ROOT / "VERSION"
    if not version_file.is_file():
        return None
    return version_file.read_text().strip()


def newest_source(source_dirs) -> tuple[float, str] | tuple[None, None]:
    """(mtime, đường dẫn) của file source mới nhất.

    Trả về đường dẫn chứ không chỉ mtime: khi kiểm tra thất bại, thứ cần biết
    là *file nào* mới hơn binary, để rebuild hoặc để nhận ra mình đang so với
    một file không liên quan.
    """
    newest_mtime: float | None = None
    newest_path: str | None = None

    for rel in source_dirs:
        root = (REPO_ROOT / rel).resolve()
        if not root.exists():
            raise ManifestError(f"source dir không tồn tại: {rel}")
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                continue
            if path.suffix not in SOURCE_SUFFIXES and path.name not in SOURCE_NAMES:
                continue
            mtime = path.stat().st_mtime
            if newest_mtime is None or mtime > newest_mtime:
                newest_mtime = mtime
                newest_path = str(path.relative_to(REPO_ROOT))

    if newest_mtime is None:
        return None, None
    return newest_mtime, newest_path


def frozen_refs(paths) -> list[str]:
    """'frozen/normalization.json@sha256:3c1a...' cho từng tạo phẩm đông lạnh.

    Hash chứ không chỉ tên file: `frozen/` bất biến theo quy ước, và hash là
    thứ chứng minh nó thật sự không bị ghi đè giữa hai lần chạy.
    """
    refs = []
    for raw in paths:
        path = Path(raw)
        resolved = path if path.is_absolute() else REPO_ROOT / path
        if not resolved.is_file():
            raise ManifestError(f"frozen artifact không tồn tại: {raw}")
        refs.append(f"{raw}@sha256:{sha256_of(resolved)}")
    return refs


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #


def build_manifest(
    phase: str,
    config: str | None = None,
    binary: str | None = None,
    seed: int | None = None,
    frozen: list[str] | None = None,
    source_dirs=DEFAULT_SOURCE_DIRS,
    notes: str | None = None,
) -> dict:
    """Dựng dict manifest. KHÔNG tự kiểm tra — xem check_manifest().

    binary=None hợp lệ cho phase chỉ chạy Python (P5, P6, P7): không có binary
    thì không có gì để so mtime. Khi đó check_manifest() nói rõ là đã bỏ qua,
    thay vì im lặng cho qua.
    """
    manifest: dict = {"phase": phase, "timestamp": iso_utc()}
    manifest.update(git_state())

    if config is None:
        manifest["config_path"] = None
        manifest["config_sha256"] = None
    else:
        config_path = Path(config)
        resolved = config_path if config_path.is_absolute() else REPO_ROOT / config_path
        if not resolved.is_file():
            raise ManifestError(f"config không tồn tại: {config}")
        manifest["config_path"] = config
        manifest["config_sha256"] = sha256_of(resolved)

    if binary is None:
        manifest["binary_path"] = None
        manifest["binary_sha256"] = None
        manifest["binary_mtime"] = None
    else:
        binary_path = Path(binary)
        resolved = binary_path if binary_path.is_absolute() else REPO_ROOT / binary_path
        if not resolved.is_file():
            raise ManifestError(
                f"binary không tồn tại: {binary} — đã ./ns3 build chưa?"
            )
        manifest["binary_path"] = binary
        manifest["binary_sha256"] = sha256_of(resolved)
        manifest["binary_mtime"] = iso_utc(resolved.stat().st_mtime)

    newest_mtime, newest_path = newest_source(source_dirs)
    manifest["newest_source_mtime"] = (
        None if newest_mtime is None else iso_utc(newest_mtime)
    )
    manifest["newest_source_file"] = newest_path
    manifest["source_dirs_scanned"] = list(source_dirs)

    manifest["ns3_version"] = ns3_version()
    manifest["seed"] = seed
    manifest["frozen_artifacts_used"] = frozen_refs(frozen or [])
    if notes:
        manifest["notes"] = notes

    return manifest


def check_manifest(manifest: dict, fail_on_dirty: bool = False) -> list[str]:
    """Hai kiểm tra của WORKFLOW.md mục 3.

    Raise StaleBinaryError nếu binary cũ hơn source mới nhất. Trả về danh sách
    cảnh báo (dirty repo, kiểm tra bị bỏ qua) để caller in ra.
    """
    warnings: list[str] = []

    if manifest["git_dirty"]:
        listed = ", ".join(manifest["git_dirty_files"][:5]) or "?"
        warnings.append(
            f"GIT DIRTY — {manifest['git_dirty_file_count']} file thay đổi/untracked "
            f"({listed}...). Kết quả KHÔNG tái lập được từ SHA "
            f"{manifest['git_sha']}. Commit trước khi chạy batch thật."
        )

    binary_mtime = manifest.get("binary_mtime")
    source_mtime = manifest.get("newest_source_mtime")

    if binary_mtime is None:
        warnings.append(
            "Không có --binary: BỎ QUA kiểm tra binary-vs-source. "
            "Chỉ hợp lệ cho phase không chạy mô phỏng."
        )
    elif source_mtime is None:
        warnings.append(
            "Không tìm thấy file source nào trong source_dirs: "
            "BỎ QUA kiểm tra binary-vs-source."
        )
    elif binary_mtime < source_mtime:
        # So sánh chuỗi ISO-8601 UTC là so sánh thời gian đúng (cùng độ dài,
        # cùng offset Z).
        raise StaleBinaryError(
            f"BINARY CŨ HƠN SOURCE — không chạy.\n"
            f"  binary : {manifest['binary_path']}  ({binary_mtime})\n"
            f"  source : {manifest['newest_source_file']}  ({source_mtime})\n"
            f"Chạy ./ns3 build rồi thử lại. Không có cờ bỏ qua kiểm tra này."
        )

    if fail_on_dirty and manifest["git_dirty"]:
        raise ManifestError("git dirty và --fail-on-dirty được bật.")

    return warnings


def write_manifest(manifest: dict, out: str | Path) -> Path:
    out_path = Path(out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return out_path


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Sinh run_manifest.json (WORKFLOW.md mục 3) và kiểm tra "
        "git_dirty + binary-vs-source mtime.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--phase", required=True, help="P0..P10")
    p.add_argument("--out", required=True, help="đường dẫn run_manifest.json")
    p.add_argument("--config", help="file config, ví dụ config/nominal.yaml")
    p.add_argument("--binary", help="binary ns-3 sắp chạy")
    p.add_argument(
        "--no-binary",
        action="store_true",
        help="phase chỉ chạy Python; bỏ qua kiểm tra mtime một cách tường minh",
    )
    p.add_argument("--seed", type=int, help="seed của lần chạy này")
    p.add_argument(
        "--frozen",
        action="append",
        default=[],
        metavar="PATH",
        help="tạo phẩm trong frozen/ mà lần chạy này dùng (lặp lại được)",
    )
    p.add_argument(
        "--source-dir",
        action="append",
        default=[],
        metavar="DIR",
        help=f"thư mục source để quét mtime (mặc định: {', '.join(DEFAULT_SOURCE_DIRS)})",
    )
    p.add_argument("--notes", help="ghi chú tự do vào manifest")
    p.add_argument(
        "--fail-on-dirty",
        action="store_true",
        help="coi git dirty là lỗi chứ không chỉ cảnh báo (nên bật cho batch thật)",
    )
    p.add_argument("--quiet", action="store_true", help="chỉ in lỗi")
    args = p.parse_args(argv)

    if not args.binary and not args.no_binary:
        p.error("cần --binary, hoặc --no-binary nếu phase này không chạy mô phỏng")
    if args.binary and args.no_binary:
        p.error("--binary và --no-binary loại trừ nhau")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    source_dirs = tuple(args.source_dir) if args.source_dir else DEFAULT_SOURCE_DIRS

    try:
        manifest = build_manifest(
            phase=args.phase,
            config=args.config,
            binary=args.binary,
            seed=args.seed,
            frozen=args.frozen,
            source_dirs=source_dirs,
            notes=args.notes,
        )
    except ManifestError as exc:
        print(f"[run_manifest] LỖI: {exc}", file=sys.stderr)
        return 1

    try:
        warnings = check_manifest(manifest, fail_on_dirty=args.fail_on_dirty)
    except StaleBinaryError as exc:
        print("\n" + "=" * 72, file=sys.stderr)
        print(f"[run_manifest] {exc}", file=sys.stderr)
        print("=" * 72 + "\n", file=sys.stderr)
        return 2
    except ManifestError as exc:
        print(f"[run_manifest] LỖI: {exc}", file=sys.stderr)
        return 3

    for warning in warnings:
        print("\n" + "!" * 72, file=sys.stderr)
        print(f"[run_manifest] CẢNH BÁO: {warning}", file=sys.stderr)
        print("!" * 72 + "\n", file=sys.stderr)

    out_path = write_manifest(manifest, args.out)
    if not args.quiet:
        try:
            shown = out_path.relative_to(REPO_ROOT)
        except ValueError:  # --out nằm ngoài repo
            shown = out_path
        print(f"[run_manifest] {shown}")
        print(
            f"[run_manifest] phase={manifest['phase']} seed={manifest['seed']} "
            f"sha={manifest['git_sha']} dirty={manifest['git_dirty']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
