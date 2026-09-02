# Frozen analysis plan — v1.2 prompt-intervention study

## Research questions

1. To what extent can the selected LLMs generate plain-English privacy-policy summaries that are readable, concise and aligned with the source?
2. How effectively does safety-focused prompting reduce hallucination, distortion and omission while maintaining readability and conciseness?
3. To what extent do automated evaluator judgements align with researcher judgements when identifying hallucination, distortion and omission?

The wording must not be changed after examining the final human results merely to make the findings appear stronger.

## Design and scope

The completed design contains 54 summaries: three policies × three model families × three prompting strategies × two matched prompt sets. The policies were purposively selected to represent short, medium and long/complex documents. Each safety-focused summary is paired with the basic summary generated from the same policy, model and prompting strategy.

The study is a controlled three-policy case study. It does not support population-wide claims about all privacy policies, LLMs or readers.

## Units of analysis

- Readability, length and compression: summary.
- Hallucination and distortion: frozen summary sentence.
- Omission/coverage: frozen important-source-unit × summary comparison.
- Intervention comparison: matched basic/safety pair within policy × model × strategy (27 pairs).
- Evaluator agreement: identical frozen sentence or source-unit–summary item.

## Outcomes

### Accessibility and conciseness

- words;
- Flesch Reading Ease;
- Flesch–Kincaid Grade;
- SMOG Grade;
- word-compression ratio.

These formula-based measures estimate textual difficulty; they do not demonstrate actual reader comprehension.

### Sentence-level source alignment

- Gemini: Supported, Partially supported, Contradicted and Unsupported;
- failure type: None, Distortion, Hallucination, or Hallucination and distortion;
- MiniCheck: binary predicted support and probability;
- researchers: the same four labels and failure taxonomy as Gemini.

Strict support rate is Supported / all included sentences. Gemini and MiniCheck remain separate measures and must not be averaged into one factuality score.

### Omission/coverage

- Covered;
- Partially covered;
- Not covered.

Strict coverage = Covered / all frozen units. Weighted coverage = (Covered + 0.5 × Partially covered) / all frozen units. Both must be reported because the 0.5 weighting is a transparent analytical convention, not a natural ground truth.

Gemini's current 936 comparisons use Gemini-proposed evidence-valid units and are preliminary. Final automated–human agreement must use the later shared human-adjudicated frozen unit set.

## Quantitative analysis

1. Report counts, means, standard deviations, ranges and category proportions.
2. Report outcomes by prompt set, model family, prompting strategy and policy.
3. For RQ2, calculate safety-focused minus basic differences for all 27 matched pairs.
4. Report mean and median paired differences, ranges, and numbers of positive/zero/negative pairs.
5. Do not treat the 1,393 sentences as 1,393 independent experiments. Sentences are nested within summaries and policies.
6. With only three policies, emphasise descriptive effect size, direction and consistency. Any inferential test must be labelled exploratory and must not be used to claim generalisation to all policies.

## Human reliability and evaluator agreement

Before agreement analysis, every workbook must pass structural validation. Pairwise researcher agreement will include exact agreement and Cohen's kappa for labels and failure types. All non-unanimous decisions will be adjudicated with a final evidence-linked reason.

Gemini will be compared with final human decisions using the original four categories and a strict binary collapse. MiniCheck will be compared only using the binary collapse because it does not produce distortion/hallucination categories. Class distributions and confusion matrices must accompany agreement statistics.

## Qualitative analysis

The written reasons and evidence will support a structured qualitative error analysis. Select illustrative cases across:

- hallucinated material assertions;
- altered certainty, scope, actor, purpose, recipient, condition or exception;
- omitted important information;
- automated-evaluator disagreements;
- cases improved by the safety-focused prompt;
- cases worsened or made unnecessarily longer by the intervention.

Examples must be selected to illustrate recurring patterns, not only dramatic failures. Each case must link the source, summary text, labels and adjudication reason.

## Missing-data rules

- Never regenerate a valid-but-poor summary.
- Technical evaluator failures may be retried and must be logged.
- Invalid evidence quotations must be corrected only by traceable alignment to frozen source/summary text, with an audit note.
- No missing researcher decision may be silently converted to a majority label.
- Human results remain pending until all three independent files are validated.
