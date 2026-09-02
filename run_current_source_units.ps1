$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "The project virtual environment was not found at $python"
    exit 1
}

Set-Location $project
$env:EXPERIMENT_CONFIG = "config/v2_prompt_intervention_v1.2.yaml"

if ($args.Count -eq 0) {
    Write-Host "Usage: .\run_current_source_units.ps1 test | run | status | freeze | test-v3 | run-v3 | status-v3 | freeze-v3"
    exit 0
}

switch ($args[0]) {
    "test"   { & $python -m src.contemporary_source_unit_validation identify --policy-id PILOT01 }
    "run"    { & $python -m src.contemporary_source_unit_validation identify }
    "status" { & $python -m src.contemporary_source_unit_validation status }
    "freeze" { & $python -m src.contemporary_source_unit_validation freeze }
    "test-v3"   { & $python -m src.contemporary_source_unit_validation --prompt-version v3 identify --policy-id PILOT01 }
    "run-v3"    { & $python -m src.contemporary_source_unit_validation --prompt-version v3 identify }
    "status-v3" { & $python -m src.contemporary_source_unit_validation --prompt-version v3 status }
    "freeze-v3" { & $python -m src.contemporary_source_unit_validation --prompt-version v3 freeze }
    default   { Write-Error "Choose test, run, status or freeze"; exit 1 }
}
