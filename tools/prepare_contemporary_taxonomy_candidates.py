from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data" / "v2_prompt_intervention_v1_2" / "source_unit_method_validation" / "final_comparison" / "validated_contemporary_source_units.csv"
OPP_CANDIDATES = ROOT / "data" / "opp115" / "experiment" / "coverage" / "taxonomy" / "opp115_unit_taxonomy_candidates.csv"
OUT_DIR = ROOT / "data" / "v2_prompt_intervention_v1_2" / "source_unit_method_validation" / "taxonomy_comparison"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = [
    "First Party Collection/Use",
    "Third Party Sharing/Collection",
    "User Choice/Control",
    "User Access, Edit and Deletion",
    "Data Retention",
    "Data Security",
    "Policy Change",
    "Do Not Track",
    "International and Specific Audiences",
    "Other",
]

STOP = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "by", "can", "could", "did", "do", "does",
    "for", "from", "had", "has", "have", "if", "in", "into", "is", "it", "its", "may", "might", "must", "not",
    "of", "on", "or", "our", "shall", "should", "so", "such", "than", "that", "the", "their", "them", "then",
    "there", "these", "they", "this", "to", "under", "us", "use", "used", "using", "was", "we", "were", "when",
    "where", "which", "who", "will", "with", "would", "you", "your",
}


def tokens(text: str) -> list[str]:
    values = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [value for value in values if len(value) > 2 and value not in STOP]


with OPP_CANDIDATES.open(encoding="utf-8-sig", newline="") as handle:
    opp_rows = list(csv.DictReader(handle))

profiles: dict[str, Counter] = {category: Counter(tokens(category)) for category in CATEGORIES}
examples: dict[str, list[str]] = defaultdict(list)
for row in opp_rows:
    category = row.get("opp_category", "").strip()
    if category not in profiles:
        continue
    text = " ".join([
        row.get("important_information", ""),
        row.get("annotation_selected_text", ""),
    ])
    profiles[category].update(tokens(text))
    annotation = row.get("annotation_selected_text", "").strip()
    if annotation and annotation not in examples[category] and len(examples[category]) < 40:
        examples[category].append(annotation)

document_frequency = Counter()
for profile in profiles.values():
    for token in profile:
        document_frequency[token] += 1


def category_score(query: Counter, category: str) -> tuple[float, list[str]]:
    profile = profiles[category]
    total = sum(profile.values()) or 1
    contributions = []
    score = 0.0
    for token, qtf in query.items():
        if token not in profile:
            continue
        idf = math.log((len(CATEGORIES) + 1) / (document_frequency[token] + 0.5))
        contribution = qtf * max(0.05, idf) * math.log1p(profile[token]) / math.sqrt(total)
        contributions.append((contribution, token))
        score += contribution
    contributions.sort(reverse=True)
    return score, [token for _, token in contributions[:8]]


with CURRENT.open(encoding="utf-8-sig", newline="") as handle:
    current_rows = list(csv.DictReader(handle))

candidate_rows = []
for row in current_rows:
    query_text = " ".join([
        row.get("important_information", ""),
        row.get("exact_source_evidence", ""),
        row.get("material_qualifiers", ""),
        row.get("why_important_to_user", ""),
    ])
    query = Counter(tokens(query_text))
    scored = []
    for category in CATEGORIES:
        score, matched = category_score(query, category)
        scored.append((score, category, matched))
    scored.sort(reverse=True)
    for rank, (score, category, matched) in enumerate(scored, 1):
        candidate_rows.append({
            "policy_id": row["policy_id"],
            "unit_id": row["validated_unit_id"],
            "rank": rank,
            "opp_category": category,
            "lexical_profile_score": round(score, 8),
            "matched_terms": "; ".join(matched),
            "example_opp_annotation": examples[category][0] if examples[category] else "",
        })

candidate_path = OUT_DIR / "contemporary_taxonomy_candidates.csv"
with candidate_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(candidate_rows[0]))
    writer.writeheader()
    writer.writerows(candidate_rows)

audit = {
    "status": "pass",
    "contemporary_units": len(current_rows),
    "policies": sorted({row["policy_id"] for row in current_rows}),
    "categories": CATEGORIES,
    "candidate_rows": len(candidate_rows),
    "candidates_per_unit": len(CATEGORIES),
    "method": "Lexical category-profile ranking used only as a review aid; it is not a final taxonomy judgement.",
}
(OUT_DIR / "contemporary_taxonomy_candidates_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
print(json.dumps(audit, indent=2))
