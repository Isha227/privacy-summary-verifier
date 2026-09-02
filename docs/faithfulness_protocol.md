# Faithfulness protocol — GPT reproducibility check

## Scope

This first faithfulness check uses only the three blinded `PILOT02 × GPT × zero`
summaries (`S027`, `S014`, `S015`). It tests whether the observed coverage
variation is accompanied by factual-consistency variation. The mapping from
blind ID to replicate remains in `BLINDING_KEY_RESTRICTED.csv` and must not be
shown to annotators before adjudication.

## 1. Freeze sentence-level claims

Run:

```powershell
python -m src.cli prepare-faithfulness
```

The script creates reproducible sentence-level candidates in
`data/pilot/faithfulness/claim_candidates.csv`. MiniCheck is designed for
sentence-level inputs, so the same units are used for all three evaluation
methods. Before scoring, one researcher checks every candidate against the
summary and changes `include` to `no` only for headings, fragments, or wholly
non-checkable statements. Record a reason in `review_notes`. Do not rewrite a
model's words and do not split or merge units after scoring begins.

After reviewing `include`, freeze the identical blank researcher files:

```powershell
python -m src.cli freeze-faithfulness
```

Do not rerun preparation after manual edits because it deliberately recreates
the candidate file. The freeze command refuses to overwrite a researcher file
once scoring has begun.

## 2. Independent human scoring

Each annotator completes only their own file. Allowed labels are:

- `Supported`: every material part of the claim is directly supported.
- `Partially supported`: some material content is supported, but part is
  absent, overstated, or imprecise.
- `Unsupported`: the policy provides no evidence for the claim.
- `Contradicted`: the policy states the opposite or is materially incompatible.

For every row, enter a short source quote when possible and always enter an
`evidence_location` such as a source heading or distinctive search phrase. For
unsupported claims, write `No supporting passage found` as the location. Work
independently and do not discuss scores until all three files validate.

```powershell
python -m src.cli validate-human-faithfulness
```

After validation, calculate agreement and adjudicate disagreements while still
blinded. Preserve the original A1/A2/A3 files.

## 3. Gemini fixed judge

The final fixed judge is `gemini-3.5-flash-lite`, frozen on 2026-08-13. It is a
stable, high-throughput model endpoint rather than a changing `latest` alias.
An initial feasibility attempt with `gemini-3.6-flash` produced 19 successful
claims before reaching the free-tier quota; those results are archived and
excluded rather than mixed with the final judge. Add `GEMINI_API_KEY` to the
local `.env`, then run:

```powershell
python -m src.cli run-gemini-faithfulness
```

The runner uses temperature 0, the complete cleaned policy, the frozen claim,
the four-label codebook, and structured JSON. It is resume-safe and appends
failed calls for audit. Gemini output is an automated judge result, not ground
truth; compare it with adjudicated human ratings.

The project is configured for the Gemini free tier. When the daily project
quota is exhausted, the runner records the first HTTP 429 and stops immediately.
Run the same command after the quota resets; successful claims are skipped.
Google states that requests-per-day quotas reset at midnight Pacific time.

## 4. MiniCheck

MiniCheck is intentionally optional because its PyTorch/model dependencies are
large. Install the official package in the pilot virtual environment only when
ready:

```powershell
pip install "minicheck @ git+https://github.com/Liyan06/MiniCheck.git@main"
python -m src.cli run-minicheck-faithfulness
```

The frozen model is `flan-t5-large`. MiniCheck returns a binary supported label
and support probability. Do not relabel those outputs as the four human
categories. Report binary performance separately or collapse the adjudicated
human reference transparently (for example, Supported = 1; all other labels =
0) before comparing methods.

## 5. Decision rule for the main study

Summarise per replicate: number of included claims, proportions in each human
label, strict supported rate, and automated scores. Consider repeated main-study
runs only if the three identical GPT conditions show a practically important
range in both coverage and faithfulness. Record the threshold and decision
before examining the remaining model/prompt conditions.
