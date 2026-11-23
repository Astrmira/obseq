# E5: native Deequ verification and constraint suggestions

The same 24 previously published keyed F7 cases and labels are used (12 legal, 12 illegal); this is matched retrospective evidence, not new blinded data. Spark DataFrames explicitly declare nullable longs for key/value and string for group. Native Deequ VerificationSuite evaluates the selected built-in id completeness/uniqueness check, adds an exact reference row count as a separate check, and separately evaluates the complete set of constraints produced by the native ConstraintSuggestionRunner using stock Rules.DEFAULT. The suggestion input is the source of the first lexically ordered non-empty case; candidate or label data do not train suggestions. This deliberately tiny profiling scope is not claimed to be sufficient for general domain inference. The fit-control evaluates that training table again.

| Configuration | False admits /12 illegal | False rejects /12 legal |
|---|---:|---:|
| Key constraints |11|1|
| Key constraints and reference row count |10|1|
| All stock suggestions learned on one source |0|12|

The key-constraint false reject is the empty legal table. The stock suggestion profile includes categorical group/value domains inferred from the single source, not the full 24-case population; accepting no illegal cases while rejecting every legal candidate is not success. In the fit control the native value-domain constraint alone failed on its own training source, which has nulls in the nullable value column. The four other suggestion checks passed on that source. This narrows the explanation to the generated value-domain rule on this runtime; no general root-cause claim about every Deequ version or training size.

Runtime: Java 21; the official [Deequ Maven POM](https://repo.maven.apache.org/maven2/com/amazon/deequ/deequ/2.0.15-spark-4.0/deequ-2.0.15-spark-4.0.pom) pins Spark 4.0.1. [Apache PySpark 4.0.1 release](https://pypi.org/project/pyspark/4.0.1/) source archive 434,204,896 bytes, SHA-256 9d1f22d994f60369228397e3479003ffe2dd736ba79165003246ff7bd48e2c73; extract only deps/jars and deps/bin (Scala path does not use Python Spark or pip). Deequ jar approx. 2 MB, verified against official Maven SHA-1 and also recorded SHA-256 cc51910a73b8de05f07353e48a167baa35232c46a9f7861a4e6fc290501703f2. Apache-2.0 for both Deequ and Spark; dependencies may carry their own licensing. No binaries distributed. Execution uses local[2], loopback and no UI.

```sh
sha256sum -c SHA256SUMS
python -B run.py "$RUNTIME_DIR" "$WRITABLE_SCRATCH" | cmp - RESULT.json
```
