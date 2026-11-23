# H2O Join E1: complete published-generator input and native Q3 checker boundary

The already extracted official Debian R 4.5.0 and data.table 1.17.0 packages and [pinned benchmark revision](https://github.com/duckdblabs/db-benchmark/tree/3b074bc3190468803b3a890301f87ce455114d20) are intact. Exact generator digest d59ddc78df4d6114ccc784fa8a3f9678b1977cfd83680767357877fa062dab9d. The unchanged generator executes setDTthreads(0L) and explicitly rejects N<10,000,000; no scaled surrogate qualifies. The earlier log reached LHS CSV writing and left 54,525,952 partial bytes; exit 137 is reported independently by the predecessor, but no logged peak RSS or OOM reason exists. Do not use this partial input.

Safe preflight repeats only library initialization and the same setDTthreads(0L) call, not generator allocations. On the current nine-CPU allowed affinity, OMP_NUM_THREADS=1 alone still gives data.table nine threads after that call. OMP_THREAD_LIMIT=1 actually gives one (separately checked before and after single-CPU affinity). This agrees with [the official data.table help](https://cloud.r-project.org/web/packages/data.table/refman/data.table.html). The exact process receipt is RECEIPT.txt; host CPU count and thread defaults are not portable. One thread can reduce thread-dependent writer costs, but will not remove the generator's concurrent resident vectors, ten-million-key universe, string conversion, and right-hand datasets. No available evidence isolates the previous stoppage's cause or bounds the complete run's peak RSS.

Large-input replay requires actual free memory and disk checked independently, not the runtime settings alone. Use a fresh isolated working directory, a timeout and an independent output-space and process-RSS sampler. The 1.5 GiB output and ~2.5 GiB sampled process-RSS guards here are abort thresholds, not guaranteed bounds. If completed once, require success exit, final generator-finished marker, permitted exact version/options, all three complete named RHS CSVs and a complete 10M-row LHS, strict schemas, and SHAs before any query. Do not infer semantic E1 outcomes from this preflight or prior partial data.

Replay preflight: CHECK_TMPDIR=/writable/disk/path sh preflight.sh EXTRACTED_H2O_PREREQUISITES. The preflight never installs system packages, modifies the generator, downloads, launches benchmark-sized allocations, or starts DuckDB. No raw data or Git.

## One later authorized bounded execution completed

With other large local work finished and resource headroom checked, one unchanged 10M generator run completed with exit 0 and its terminal marker, no guard trigger. It produced exact promised rows: 10,000,000 LHS plus 10, 10,000 and 10,000,000 RHS; check schemas and binding digests in GENERATOR.json. Runtime was one affinity CPU, OMP_THREAD_LIMIT=1 and OMP_NUM_THREADS=1, official pinned packages and generator arguments 1e7 0 5 0. The monitor sampled at most 1,860,997,120 bytes RSS and 891,233,215 output bytes while child was active. These are sampled observations on this attempt, not exact peak/final file length measurements, comparative timing or diagnosis of the first 137. Complete native files remain intact in the local scratch workspace, not in this text packet. Do not rerun a comparatively large attempt just to reproduce the RSS number.

## Scoped semantic Q3 result

The official integer-key medium left join is read on all 10,000,000 LHS rows with the complete 10,000 unique-key RHS. Exact streamed CSV oracle sums fixed decimal micros. DuckDB 1.4.3 projects the same query's counts and sums with known types, not a materialized full-width performance trial. Checks:

- **8,547,170 matched**, **500,220** left NULL keys, and **952,610** nonnull unmatched keys. All left rows remain represented once.
- Equality and null-safe-equality variants yield the same counts and exact sums on this cohort because the RHS key is never NULL. A separate authored single-null-pair native control distinguishes ordinary equality (joined v2 is NULL) from null-safe equality (v2=7); no actual cohort divergence is claimed.
- Change only the assignment of two distinct right payloads, exchanging them between distinct native-confirmed left occurrence IDs. Output count and column sums remain mathematically unchanged while the keyed relation is wrong. The separately measured publisher-style Double sums rounded to three places also match exactly (475042480.57; 423957578.77 in both). This is a counterfactual checker sensitivity control on two verified matched rows, not an engine error or claim of floating bit equivalence. No changes to source inputs.
- Other Join queries and the full 5 GB tier are outside this scoped result; this closes only this exact supervised 10M source gate and Q3 semantic/control evidence.

Reproduce check.py with DuckDB 1.4.3 and the complete admitted scratch source directory holding its MONITOR.json. Every file SHA is rechecked before reading. Q3.json is the deterministic semantic receipt; GENERATOR.json is a separate one-run resource/admission receipt. UPSTREAM.sha256 identifies readable official prerequisite artifacts used without redistribution.


Use the [pinned Debian R and data.table setup and benchmark archive](../h2o-native-grouped-definedness/README.md) used for the GroupBy evidence, including the same published H2O commit. Extract its exact _data/join-datagen.R to the prerequisites directory as join-generator.R, and duckdb/join-duckdb.py as join-duckdb.py if auditing source, with UPSTREAM.sha256. This packet includes no executable package or upstream generator. With guarded.py, supply the prerequisites directory and a new writable work location. The explicit --reserved-and-cleared flag acknowledges verified local resource headroom. A successful fresh run emits MONITOR.json in that work location. Use a pinned package environment for the semantic replay:

    set -o pipefail
    sha256sum -c SHA256SUMS
    python -B check.py /path/to/admitted/h2o/generated/joins | cmp - Q3.json
