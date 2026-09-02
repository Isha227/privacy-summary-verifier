$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "The project virtual environment was not found at $python"
    exit 1
}

Set-Location $project
$env:EXPERIMENT_CONFIG = "config/v2_prompt_intervention_v1.2.yaml"

if ($args.Count -eq 0) {
    Write-Host "Usage: .\run_final_coverage.ps1 validate | test | run | status | analyse"
    exit 0
}

switch ($args[0]) {
    "validate" { & $python -m src.cli validate-v12-final-coverage }
    "test"     { & $python -m src.cli run-v12-final-gemini-coverage --max-batches 1 }
    "run"      { & $python -m src.cli run-v12-final-gemini-coverage }
    "status"   { & $python -m src.cli status-v12-final-coverage }
    "analyse"  { & $python -m src.cli analyse-v12-final-coverage }
    default     { Write-Error "Choose validate, test, run, status, or analyse."; exit 1 }
}
