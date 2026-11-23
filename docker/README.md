# ObsEq Containerized Native Environment

This directory holds the reproducible Linux container specification for **Tier 3** native producer execution (pinning system-level C/C++, JVM, and CLI dependencies including `GDAL`, `GEOS`, `PROJ`, `SQLite`, `PostgreSQL` client/server tools, `OpenJDK` + `Deequ`, `LibreOffice Calc`, and `SQLLogicTest`).

## Quick Usage

Once the `Dockerfile` is built:

```sh
docker build -t obseq-native:latest -f docker/Dockerfile .
docker run --rm -it obseq-native:latest python -B replay.py --comparators
```

To bind downloaded large-scale benchmark datasets (such as ClickBench `hits` shards or generated `TPC-H`/`TPC-DS` `SF10` databases) into the container, mount your host data directory and pass the corresponding `LOCAL_BINDINGS.json`:

```sh
docker run --rm -v /path/to/datasets:/data:ro obseq-native:latest \
  python -B replay.py --native-inputs /data/LOCAL_BINDINGS.json --scratch /tmp/obseq-scratch
```
