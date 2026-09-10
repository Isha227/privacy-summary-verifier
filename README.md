# Privacy Summary Verifier

Code and reproducibility outputs for an MSc experiment evaluating
plain-English privacy-policy summaries.

## Experiment

Three language models (GPT, Llama and Mistral) generated summaries using
zero-shot, role-based and structured prompting. Each strategy was tested with
a Basic and a Safety-focused prompt version. The corpus contains 27 OPP-115
policies and three contemporary policies from Mozilla, DuckDuckGo and
Automattic, producing 540 summaries.

The experiment measures:

- accessibility through Flesch Reading Ease and source text retained;
- sentence source alignment through Gemini labels, explanations and evidence;
- information coverage through Gemini and human evaluation;
- agreement between Gemini and human decisions on the contemporary subset;
- compatibility of independently extracted source units with OPP-115 taxonomy.

Inferential tests use the 27 OPP-115 policies. The three contemporary policies
form a separate human-validation study. RQ3 uses the same Gemini source-unit
extraction on three historical and three contemporary policies, with the human
units reported separately as validation.

## Repository structure

```text
app/         Streamlit prototype
config/      final frozen experiment configurations
data/        description of required local data
prompts/     final Basic and Safety-focused prompts
results/     compact result tables and figures
src/         experiment and evaluation code
tools/       audit, analysis and figure-generation code
```

## Run the prototype

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\streamlit run app\privacy_summary_verifier.py
```

The prototype requires the local experimental data described in
`data/README.md`. Real API keys must be stored in `.env`; this file is excluded
from Git. `.env.example` lists the required variable names without credentials.

## Reproduce the principal stages

The PowerShell entry points are:

- `run_v12_analysis.ps1` for the contemporary-policy experiment;
- `run_opp115.ps1` for OPP-115 generation, verification and taxonomy mapping;
- `run_current_source_units.ps1` for contemporary source-unit extraction;
- `run_final_coverage.ps1` for final contemporary coverage evaluation;
- `run_dashboard.ps1` for the prototype.

Machine-readable final results are under `results/`. Large intermediate data,
restricted blinding keys, researcher-identifying files and API credentials are
not distributed.

This repository is a research prototype. Its summaries are not legal advice.
