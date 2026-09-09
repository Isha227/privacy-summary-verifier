# Code guide

The command-line entry point is cli.py. The modules are grouped conceptually
below so readers do not need to infer the workflow from filenames.

## Prepare and generate

- preprocess.py and refine_main_cleaning.py — clean source documents.
- providers.py and runner.py — call the three model providers and log outputs.
- anonymise.py — replace experimental conditions with blind identifiers.

## Evaluate accessibility

- evaluate.py — word counts, readability and compression.
- analyse_textstat_readability.py and analyse_source_readability.py — supporting
  readability analysis.

## Verify sentence source alignment

- v2_statements.py — split summaries into evaluable statements.
- v2_statement_verifier.py and run_v12_gemini.py — Gemini evidence-linked
  verification.
- faithfulness.py and validate_v12_minicheck.py — faithfulness preparation and
  MiniCheck validation.

## Verify information coverage

- v2_source_units.py — identify important source information.
- v2_coverage_verifier.py and run_v12_gemini_coverage.py — assess whether units
  are retained in summaries.
- v12_final_coverage.py and analyse_human_coverage.py — final researcher and
  Gemini coverage analysis.

## Analyse taxonomy and final results

- opp115_taxonomy.py and taxonomy_v3_mapping.py — map extracted units to the
  OPP-115 taxonomy.
- statistical_analysis.py — recompute the final 30-policy statistical results.

Files retaining version markers are frozen research artefacts. Renaming those
internal modules would weaken traceability between the code, audit logs and
methodology. Reader-facing applications, prompts and result files use plain
descriptive names.
