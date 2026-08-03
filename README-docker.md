# Docker environment for the ns-3 research project

This environment packages ns-3.45, its C++ build toolchain, and the Python
analysis stack. The source and compiled simulator are immutable image content.
Datasets are never copied into the image: Compose requires a writable host
directory and mounts it at `/data`.

## Design

- Ubuntu 22.04 is the image base, matching the original host environment.
- ns-3 is configured with the `default` profile and built during `docker build`.
- Only modules used by `scratch/linkscore/link-dataset-fanet.cc` are enabled.
- CMake uses Ninja and ccache; BuildKit caches apt, pip, and compiler data.
- Python packages, including transitive dependencies, are pinned in
  `requirements.txt`.
- Runtime uses the unprivileged `ns3` user and drops every Linux capability.
- The repository's `.git` directory is mounted read-only so
  `scripts/run_manifest.py` can still record the exact commit without adding
  the 1.4 GB Git object database to the image. Bootstrap creates a disposable
  index in `/tmp` and marks only the deliberately external dataset paths as
  `skip-worktree`, so omitted tracked datasets do not create a false dirty
  state while real source changes still do.
- Source is not bind-mounted. This prevents a host mount from hiding or
  invalidating the ns-3 build baked into the image.

The ns-3 project lists g++, Python 3, CMake, Ninja, and Git as the required
toolchain for ns-3.36 and newer. See the official
[ns-3.45 installation guide](https://www.nsnam.org/docs/release/3.45/installation/).

## First-time setup

Install Docker Engine with the Compose v2 plugin. On Windows, enable Docker
Desktop's WSL2 integration and clone the repository inside the WSL filesystem
(for example `~/src/ns3`), not under `/mnt/c`, for much faster compilation and
filesystem access.

From the repository root:

```bash
mkdir -p "$HOME/ns3-data"

cat > .env <<EOF
NS3_DATASET_DIR=$HOME/ns3-data
HOST_UID=$(id -u)
HOST_GID=$(id -g)
VCS_REF=$(git rev-parse HEAD)
EOF

docker compose config
docker compose up --build -d
docker compose ps
```

`NS3_DATASET_DIR` is mandatory and must already exist. Compose will not
silently create a dataset directory inside the repository. The bootstrap also
refuses to start unless `/data` is a real writable mount.

Open a shell and verify the environment:

```bash
docker compose exec ns3 bash
./ns3 show profile
test -x build/scratch/linkscore/ns3.45-link-dataset-fanet-default
python --version
python -c 'import numpy, pandas, matplotlib, sklearn, scipy, statsmodels; print("ML stack OK")'
```

## Rebuilding

After changing source, configuration, the Dockerfile, or requirements:

```bash
VCS_REF=$(git rev-parse HEAD)
docker compose build --build-arg VCS_REF="$VCS_REF" ns3
docker compose up -d --force-recreate
```

The source `COPY` invalidates only the final ns-3 build layer. System and
Python dependency layers remain cached, while ccache accelerates recompilation.

To refresh the Ubuntu base and apt packages:

```bash
docker compose build --pull --no-cache ns3
docker compose up -d --force-recreate
```

Use `--no-cache` only for a deliberate dependency refresh. Normal source
changes should retain the cache.

## Mounting datasets

The host directory configured by `NS3_DATASET_DIR` appears as `/data` and is
read/write. Keep all campaigns and generated analysis outputs below it:

```text
host:      $NS3_DATASET_DIR/dataset_1000x10
container: /data/dataset_1000x10
```

Changing dataset disks requires only an `.env` edit followed by container
recreation:

```bash
docker compose down
# Edit NS3_DATASET_DIR in .env.
docker compose up -d
```

The image contains no dataset directories from the repository because
`.dockerignore` excludes `data`, `dataset`, and `dataset_*`.

## Running simulations

Create a new 1,000-scenario, 10-seed campaign, initially running scenarios
1 through 100:

```bash
docker compose exec ns3 bash
./scripts/run_campaign.sh \
  --scenarios 1000 \
  --seeds 10 \
  --out /data/dataset_1000x10 \
  --scenario-start 1 \
  --scenario-end 100 \
  --workers auto \
  --yes
```

Resume another range without changing the dataset format:

```bash
./scripts/run_campaign.sh \
  --out /data/dataset_1000x10 \
  --resume \
  --scenario-start 101 \
  --scenario-end 200 \
  --workers auto \
  --yes
```

Ninja and the campaign's `--workers auto` use the CPU and memory visible to
the container. Compose sets no artificial CPU or RAM limit, so a 44C/88T Cloud
PC is available to the workload.

## Running ML and analysis scripts

Use `/data/...` for dataset inputs and persistent outputs. For example:

```bash
docker compose exec ns3 bash

python test/minmax_metrics_s0001_s0081/analyze.py \
  --dataset /data/dataset_1000x10 \
  --scenario-start 1 \
  --scenario-end 81 \
  --out /data/analysis/minmax_s0001_s0081

python analysis/validate/p2_batch_stats.py \
  /data/calib /data/train \
  --json /data/analysis/p2_batch_stats.json
```

Scripts with frozen inputs can read those inputs from the image and should be
given an output path below `/data` when the result must survive container
replacement. No simulation or ML script is modified by this Docker setup.

## Upgrading dependencies

1. Change only the intended pins in `requirements.txt`.
2. Rebuild the image.
3. Verify the resolver and imports:

```bash
docker compose build --no-cache ns3
docker compose run --rm ns3 pip check
docker compose run --rm ns3 \
  python -c 'import numpy, pandas, matplotlib, sklearn, scipy, statsmodels'
```

Commit the new requirements and Dockerfile together. Do not run `pip install`
inside a long-lived container; that creates an environment that cannot be
reproduced from Git.

## Using the same image on a Cloud PC

The simplest route is to clone the same commit on the Cloud PC, create the
external dataset directory and `.env`, then run:

```bash
docker compose up --build -d
```

To reuse an already-built image exactly, publish it to a registry under an
immutable commit tag:

```bash
docker tag ns3-research:local registry.example/ns3-research:$(git rev-parse --short HEAD)
docker push registry.example/ns3-research:$(git rev-parse --short HEAD)
```

On the Cloud PC, clone that same commit and set this additional `.env` value:

```text
NS3_IMAGE=registry.example/ns3-research:<commit>
```

Then start without rebuilding:

```bash
docker compose pull ns3
docker compose up --no-build -d
```

For Linux and Windows+WSL2 on x86-64, the same image can be used directly.
For mixed CPU architectures, publish a multi-platform image with Docker
Buildx and use the same commit tag or, preferably, the registry digest.

## Reproducibility and operational notes

- The Git commit, Dockerfile, exact Python pins, ns-3 `VERSION`, simulation
  configuration, and binary hash together identify a run.
- `run_manifest.py` sees the clone's read-only Git metadata. Rebuild whenever
  the checked-out commit changes; a mismatched image/worktree is reported as
  dirty by Git provenance.
- The Ubuntu tag receives security updates. For bit-for-bit base-image
  reproduction, pin `ubuntu:22.04` to a reviewed digest and record the image
  digest used for every campaign.
- The image intentionally retains GCC, CMake, Ninja, and build artifacts: this
  is a ready-to-build research image, not a stripped production runtime.
- No root process is used at runtime. FANET simulation does not need host
  networking, `NET_ADMIN`, devices, or privileged mode.
- Stop the environment with `docker compose down`. Dataset files remain on the
  host and are never removed by that command.
