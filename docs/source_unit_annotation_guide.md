# Pilot source-information-unit annotation guide

## Purpose

Identify the important privacy information present in each source policy before
examining any generated summary. These agreed source units later form the
coverage denominator. They are not summary claims and must not be inferred from
what a model happened to write.

## Frozen pilot categories

| Code | Category |
|---|---|
| C1 | Data Collection & Sources |
| C2 | Purpose & Legal Basis |
| C3 | Data Sharing & Recipients |
| C4 | Data Retention |
| C5 | User Rights & Controls |
| C6 | Tracking, Profiling & Automated Processing |
| C7 | International Transfers |
| C8 | Data Security |
| C9 | Contact, Complaints & Policy Administration |

Children/specific audiences, sensitive data, consent, cookies, advertising,
policy changes, and business closure are conditional subtopics within the most
appropriate category; do not create extra top-level categories during the
pilot.

## What counts as one unit

A unit is one independently scorable proposition whose omission or distortion
would remove meaningful privacy information. Write it as a short factual
sentence. Split propositions when a summary could reasonably preserve one but
omit another.

Example source:

> We retain transaction records for seven years where financial law requires.

Recommended unit:

`Transaction records are retained for seven years where financial law requires.`

Do not split `seven years` or the legal condition into separate units; record
them in `material_qualifiers` because they determine whether later coverage is
full or partial.

Example source:

> We collect your email and precise location to create your account and provide
> location-based recommendations.

Possible units:

- Email address is collected to create/manage an account.
- Precise location is collected to provide location-based recommendations.

## Annotation rules

1. Read only the cleaned source file assigned to the policy.
2. Work independently; do not compare lists until all three are complete.
3. Include only information explicitly stated in the frozen source.
4. Preserve meaningful scope, purpose, recipient, duration, exception, and
   condition in `material_qualifiers`.
5. Use semantic propositions, not copied paragraphs or broad topic labels.
6. Do not create a unit merely because a category could have appeared.
7. A statement that information is not collected/shared is still a unit.
8. Put evidence in `source_quote_or_locator`; keep quotations short and use a
   heading plus distinctive phrase where possible.
9. Use provisional IDs such as `A1-C1-U01`, where `A1` identifies the annotator.
10. Do not open anonymised summaries or the blinding key during this task.

## Independent workflow

Each researcher makes a personal copy of each `source_units_PILOT*.csv`, adding
their anonymised annotator code to the filename—for example,
`source_units_PILOT01_A1.csv`. Do not overwrite another researcher’s file.

Recommended order: annotate `PILOT01`, compare only after everyone finishes it,
clarify the guide if necessary, then independently annotate `PILOT02` and
`PILOT03`. Record all rule changes in the pilot decision log.

## Adjudication

After independent work, align equivalent units in
`source_unit_adjudication.csv`. Mark each row `unanimous`, `boundary disagreement`,
`category disagreement`, `wording disagreement`, or `unique unit`. Discuss and
record the decision and rationale. Assign final IDs such as `P01-C1-U01` only
after agreement. The adjudicated list—not any one researcher’s list—is used to
score summary coverage.

## Later 0/1/2 coverage scoring

- `2`: essential meaning and all material qualifiers are preserved accurately.
- `1`: core meaning is present but a meaningful qualifier, scope, condition, or
  detail is lost.
- `0`: absent, materially distorted, or contradicted.

Do not score summaries yet. First finish and freeze the source-unit lists.
