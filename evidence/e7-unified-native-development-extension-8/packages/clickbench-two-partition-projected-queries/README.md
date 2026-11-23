# E1 ClickBench: run three unchanged stock queries via a narrow authentic projection

The 100-object metadata audit
established 99,997,497 footer rows, not a full payload run. This follow-up
executes the first three actual unchanged DuckDB workload SELECTs on
**two** published partitions: existing complete hits_0 and the original
two compressed columns of hits_1. No claim about other partitions'
payloads or any broader suite. Workload source is the
[official stock file](https://github.com/ClickHouse/ClickBench/blob/main/duckdb/queries.sql),
SHA-256 checked in the runner against the previous exact stock revision.

For hits_1, condition public HTTP 206 requests on that object's ETag and
exact inclusive ranges; verify the earlier SHA of the complete footer.
Use the footer's original dictionary/data-page offsets and compressed
lengths to restore only AdvEngineID and ResolutionWidth into a local sparse
scratch file with the original logical length. Every selected source
chunk is present; all other payload spans are not admitted. This is
**not a valid general replacement for the original file**: do not query
any unsupported field or distribute the partial file. The native view
exposes only those two admitted columns. The added payload cost was
283,345 accepted compressed bytes plus a 65,536-byte suffix
(excluding headers and retries), versus a 174,965,044-byte original.
The first partition was already fully available, not reacquired.
The complete all-100 projection was not performed.

DuckDB 1.4.3 executes the exact stock Q1, Q2, Q3 strings over the two-part
view. PyArrow 26.0.1 independently decodes the physical integers,
checks lengths/types and computes exact scalar counters and an average
as an integer rational against the native result:

- Q1 count 2,000,000.
- Q2 nonzero AdvEngineID 17,486; 14,174 from hits_0 and 3,312 from hits_1.
- Q3 SUM(AdvEngineID) 88,574; count 2,000,000; exact average width
  2,818,304,017/2,000,000, with matching returned double 1409.1520085.

The payload validation independently counts nonnegative integer ranges
and seals admitted compressed offsets/lengths and bytes. No uploaded
payload, raw rows, unauthorized fields, native performance, result
from other stock queries, or broad exact AVG policy is inferred.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B capture.py DATASET-FOOTERS.json EMPTY_SCRATCH_DIR 1
    python3 -B check.py EMPTY_SCRATCH_DIR PART1.json STOCK_QUERIES_SQL FULL_HITS_0_PARQUET | cmp - RESULT.json

Reacquisition requires the same public object version access; reject
changed ETag, range, footer or chunk seal. Staging file is sparse only
locally and never included in the packet.
