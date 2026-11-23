FROM ubuntu:24.04@sha256:9a04f13b3f80ef056361e30868593b1cfd2279fe19e4081cb93a90bf56819d6a

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
WORKDIR /opt/obseq

# Bootstrap HTTPS from the pinned certificate package before the signed APT snapshot.
ADD https://snapshot.ubuntu.com/ubuntu/20261123T000000Z/pool/main/c/ca-certificates/ca-certificates_20240203_all.deb /tmp/ubuntu-ca.deb
RUN printf '%s  %s\n' 641de77d8f142cfd62a1a6f964ba67b20754d3337c480efb529d086075a06c9a /tmp/ubuntu-ca.deb \
      | sha256sum --check - \
    && dpkg-deb -x /tmp/ubuntu-ca.deb /tmp/ubuntu-ca \
    && find /tmp/ubuntu-ca/usr/share/ca-certificates -name '*.crt' -exec cat {} + > /tmp/ubuntu-ca.pem \
    && sed -i -E 's|^URIs: .*|URIs: https://snapshot.ubuntu.com/ubuntu/20261123T000000Z/|' \
        /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get -o Acquire::https::CaInfo=/tmp/ubuntu-ca.pem -o APT::Update::Error-Mode=any update \
    && DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::https::CaInfo=/tmp/ubuntu-ca.pem install -y --no-install-recommends \
        ca-certificates \
        bison build-essential bzip2 curl flex libicu-dev libreadline-dev \
        openjdk-17-jdk-headless python3.12 python3.12-venv pkg-config zlib1g-dev \
        libcairo2 libcups2t64 libdbus-1-3 libfontconfig1 libglib2.0-0t64 \
        libice6 libsm6 libxext6 libxinerama1 libxrender1 \
    && rm -rf /var/lib/apt/lists/* /tmp/ubuntu-ca /tmp/ubuntu-ca.deb /tmp/ubuntu-ca.pem

COPY docker /opt/obseq/docker
COPY requirements.lock pyproject.toml README.md LICENSE replay.py NUMBERS.json SHA256SUMS /opt/obseq/
COPY .dockerignore .gitattributes .gitignore CITATION.cff TAXONOMY.md REPRODUCIBILITY.md requirements.in \
    fetch_clickbench.py build_tpc.py /opt/obseq/
COPY scripts /opt/obseq/scripts
COPY evidence /opt/obseq/evidence
COPY zoneinfo /opt/obseq/zoneinfo

ENV PATH="/opt/obseq/venv/bin:/opt/obseq/tools:/opt/obseq/pgsql/bin:${PATH}" \
    JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64" \
    PROJ_DATA="/opt/obseq/gdal/share/proj" \
    GDAL_DATA="/opt/obseq/gdal/share/gdal" \
    PROJ_NETWORK="OFF" \
    PYTHONTZPATH="/opt/obseq/zoneinfo" \
    OBSEQ_SYSTEM_PYTHON="/opt/obseq/gdal/bin/python" \
    OBSEQ_RUNTIME_BINDINGS="/opt/obseq/docker/runtime-bindings.json"

ARG PIP_INDEX_URL
ARG OBSEQ_SOURCE_MIRROR
RUN bash docker/install-runtime.sh

# Match the archived date API where Ubuntu's system Python links older SQLite.
ENV LD_PRELOAD="/opt/obseq/sqlite/lib/libsqlite3.so.0"
RUN python -IB replay.py \
    && python -B replay.py --comparators \
    && obseq-verify-windows --help \
    && soffice --headless --version

RUN useradd --create-home obseq
USER obseq
CMD ["python", "-B", "replay.py"]
