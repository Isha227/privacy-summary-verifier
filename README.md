# Privacy Summary Verifier

Code and final derived results for the MSc AI dissertation **Verifying
LLM-Generated Plain-English Summaries of Privacy Policies**.

## What this study does

The study asks whether privacy policies can be summarised in accessible plain
English while preserving their source information. It compares:

- GPT, Llama and Mistral;
- zero-shot, role-based and structured prompting;
- Basic and Safety-focused prompt versions;
- readability, conciseness, sentence source alignment and information coverage.

The experiment contains 30 policies and 540 summaries. Twenty-seven historical
policies come from OPP-115. Three contemporary consumer-technology policies
receive additional independent researcher evaluation.

The 27-policy OPP-115 subset supports the inferential comparisons. The three
contemporary policies provide the human-validation study and a matched
taxonomy comparison; their results are not pooled into those significance
tests.

## Start here

| If you want to… | Open… |
|---|---|
| Understand the study | docs/methodology.md |
| Understand the labels | docs/evaluation_labels.md |
| Read the findings | results/README.md |
| Reproduce the workflow | docs/reproduction_guide.md |
| Explore the prototype | docs/prototype_guide.md |

## Repository structure

- app — Streamlit evidence explorer.
- config — frozen experiment and model settings.
- prompts — Basic, Safety-focused and evaluator prompts.
- src — generation, evaluation and analysis code.
- notebooks — MiniCheck GPU notebook.
- results — final, reader-friendly result tables and figures.
- docs — method, labels and reproduction guidance.
- data — local-data structure only; restricted data are not published.
- tests — automated checks.

## Run the prototype

Create a virtual environment, install requirements, then run:

    streamlit run app/privacy_summary_verifier.py

The full evidence explorer requires the derived local data described in
data/README.md. API keys belong only in a local .env file. No summary in this
repository is legal advice.
