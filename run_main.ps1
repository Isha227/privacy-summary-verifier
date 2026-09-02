$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "The project virtual environment was not found at $python"
    exit 1
}

Set-Location $project
$env:EXPERIMENT_CONFIG = "config/main_experiment.yaml"

if ($args.Count -eq 0) {
    Write-Host "Usage: .\run_main.ps1 validate | dry-run | run"
    exit 0
}

switch ($args[0]) {
    "validate" { & $python -m src.cli validate --expected-policies 30 }
    "dry-run"  { & $python -m src.cli run --dry-run }
    "run"      { & $python -m src.cli run }
    default    { Write-Error "Choose validate, dry-run, or run."; exit 1 }
}
