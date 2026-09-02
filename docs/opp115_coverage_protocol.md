# OPP-115 coverage and taxonomy-comparison protocol

## Purpose

This extension measures omission in the 486 OPP summaries without allowing a
predefined taxonomy to determine what Gemini initially treats as important.
It is separate from MiniCheck and sentence-level source alignment.

## Frozen order of work

1. Gemini reads each of the 27 source policies without seeing summaries or the
   OPP-115 taxonomy.
2. Gemini proposes policy-specific information important to an ordinary adult
   reader. Every unit must cite valid source passage IDs; the program retrieves
   the exact evidence.
3. After all 27 sets pass validation, they are consolidated and frozen. The
   freeze records a SHA-256 hash.
4. Each frozen unit is checked against all 18 blinded summaries belonging to
   its policy. Labels are `Covered`, `Partially covered` and `Not covered`.
5. Only after unit freezing may the units be compared with the original
   consolidated OPP-115 annotations. Candidate mappings require researcher
   review; an unmapped unit is not automatically treated as a new taxonomy
   category.

## Commands

Run from `pilot_study`:

```powershell
.\run_opp115.ps1 test-coverage-units
.\run_opp115.ps1 identify-coverage-units
.\run_opp115.ps1 coverage-unit-status
.\run_opp115.ps1 freeze-coverage-units
.\run_opp115.ps1 test-coverage
.\run_opp115.ps1 run-coverage
.\run_opp115.ps1 coverage-status
.\run_opp115.ps1 audit-coverage
.\run_opp115.ps1 prepare-taxonomy-comparison
```

The first and fifth commands spend Gemini quota. All API stages are resumable.
Do not freeze incomplete units, and do not run taxonomy comparison before the
source-unit freeze.

## Metrics

- Strict coverage = `Covered / all units`.
- Weighted coverage = `(Covered + 0.5 × Partially covered) / all units`.
- Omission rate = `Not covered / all units`.

These are reported by policy, model, prompting strategy and prompt version.
The 0.5 partial weight is a transparent scoring convention, not a natural
ground truth.
