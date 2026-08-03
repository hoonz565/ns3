# syntax=docker/dockerfile:1.7

ARG UBUNTU_VERSION=22.04
FROM ubuntu:${UBUNTU_VERSION}

ARG DEBIAN_FRONTEND=noninteractive
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG VCS_REF=local

LABEL org.opencontainers.image.title="ns-3 FANET research environment" \
      org.opencontainers.image.description="Reproducible ns-3.45 and Python ML environment" \
      org.opencontainers.image.revision="${VCS_REF}"

ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH} \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    GIT_OPTIONAL_LOCKS=0 \
    CCACHE_COMPRESS=1 \
    CCACHE_MAXSIZE=5G

RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' \
        > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get install --no-install-recommends -y \
        build-essential \
        ca-certificates \
        ccache \
        cmake \
        fonts-dejavu-core \
        git \
        ninja-build \
        pkg-config \
        python3 \
        python3-pip \
        python3-venv

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv "${VIRTUAL_ENV}"

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install pip==25.3 setuptools==80.9.0 wheel==0.45.1 && \
    pip install -r /tmp/requirements.txt && \
    pip check

RUN test "${USER_ID}" -ge 1000 && test "${GROUP_ID}" -ge 1000 && \
    groupadd --gid "${GROUP_ID}" ns3 && \
    useradd --uid "${USER_ID}" --gid "${GROUP_ID}" \
        --create-home --shell /bin/bash ns3 && \
    install -d -o ns3 -g ns3 \
        /data \
        /workspace/ns-3 \
        /home/ns3/.cache/ccache \
        /home/ns3/.cache/matplotlib

ENV HOME=/home/ns3 \
    CCACHE_DIR=/home/ns3/.cache/ccache \
    MPLCONFIGDIR=/home/ns3/.cache/matplotlib \
    NS3_DATA_DIR=/data

COPY --chmod=755 bootstrap.sh /usr/local/bin/ns3-bootstrap

WORKDIR /workspace/ns-3
COPY --chown=ns3:ns3 . .

USER ns3

RUN --mount=type=cache,target=/home/ns3/.cache/ccache,uid=${USER_ID},gid=${GROUP_ID} \
    ./ns3 configure -G Ninja \
        --build-profile=default \
        --enable-asserts \
        --enable-logs \
        --disable-examples \
        --disable-tests \
        --disable-python-bindings \
        --disable-gtk \
        --enable-modules="applications;core;internet;mobility;network;olsr;propagation;traffic-control;wifi" && \
    ./ns3 build scratch/linkscore/link-dataset-fanet && \
    bash scripts/run_tests.sh && \
    test -x build/scratch/linkscore/ns3.45-link-dataset-fanet-default

ENTRYPOINT ["ns3-bootstrap"]
CMD ["sleep", "infinity"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD test -x build/scratch/linkscore/ns3.45-link-dataset-fanet-default && test -w /data || exit 1
