import ast
import csv
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReleaseIntegrityTest(unittest.TestCase):
    def test_prototype_is_valid_python(self):
        source = (ROOT / "app" / "privacy_summary_verifier.py").read_text(encoding="utf-8")
        ast.parse(source)

    def test_final_summary_table_contains_540_rows(self):
        path = ROOT / "results" / "summary_quality" / "all_540_summaries.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            self.assertEqual(sum(1 for _ in csv.DictReader(handle)), 540)

    def test_paired_analysis_contains_five_direct_outcomes(self):
        path = ROOT / "results" / "statistics" / "basic_vs_safety_focused.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            {row["outcome"] for row in rows},
            {
                "Reading Ease",
                "Source text retained",
                "Hallucination",
                "Distortion",
                "Omission",
            },
        )


if __name__ == "__main__":
    unittest.main()
