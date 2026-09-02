from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/opp115/experiment/evaluations/readability_compression.csv"
OUTPUT = ROOT / "data/opp115/experiment/audits/readability_compression_audit.json"

KEY = ("policy_id", "model_family", "prompt_strategy", "replicate")
NUMERIC = (
    "words",
    "sentences",
    "characters",
    "flesch_reading_ease",
    "flesch_kincaid_grade",
    "smog_grade",
    "output_tokens",
    "max_output_tokens",
    "source_words",
    "word_compression_ratio",
    "character_compression_ratio",
)


def prompt_set(strategy: str) -> str:
    return "Safety-focused" if strategy.startswith("safety_") else "Basic"


def prompting_strategy(strategy: str) -> str:
    if strategy.endswith("direct"):
        return "Zero-shot"
    if strategy.endswith("role_guided"):
        return "Role-based"
    if strategy.endswith("structured"):
        return "Structured"
    raise ValueError(f"Unknown prompt strategy: {strategy}")


with INPUT.open(encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))

keys = [tuple(row[field] for field in KEY) for row in rows]
duplicates = [dict(zip(KEY, key)) for key, count in Counter(keys).items() if count > 1]
missing = {
    field: sum(not str(row.get(field, "")).strip() for row in rows)
    for field in NUMERIC
}

policy_sources: dict[str, set[int]] = defaultdict(set)
for row in rows:
    policy_sources[row["policy_id"]].add(int(float(row["source_words"])))

grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
for row in rows:
    grouped[(row["model_family"], prompt_set(row["prompt_strategy"]), prompting_strategy(row["prompt_strategy"]))].append(row)

summary = []
for (model, set_name, strategy), values in sorted(grouped.items()):
    summary.append(
        {
            "model_family": model,
            "prompt_set": set_name,
            "prompting_strategy": strategy,
            "n": len(values),
            "mean_words": round(mean(float(v["words"]) for v in values), 2),
            "median_words": round(median(float(v["words"]) for v in values), 2),
            "mean_flesch_reading_ease": round(mean(float(v["flesch_reading_ease"]) for v in values), 2),
            "mean_flesch_kincaid_grade": round(mean(float(v["flesch_kincaid_grade"]) for v in values), 2),
            "mean_smog_grade": round(mean(float(v["smog_grade"]) for v in values), 2),
            "mean_word_compression_ratio": round(mean(float(v["word_compression_ratio"]) for v in values), 4),
        }
    )

by_policy: dict[str, list[dict[str, str]]] = defaultdict(list)
for row in rows:
    by_policy[row["policy_id"]].append(row)

policy_summary = []
for policy, values in sorted(by_policy.items()):
    policy_summary.append(
        {
            "policy_id": policy,
            "source_words": int(float(values[0]["source_words"])),
            "n": len(values),
            "mean_summary_words": round(mean(float(v["words"]) for v in values), 2),
            "mean_flesch_reading_ease": round(mean(float(v["flesch_reading_ease"]) for v in values), 2),
            "mean_flesch_kincaid_grade": round(mean(float(v["flesch_kincaid_grade"]) for v in values), 2),
            "mean_smog_grade": round(mean(float(v["smog_grade"]) for v in values), 2),
            "mean_word_compression_ratio": round(mean(float(v["word_compression_ratio"]) for v in values), 4),
        }
    )

audit = {
    "input": str(INPUT),
    "rows": len(rows),
    "unique_conditions": len(set(keys)),
    "policies": len({row["policy_id"] for row in rows}),
    "models": dict(Counter(row["model_family"] for row in rows)),
    "prompt_strategies": dict(Counter(row["prompt_strategy"] for row in rows)),
    "prompt_sets": dict(Counter(prompt_set(row["prompt_strategy"]) for row in rows)),
    "duplicates": duplicates,
    "missing_numeric_values": missing,
    "policies_with_inconsistent_source_words": {
        policy: sorted(values) for policy, values in policy_sources.items() if len(values) != 1
    },
    "token_ceiling_rows": sum(row["at_token_ceiling"].lower() == "true" for row in rows),
    "reasoning_leak_rows": sum(row["reasoning_leak_detected"].lower() == "true" for row in rows),
    "metric_ranges": {
        field: {
            "min": min(float(row[field]) for row in rows),
            "max": max(float(row[field]) for row in rows),
        }
        for field in NUMERIC
    },
    "condition_summary": summary,
    "policy_summary": policy_summary,
}

audit["valid"] = (
    audit["rows"] == 486
    and audit["unique_conditions"] == 486
    and audit["policies"] == 27
    and not audit["duplicates"]
    and not any(audit["missing_numeric_values"].values())
    and not audit["policies_with_inconsistent_source_words"]
    and audit["token_ceiling_rows"] == 0
)

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(audit, indent=2), encoding="utf-8")
print(json.dumps(audit, indent=2))
