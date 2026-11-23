# EA&B E7: independent native controls for hidden group roles and paired fold timing

An independent author, without prior project results, froze 18 finite authored cases and a literal standard-library oracle. The case manifest and inputs were used for the native evaluator, while labels and the author oracle were withheld until both the evaluator and its native predictions had been hashed. AUTHOR-SEALED.sha256 records the author artifact; CANDIDATE-FREEZE.sha256 records the separately frozen predictions. The labels are included here now that scoring is complete. The two exact methods are deliberately different; the hashes demonstrate integrity of the final bytes, not a claim of a public timestamp authority. No preceding holdout labels were used.

All 18 complete result families matched. Within the intentionally challenging synthetic slice:

- Eight cases use [native DuckDB grouping roles](https://duckdb.org/docs/lts/sql/query_syntax/grouping_sets) and LIMIT/OFFSET, native RANK, or native DENSE_RANK. Exact finite peer-band selection enumerates *sets of bags*, keeping every occurrence and the producer mask. Deriving that mask from visible nullness instead disagrees on all eight scoped full-family contracts. In three cases, projecting away masks strictly reduces the number of distinct legal bags; one projected answer can correspond to multiple provenance assignments even when the visible bag is well specified.
- Ten civil cases model one explicit rollback with two known integer offsets. Native DuckDB SQL derives allowed endpoint candidates under each offset and forms the nonnegative pair relation. Marginal earliest selection alone reproduces the entire admissible joint answer set in only three of these ten controls. In two cases an observed exact duration still leaves multiple distinct compatible instant pairs. This is a finite fold contract, not a test of any actual timezone library's default or a claim about a sampled region. [PEP 495](https://peps.python.org/pep-0495/) describes the real distinction between a repeated wall clock and its possible instants.

The author oracle literally enumerates alternative orderings/instants; the checked SQL route uses native stock grouping or exact offset inverses and rank gates. A single native LIMIT run only establishes membership; paired score-band combinatorics is what gives complete legal family. The wrong nullness and marginal shortcuts answer intentionally weaker contracts, not reported engine defects. These targeted fixtures do not estimate false-admission rates in a population and do not complete the broader independent E7 suite.

Replay with DuckDB 2.0.1 installed and ordinary Python:

    set -o pipefail
    sha256sum -c SHA256SUMS
    sha256sum -c AUTHOR-SEALED.sha256
    sha256sum -c CANDIDATE-FREEZE.sha256
    python -B check.py | cmp - PREDICTIONS.json
    python -B oracle.py | cmp - labels.json
    python -IB score.py | cmp - RESULT.json
