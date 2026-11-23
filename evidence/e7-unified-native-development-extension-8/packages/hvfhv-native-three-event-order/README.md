# E3 F8: default civil-time conversion rejects feasible request/ride event chains

Use authentic November 2025 [NYC TLC High Volume FHV records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page), pinned identically to the earlier two-endpoint-duration pipeline. Here the downstream task is a three-event admissions check using the additional published request field, not a trip-duration constraint: admit iff there exists a UTC interpretation with request <= pickup <= dropoff. The inputs are stored zone-free microseconds. Compare to stock late-fold localization of each event separately, then enforce the same order. No actual UTC or service policy is imputed.

| Four-hour local pickup cohort | Rows | No feasible event chain | Feasible but rejected by default | Both sides of an illustrative 15-minute wait threshold possible |
|---|---:|---:|---:|---:|
| Nov 2 fold | 171,149 | 611 | 15,825 | 60,709 |
| Nov 9 ordinary Sunday | 123,660 | 546 | 0 | 0 |

For each of the 15,825 erroneous rejections under the existential contract there is exactly one legal ordered chain, including 15,201 meeting the stated wait threshold. Those already lacking any legal chain are not attributed to the default localization. The threshold result reports both possible labels, not a chosen performance score. No missing/out-of-date-guard endpoint exclusions occurred in these measured cohorts. The two date windows are fixed as 00–04 local; no hidden row selection or provider-name ranking.

Exact DuckDB 2.0.1 native ICU conversion, adjacent-hour expansion, roundtrip and ordered joins agree with separate PyArrow + Python ZoneInfo on all 30 reported cohort/provider/chain-multiplicity strata. The one-hour expansion is limited to the named contemporary dates and date guard. This is an additional downstream eligibility/SLA pipeline on the same established HVFHV source, not an additional independent data collection or estimate of observed service defects.

    set -e -o pipefail
    sha256sum -c SHA256SUMS
    python3 -B check.py PINNED_HVFHV_FILE PINNED_NEW_YORK_TZIF | cmp - RESULT.json

No raw event data distributed.
