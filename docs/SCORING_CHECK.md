# Scoring check

`scripts/check_scoring.py` recomputes S1, S2, S3, the score, the tier and the confidence for every row in
[sample/public-safe-sample.csv](../sample/public-safe-sample.csv). It uses the as-built formulas in
[clay/formulas.md](../clay/formulas.md). CI runs it on every push.

```bash
python scripts/check_scoring.py            # fails on a formula mismatch
python scripts/check_scoring.py --strict   # also fails on a documentation gap
python -m pytest -q
```

## What it can and cannot check

- It checks score, tier and confidence exactly.
- It checks the ICP gate only in part. The CSV has no employee count, so a REVIEW caused by size cannot be confirmed.
- It treats S1 Level as present whenever S1 Final is present. The CSV has S1 Final only.
- It takes Evidence Age from the CSV. It does not recompute it from dates.

## Result on the 2026-10-26 sample

**Formula mismatches: 0.** Every score, tier and confidence in the CSV matches the formulas.

**Documentation gaps: 3.** In these rows the formulas and the CSV agree, but the written rules suggest a different
outcome. The data has not been changed.

| Account | CSV | What the docs suggest | Why they differ |
|---|---|---|---|
| Elective | Gate REVIEW, tier HIGH | Resolve the gate before research | The gate says "verify before spending research credits". The Claygent run condition only skips FAIL, and the Tier formula ignores REVIEW. Entity is PARTIAL and business model is blank. QA put it on hold, but the tier stays HIGH. |
| dormakaba | Gate REVIEW, tier HIGH | Resolve the gate before research | Same cause. Entity is PARTIAL (Americas subsidiary) and business model is UNKNOWN. |
| Sundayy | Entity MISMATCH, tier LOW | REVIEW | SCORING.md says REVIEW when "the enriched record is a different company". The Tier formula checks "no S1" first, so a row that was never researched becomes LOW. It is not a customer and did not fail the gate, so EXCLUDED does not apply either. |

## Options, not applied

1. Add `{{ICP Gate}} === "REVIEW"` to the Tier formula, before the score checks, so an unresolved gate cannot be HIGH.
2. Or keep the formula and change the docs: say a gate REVIEW is resolved by the human QA pass, not by the tier.
3. Move the `Entity Check === "MISMATCH"` test above `!{{S1 Level}}`, so Sundayy becomes REVIEW. Or change the SCORING.md tier table to say an unresearched mismatch is LOW.

Either way, the formula, the docs and the CSV should then be updated together.
