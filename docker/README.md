# ObsEq Containerized Native Environment

The Linux x86-64 build uses Ubuntu 24.04 and a signed Ubuntu package snapshot. The GDAL environment is locked to the complete conda package set used on Linux, including GDAL 3.10.3, GEOS 3.13.1 and PROJ 9.6.0. The installer verifies pinned SQLite 3.53.1, PostgreSQL 17.12, LibreOffice 7.3.7.2, Spark 4.0.1, Deequ 2.0.15, CWI and both SQLLogicTest sources. OpenJDK 17 comes from the Ubuntu snapshot.

## Quick Usage

Once the `Dockerfile` is built:

```sh
docker build --platform linux/amd64 -t obseq-native -f docker/Dockerfile .
docker run --rm obseq-native python -B replay.py
docker run --rm obseq-native python -B replay.py --comparators
```

To use a reachable PyPI mirror, pass `--build-arg PIP_INDEX_URL=HTTPS_INDEX_URL`.
The image still checks the wheel hashes in the dependency locks.

To bind downloaded large-scale benchmark datasets (such as ClickBench `hits` shards or generated `TPC-H`/`TPC-DS` `SF10` databases) into the container, mount your host data directory and pass the corresponding `LOCAL_BINDINGS.json`:

```sh
docker run --rm -v /path/to/datasets:/data:ro obseq-native \
  python -B replay.py --native-inputs /data/LOCAL_BINDINGS.json --scratch /tmp/obseq-scratch
```

Put only the inputs you have in `LOCAL_BINDINGS.json`. Paths must be absolute inside the container. The example is a roster of role names and expected path shapes. Start with `{}` for a run that uses only bundled bindings. Each missing optional binding appears as `NA (missing optional input role: …)` and contributes to `skipped_missing_inputs`. An assigned path that is absent, a bad digest, a producer error, a semantic divergence or a timeout produces a nonzero exit. [External input roles and seals](INPUTS.md)

Historical receipts retain the original byte outputs. The current native runner permits differences in explicitly listed version fields for the cases in [SEMANTIC-PROJECTIONS.json](../evidence/e7-archived-native-replay-extension-10/SEMANTIC-PROJECTIONS.json). It still checks the payload, verdicts, counts and input identities. The workbook timezone receipt uses the bundled TZif and retains its SHA-256 comparison.

The H2O association-moment producer reads two full generated CSVs and includes a full native join. The archived case has a 180-second timeout and the full native workflow was run on a Linux server. Allow at least 16 GiB for full-data producer runs as described in the [reproducibility guide](../REPRODUCIBILITY.md). On a slower machine, set `--timeout 480` to override the time limit without changing input rows or expected verdicts.

The native 10M-row association-moment case passed a repeat Linux run in
128.84 seconds with the 480-second override. See the [table replay examples](REPLAY-EXAMPLES.md)
for source inputs and commands for representative Table 4, 6 and 7 cells.
