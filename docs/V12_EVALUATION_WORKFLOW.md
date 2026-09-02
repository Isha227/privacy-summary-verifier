# v1.2 evaluation workflow

This workflow applies only to the frozen 54-summary prompt-intervention dataset.

## What is evaluated

- **Readability and conciseness:** already calculated for every summary.
- **Faithfulness:** every frozen summary sentence is checked against its complete source policy.
- **Omission/coverage:** important source information is identified source-first, frozen after adjudication, and then checked against every summary.
- **Evaluator agreement:** Gemini and MiniCheck are compared with the final researcher judgements on exactly matching sentence IDs. Gemini coverage scores are compared with researcher coverage scores on exactly matching source-unit/summary pairs.

## Gemini

Gemini performs two separate jobs:

1. statement-to-source verification for hallucination and distortion;
2. source-first identification followed by source-unit-to-summary verification for omission/coverage.

The preliminary Gemini-only coverage results use Gemini's own evidence-validated source units. After the researchers' independent proposals are adjudicated, Gemini will also score the shared frozen unit set so that automated–human agreement compares identical items.

The full run is resumable. Successful items are logged and skipped on a restart.

```powershell
$env:EXPERIMENT_CONFIG="config/v2_prompt_intervention_v1.2.yaml"
.\.venv\Scripts\python.exe -m src.run_v12_gemini
```

Do not use the preliminary Gemini-only coverage scores as the final automated–human agreement dataset. That comparison requires the later shared frozen unit set.

## MiniCheck in Google Colab

1. Open Google Colab and upload `notebooks/MiniCheck_V12_Colab.ipynb`.
2. Select **Runtime > Change runtime type > T4 GPU**.
3. Run the first installation cell.
4. When asked, upload `data/v2_prompt_intervention_v1_2/minicheck_colab/MiniCheck_V12_inputs.zip`.
5. Connect the Google Drive account that should store checkpoints.
6. Run the remaining cells in order.
7. If Colab disconnects, open the notebook again and repeat the cells. Completed statement IDs are loaded from Drive and skipped.
8. Completion is valid only when the notebook reports `Successful: 1393 / 1393` and `Summaries represented: 54 / 54`.
9. Save `minicheck_v12_statement_scores_FINAL.csv` in `data/v2_prompt_intervention_v1_2/evaluations/minicheck/`.

MiniCheck is binary. Do not convert its predictions into the four human/Gemini categories, and do not treat MiniCheck as an omission measure.

## Researchers: Phase 1

Give one package to each researcher: A1, A2 and A3. Researchers work independently and must not open:

- `BLINDING_KEY_RESTRICTED.csv`;
- Gemini or MiniCheck results;
- another researcher's workbook.

Each researcher completes both tasks in their own workbook.

### Faithfulness

For each sentence:

1. open the corresponding complete source policy;
2. assign `Supported`, `Partially supported`, `Contradicted` or `Unsupported`;
3. assign the matching failure type;
4. copy exact source evidence where applicable;
5. give a concise reason for the decision;
6. record confidence.

`None` is valid only with `Supported`. `Partially supported` normally indicates distortion or a mixed supported/unsupported statement. `Unsupported` normally indicates hallucination. A `Contradicted` statement conflicts materially with the source.

### Source-first important information

For each policy, read the source before consulting its summaries. Record one independently assessable important proposition per row. Use only information explicitly present in the policy; do not use a fixed privacy taxonomy and do not infer missing topics. Copy exact source wording and preserve material qualifications.

The number of source units is not fixed. Unused rows remain blank.

Save as:

- `human_v12_A1_PHASE1_COMPLETED.xlsx`
- `human_v12_A2_PHASE1_COMPLETED.xlsx`
- `human_v12_A3_PHASE1_COMPLETED.xlsx`

## Researchers: Phase 2

After all Phase 1 workbooks are returned:

1. combine the independently proposed source units;
2. remove exact duplicates without changing meaning;
3. adjudicate disagreements and overlapping units;
4. freeze one policy-specific source-unit list with exact evidence;
5. generate identical blinded coverage workbooks for A1, A2 and A3;
6. have every researcher score every frozen unit against every associated summary as `Covered`, `Partially covered` or `Not covered`, with evidence and reason;
7. ask Gemini to score the same unit-summary pairs;
8. calculate researcher agreement, adjudicate disagreements, and compare Gemini with the final human decisions.

An absent topic is never an omission. A unit enters the coverage denominator only when it is explicitly present in that policy and retained in the adjudicated source-unit set.

## Analysis commands

Revalidate and rebuild the completed automated analysis:

```powershell
.\run_v12_analysis.ps1 -Stage automated
```

After placing all three completed Phase 1 workbooks in their original researcher package folders:

```powershell
.\run_v12_analysis.ps1 -Stage validate-humans
```

Only after validation succeeds:

```powershell
.\run_v12_analysis.ps1 -Stage prepare-adjudication
```

Coverage Phase 2 is generated only after `frozen_source_units_FINAL.csv` has been manually adjudicated and frozen. This prevents the software from making semantic deduplication decisions on behalf of the researchers.
