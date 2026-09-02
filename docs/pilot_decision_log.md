# Pilot decision log

## Corpus and providers

- Three policies were frozen as short (`PILOT01`, Mozilla), medium
  (`PILOT02`, DuckDuckGo), and long/complex (`PILOT03`, Automattic).
- Provider smoke tests succeeded for all three frozen model IDs.
- GPT-5.6 Luna rejected an explicit `temperature`; the parameter is omitted and
  logged as provider-controlled. Llama and Mistral use `0.0`.

## Reproducibility check

The predefined condition `PILOT02 × GPT × zero-shot` was generated three times.
This is a pilot diagnostic only. One generation per condition remains the
candidate main-study design, subject to coverage and faithfulness stability.

After blinded PILOT02 coverage scoring and adjudication, the three retained GPT
zero-shot runs scored 69.4%, 75.0%, and 63.9% coverage (mean 69.4%; range 11.1
percentage points). This indicates non-trivial run-to-run coverage variation.
The main-study repetition decision remains pending the corresponding
faithfulness comparison and an explicit practicality/power trade-off.

## Execution incident

The initial 29-execution matrix was accidentally launched twice. Both batches
remain in the append-only generation log. The second batch overwrote output
files because filenames were condition-based. The runner was subsequently made
resume-safe; evaluation and anonymisation now select the latest successful row
per unique condition. This incident must be disclosed in the pilot record and
does not add observations to the analytical dataset.

## Token ceiling refinement

The original 900-token ceiling caused technical truncation. Only responses that
exhausted their configured ceiling were retried, first at 1,200 and, where still
necessary, at 1,500 tokens. Earlier attempts remain in the log. The retained 29
outputs contain no response at its token ceiling. The provisional main-study
ceiling is therefore 1,500 tokens.

## Pending decisions

- Assess the three GPT replicates for coverage and faithfulness stability.
- Decide whether the 350–550-word instruction needs revision: some complete
  outputs exceed it, which is instruction non-compliance rather than truncation.
- Complete blinded coverage and faithfulness evaluation before freezing the
  main protocol.

## Source-unit annotation

The nine-category pilot taxonomy and independent source-unit procedure are
defined in `docs/source_unit_annotation_guide.md`. Three researchers must first
identify source units independently, then adjudicate a single frozen list per
policy before viewing or scoring generated summaries.

PILOT01 used 25 final units; PILOT02 used 36. Exact three-rater agreement was
89.3% (201/225) and 92.4% (366/396), respectively. All disagreements were one
score point and were adjudicated while outputs remained blinded.
