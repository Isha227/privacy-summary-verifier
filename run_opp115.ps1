$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "The project virtual environment was not found at $python"
    exit 1
}

Set-Location $project
$env:EXPERIMENT_CONFIG = "config/opp115_extension_v1.0.yaml"
$env:OPP115_COVERAGE_PROFILE = "opp115_coverage"

if ($args.Count -eq 0) {
    Write-Host "Usage: .\run_opp115.ps1 freeze-check | validate | dry-run | test-providers | run | status | freeze-outputs | verify-output-freeze | evaluate | anonymise | prepare-faithfulness | test-gemini-faithfulness | run-gemini-faithfulness | gemini-faithfulness-status | build-minicheck-colab | test-coverage-units | identify-coverage-units | coverage-unit-status | freeze-coverage-units | test-coverage | run-coverage | coverage-status | audit-coverage | test-coverage-units-v3 | identify-coverage-units-v3 | coverage-unit-status-v3 | freeze-coverage-units-v3 | test-coverage-v3 | run-coverage-v3 | coverage-status-v3 | audit-coverage-v3 | prepare-taxonomy-comparison | prepare-taxonomy-v3 | test-taxonomy-v3 | run-taxonomy-v3 | taxonomy-status-v3 | audit-taxonomy-v3 | analyse-taxonomy-v3 | analyse-taxonomy-thresholds"
    exit 0
}

switch ($args[0]) {
    "freeze-check"   { & $python tools\validate_opp115_freeze.py }
    "validate"       { & $python -m src.cli validate --expected-policies 27 }
    "dry-run"        { & $python -m src.cli run --dry-run }
    "test-providers" { & $python -m src.cli test-providers }
    "run"            { & $python -m src.cli run }
    "status"          {
        $log = Join-Path $project "data\opp115\experiment\logs\generation_log.csv"
        if (-not (Test-Path -LiteralPath $log)) {
            Write-Host "No generation log yet: 0 / 486 successful"
        }
        else {
            $rows = Import-Csv -LiteralPath $log
            $latest = $rows | Sort-Object timestamp_utc | Group-Object policy_id, model_family, prompt_strategy, replicate | ForEach-Object { $_.Group[-1] }
            $successful = @($latest | Where-Object status -eq "success").Count
            $failed = @($latest | Where-Object status -ne "success").Count
            Write-Host "Latest conditions: success=$successful / 486; failed=$failed; remaining=$((486 - $successful))"
        }
    }
    "freeze-outputs"  { & $python tools\freeze_opp115_outputs.py }
    "verify-output-freeze" { & $python tools\freeze_opp115_outputs.py --verify-only }
    "evaluate"       { & $python -m src.cli evaluate }
    "anonymise"      { & $python -m src.cli anonymise }
    "prepare-faithfulness" { & $python -m src.cli prepare-faithfulness }
    "test-gemini-faithfulness" { & $python -m src.cli run-gemini-batched-faithfulness --max-batches 1 }
    "run-gemini-faithfulness" { & $python -m src.cli run-gemini-batched-faithfulness }
    "gemini-faithfulness-status" {
        $claimsPath = Join-Path $project "data\opp115\experiment\faithfulness\prepared\claim_candidates.csv"
        $resultsPath = Join-Path $project "data\opp115\experiment\evaluations\faithfulness\gemini_claim_scores_batched__gemini-3.5-flash-lite__source-passage-ids-v2.csv"
        $total = if (Test-Path -LiteralPath $claimsPath) { @(Import-Csv -LiteralPath $claimsPath | Where-Object include -eq "yes").Count } else { 0 }
        $complete = if (Test-Path -LiteralPath $resultsPath) {
            @(Import-Csv -LiteralPath $resultsPath | Where-Object status -eq "success" | Sort-Object blind_id,claim_id -Unique).Count
        } else { 0 }
        Write-Host "Gemini source-passage evidence claims: $complete / $total complete; remaining=$($total - $complete)"
    }
    "build-minicheck-colab" { & $python -m src.build_opp115_minicheck_colab }
    "test-coverage-units" { & $python -m src.opp115_coverage identify-units --max-policies 1 }
    "identify-coverage-units" { & $python -m src.opp115_coverage identify-units }
    "coverage-unit-status" { & $python -m src.opp115_coverage unit-status }
    "freeze-coverage-units" { & $python -m src.opp115_coverage freeze-units }
    "test-coverage" { & $python -m src.opp115_coverage score --max-summaries 1 }
    "run-coverage" { & $python -m src.opp115_coverage score }
    "coverage-status" { & $python -m src.opp115_coverage status }
    "audit-coverage" { & $python -m src.opp115_coverage audit }
    "test-coverage-units-v3" { $env:OPP115_COVERAGE_PROFILE = "opp115_coverage_v3"; & $python -m src.opp115_coverage identify-units --max-policies 1 }
    "identify-coverage-units-v3" { $env:OPP115_COVERAGE_PROFILE = "opp115_coverage_v3"; & $python -m src.opp115_coverage identify-units }
    "coverage-unit-status-v3" { $env:OPP115_COVERAGE_PROFILE = "opp115_coverage_v3"; & $python -m src.opp115_coverage unit-status }
    "freeze-coverage-units-v3" { $env:OPP115_COVERAGE_PROFILE = "opp115_coverage_v3"; & $python -m src.opp115_coverage freeze-units }
    "test-coverage-v3" { $env:OPP115_COVERAGE_PROFILE = "opp115_coverage_v3"; & $python -m src.opp115_coverage score --max-summaries 1 }
    "run-coverage-v3" { $env:OPP115_COVERAGE_PROFILE = "opp115_coverage_v3"; & $python -m src.opp115_coverage score }
    "coverage-status-v3" { $env:OPP115_COVERAGE_PROFILE = "opp115_coverage_v3"; & $python -m src.opp115_coverage status }
    "audit-coverage-v3" { $env:OPP115_COVERAGE_PROFILE = "opp115_coverage_v3"; & $python -m src.opp115_coverage audit }
    "prepare-taxonomy-comparison" { & $python -m src.opp115_taxonomy }
    "prepare-taxonomy-v3" { & $python -m src.taxonomy_v3_mapping prepare }
    "test-taxonomy-v3" { & $python -m src.taxonomy_v3_mapping run --max-batches 1 }
    "run-taxonomy-v3" { & $python -m src.taxonomy_v3_mapping run }
    "taxonomy-status-v3" { & $python -m src.taxonomy_v3_mapping status }
    "audit-taxonomy-v3" { & $python -m src.taxonomy_v3_mapping audit }
    "analyse-taxonomy-v3" { & $python .\tools\analyse_taxonomy_v3.py }
    "analyse-taxonomy-thresholds" { & $python .\tools\analyse_opp_threshold_sensitivity.py }
    default           { Write-Error "Choose a command shown by running .\run_opp115.ps1 with no arguments."; exit 1 }
}
