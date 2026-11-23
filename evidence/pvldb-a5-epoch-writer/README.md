# A5 native epoch writer cost pilot

This paired experiment times the writer side of the
E6/O2 scoped DuckDB price-overlay protocol.
The source is signed DuckDB 1.4.3 TPC-H DBGEN at SF1, with 6,001,215
lineitems. The two arms use the same price-overlay upsert and transaction.
The tracked arm classifies each write against the unchanged region-zero
join and advances the epoch for an in-scope nonzero change in that
transaction. Rollback and exact post-state checks run for each arm.

Five pairs use 96 native row keys per arm per pair, with 32 for each
transaction category. The median within-pair elapsed-time ratios
(tracked / untracked) were 2.05× for an in-scope nonzero write, 2.03×
for an out-of-scope nonzero write, and 1.12× for an in-scope zero write.
The source, overlay and epoch are in memory. These timings include
transaction execution on the shared server while the TPC-DS census
was running, and apply to a single writer.
The later sections record durable timings and the contract-source census.
Concurrent writer measurements remain open.

## Durable single-writer follow-up

The same pairing was repeated with persistent tables in one new DuckDB
file. Each write commits individually. A checkpoint before each arm
keeps table setup out of the timed write sequence. The WAL immediately
after 96 commits contained 19,464 bytes with epoch tracking and
15,752 bytes without tracking in all five pairs. The final overlay
was checked by closing and reopening the database. The run overlaps
the separate read-only ClickBench comparator on a shared server.

| Transaction class | Untracked median of medians | Tracked median of medians | Median paired ratio |
| --- | ---: | ---: | ---: |
| In-scope, nonzero | 6.724 ms | 15.852 ms | 1.999× |
| Outside scope, nonzero | 7.702 ms | 15.816 ms | 1.981× |
| In-scope, zero | 7.652 ms | 9.007 ms | 1.144× |

The timing ratio is computed within each paired repeat before taking
its median. `DURABLE-RESULT.json` and `DURABLE-INPUTS.sha256` bind this
follow-up. The original in-memory run's pre-execution entry points
remain available at the archived experiment commit `2deee69a3`.

```sh
python -IB run.py PINNED_TPCH_QUERY_JSON SIGNED_TPCH_EXTENSION
python -IB run.py PINNED_TPCH_QUERY_JSON SIGNED_TPCH_EXTENSION --durable-db NEW_DB_PATH
```

## Contract-source census

`python -B contract_inventory.py ..` enumerates the contract-source evidence
for the 305 benchmark queries, the original 108 cases, the later 138 cases,
and 58 distinct authored development replays. The native ordered-window
receipts establish automatic derivation for 116 queries. The remaining
189 benchmark queries retain their static features for further adjudication.
Original E7 cases each contain one explicit case statement. The later cases
share six panel definitions. `DEVELOPMENT-CONTRACTS.tsv` records the sources
and named clauses behind the 58 development entries. Twenty-two use a
declaration shared across the checks in their packet and 36 use per-case
statements. The inventory separately records clause counts and nonblank
replay source lines where a pinned entry point exists.

`CONTRACT-INVENTORY.json` keeps these scope and size measures separate from
the E6 instrumented timings. See the E6 ratio audit
for backup digests (O1), epoch and dependency checks (O2), and sparse intent
witnesses (O5).
