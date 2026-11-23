FROM ubuntu:24.04@sha256:9a04f13b3f80ef056361e30868593b1cfd2279fe19e4081cb93a90bf56819d6a

SHELL ["/bin/bash", "-o", "pipefail", "-c"]
WORKDIR /opt/obseq

# Ubuntu's signed snapshot fixes bootstrap packages including OpenJDK 17.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && sed -i -E 's|^URIs: .*|URIs: https://snapshot.ubuntu.com/ubuntu/20261123T000000Z/|' \
        /etc/apt/sources.list.d/ubuntu.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        bison build-essential bzip2 curl flex libicu-dev libreadline-dev \
        openjdk-17-jdk-headless python3.12 python3.12-venv pkg-config zlib1g-dev \
        libdbus-1-3 libfontconfig1 libglib2.0-0t64 libxext6 libxinerama1 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

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

RUN bash docker/install-runtime.sh

# Match the archived date API where Ubuntu's system Python links older SQLite.
ENV LD_PRELOAD="/opt/obseq/sqlite/lib/libsqlite3.so.0"
RUN python -IB replay.py \
    && python -B replay.py --comparators \
    && obseq-verify-windows --help

RUN useradd --create-home obseq
USER obseq
CMD ["python", "-B", "replay.py"]
