# EA&B E5: Great Expectations search vs full-field token contract

Official GX [expectation gallery](https://greatexpectations.io/expectations/expect_column_values_to_match_regex/) expressly says the regex can match anywhere. Official [1.25.0 PyPI release](https://pypi.org/project/great-expectations/1.25.0/) supplied the wheel matched to metadata in artifact.json. Pinned publisher source commit f24de74468d697a8ca074fe9e91e0661c4cd89a2; the installed Pandas metric calls `str.contains`, and its SQLAlchemy metric delegates to a dialect expression. This is a tested policy mismatch and stock repair, not a GX defect.

PLAN.json was digested before the first run. Per fixture source, a legal value is exactly three ASCII uppercase letters, one hyphen and exactly two ASCII digits, without normalization. The independent Python oracle uses character bounds and length rather than any regex. The 12 distinct authored, non-null values include positive controls, prefix/suffix content, LF/CRLF and Unicode lookalikes. No native input adaptation beyond typed in-memory table materialization; SQLite insertion round-trips exact strings. Stock result labels trace to partial unexpected values, with a complete count check on this small fixture. Default mostly is unchanged. The 12-row batch fails under every arm; only the separate matched legal-only/plus-LF batch demonstrates a false pass.

Pandas and SQLAlchemy SQLite agree: search admits 5/10 faults; caret/dollar anchoring admits only the final LF, whereas \A and \Z admit none and reject neither positive. Python dollar permits a match before a terminal newline. Strongest fair baseline is the strict-anchor built-in, not the documented search misconfiguration. Other regex engines can interpret or reject these anchors differently. There is no workload prevalence, standalone novelty, or evidence for other GX backends. Installation and databases are local only; package dependencies/deps and wheels not part of the publication packet.

Install wheel-only with dependency pins in requirements.txt in a fresh scratch target named deps inside your replay directory. From this packet directory:
```sh
set -o pipefail
sha256sum -c SHA256SUMS
python3 -IB check.py /path/to/replay-directory | cmp - result.json
```
