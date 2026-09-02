# Completed v1.2 Methods and Results Record

This file previously contained report placeholders. All experimental, automated, human-evaluation and adjudication stages are now complete. The submission-ready prose is in `outputs/final_report_v12/Verifying_LLM_Generated_Plain_English_Summaries_of_Privacy_Policies.docx`.

## Methods and materials

The controlled within-document study crossed three privacy policies, three model families, three prompting strategies and two matched prompt sets. GPT-5.6 Luna, Llama 3.3 70B Instruct Turbo and Mistral Large 3 generated 54 summaries: 27 basic and 27 safety-focused outputs. The strategies were a zero-shot baseline, role-based prompting and structured-reasoning prompting.

Readability and conciseness were evaluated with word count, Flesch Reading Ease, Flesch-Kincaid Grade, SMOG Grade and word-compression ratio. Source alignment was evaluated bidirectionally. Gemini, MiniCheck and three independent members of the dissertation research team assessed 1,393 frozen summary sentences. The human phase produced 4,179 ratings, with 100 disputed sentence rows adjudicated.

For source-first coverage, the researchers proposed important policy information before reading the summaries. Adjudication froze 165 policy-specific units: 29 for PILOT01, 47 for PILOT02 and 89 for PILOT03. Each researcher and Gemini assessed every unit against all 18 summaries for its policy. This produced 2,970 comparisons per evaluator and 8,910 human ratings. The 475 non-unanimous comparisons were adjudicated.

## Final results

- All 54 summaries, 1,393 sentence assessments and 2,970 final coverage comparisons are complete.
- Final human sentence labels: 1,300 Supported, 87 Partially supported, five Unsupported and one Contradicted.
- Human sentence pairwise exact agreement: 93.8%-96.4%; Cohen's kappa: 0.454-0.590.
- Gemini-human four-class sentence agreement: 92.5%; kappa: 0.233.
- MiniCheck-human binary sentence agreement: 85.9%; kappa: 0.073.
- Final human coverage labels: 1,156 Covered, 793 Partially covered and 1,021 Not covered.
- Human coverage pairwise exact agreement: 87.9%-90.1%; kappa: 0.816-0.849.
- Gemini-human exact coverage agreement: 76.8%; kappa: 0.640; quadratic weighted kappa: 0.820.

Across the 27 matched pairs, safety-focused prompting increased mean strict human coverage by 16.56 percentage points and mean weighted coverage by 13.09 points. Strict coverage improved in 23 pairs, was unchanged in two and declined in two; weighted coverage improved in 25 pairs and declined in two. The intervention also made summaries longer in 24 pairs and reduced Flesch Reading Ease in 19, demonstrating a trade-off between information retention, conciseness and automated readability.

The final interpretation is not that one prompt solved the task. Safety-focused prompting retained more important source information, but usually produced longer and harder-to-read summaries. Automated evaluators were useful for inspection but did not reproduce researcher decisions perfectly, especially on the less balanced sentence-faithfulness task. Evidence-linked human judgement therefore remains necessary for high-stakes legal-information summarisation.
