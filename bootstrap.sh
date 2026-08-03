#!/usr/bin/env bash
set -euo pipefail

cd /workspace/ns-3

binary=build/scratch/linkscore/ns3.45-link-dataset-fanet-default
if [[ ! -x "$binary" ]]; then
    echo "ERROR: ns-3 binary is missing; rebuild the image." >&2
    exit 70
fi

if ! awk '$5 == "/data" { found=1 } END { exit !found }' /proc/self/mountinfo; then
    echo "ERROR: /data is not mounted; set NS3_DATASET_DIR before starting Compose." >&2
    exit 71
fi

if [[ ! -w /data ]]; then
    echo "ERROR: /data is not writable by uid=$(id -u), gid=$(id -g)." >&2
    exit 72
fi

# Compose mounts the real object database read-only. Build a disposable index
# from HEAD, then hide only dataset paths deliberately excluded from the image.
# Source changes still make run_manifest.py report git_dirty=true.
if [[ ! -e .git ]]; then
    echo "ERROR: Git metadata is not mounted; use docker compose to start the image." >&2
    exit 73
fi
export GIT_INDEX_FILE=/tmp/ns3-runtime-git-index
git read-tree HEAD
git ls-files -z -- data dataset 'dataset_*' |
    git update-index --skip-worktree -z --stdin

umask 0002
exec "$@"
