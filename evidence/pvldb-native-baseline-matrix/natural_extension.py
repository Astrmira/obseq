"""Score the remaining E9 release families from sealed native observations."""

import csv
from decimal import Decimal
import json
import re

from later import token
from natural import main


def historical(read):
    family = "group-collation-type"
    packet = "e9-native-historical-f9-duckdb-cli"
    ref = [[name, "INTEGER", 1] for name in ("binary", "nocase_group", "nocase_plain")]
    for release in ("0.8.1", "0.9.1"):
        rows = [[name, kind, int(value)] for name, kind, value in csv.reader(read(packet, release + ".csv").splitlines())]
        yield family, release, ref, rows, ("text", "text", "int"), (0,), rows == ref

    family = "insert-decimal-export"
    packet = "e9-native-historical-o4-decimal-export"
    reference = [["2.710000000000000000"], ["3.140000000000000000"]]
    for release in ("1.0.0", "1.1.0"):
        raw = read(packet, release + ".raw")
        values = [[value] for value in re.findall(r"^INSERT INTO .+ VALUES\(([-.0-9]+)\);$", raw, re.M)]
        if len(values) != 2 or raw.splitlines()[:2] != [r[0] for r in reference]:
            raise ValueError("changed decimal export receipt")
        legal = [Decimal(r[0]) for r in values] == [Decimal(r[0]) for r in reference]
        yield family, release, reference, values, ("text",), (), legal

    family = "upsert-state-and-receipt"
    packet = "e9-native-historical-f5-upsert-effects"
    reference = [["keep", "kept"], ["clear", None], ["returning_id", "1"], ["stored_id", "1"], ["stored_value", "30"]]
    for release in ("1.2.1", "1.2.2", "1.4.0"):
        keep, clear, initial, returning, stored = list(csv.reader(read(packet, release + ".raw").splitlines()))
        if initial != ["1"] or [keep[0], clear[0], stored[0]] != ["keep", "clear", "stored"]:
            raise ValueError("changed native upsert trace")
        def nullable(v):
            return None if v == "NULL" else v
        rows = [["keep", nullable(keep[2])], ["clear", nullable(clear[2])],
                ["returning_id", returning[0]], ["stored_id", stored[1]], ["stored_value", stored[2]]]
        yield family, release, reference, rows, ("text", "text"), (0,), rows == reference

    family = "copy-summary-bound"
    packet = "e9-native-f6-parquet-claimed-stats"
    for release in ("1.5.4", "1.5.5"):
        copy, footer, minority = list(csv.reader(read(packet, release + ".raw").splitlines()))
        minimum, maximum = (re.search(rf"\b{field}=([0-9.]+)", copy[4])[1] for field in ("min", "max"))
        if footer != ["footer", "5.0000", "8.0000", "3"] or minority != ["minority", "100"]:
            raise ValueError("changed independent Parquet footer")
        reference = [[float(footer[1]), float(footer[2])]]
        rows = [[float(minimum), float(maximum)]]
        yield family, release, reference, rows, ("float", "float"), (), rows == reference


def numeric_text_and_predicates(read):
    packet = "e9-native-f10-geos-precision-measure"
    for row in read(packet, "RESULT.json"):
        measure = row["positive_grid_last_m"]
        reference, rows = [[7.0]], [[None if measure == "NaN" else measure]]
        yield ("precision-ring-measure", row["version"].split("-", 1)[0], reference, rows,
               ("float",), (), row["nan_m_count"] == 0 and measure == 7.0)

    packet = "e9-native-f7-pandas-rolling-std"
    for release in ("1.4.1", "1.5.0"):
        data = read(packet, release + ".json")["arms"]
        reference = [[order, 0.0] for order in sorted(data)]
        rows = [[order, data[order]["full"]["std"]] for order in sorted(data)]
        if any(item["full"]["exact_variance"] != "0" for item in data.values()):
            raise ValueError("changed constant-window variance reference")
        yield "rolling-variance-cancellation", release, reference, rows, ("text", "float"), (0,), rows == reference

    packet = "e9-native-f9-nullable-cumulative-type"
    n = 9007199254740993
    expected = {"cummax": [n, None, n], "cummin": [n, None, 1], "cumprod": [n, None, n], "cumsum": [n, None, n + 1]}
    reference = [[op, "Int64", token(values)] for op, values in sorted(expected.items())]
    for release in ("3.0.3", "3.1.0"):
        data = read(packet, release + ".json")["observations"]["int_boundary|dropna=True"]
        rows = [[op, kind, token(values)] for op, (kind, values) in sorted(data.items())]
        yield "nullable-cumulative-group-type", release, reference, rows, ("text", "text", "text"), (0,), rows == reference

    packet = "e9-native-f2-polars-unnest-sibling-null"
    reference = [[1, 100, None], [1, 100, "hi"]]
    for release in ("0.15.15", "0.15.16"):
        data = json.loads(read(packet, release + ".raw"))
        if data["typ"] != data["inferred"]:
            raise ValueError("changed nested-data schema controls")
        yield "nested-sibling-null-explode", release, reference, data["typ"], ("int", "int", "text"), (), data["typ"] == reference

    packet = "e9-native-f1-styler-index-representation"
    for release in ("2.0.1", "2.1.0"):
        data = sorted(read(packet, release + ".json")["rendered"].items())
        reference = [[int(key), int(key)] for key, _ in data]
        rows = [[int(key), int(value)] for key, value in data]
        yield "styler-index-representation", release, reference, rows, ("int", "int"), (0,), rows == reference

    packet = "e9-native-f10-valid-segment-intersection"
    for release in ("3.10.2", "3.10.3"):
        data = json.loads(read(packet, release + ".raw"))
        yield "valid-segment-intersection", release, [[1]], [[data["direct"]]], ("int",), (), data["direct"] == 1


def supplemental(read):
    packet = "e9-supplemental-f4-polars-cached-lineage"
    for version, cases in sorted(read(packet, "RESULT.json").items()):
        reference, rows = [], []
        for i, row in enumerate(cases):
            reference.extend([i, *values] for values in row["expected"])
            rows.extend([i, *values] for values in row["engines"]["in-memory"]["observed"])
        yield "polars-cache-lineage", version, reference, rows, ("int", "text", "int"), (), rows == reference

    packet = "e9-supplemental-f7-pandas-rolling-future-window"
    data = read(packet, "RESULT.json")
    reference = [data["oracle"]["expected"]]
    for row in data["releases"]:
        if row["version"] not in {"2.3.3", "3.0.0"}:
            continue
        rows = [row["values"]["future_outlier"]]
        yield ("pandas-historical-rolling-moments", row["version"], reference, rows,
               ("float", "float"), (), all(row["matches_independent_oracle"]["future_outlier"]))

    packet = "e9-supplemental-o3-native-categorical-topk"
    for version, cohort in sorted(read(packet, "RESULT.json")["results"].items()):
        for row in cohort["authored"]:
            reference = [[value] for value in sorted(row["selected_categories"])]
            rows = [[value] for value in row["series_selected"]]
            arm = version + "/" + ",".join(row["input"])
            yield "polars-categorical-series-topk", arm, reference, rows, ("text",), (), row["series_legal"]

    packet = "e9-supplemental-o3-polars-group-representative"
    for version in ("1.44.2", "2.0.0"):
        for mode, report in sorted(read(packet, version + ".json")["reports"].items()):
            for i, row in enumerate(report["cases"]):
                reference = [[group, *rep] for group, rep in enumerate(min(row["legal"]))]
                rows = [[group, *rep] for group, rep in enumerate(row["observed"])]
                yield ("polars-grouped-coupled-representative", f"{version}/{mode}/{i}", reference, rows,
                       ("int", "int", "int"), (0,), not row["outside"])


def cases(read):
    yield from historical(read)
    yield from numeric_text_and_predicates(read)
    yield from supplemental(read)


if __name__ == "__main__":
    main(cases)
