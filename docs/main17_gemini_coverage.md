# MAIN17 Gemini coverage scoring

## Purpose

Gemini scores each of the 126 frozen MAIN17 source units against each of the
nine coverage-only blinded summaries. The model and prompt mapping is never
loaded by the scorer.

## Score definitions

- `2`: essential meaning and all material qualifiers are preserved accurately.
- `1`: core meaning is present, but a meaningful qualifier, scope, condition,
  duration, recipient, purpose, exception, or detail is missing or weakened.
- `0`: the unit is absent, materially distorted, or contradicted.

## First test

From the `pilot_study` folder, run one batch. The launcher uses the project's
`.venv` directly, so manual activation is optional:

```powershell
.\run_main17_coverage.ps1 -MaxBatches 1
```

One batch contains at most 15 units. Review the printed result before scaling.

## Continue

For example, run ten additional pending batches:

```powershell
.\run_main17_coverage.ps1 -MaxBatches 10
```

The scorer resumes from successful `(blind_id, unit_id)` pairs and does not
replace existing successful rows. If the Gemini free-tier quota returns HTTP
429, the runner stops and can be rerun after the quota becomes available.

## Outputs

Results are written under:

`data/main/coverage_validation/MAIN17/evaluations/`

The claim-level file records blind ID, unit ID, category, score, summary
evidence, rationale, whether the evidence is a verbatim substring, request ID,
timestamp, status, and error. A separate batch log records technical failures.
