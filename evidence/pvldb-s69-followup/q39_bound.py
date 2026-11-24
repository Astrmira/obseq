"""Recount order-independent binary64 bounds from exact Q39 group statistics."""

import argparse
import csv
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path


U_DEN = 1 << 53
HEADER = ("warehouse", "item", "month", "count", "sum", "squares", "min", "max")


def cv_bound(n, s, squares, lo, hi):
    """Return an exact rational relative bound and the exact squared CV."""
    if not (0 <= lo <= hi < 2**31 and 0 < n <= 2**16 and n * lo <= s <= n * hi):
        raise ValueError("Input outside the integer proof domain")
    if 48 * n * n * max(1, hi) >= U_DEN:
        raise ValueError("Mean error budget outside the proof domain")
    variance_numerator = n * squares - s * s
    if n == 1 or s == 0:
        if variance_numerator != 0 or lo != hi:
            raise ValueError("Invalid degenerate group statistics")
        return 0, 1, 0, 0
    r = hi - lo
    if r == 0:
        if variance_numerator != 0:
            raise ValueError("A constant group must have zero variance")
        return 0, 1, 0, 1
    if 2 * variance_numerator < n * r * r:
        raise ValueError("Group M2 below the contribution of its extrema")
    # The sum of local M2 correction errors is at most one unit roundoff
    # times this integer. See Q39-BOUND.md for the binary-tree argument.
    l0 = (18 * hi * r + 8 * r * r) * n * (n - 1) + 24 * (n - 1) * (hi * r + r * r)
    numerator = 4 * l0 * n + (8 * n + 16) * variance_numerator
    denominator = U_DEN * variance_numerator
    if 4 * numerator >= denominator:
        raise ValueError("Small-error condition for CV finalization violated")
    return numerator, denominator, n * variance_numerator, (n - 1) * s * s


def analyze(path, references=None):
    maximum, worst = (0, 1), None
    previous = None
    checked = rows = nulls = constant = passing = ambiguous = exact_ties = output_keys = 0
    max_n = max_input = 0
    min_gap = (1, 1)
    january_admitted = False
    with gzip.open(path, "rt", encoding="ascii", newline="") as stream:
        reader = csv.reader(stream)
        if tuple(next(reader)) != HEADER:
            raise ValueError("Bad statistics schema")
        for row in reader:
            w, i, month, n, s, sq, lo, hi = map(int, row)
            key = (w, i, month)
            if month not in (1, 2) or (previous is not None and key <= previous):
                raise ValueError("Stats must be unique and ordered by group key")
            if previous is None or key[:2] != previous[:2]:
                january_admitted = False
            previous = key
            rows += n
            checked += 1
            max_n = max(n, max_n)
            max_input = max(hi, max_input)
            bn, bd, cn, cd = cv_bound(n, s, sq, lo, hi)
            if cd == 0:
                nulls += 1
                continue
            if cn == 0:
                constant += 1
            if bn * maximum[1] > maximum[0] * bd:
                maximum, worst = (bn, bd), [w, i, month, n, s, sq, lo, hi]
            scale = cd * bd * bd
            # Squaring the positive endpoints avoids floating-point rounding in the proof.
            exact_ties += cn == cd
            gap = abs(cn - cd)
            if gap and gap * min_gap[1] < min_gap[0] * cd:
                min_gap = gap, cd
            if cn > cd:
                if references is not None and (w, i) in references:
                    references[w, i][month] = (Fraction(s, n), Fraction(cn, cd), Fraction(bn, bd))
                passing += 1
                ambiguous += cn * (bd - bn)**2 <= scale
                if month == 1:
                    january_admitted = True
                elif january_admitted:
                    output_keys += 1
            else:
                ambiguous += cn * (bd + bn)**2 > scale
    upper = Fraction(*maximum)
    return {
        "groups": checked, "inventory_rows": rows, "null_or_zero_mean_groups": nulls,
        "constant_nonzero_mean_groups": constant, "admitted_month_groups": passing,
        "threshold_ambiguous_groups": ambiguous, "exact_threshold_ties": exact_ties,
        "paired_output_keys": output_keys, "max_group_size": max_n, "max_quantity": max_input,
        "max_cv_relative_bound_fraction": str(upper),
        "max_cv_relative_bound": float(upper),
        "worst_group": worst, "min_nonzero_cv_squared_threshold_gap": str(Fraction(*min_gap)),
    }


def verify_native(stats, directory, fingerprints):
    """Verify the original exact keys and projections under the derived bounds."""
    receipt = {}
    for name, digest in sorted(fingerprints.items()):
        payload = (directory / name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != digest:
            raise ValueError(f"Unexpected Q39 raw shard: {name}")
        for line in payload.splitlines():
            row = json.loads(line)
            key = tuple(row["key"])
            if key in receipt:
                raise ValueError("Duplicate Q39 output key")
            receipt[key] = row
    refs = {key: {} for key in receipt}
    summary = analyze(stats, refs)
    if len(receipt) != summary["paired_output_keys"] or any(set(ref) != {1, 2} for ref in refs.values()):
        raise ValueError("The archived paired keys differ from the exact derived keys")

    def accepts(key, vector):
        if key not in refs:
            return False
        for month in (1, 2):
            mean, cv2, radius = refs[key][month]
            observed_mean, observed_cv = map(Fraction, vector[2 * (month - 1):2 * month])
            if abs(observed_mean - mean) > mean * Fraction(3, U_DEN):
                return False
            if observed_cv < 0 or not cv2 * (1 - radius)**2 <= observed_cv**2 <= cv2 * (1 + radius)**2:
                return False
        return True

    accepted = {"t1": 0, "t4": 0}
    for key, row in receipt.items():
        exact = [v for month in (1, 2) for v in refs[key][month][:2]]
        if list(map(Fraction, row["fractions"])) != exact:
            raise ValueError(f"Archived and independently recomputed exact values differ: {key}")
        for arm in accepted:
            accepted[arm] += accepts(key, [float.fromhex(v) for v in row[arm]])
    if any(count != len(receipt) for count in accepted.values()):
        raise ValueError("A native projection exceeded the analytic radius")
    w, i = next(key for key in sorted(receipt) if (key[0], key[1] + 1) not in receipt)
    base = [float.fromhex(v) for v in receipt[w, i]["t4"]]
    near = base.copy()
    near[0] = float.fromhex(receipt[w, i]["t1"][0]) * (1 + 5e-7)
    large = base.copy()
    large[0] *= 2
    controls = {
        "M1_exact_key_plus_one": accepts((w, i + 1), base),
        "M5_near_float": accepts((w, i), near),
        "large_float_control": accepts((w, i), large),
    }
    if any(controls.values()):
        raise ValueError("A frozen Q39 negative control was accepted")
    summary["archived_projection_check"] = {
        "rows_accepted": accepted, "rows_per_arm": len(receipt),
        "mutant_location": [w, i], "mutants_accepted": controls, "M5_hex": near[0].hex(),
    }
    return summary


def extract(db_path, output):
    import duckdb

    if duckdb.__version__ != "1.4.3":
        raise ValueError("Expected the pinned Q39 DuckDB release")
    con = duckdb.connect(str(db_path), read_only=True, config={"threads": 1})
    if con.execute("SELECT typeof(inv_quantity_on_hand) FROM inventory LIMIT 1").fetchone() != ("INTEGER",):
        raise ValueError("Integer AVG proof requires the stock inventory quantity type")
    cur = con.execute("""
        SELECT w_warehouse_sk, i_item_sk, d_moy,
               count(inv_quantity_on_hand), sum(inv_quantity_on_hand),
               sum(inv_quantity_on_hand::HUGEINT * inv_quantity_on_hand),
               min(inv_quantity_on_hand), max(inv_quantity_on_hand)
        FROM inventory
        JOIN item ON inv_item_sk = i_item_sk
        JOIN warehouse ON inv_warehouse_sk = w_warehouse_sk
        JOIN date_dim ON inv_date_sk = d_date_sk
        WHERE d_year = 2001 AND d_moy IN (1, 2)
        GROUP BY w_warehouse_name, w_warehouse_sk, i_item_sk, d_moy
        HAVING count(inv_quantity_on_hand) > 0
        ORDER BY w_warehouse_sk, i_item_sk, d_moy
    """)
    with output.open("xb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
        stream.write((",".join(HEADER) + "\n").encode("ascii"))
        while batch := cur.fetchmany(16_384):
            stream.write("".join(",".join(map(str, row)) + "\n" for row in batch).encode("ascii"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stats", type=Path)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--native-directory", type=Path)
    parser.add_argument("--native-digests", type=Path)
    args = parser.parse_args()
    if args.database:
        extract(args.database, args.stats)
    if (args.native_directory is None) != (args.native_digests is None):
        parser.error("Supply both native receipt options or neither")
    if args.native_directory:
        fingerprints = json.loads(args.native_digests.read_bytes())["source_parts_sha256"]
        result = verify_native(args.stats, args.native_directory, fingerprints)
    else:
        result = analyze(args.stats)
    print(json.dumps(result, indent=2, sort_keys=True))
