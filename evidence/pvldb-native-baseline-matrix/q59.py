"""Independently reconstruct the TPC-DS Q59 window from source-table values."""

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import runpy
import sys

import duckdb
import pyarrow as pa


DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
WINDOW = 100


def weekly_sales(db, dates):
    """Use Arrow for exact batch subtotals and Python for the weekly rollup."""
    if not dates:
        return {}, 0
    totals = defaultdict(lambda: [None] * len(DAYS))
    scanned = 0
    reader = db.execute("""
        SELECT ss_sold_date_sk, ss_store_sk, ss_sales_price
        FROM store_sales WHERE ss_sold_date_sk BETWEEN ? AND ?
    """, [min(dates), max(dates)]).fetch_record_batch(250_000)
    for batch in reader:
        scanned += batch.num_rows
        subtotals = pa.Table.from_batches([batch]).group_by(
            ["ss_sold_date_sk", "ss_store_sk"], use_threads=False
        ).aggregate([("ss_sales_price", "sum")])
        for day, store, price in zip(*(column.to_pylist() for column in subtotals.columns)):
            if day not in dates or store is None:
                continue
            week, weekday = dates[day]
            values = totals[week, store]
            if price is not None:
                values[weekday] = (values[weekday] or Decimal(0)) + price
    return totals, scanned


def ratio(left, right):
    # The SQL expression divides two DECIMAL sums and returns a binary64.
    if left is None or right is None:
        return None
    if right == 0:
        return "NaN" if left == 0 else math.copysign(math.inf, float(left))
    return float(left) / float(right)


def key_order(key):
    return tuple((cell is not None, cell) for cell in key)


def reference(db):
    date_rows = db.execute("SELECT d_date_sk, d_week_seq, d_month_seq, d_day_name FROM date_dim").fetchall()
    stores = dict((sk, (name, ident)) for sk, name, ident in db.execute(
        "SELECT s_store_sk, s_store_name, s_store_id FROM store"
    ).fetchall())
    first, second = (Counter(week for _, week, month, _ in date_rows if lo <= month <= hi)
                     for lo, hi in ((1212, 1223), (1224, 1235)))
    relevant = first.keys() | second.keys()
    dates = {sk: (week, DAYS.index(day.strip())) for sk, week, _, day in date_rows if week in relevant}
    weeks, scanned = weekly_sales(db, dates)
    targets = defaultdict(list)
    for (week, sk), values in weeks.items():
        if week in second and sk in stores and stores[sk][1] is not None:
            targets[week, stores[sk][1]].append(values)

    counts = defaultdict(Counter)
    for (week, sk), values in weeks.items():
        if week not in first or sk not in stores:
            continue
        name, ident = stores[sk]
        for peer in targets[week + 52, ident]:
            payload = tuple(map(ratio, values, peer))
            counts[name, ident, week][payload] += first[week] * second[week + 52]
    remaining = WINDOW
    bands = []
    for key in sorted(counts, key=key_order):
        available = sum(counts[key].values())
        quota = min(remaining, available)
        bands.append((key, quota, counts[key]))
        remaining -= quota
        if not remaining:
            break
    return bands, scanned


def accepts(bands, rows):
    if len(rows) != sum(quota for _, quota, _ in bands):
        return False
    offset = 0
    for key, quota, capacity in bands:
        observed = Counter()
        for row in rows[offset:offset + quota]:
            if row[:3] != key:
                return False
            observed[tuple("NaN" if isinstance(x, float) and math.isnan(x) else x for x in row[3:])] += 1
        if observed - capacity:
            return False
        offset += quota
    return True


def evaluate(database, query_file, verifier=None):
    query = dict((int(k), v) for k, v in json.loads(query_file.read_bytes())["queries"])[59]
    relation, separator, _ = query.strip().rstrip(";").rpartition("ORDER BY")
    if not separator:
        raise ValueError("frozen Q59 lacks its final ORDER BY")
    with duckdb.connect(str(database), read_only=True,
                        config={"threads": "4", "memory_limit": "10GB"}) as db:
        bands, scanned = reference(db)
        native = db.execute(query).fetchall()
        cases = {"native": native}
        for direction in ("ASC", "DESC"):
            peer_order = ", ".join(f"{i} {direction} NULLS LAST" for i in range(4, 11))
            cases[f"projected_peer_sort_{direction.lower()}"] = db.execute(f"""
                SELECT * FROM ({relation}) ORDER BY 1 NULLS FIRST, 2 NULLS FIRST,
                       3 NULLS FIRST, {peer_order} LIMIT {WINDOW}
            """).fetchall()
    cases["shape_negative"] = native[1:]
    mutated = native.copy()
    pos, column = next((i, j) for i, row in enumerate(native) for j in range(3, 10)
                       if isinstance(row[j], float) and math.isfinite(row[j]))
    key = mutated[pos][:3]
    capacity = next(capacity for band_key, _, capacity in bands if band_key == key)
    changed = list(mutated[pos])
    changed[column] = 1 + max(abs(row[column - 3]) for row in capacity
                              if isinstance(row[column - 3], float) and math.isfinite(row[column - 3]))
    mutated[pos] = tuple(changed)
    cases["same_count_invalid_ratio"] = mutated
    decisions = {arm: {"accepted": accepts(bands, rows), "observed_rows": len(rows)}
                 for arm, rows in cases.items()}
    facts = {
        "source_contract": "independent exact batch sales sums, source-store pairing and date-dimension multiplicity",
        "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        "sales_rows_scanned": scanned,
        "required_rows": sum(quota for _, quota, _ in bands),
        "selected_peer_bands": len(bands),
        "cutoff_peer_size": sum(bands[-1][2].values()),
        "cutoff_peer_output_rows": bands[-1][1],
        "position_differences_ascending_vs_descending": sum(
            a != b for a, b in zip(cases["projected_peer_sort_asc"], cases["projected_peer_sort_desc"])
        ),
        "decisions": decisions,
    }
    expected = [True, True, True, False, False]
    if [row["accepted"] for row in decisions.values()] != expected:
        raise ValueError(f"Q59 independent source comparison disagrees: {facts}")
    if verifier is not None:
        with duckdb.connect(str(database), read_only=True, config={"threads": "4"}) as db:
            schema = db.execute(f"SELECT * FROM ({query.strip().rstrip(';')}) LIMIT 0").fetch_arrow_table().schema
            inputs = {arm: pa.Table.from_pylist(
                [dict(zip(schema.names, row, strict=True)) for row in rows], schema=schema
            ) for arm, rows in cases.items()}
            results = verifier(db, query, inputs)
        facts["typed_window_verdicts"] = {arm: row["accepted"] for arm, row in results.items()}
        if any(facts["typed_window_verdicts"][arm] != row["accepted"] for arm, row in decisions.items()):
            raise ValueError(f"Q59 typed verifier disagrees with the independent source reference: {facts}")
    entries = [(arm, cases[arm], decisions[arm]["accepted"]) for arm in
               ("projected_peer_sort_asc", "projected_peer_sort_desc", "shape_negative")]
    return native, entries, facts


def load_verifier(path):
    sys.path.insert(0, str(path.resolve().parent))
    try:
        return runpy.run_path(str(path))["call"]
    finally:
        sys.path.pop(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query_file", type=Path)
    parser.add_argument("database", type=Path)
    parser.add_argument("--verify-window", type=Path, help="score the same arms with verify_windows.py")
    args = parser.parse_args()
    _, _, receipt = evaluate(args.database, args.query_file,
                             load_verifier(args.verify_window) if args.verify_window else None)
    print(json.dumps({"duckdb": duckdb.__version__, "pyarrow": pa.__version__, **receipt},
                     indent=2, sort_keys=True))
