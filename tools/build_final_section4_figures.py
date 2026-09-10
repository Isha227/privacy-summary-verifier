from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "section4_revised_figures"
OUT.mkdir(parents=True, exist_ok=True)
BASE = ROOT / "data" / "v2_prompt_intervention_v1_2"

NAVY = "#174A7E"
BLUE = "#5B9BD5"
LIGHT_BLUE = "#DCEAF7"
ORANGE = "#E69F00"
RED = "#C23B33"
GREY = "#6B7280"
GRID = "#D9DEE5"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": "#606770",
    "svg.fonttype": "none",
})


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=400, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def proportions(frame, label_col, labels, prefix):
    counts = pd.crosstab(frame["blind_id"], frame[label_col]).reindex(columns=labels, fill_value=0)
    props = counts.div(counts.sum(axis=1), axis=0)
    props.columns = [prefix + x.lower().replace(" ", "_") for x in labels]
    return props.reset_index()


# Build the harmonised summary-level data used by Section 4.
quality = pd.read_csv(ROOT / "results" / "summary_quality" / "all_540_summaries.csv")
opp_align = pd.read_csv(ROOT / "data" / "opp115" / "experiment" / "evaluations" / "faithfulness" /
                        "gemini_claim_scores_batched__gemini-3.5-flash-lite__source-passage-ids-v2.csv")
cur_align = pd.read_csv(BASE / "evaluations" / "gemini_statement_verification_all.csv")
opp_cov = pd.read_csv(ROOT / "data" / "opp115" / "experiment" / "coverage_v3" / "evaluations" /
                      "gemini_coverage_scores.csv")
cur_cov = pd.read_csv(BASE / "evaluations" / "final_coverage_results" /
                      "final_human_and_gemini_coverage.csv")

align_labels = ["Supported", "Partially supported", "Unsupported", "Contradicted"]
coverage_labels = ["Covered", "Partially covered", "Not covered"]
align = pd.concat([
    proportions(opp_align, "label", align_labels, "align_").assign(corpus="OPP-115"),
    proportions(cur_align, "label", align_labels, "align_").assign(corpus="Contemporary"),
], ignore_index=True)
coverage = pd.concat([
    proportions(opp_cov, "coverage_label", coverage_labels, "cov_").assign(corpus="OPP-115"),
    proportions(cur_cov, "final_human_label", coverage_labels, "cov_").assign(corpus="Contemporary"),
], ignore_index=True)
data = quality.merge(align, on=["corpus", "blind_id"], validate="one_to_one")
data = data.merge(coverage, on=["corpus", "blind_id"], validate="one_to_one")
# The dissertation defines hallucination operationally as Unsupported only.
# Contradicted remains a separate alignment label and must not be folded into
# the hallucination bars.
data["hallucination"] = data["align_unsupported"]
data["distortion"] = data["align_partially_supported"]
data["omission"] = data["cov_not_covered"]
assert len(data) == 540 and data["policy_id"].nunique() == 30

corpora = ["OPP-115", "Contemporary"]
corpus_titles = {"OPP-115": "OPP-115 policies (n = 27)", "Contemporary": "Contemporary policies (n = 3)"}
models = ["gpt", "llama", "mistral"]
model_labels = ["GPT", "Llama", "Mistral"]
strategies = ["direct", "role_guided", "structured"]
strategy_labels = ["Zero-shot", "Role-based", "Structured"]
failures = ["hallucination", "distortion", "omission"]
failure_labels = ["Hallucination", "Distortion", "Omission"]
failure_colours = [RED, ORANGE, NAVY]


def grouped_factor_figure(factor, levels, labels, name, caption_title):
    fig, axes = plt.subplots(2, 2, figsize=(10.6, 6.7), layout="constrained")
    export = []
    for row, corpus in enumerate(corpora):
        frame = data[data["corpus"].eq(corpus)]
        means = frame.groupby(factor).mean(numeric_only=True).reindex(levels)
        x = np.arange(len(levels))

        ax = axes[row, 0]
        width = 0.34
        re_vals = means["flesch_reading_ease"].to_numpy()
        retained = means["word_compression_ratio"].to_numpy() * 100
        ax.bar(x - width / 2, re_vals, width, color=NAVY, label="Reading Ease")
        ax.bar(x + width / 2, retained, width, color=BLUE, label="Source text retained (%)")
        ax.set_xticks(x, labels)
        ax.set_ylabel("Mean score / percentage")
        ax.set_title(f"{corpus_titles[corpus]} — accessibility", loc="left", fontweight="bold")
        ax.grid(axis="y", color=GRID, linewidth=.7)
        ax.set_axisbelow(True)
        if row == 0:
            ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(.5, 1.18))

        ax = axes[row, 1]
        width = 0.23
        for j, (metric, label, colour) in enumerate(zip(failures, failure_labels, failure_colours)):
            vals = means[metric].to_numpy() * 100
            ax.bar(x + (j - 1) * width, vals, width, color=colour, label=label)
        ax.set_xticks(x, labels)
        ax.set_ylabel("Mean failure rate (%)")
        ax.set_title(f"{corpus_titles[corpus]} — reliability failures", loc="left", fontweight="bold")
        ax.grid(axis="y", color=GRID, linewidth=.7)
        ax.set_axisbelow(True)
        if row == 0:
            ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(.5, 1.18))

        for level, display in zip(levels, labels):
            rec = {"corpus": corpus, factor: display}
            subset = means.loc[level]
            rec.update({
                "reading_ease": subset["flesch_reading_ease"],
                "source_text_retained_percent": subset["word_compression_ratio"] * 100,
                "hallucination_percent": subset["hallucination"] * 100,
                "distortion_percent": subset["distortion"] * 100,
                "omission_percent": subset["omission"] * 100,
            })
            export.append(rec)
    fig.suptitle(caption_title, fontsize=13, fontweight="bold")
    save(fig, name)
    pd.DataFrame(export).to_csv(OUT / f"{name}_values.csv", index=False)


grouped_factor_figure(
    "model_family", models, model_labels, "Figure_1_model_effects",
    "Summary quality by generation model",
)
grouped_factor_figure(
    "strategy", strategies, strategy_labels, "Figure_2_prompting_strategy_effects",
    "Summary quality by prompting strategy",
)


# Basic versus Safety-focused: matched design, displayed separately by corpus.
fig, axes = plt.subplots(2, 2, figsize=(10.6, 6.7), layout="constrained")
version_export = []
for row, corpus in enumerate(corpora):
    frame = data[data["corpus"].eq(corpus)]
    means = frame.groupby("prompt_set").mean(numeric_only=True).reindex(["basic", "safety_focused"])
    labels = ["Basic", "Safety-focused"]
    x = np.arange(2)

    ax = axes[row, 0]
    width = .34
    ax.bar(x - width / 2, means["flesch_reading_ease"], width, color=NAVY, label="Reading Ease")
    ax.bar(x + width / 2, means["word_compression_ratio"] * 100, width, color=BLUE,
           label="Source text retained (%)")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Mean score / percentage")
    ax.set_title(f"{corpus_titles[corpus]} — accessibility", loc="left", fontweight="bold")
    ax.grid(axis="y", color=GRID, linewidth=.7)
    ax.set_axisbelow(True)
    if row == 0:
        ax.legend(frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(.5, 1.18))

    ax = axes[row, 1]
    width = .23
    for j, (metric, label, colour) in enumerate(zip(failures, failure_labels, failure_colours)):
        ax.bar(x + (j - 1) * width, means[metric] * 100, width, color=colour, label=label)
    ax.set_xticks(x, labels)
    ax.set_ylabel("Mean failure rate (%)")
    ax.set_title(f"{corpus_titles[corpus]} — reliability failures", loc="left", fontweight="bold")
    ax.grid(axis="y", color=GRID, linewidth=.7)
    ax.set_axisbelow(True)
    if row == 0:
        ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(.5, 1.18))

    for key, display in zip(["basic", "safety_focused"], labels):
        m = means.loc[key]
        version_export.append({
            "corpus": corpus, "prompt_version": display,
            "reading_ease": m["flesch_reading_ease"],
            "source_text_retained_percent": m["word_compression_ratio"] * 100,
            "hallucination_percent": m["hallucination"] * 100,
            "distortion_percent": m["distortion"] * 100,
            "omission_percent": m["omission"] * 100,
        })
fig.suptitle("Basic and Safety-focused prompt versions", fontsize=13, fontweight="bold")
save(fig, "Figure_3_prompt_version_effects")
pd.DataFrame(version_export).to_csv(OUT / "Figure_3_prompt_version_effects_values.csv", index=False)


# RQ2: two simple views of agreement.  The earlier confusion matrices were
# accurate but visually dense.  Exact agreement and Cohen's kappa answer two
# different reader-facing questions and are therefore displayed separately.
ratings = pd.read_csv(BASE / "human_evaluation" / "adjudication" /
                      "human_phase1_all_faithfulness_ratings.csv")
adjudicated = pd.read_csv(BASE / "human_evaluation" / "adjudication" /
                         "faithfulness_disagreements_ADJUDICATED.csv").set_index("statement_id")
final = {}
for statement_id, group in ratings.groupby("statement_id"):
    if statement_id in adjudicated.index:
        final[statement_id] = adjudicated.loc[statement_id, "final_label"]
    else:
        assert group["label"].nunique() == 1
        final[statement_id] = group["label"].iloc[0]
gemini = cur_align.copy()
gemini["human"] = gemini["statement_id"].map(final)
assert gemini["human"].notna().all() and len(gemini) == 1393

def cohen_kappa(human, automated, labels):
    matrix = pd.crosstab(human, automated).reindex(index=labels, columns=labels, fill_value=0)
    n = matrix.to_numpy().sum()
    observed = np.trace(matrix.to_numpy()) / n
    expected = np.dot(matrix.sum(axis=1), matrix.sum(axis=0)) / (n * n)
    return float((observed - expected) / (1 - expected)), matrix


agreement_specs = [
    ("Source alignment", gemini["human"], gemini["label"], align_labels, "alignment"),
    ("Information coverage", cur_cov["final_human_label"], cur_cov["gemini_label"],
     coverage_labels, "coverage"),
]
agreement_audit = {}
agreement_rows = []
agreement_matrices = {}
for task, human, automated, labels, key in agreement_specs:
    exact = float(np.mean(np.asarray(human) == np.asarray(automated)))
    kappa, matrix = cohen_kappa(human, automated, labels)
    matrix.to_csv(OUT / f"Figure_4_{key}_confusion_counts.csv")
    agreement_matrices[key] = (matrix, labels)
    agreement_audit[key] = {"n": int(len(human)), "exact_agreement": exact, "kappa": kappa}
    agreement_rows.append({"task": task, "n": int(len(human)),
                           "exact_agreement_percent": exact * 100, "cohen_kappa": kappa})

agreement_frame = pd.DataFrame(agreement_rows)
fig, axes = plt.subplots(1, 2, figsize=(11.4, 5.3), layout="constrained")
matrix_display = [
    ("alignment", "Source alignment", 92.5, .233),
    ("coverage", "Information coverage", 76.8, .640),
]
for ax, (key, task, exact, kappa) in zip(axes, matrix_display):
    matrix, labels = agreement_matrices[key]
    row_pct = matrix.div(matrix.sum(axis=1).replace(0, np.nan), axis=0) * 100
    ax.imshow(row_pct.fillna(0), vmin=0, vmax=100, cmap="Blues")
    for i in range(len(labels)):
        for j in range(len(labels)):
            pct = row_pct.iloc[i, j]
            count = int(matrix.iloc[i, j])
            cell_text = f"{count:,}\n({pct:.1f}%)" if pd.notna(pct) else "0\n(—)"
            ax.text(j, i, cell_text, ha="center", va="center",
                    color="white" if pd.notna(pct) and pct >= 55 else "#111827",
                    fontsize=9.3, fontweight="bold" if i == j else "normal")
            if i == j and count > 0:
                ax.add_patch(plt.Rectangle((j - .48, i - .48), .96, .96,
                                           fill=False, edgecolor="#1B7F5A", linewidth=2.2))
    wrapped = [label.replace("Partially supported", "Partially\nsupported")
               .replace("Partially covered", "Partially\ncovered") for label in labels]
    ax.set_xticks(range(len(labels)), wrapped)
    ax.set_yticks(range(len(labels)), wrapped)
    ax.set_xlabel("Gemini decision")
    ax.set_ylabel("Final human decision")
    ax.set_title(f"{task}\nExact agreement {exact:.1f}%  |  κ = {kappa:.3f}",
                 fontweight="bold", pad=12)

fig.suptitle("Where Gemini agreed and disagreed with the final human reference",
             fontsize=13, fontweight="bold")
save(fig, "Figure_4_gemini_human_agreement")
agreement_frame.to_csv(OUT / "Figure_4_gemini_human_agreement_values.csv", index=False)


# RQ3: matched three historical and three contemporary technology policies.
taxonomy = pd.read_csv(ROOT / "data" / "opp115" / "experiment" / "taxonomy_v3" /
                       "evaluations" / "gemini_taxonomy_mappings.csv")
historical = taxonomy[(taxonomy["dataset"].eq("OPP historical")) &
                      (taxonomy["policy_id"].isin(["OPP01", "OPP02", "OPP03"]))].copy()
review = pd.read_csv(ROOT / "data" / "opp115" / "experiment" / "taxonomy_v3" /
                     "analysis" / "contemporary_other_review_final.csv").set_index("unit_id")
contemporary_human = taxonomy[taxonomy["dataset"].eq("Contemporary human reference")].copy()
contemporary_human["final_category"] = [
    review.loc[u, "final_category"] if u in review.index else cat
    for u, cat in zip(contemporary_human["unit_id"], contemporary_human["primary_category"])
]
contemporary_gemini = taxonomy[taxonomy["dataset"].isin([
    "Contemporary Gemini source unit",
    "Contemporary Gemini validated addition",
])].copy()
assert len(historical) == 151 and len(contemporary_gemini) == 114 and len(contemporary_human) == 165

categories = [
    "First Party Collection/Use", "Third Party Sharing/Collection", "User Choice/Control",
    "User Access, Edit and Deletion", "Data Retention", "Data Security", "Policy Change",
    "Do Not Track", "International and Specific Audiences", "Other",
]
hist_pct = historical["primary_category"].value_counts(normalize=True).reindex(categories, fill_value=0) * 100
cur_pct = contemporary_gemini["primary_category"].value_counts(normalize=True).reindex(categories, fill_value=0) * 100
short_categories = [
    "First-party collection/use", "Third-party sharing/collection", "User choice/control",
    "Access, edit and deletion", "Data retention", "Data security", "Policy change",
    "Do Not Track", "International/specific audiences", "Other",
]

fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.6), gridspec_kw={"width_ratios": [3.1, 1]}, layout="constrained")
ax = axes[0]
y = np.arange(len(categories))
h = .34
ax.barh(y + h / 2, hist_pct, h, color=NAVY, label="Historical technology policies")
ax.barh(y - h / 2, cur_pct, h, color=BLUE, label="Contemporary technology policies")
ax.set_yticks(y, short_categories)
ax.invert_yaxis()
ax.set_xlabel("Source units in category (%)")
ax.set_title("Distribution across OPP-115 categories", loc="left", fontweight="bold")
ax.grid(axis="x", color=GRID, linewidth=.7)
ax.set_axisbelow(True)
ax.legend(frameon=False, loc="lower right")

ax = axes[1]
fit_hist = (historical["primary_category"] != "Other").mean() * 100
fit_cur = (contemporary_gemini["primary_category"] != "Other").mean() * 100
fit_human = (contemporary_human["final_category"] != "Other").mean() * 100
bars = ax.bar([0, 1, 2], [fit_hist, fit_cur, fit_human], color=[NAVY, BLUE, "#6B7280"], width=.62)
ax.set_xticks([0, 1, 2], ["Historical\nGemini", "Current\nGemini", "Current\nhuman"])
ax.set_ylim(0, 105)
ax.set_ylabel("Units mapped outside ‘Other’ (%)")
ax.set_title("Taxonomy fit", loc="left", fontweight="bold")
ax.grid(axis="y", color=GRID, linewidth=.7)
ax.set_axisbelow(True)
for bar, value in zip(bars, [fit_hist, fit_cur, fit_human]):
    ax.text(bar.get_x() + bar.get_width()/2, value + 1.3, f"{value:.1f}%", ha="center", fontweight="bold")
fig.suptitle("Matched historical–contemporary taxonomy comparison (3 policies per group)",
             fontsize=13, fontweight="bold")
save(fig, "Figure_5_matched_taxonomy_comparison")
pd.DataFrame({
    "category": categories,
    "historical_percent": hist_pct.values,
    "contemporary_gemini_percent": cur_pct.values,
    "contemporary_human_percent": contemporary_human["final_category"].value_counts(normalize=True).reindex(categories, fill_value=0).values * 100,
}).to_csv(OUT / "Figure_5_matched_taxonomy_comparison_values.csv", index=False)


captions = """Figure 1. Mean accessibility and reliability outcomes by generation model, shown separately for 27 OPP-115 and three contemporary policies. Model means average across all three prompting strategies and both prompt versions. Lower hallucination, distortion and omission rates indicate better reliability.

Figure 2. Mean accessibility and reliability outcomes by prompting strategy, shown separately for the two policy corpora. Strategy means average across all three generation models and both prompt versions. Lower failure rates indicate better reliability.

Figure 3. Mean outcomes under Basic and Safety-focused prompting, shown separately for 27 OPP-115 policies and three contemporary policies. Comparisons are matched by policy, model and prompting strategy. Higher source-text retention indicates a longer, less compressed summary; lower failure rates indicate better reliability.

Figure 4. Confusion matrices comparing Gemini with the final human reference for source alignment and information coverage. Rows show final human decisions and columns show Gemini decisions. Each cell reports the count and percentage within its human-label row; green diagonal outlines indicate agreement.

Figure 5. Distribution of Gemini-extracted source units across OPP-115 categories in a matched comparison of three historical and three contemporary technology policies. Taxonomy fit is the percentage assigned to one of the nine substantive categories rather than Other. The separate contemporary human-reference result provides a validation check and is not included in the distribution comparison.
"""
(OUT / "captions.txt").write_text(captions, encoding="utf-8")
(OUT / "verification.json").write_text(json.dumps({
    "summary_rows": int(len(data)),
    "policies": int(data["policy_id"].nunique()),
    "corpus_summary_counts": data["corpus"].value_counts().to_dict(),
    "agreement": agreement_audit,
    "taxonomy": {
        "historical_units": int(len(historical)),
        "contemporary_gemini_units": int(len(contemporary_gemini)),
        "contemporary_human_units": int(len(contemporary_human)),
        "historical_fit_percent": fit_hist,
        "contemporary_gemini_fit_percent": fit_cur,
        "contemporary_human_fit_percent": fit_human,
        "historical_other": int((historical["primary_category"] == "Other").sum()),
        "contemporary_gemini_other": int((contemporary_gemini["primary_category"] == "Other").sum()),
        "contemporary_human_other": int((contemporary_human["final_category"] == "Other").sum()),
    },
}, indent=2), encoding="utf-8")

print(f"Created report figures in {OUT}")
print(json.dumps(agreement_audit, indent=2))
print(f"Matched taxonomy: historical {len(historical)} units, {fit_hist:.2f}% fit; "
      f"contemporary Gemini {len(contemporary_gemini)} units, {fit_cur:.2f}% fit; "
      f"contemporary human {len(contemporary_human)} units, {fit_human:.2f}% fit")
