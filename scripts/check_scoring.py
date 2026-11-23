"""Recompute score, tier and confidence for the sample CSV and report mismatches.

The rules are the as-built Clay formulas in clay/formulas.md (Group 2 and Group 4).
Standard library only.

    python scripts/check_scoring.py                      # exit 1 on a formula mismatch
    python scripts/check_scoring.py --strict             # also exit 1 on a documentation gap

Two kinds of finding:

- formula mismatch: a CSV cell differs from what the formulas produce. This means
  the data or the formulas doc is wrong.
- documentation gap: the formulas and the CSV agree, but the plain-English rules in
  docs/SCORING.md or the gate wording say something different. These are listed,
  not fixed. See docs/SCORING_CHECK.md.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

DEFAULT_CSV = Path(__file__).resolve().parents[1] / "sample" / "public-safe-sample.csv"

S1_POINTS = {"EXACT_CORROBORATED": 50, "EXACT_SINGLE": 40, "EXPERIENCE_ONLY": 25,
             "AMBIGUOUS_VERSION": 20, "PLATFORM_FALSE_POSITIVE": 0, "NONE": 0}
S2_POINTS = {"ACTIVE": 30, "LIKELY": 20, "WEAK": 10, "COMPLETED": 0, "NONE": 0}
S3_POINTS = {"ATTESTED": 20, "REGULATED": 15, "ENTERPRISE_OR_GOV_BUYERS": 10, "GENERAL": 5, "NONE": 0}
WEAK_S1 = {"EXPERIENCE_ONLY", "AMBIGUOUS_VERSION", "PLATFORM_FALSE_POSITIVE", "NONE"}
SERVICES = {"IT_SERVICES_OR_STAFFING", "PROFESSIONAL_SERVICES"}

CHECKED = ["s1_score", "s2_score", "s3_score", "signal_score", "tier", "evidence_confidence"]


def _num(v) -> float:
    """JavaScript Number(): empty string is 0, junk is NaN."""
    v = "" if v is None else str(v).strip()
    if v == "":
        return 0.0
    try:
        return float(v)
    except ValueError:
        return float("nan")


def gate_floor(r: dict) -> str:
    """ICP Gate without the employee-count test (the CSV has no employee count).

    Returns FAIL or REVIEW when the formula must give that, else PASS_OR_REVIEW.
    """
    model = (r.get("business_model") or "").strip()
    if model in SERVICES:
        return "FAIL"
    if r.get("entity_check") in ("MISMATCH", "NOT_FOUND") or not model or model == "UNKNOWN":
        return "REVIEW"
    return "PASS_OR_REVIEW"


def compute(r: dict) -> dict:
    """Apply the Group 4 formulas to one row. Inputs are taken from the CSV as Clay would."""
    s1_final = (r.get("s1_final") or "").strip()
    s1_level = s1_final  # the CSV has S1 Final only; S1 Level is set whenever S1 Final is
    s2_cat = (r.get("s2_category") or "").strip()
    s3_cat = (r.get("s3_category") or "").strip()
    age = _num(r.get("evidence_age_days"))

    if not s1_final:
        s1 = ""
    else:
        b = S1_POINTS.get(s1_final, 0)
        s1 = 0 if b == 0 else 10 if age > 365 else min(b, 25) if age > 120 else b
    s2 = "" if not s2_cat else S2_POINTS.get(s2_cat, 0)
    s3 = "" if not s3_cat else S3_POINTS.get(s3_cat, 0)
    score = max(1, int(_num(s1) + _num(s2) + _num(s3))) if s1_level else ""

    if r.get("suppressed") == "YES" or r.get("icp_gate") == "FAIL":
        tier = "EXCLUDED"
    elif not s1_level:
        tier = "LOW"
    elif r.get("contradiction") == "YES" or r.get("entity_check") == "MISMATCH":
        tier = "REVIEW"
    elif _num(score) >= 75:
        tier = "MEDIUM" if _num(s1) < 20 else "HIGH"
    elif _num(score) >= 50:
        tier = "MEDIUM"
    else:
        tier = "LOW"

    if not s1_final:
        conf = ""
    elif (r.get("contradiction") == "YES" or r.get("entity_check") in ("MISMATCH", "NOT_FOUND")
          or age > 365 or s1_final in WEAK_S1):
        conf = "LOW"
    elif s1_final == "EXACT_CORROBORATED" and age <= 120 and r.get("entity_check") == "MATCH":
        conf = "HIGH"
    else:
        conf = "MEDIUM"

    return {"s1_score": s1, "s2_score": s2, "s3_score": s3, "signal_score": score,
            "tier": tier, "evidence_confidence": conf}


def formula_mismatches(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        got = compute(r)
        for f in CHECKED:
            want, have = str(got[f]), (r.get(f) or "").strip()
            if want != have:
                out.append({"company": r.get("company"), "field": f, "csv": have, "formula": want})
        floor, gate = gate_floor(r), (r.get("icp_gate") or "").strip()
        if (floor in ("FAIL", "REVIEW") and gate != floor) or (floor == "PASS_OR_REVIEW" and gate not in ("PASS", "REVIEW")):
            out.append({"company": r.get("company"), "field": "icp_gate", "csv": gate, "formula": floor})
    return out


def doc_gaps(rows: list[dict]) -> list[dict]:
    """Rows where formulas and CSV agree but the written rules suggest another outcome."""
    out = []
    for r in rows:
        tier = (r.get("tier") or "").strip()
        if r.get("icp_gate") == "REVIEW" and tier == "HIGH":
            out.append({"company": r.get("company"), "rule": "gate_review_scored_high",
                        "detail": f"ICP gate REVIEW (entity {r.get('entity_check')}, model "
                                  f"{r.get('business_model') or 'blank'}) says 'verify before spending research "
                                  "credits', but the Tier formula ignores the gate unless it is FAIL, so the row "
                                  "was researched and tiered HIGH."})
        if r.get("entity_check") == "MISMATCH" and tier != "REVIEW":
            out.append({"company": r.get("company"), "rule": "different_company_not_review",
                        "detail": f"SCORING.md says REVIEW when 'the enriched record is a different company', "
                                  f"but the Tier formula checks for no S1 first, so it is {tier}."})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("csv", nargs="?", default=str(DEFAULT_CSV))
    ap.add_argument("--strict", action="store_true", help="also fail on documentation gaps")
    args = ap.parse_args(argv)

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    mism, gaps = formula_mismatches(rows), doc_gaps(rows)

    print(f"Checked {len(rows)} rows against clay/formulas.md.")
    print(f"Formula mismatches: {len(mism)}")
    for m in mism:
        print(f"  {m['company']}: {m['field']} is {m['csv']!r} in the CSV, formula gives {m['formula']!r}")
    print(f"Documentation gaps (formula and CSV agree, written rules differ): {len(gaps)}")
    for g in gaps:
        print(f"  {g['company']} [{g['rule']}]: {g['detail']}")
    return 1 if mism or (args.strict and gaps) else 0


if __name__ == "__main__":
    sys.exit(main())
