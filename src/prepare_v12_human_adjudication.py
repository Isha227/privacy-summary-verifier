from __future__ import annotations

import csv
import json
import re
from itertools import combinations

import pandas as pd

from .common import ROOT
from .validate_v12_human_phase1 import validate_workbook


BASE = ROOT / "data/v2_prompt_intervention_v1_2/human_evaluation"
OUT = BASE / "adjudication"


def _kappa(left: pd.Series, right: pd.Series) -> float:
    labels = sorted(set(left) | set(right))
    observed = float((left == right).mean())
    expected = sum(float((left == label).mean()) * float((right == label).mean()) for label in labels)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    faith_frames, unit_frames = [], []
    for evaluator in ("A1", "A2", "A3"):
        path = BASE / f"Researcher_{evaluator}_Package/human_v12_{evaluator}_PHASE1_COMPLETED.xlsx"
        faith, units, errors = validate_workbook(path, evaluator)
        if errors:
            raise RuntimeError(f"{evaluator} workbook is invalid; run validate_v12_human_phase1 first")
        faith_frames.append(pd.DataFrame(faith))
        unit_frames.append(pd.DataFrame(units))
    all_faith = pd.concat(faith_frames, ignore_index=True)
    all_faith.to_csv(OUT / "human_phase1_all_faithfulness_ratings.csv", index=False)

    labels = all_faith.pivot(index="statement_id", columns="evaluator", values="label")
    failures = all_faith.pivot(index="statement_id", columns="evaluator", values="failure_type")
    agreement_rows = []
    for left, right in combinations(("A1", "A2", "A3"), 2):
        agreement_rows.append({"comparison": f"{left} vs {right}", "n": len(labels),
                               "label_exact_agreement": float((labels[left] == labels[right]).mean()),
                               "label_cohen_kappa": _kappa(labels[left], labels[right]),
                               "failure_exact_agreement": float((failures[left] == failures[right]).mean()),
                               "failure_cohen_kappa": _kappa(failures[left], failures[right])})
    pd.DataFrame(agreement_rows).to_csv(OUT / "human_phase1_pairwise_agreement.csv", index=False)

    wide = labels.add_prefix("label_").join(failures.add_prefix("failure_")).reset_index()
    details = all_faith.pivot(index="statement_id", columns="evaluator", values=["exact_source_evidence", "reason", "confidence"])
    details.columns = [f"{field}_{evaluator}" for field, evaluator in details.columns]
    wide = wide.merge(details.reset_index(), on="statement_id", validate="one_to_one")
    wide["label_unanimous"] = wide[["label_A1", "label_A2", "label_A3"]].nunique(axis=1) == 1
    wide["failure_unanimous"] = wide[["failure_A1", "failure_A2", "failure_A3"]].nunique(axis=1) == 1
    disagreements = wide[~(wide["label_unanimous"] & wide["failure_unanimous"])].copy()
    disagreements["final_label"] = ""
    disagreements["final_failure_type"] = ""
    disagreements["final_evidence"] = ""
    disagreements["adjudication_reason"] = ""
    disagreements.to_csv(OUT / "faithfulness_disagreements_FOR_ADJUDICATION.csv", index=False)

    units = pd.concat(unit_frames, ignore_index=True)
    units["normalised_information"] = units["important_information_in_plain_language"].astype(str).str.lower().str.replace(r"\W+", " ", regex=True).str.strip()
    units["exact_text_duplicate_group_size"] = units.groupby(["policy_id", "normalised_information"])["proposed_unit_id"].transform("size")
    units["retain_in_frozen_set"] = ""
    units["final_unit_id"] = ""
    units["adjudication_notes"] = ""
    units.to_csv(OUT / "source_unit_proposals_FOR_ADJUDICATION.csv", index=False)
    summary = {"faithfulness_ratings": len(all_faith), "statements": len(labels),
               "faithfulness_disagreements": len(disagreements), "source_unit_proposals": len(units)}
    (OUT / "phase1_adjudication_status.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
