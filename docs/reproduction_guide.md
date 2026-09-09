# Reproduction guide

1. Install requirements.txt.
2. Copy .env.example to .env and add authorised API keys locally.
3. Review config/experiment_settings.yaml and config/FROZEN_MODELS.md.
4. Add source documents using data/README.md.
5. Use src for preprocessing, generation and evaluation.
6. Run notebooks/minicheck_evaluation.ipynb when a GPU is available.
7. Recompute final statistics with src/statistical_analysis.py.
8. Inspect results and the evidence-linked Streamlit prototype.

Successful generations should not be regenerated merely because their quality
is poor. Retries are reserved for documented technical failures.
