import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_scoring", ROOT / "scripts" / "check_scoring.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)

SAMPLE = ROOT / "sample" / "public-safe-sample.csv"


def rows():
    with open(SAMPLE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def base(**kw):
    r = {"business_model": "PRODUCT_SOFTWARE", "suppressed": "NO", "entity_check": "MATCH", "icp_gate": "PASS",
         "evidence_age_days": "10", "s1_final": "EXACT_CORROBORATED", "s2_category": "ACTIVE",
         "s3_category": "ATTESTED", "contradiction": "NO"}
    r.update(kw)
    return r


def test_sample_matches_the_as_built_formulas():
    assert cs.formula_mismatches(rows()) == []


def test_known_documentation_gaps_are_reported():
    gaps = {(g["company"], g["rule"]) for g in cs.doc_gaps(rows())}
    assert gaps == {
        ("Elective", "gate_review_scored_high"),
        ("dormakaba", "gate_review_scored_high"),
        ("Sundayy", "different_company_not_review"),
    }


def test_s1_staleness_rules():
    assert cs.compute(base(evidence_age_days="200"))["s1_score"] == 25
    assert cs.compute(base(evidence_age_days="400"))["s1_score"] == 10
    assert cs.compute(base(s1_final="PLATFORM_FALSE_POSITIVE", evidence_age_days="400"))["s1_score"] == 0


def test_tier_rules():
    assert cs.compute(base())["tier"] == "HIGH"
    assert cs.compute(base(suppressed="YES"))["tier"] == "EXCLUDED"
    assert cs.compute(base(icp_gate="FAIL"))["tier"] == "EXCLUDED"
    assert cs.gate_floor(base(business_model="IT_SERVICES_OR_STAFFING")) == "FAIL"
    assert cs.compute(base(contradiction="YES"))["tier"] == "REVIEW"
    assert cs.compute(base(s1_final=""))["tier"] == "LOW"
    assert cs.compute(base(s2_category="NONE", s3_category="NONE"))["tier"] == "MEDIUM"  # 50


def test_confidence_rules():
    assert cs.compute(base())["evidence_confidence"] == "HIGH"
    assert cs.compute(base(entity_check="PARTIAL"))["evidence_confidence"] == "MEDIUM"
    assert cs.compute(base(s1_final="EXPERIENCE_ONLY"))["evidence_confidence"] == "LOW"


def test_a_changed_cell_is_caught():
    data = rows()
    data[0]["signal_score"] = "91"
    found = cs.formula_mismatches(data)
    assert any(m["field"] == "signal_score" and m["company"] == data[0]["company"] for m in found)


def test_cli_exit_codes(capsys):
    assert cs.main([str(SAMPLE)]) == 0
    assert "Elective" in capsys.readouterr().out
    assert cs.main([str(SAMPLE), "--strict"]) == 1
