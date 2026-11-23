# E4/E5: a native Parquet read can erase distinct NULL and IEEE NaN roles

The complete digest-pinned November 2025 Yellow TLC Airport_fee field
contains 4,181,444 physical binary64 rows, 1,014,740 genuine NULLs,
and zero valid NaNs by typed Arrow observation. This does not assert
anything about physical fare correctness. The control is deliberately
authored: only the first selected original NULL becomes a valid
binary64 NaN in a new Parquet file. Exact original row identities,
all other values, schema and row count remain fixed. The native source
is not modified.

The frozen first consecutive 2,048-row panel is entirely NULL. In a
separate follow-on mixed panel, add the first 1,024 defined source
rows to the first 1,024 selected NULL rows, preserving original IDs.
That panel's only changed cell is again NULL→valid NaN. Native Arrow
validity and DuckDB NULL/isnan counts distinguish the first pair;
mixed DuckDB COUNT(amount) is 1,024→1,025 and SUM changes from finite
to NaN. Thus the change can matter even when most of the paired
table is unchanged and neither version has lost row identity.

For both panels, Pandas 2.2.3 native read_parquet with default NumPy
backing emits identical isna roles, and assert_frame_equal accepts.
With the exact same Parquet engine, dtype_backend='pyarrow' and
'numpy_nullable' preserve the new valid observation and reject.
Native Polars read_parquet and comparison also distinguish the tested
first pair by explicit null and NaN counts. All tested unchanged
frame controls pass. This pinpoints ingestion over a lossy value
projection: removing tolerance from an equality check after
conflation cannot restore the input distinction. Starting from
the [Pandas native backend options](https://pandas.pydata.org/pandas-docs/version/2.2/reference/api/pandas.read_parquet.html)
and the [Arrow validity representation](https://arrow.apache.org/docs/format/Columnar.html#validity-bitmaps),
bind the validity mask separate from present payload representation
whenever the application contract distinguishes them.

No claim that using a default missingness quotient is generally wrong,
that Pandas cannot represent the distinction, or that source data
contained the injected behavior, raw data or financial analysis.
Exact NaN payload-bit comparisons and performance outside scope.

    set -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B run.py PINNED_NOVEMBER_TLC_PARQUET SCRATCH_DIR | cmp - RESULT.json

Initial plan/code identities are recorded in ORIGINAL-PRE.sha256;
the later mixed control and current code resolve REPLAY.sha256.
Requires the explicitly recorded native versions. No raw rows exported.
