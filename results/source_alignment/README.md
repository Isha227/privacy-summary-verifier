# Sentence source-alignment results

The per-summary alignment measures for all 540 summaries are columns in
../summary_quality/all_540_summaries.csv:

- gemini_support_rate;
- gemini_weighted_alignment;
- distortion_rate;
- hallucination_rate;
- minicheck_mean_probability.

Model-level averages appear in ../summary_quality/results_by_model.csv.
Inferential tests for these outcomes appear in ../statistics.

Item-level evidence is deliberately not duplicated here. It is displayed by
the local prototype, where the source passage, label and explanation remain
linked to the correct summary sentence.
