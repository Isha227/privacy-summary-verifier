# Privacy Summary Verifier

Reproducibility repository for the MSc AI dissertation **Verifying
LLM-Generated Plain-English Summaries of Privacy Policies**.

The study asks whether summaries can become easier to read and more concise
without losing alignment with their source policies. It compares GPT, Llama
and Mistral across zero-shot, role-based and structured-reasoning prompting,
using Basic and Safety-focused prompt versions.

## Final study at a glance

- 30 privacy policies: 27 from OPP-115 and three contemporary consumer-service
  policies.
- 540 summaries from a 30 × 3 × 3 × 2 matched experimental design.
- Accessibility: Flesch Reading Ease, word count and compression.
- Sentence source alignment: MiniCheck and Gemini, with researcher validation
  on the contemporary subset.
- Information coverage: independently extracted source units checked against
  each summary, with researcher validation on the contemporary subset.
- Taxonomy analysis: source units mapped after extraction to the ten OPP-115
  categories, allowing a descriptive historical-versus-contemporary comparison.

## Prototype

Run the evidence-linked Streamlit application from the project root:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run streamlit_v12_app.py
```

The app contains six views: contemporary summary verification, contemporary
coverage, evaluator agreement, study overview, an OPP-115 evidence explorer,
and taxonomy mapping. The local full-data version reads the completed study
files under `data/`; these files are excluded from GitHub because they contain
large derived datasets and restricted blinding materials.

## Repository map

- `src/` — preprocessing, generation, evaluation and analysis modules.
- `config/` — frozen model and experiment configuration.
- `prompts/` — Basic and Safety-focused prompt templates.
- `notebooks/` — MiniCheck Colab notebooks.
- `docs/` — collection, annotation and reproducibility protocols.
- `tests/` — validation and prototype smoke tests.
- `report/` — final dissertation document.
- `viva/` — viva preparation and prototype demonstration guide.

API keys must be stored only in a local `.env` file. Raw policies, generated
outputs, evaluation files, human workbooks and blinding keys are intentionally
excluded from version control. See `data/README.md` for the expected local data
layout.

## Earlier development notes

## Final v1.2 study status

The completed matched prompt-intervention study is stored under
`data/v2_prompt_intervention_v1_2/`. It contains 54 summaries generated from
three policies, three model families, three prompting strategies and basic
versus safety-focused prompt sets. Gemini and MiniCheck completed all 1,393
sentence assessments. Three researchers completed 4,179 independent sentence
ratings and 8,910 independent coverage ratings. The final shared coverage set
contains 165 human-adjudicated source units and 2,970 unit-summary comparisons.

Final coverage outputs are in
`data/v2_prompt_intervention_v1_2/evaluations/final_coverage_results/`. Run:

```powershell
.\run_final_coverage.ps1 status
.\run_final_coverage.ps1 analyse
.\run_dashboard.ps1
```

The dashboard now uses the final shared coverage denominator and displays both
Gemini and final human judgements. The older pilot and 30-policy pipeline below
is retained as methodological development history; it is not the final v1.2
experimental dataset.

Reproducible pilot for comparing GPT, Llama, and Mistral with zero-shot, role,
and structured-reasoning prompts. The pilot uses 3 policies (27 standard
conditions) plus two extra replicates of `PILOT02 × GPT × zero`, for 29 outputs;
the main study uses 30 policies (270 generations).

## Responsible use

- Check each website's terms and robots policy before downloading. Prefer an
  official downloadable policy or a manual browser save; do not bypass access
  controls.
- Policies are public documents, but preserve provenance and access dates.
- Never put API keys in this folder. Use `.env` locally; it is git-ignored.
- Freeze model IDs and generation settings before the experiment. Do not retry
  a valid but poor output. Retry only documented technical failures.
- A pilot tests feasibility and the procedure; exclude its policies from the
  confirmatory 30-policy corpus.

## Quick start

```powershell
cd pilot_study
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python -m src.cli init-metadata
python -m src.cli test-providers
python -m src.cli preprocess
python -m src.cli validate --expected-policies 3
python -m src.cli run --dry-run
python -m src.cli run
python -m src.cli evaluate
python -m src.cli anonymise
```

Put original HTML/PDF/TXT files in `data/pilot/raw/` and complete
`data/pilot/metadata/policies.csv`. Use IDs `PILOT01`–`PILOT03`. The runner
creates one JSON and one TXT output per condition and appends an immutable-style
CSV log. `--dry-run` makes no API calls.

## Experimental controls

`config/experiment.yaml` is the single source of truth. The selected model IDs
are also recorded in `config/FROZEN_MODELS.md`; confirm that your accounts can
access them, then freeze the configuration file and record its hash in the
dissertation. Default temperature is 0 for repeatability. Prompts have
the same task, audience, and output constraints; only the intended prompting
strategy differs. “Structured reasoning” asks for an internal checklist and
only the final summary, avoiding collection of hidden reasoning.

## Pipeline

1. Select and archive policies using `docs/policy_collection_protocol.md`.
2. Record provenance before cleaning.
3. Preprocess to UTF-8 text; visually compare against the source.
4. Validate corpus/config and inspect all 29 dry-run executions.
5. Generate once per condition and retain failures in the log.
6. Evaluate readability and compression. These are descriptive measures, not
   evidence of factual faithfulness.
7. Use blinded IDs for human annotation. Keep the key restricted until scoring
   is complete.
8. For the GPT reproducibility faithfulness check, follow
   `docs/faithfulness_protocol.md`: freeze sentence-level claims, complete the
   three independent blinded human files, then run the fixed Gemini and
   MiniCheck judges.

## Output schema

Generation log fields include run ID, policy/model/prompt identifiers, prompt
and source hashes, parameters, token counts, latency, timestamp, status, error,
and output paths. Evaluation provides word/sentence counts, Flesch Reading Ease,
Flesch–Kincaid grade, SMOG (where valid), and word/character compression ratios.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The frozen provider arrangement is OpenAI GPT-5.6 Luna, Together AI Llama 3.3
70B Instruct Turbo, and Mistral AI Mistral Large 3. Put `OPENAI_API_KEY`,
`TOGETHER_API_KEY`, and `MISTRAL_API_KEY` in `.env`. Do not replace the fixed
IDs with changing `latest` aliases.

API responses and token accounting vary by provider. Inspect one successful
call from each of OpenAI, Together, and Mistral before launching the full matrix.

The runner is resume-safe: conditions already recorded as successful are
skipped. Failed conditions may be retried, while valid-but-poor summaries are
never regenerated. Evaluation and anonymisation select the latest successful
record for each unique policy/model/prompt/replicate condition.

If a pilot response exhausts an earlier output-token ceiling, increase the
configured ceiling and run `python -m src.cli run --retry-truncated`. Only those
documented technical truncations are regenerated; the earlier log rows remain.

For pages containing cookie banners or subscription controls, explicit content
boundaries are recorded under `preprocess_boundaries` in the configuration.
This removes webpage interface text reproducibly without rewriting policy text.
