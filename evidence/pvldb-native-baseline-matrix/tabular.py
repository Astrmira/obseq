"""Reusable native E5 table comparators with an explicit value carrier."""

import datacompy
import numpy as np
import pandas as pd
import polars as pl
from polars.testing import assert_frame_equal as pl_equal


VERSIONS = {"pandas": pd.__version__, "polars": pl.__version__,
            "datacompy": datacompy.__version__, "numpy": np.__version__}
PINNED = {"pandas": "2.2.3", "polars": "1.31.0", "datacompy": "0.16.8", "numpy": "2.2.6"}
PANDAS = {"int": "Int64", "uint": "UInt64", "float": "Float64", "bool": "boolean", "text": "object"}
POLARS = {"int": pl.Int64, "uint": pl.UInt64, "float": pl.Float64, "bool": pl.Boolean, "text": pl.String}


def frames(rows, kinds):
    names = [f"f{i}" for i in range(len(kinds))]
    fields = [[row[i] for row in rows] for i in range(len(kinds))]
    p = pd.DataFrame({name: pd.Series(field, dtype=PANDAS[kind])
                      for name, field, kind in zip(names, fields, kinds)})
    q = pl.DataFrame({name: pl.Series(field, dtype=POLARS[kind])
                      for name, field, kind in zip(names, fields, kinds)})
    original = [tuple(row) for row in rows]
    normal_p = [tuple(None if pd.isna(value) else value for value in row)
                for row in p.itertuples(index=False, name=None)]
    if normal_p != original or q.rows() != original:
        raise ValueError("baseline carrier changed source values")
    return p, q


def compare_datacompy(lhs, rhs, *, keys=()):
    fields = [f"f{i}" for i in keys]
    if not fields:
        fields = ["__position"]
        lhs_id = lhs.assign(__position=np.arange(len(lhs), dtype=np.int64))
        rhs_id = rhs.assign(__position=np.arange(len(rhs), dtype=np.int64))
    else:
        lhs_id, rhs_id = lhs, rhs
        for frame in (lhs, rhs):
            if frame[fields].isna().any().any() or frame.duplicated(fields).any():
                return None, "inapplicable_natural_key"
    try:
        return bool(datacompy.Compare(lhs_id, rhs_id, join_columns=fields).matches()), None
    except Exception as exc:
        return None, type(exc).__name__


def compare(reference, candidate, kinds, *, keys=()):
    if VERSIONS != PINNED:
        raise ValueError(f"unexpected E5 environment: {VERSIONS}")
    lhs, lpl = frames(reference, kinds)
    rhs, rpl = frames(candidate, kinds)
    verdicts, errors = {}, {}
    for name, fn, operands, opts in (
        ("pandas_default", pd.testing.assert_frame_equal, (lhs, rhs), {}),
        ("pandas_check_like", pd.testing.assert_frame_equal, (lhs, rhs), {"check_like": True}),
        ("pandas_dtype_relaxed", pd.testing.assert_frame_equal, (lhs, rhs), {"check_dtype": False}),
        ("polars_default", pl_equal, (lpl, rpl), {}),
        ("polars_ignore_order", pl_equal, (lpl, rpl), {"check_row_order": False}),
    ):
        try:
            fn(*operands, **opts)
        except AssertionError:
            verdicts[name] = False
        except Exception as exc:
            verdicts[name], errors[name] = None, type(exc).__name__
        else:
            verdicts[name] = True
    verdicts["datacompy_keyed"], error = compare_datacompy(lhs, rhs, keys=keys)
    if error is not None:
        errors["datacompy_keyed"] = error
    return {"tool_verdicts": verdicts, "tool_errors_or_na": errors,
            "key_mode": "declared_natural" if keys else "physical_position"}
