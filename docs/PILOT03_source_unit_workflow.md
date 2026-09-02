# PILOT03 independent source-unit annotation

## Files

- A1 completes `source_units_PILOT03_A1.csv`.
- A2 completes `source_units_PILOT03_A2.csv`.
- A3 completes `source_units_PILOT03_A3.csv`.
- All annotators use the frozen source `data/pilot/clean/PILOT03.txt`.

Work independently. Do not inspect another annotator's file until all three are
complete. Add one row per distinct privacy information unit. The starter row is
only a blank template and may be completed as the first unit.

## What counts as one unit

A unit should express one independently scorable privacy proposition. Split a
sentence or bullet when it contains materially different information about:

- the data collected;
- the source or collection method;
- the purpose of processing;
- sharing or recipients;
- retention;
- security;
- user rights or choices;
- international transfers;
- children;
- policy changes or contact details.

Keep necessary qualifiers with the proposition, including words such as
`may`, `if`, `when`, `for as long as`, named services, exceptions, and regional
limits. Do not create units for promotional language, navigation text, licence
notices, or repeated statements that add no material detail.

## PILOT03 cautions

This is the long/complex policy. Work section by section and preserve the
Automattic service-specific distinctions. Do not collapse every example into a
separate unit, but retain an example when it changes what data, purpose,
recipient, right, or condition is communicated. A single broad unit should not
combine several independently scorable practices merely to reduce the count.

## Required fields

- `annotator_id`: keep the assigned A1, A2, or A3 value.
- `policy_id`: always `PILOT03`.
- `unit_id`: use the pattern `A1-C1-U01`, changing annotator, category, and
  sequence as appropriate.
- `category`: use the frozen coverage codebook category (`C1`, `C2`, etc.).
- `source_section`: copy the nearest policy heading.
- `source_quote_or_locator`: record a short distinctive source phrase.
- `information_unit`: paraphrase the single proposition faithfully.
- `material_qualifiers`: preserve conditions and limitations needed for fair
  scoring; leave blank only when none apply.
- `notes`: optional annotation uncertainty or cross-reference.

Before declaring completion, confirm every row has an annotator ID, policy ID,
unit ID, category, source section, locator, and information unit.
