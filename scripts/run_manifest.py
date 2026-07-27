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

# --- sim_params_sha256 (P4) -------------------------------------------------
# Hash các GIÁ TRỊ HIỆU DỤNG mà scenario thực sự đọc, lấy từ meta.json do
# chính binary in ra sau run. Khác config_sha256 (hash FILE conf): file conf
# chứa cả key phía phân tích (gate*, seeds* — binary khai là "của Python"),
# nên đổi một ngưỡng cổng là đổi config_sha256 dù mô phỏng không đổi một bit.
# sim_params_sha256 chỉ phủ tham số mô phỏng → hai run so sánh được khi và
# chỉ khi hash này trùng. config_sha256 GIỮ NGUYÊN để không mất so sánh với
# 35 manifest lịch sử.
#
# Loại khỏi hash: trường định danh per-run, không phải lựa chọn tham số.
#   seed          — mỗi run một giá trị, đúng thiết kế
#   flows         — rút từ RNG stream của seed (dẫn xuất của seed)
#   phase         — nhãn tổ chức (P2/P10), không đổi hành vi binary
#   config_files  — đường dẫn file, đã có config_sha256 lo
SIM_PARAMS_EXCLUDE = {"seed", "flows", "phase", "config_files"}


def sim_params_sha256(meta: dict) -> str:
    """Hash chính tắc của tham số mô phỏng hiệu dụng trong meta.json.

    Chính tắc hoá: bỏ SIM_PARAMS_EXCLUDE, json.dumps sort_keys, separators
    gọn. Float đi qua json.load->dumps là ổn định (300.000000 -> 300.0) miễn
    là mọi nơi cùng dùng hàm NÀY — đừng tự chế bản khác.

    PHỦ SÓNG — biết rõ giới hạn: hash này chỉ phủ các key mà binary IN vào
    meta.json (hiện ~20 key: tx power, cửa sổ, tải, probe/beacon...). Nó bắt
    được CLI override (--txPowerDbm=20 hiện trong meta.json) — thứ mà hash
    file conf không thấy. Nhưng nó KHÔNG phủ tham số conf mà meta.json không
    in (exponent, nakagami*, gm*, frameRetryLimit, dataMode, area*...) —
    phần đó do config_sim_sha256 bên dưới phủ. Khoá so sánh giữa hai run vì
    thế là BỘ BA: binary_sha256 (code + default biên dịch) +
    config_sim_sha256 (key mô phỏng trong conf) + sim_params_sha256 (giá trị
    hiệu dụng binary tự khai, gồm CLI override).
    """
    core = {k: v for k, v in meta.items() if k not in SIM_PARAMS_EXCLUDE}
    canon = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


def _conf_is_analysis_key(key: str) -> bool:
    """Key phía phân tích — danh sách GƯƠNG với registry của binary.

    link-dataset-fanet in vào stdout.log đúng các key nó không đọc và coi là
    "của Python": gate*, seeds*, rHalfM. Đổi các key này không đổi mô phỏng
    (đã kiểm chứng P4: giá trị đo của 35 seed trùng khít trước/sau khi đổi
    gateNearQMax). Dùng quy tắc tiền tố thay vì danh sách cứng để gate mới
    thêm sau này không lọt vào hash mô phỏng.
    """
    return key.startswith("gate") or key.startswith("seeds") or key == "rHalfM"


def conf_sim_canonical(text: str) -> str:
    """Dạng chính tắc của PHẦN MÔ PHỎNG trong một file conf key=value.

    Bỏ comment (# tới cuối dòng), bỏ dòng trắng, bỏ key phía phân tích;
    key trùng lấy lần cuối (khớp cách binary nạp); sort theo key. Giá trị
    giữ NGUYÊN dạng chuỗi — binary mới là bên parse, chuỗi bằng nhau là
    bất biến đúng cho file conf.
    """
    kv: dict[str, str] = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if not key or _conf_is_analysis_key(key):
            continue
        kv[key] = value
    return "\n".join(f"{k} = {kv[k]}" for k in sorted(kv))


def conf_sim_sha256(text: str) -> str:
    return hashlib.sha256(conf_sim_canonical(text).encode()).hexdigest()


def augment_with_meta(manifest_path: Path, meta_path: Path) -> dict:
    """Thêm sim_params_sha256 vào manifest ĐÃ CÓ (gọi sau khi run xong).

    Chỉ THÊM trường mới, không sửa trường nào đã ghi — manifest tiền-run vẫn
    là vết gốc. Idempotent: gọi lại cho cùng meta.json ra cùng kết quả.
    """
    with manifest_path.open() as fh:
        manifest = json.load(fh)
    with meta_path.open() as fh:
        meta = json.load(fh)
    manifest["sim_params_sha256"] = sim_params_sha256(meta)
    manifest["sim_params_source"] = str(meta_path)
    manifest["sim_params_excluded_keys"] = sorted(SIM_PARAMS_EXCLUDE)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


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

    # Nhiều file config ghép được (file sau ghi đè file trước), nên manifest
    # phải ghi cả danh sách theo thứ tự: chỉ hash file cuối là mất phần lớn
    # tham số, chỉ hash file đầu là mất phần bị ghi đè.
    config_list = [] if config is None else ([config] if isinstance(config, str) else list(config))
    if not config_list:
        manifest["config_paths"] = []
        manifest["config_sha256"] = None
        manifest["config_sha256_each"] = []
        manifest["config_sim_sha256"] = None
    else:
        digest = hashlib.sha256()
        sim_digest = hashlib.sha256()
        each = []
        for raw in config_list:
            config_path = Path(raw)
            resolved = config_path if config_path.is_absolute() else REPO_ROOT / config_path
            if not resolved.is_file():
                raise ManifestError(f"config không tồn tại: {raw}")
            one = sha256_of(resolved)
            each.append(f"{raw}@sha256:{one}")
            # Hash gộp theo thứ tự nạp: đổi thứ tự file là đổi tham số hiệu dụng,
            # nên nó phải ra hash khác.
            digest.update(raw.encode())
            digest.update(bytes.fromhex(one))
            # Bản chỉ-key-mô-phỏng (P4): bỏ gate*/seeds*/rHalfM trước khi hash,
            # để đổi ngưỡng cổng không đổi khoá so sánh giữa các batch.
            # KHÔNG đưa tên file vào digest này — di chuyển/đổi tên conf mà
            # nội dung mô phỏng y nguyên thì hai run vẫn so sánh được.
            sim_digest.update(conf_sim_canonical(resolved.read_text()).encode())
            sim_digest.update(b"\x00")
        manifest["config_paths"] = config_list
        manifest["config_sha256"] = digest.hexdigest()
        manifest["config_sha256_each"] = each
        manifest["config_sim_sha256"] = sim_digest.hexdigest()

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
    p.add_argument("--phase", help="P0..P10 (bắt buộc trừ khi --augment-meta)")
    p.add_argument("--out", required=True, help="đường dẫn run_manifest.json")
    p.add_argument(
        "--augment-meta",
        metavar="META_JSON",
        help="chế độ SAU-RUN: thêm sim_params_sha256 (hash tham số hiệu dụng "
        "từ meta.json của binary) vào manifest ĐÃ CÓ tại --out rồi thoát. "
        "Không sửa trường nào khác. Idempotent.",
    )
    p.add_argument(
        "--config",
        action="append",
        default=[],
        metavar="PATH",
        help="file sim-config; lặp lại được theo đúng thứ tự truyền cho scenario "
        "(file sau ghi đè file trước)",
    )
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

    if args.augment_meta:
        return args  # chế độ sau-run: chỉ cần --out + --augment-meta
    if not args.phase:
        p.error("cần --phase (trừ chế độ --augment-meta)")
    if not args.binary and not args.no_binary:
        p.error("cần --binary, hoặc --no-binary nếu phase này không chạy mô phỏng")
    if args.binary and args.no_binary:
        p.error("--binary và --no-binary loại trừ nhau")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.augment_meta:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = REPO_ROOT / out_path
        meta_path = Path(args.augment_meta)
        if not meta_path.is_absolute():
            meta_path = REPO_ROOT / meta_path
        if not out_path.is_file():
            print(f"[run_manifest] LỖI: manifest chưa tồn tại: {args.out} — "
                  "augment chỉ THÊM vào manifest đã sinh tiền-run", file=sys.stderr)
            return 1
        if not meta_path.is_file():
            print(f"[run_manifest] LỖI: meta.json không tồn tại: {args.augment_meta}",
                  file=sys.stderr)
            return 1
        manifest = augment_with_meta(out_path, meta_path)
        if not args.quiet:
            print(f"[run_manifest] augment: sim_params_sha256="
                  f"{manifest['sim_params_sha256'][:12]}… -> {args.out}")
        return 0

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
