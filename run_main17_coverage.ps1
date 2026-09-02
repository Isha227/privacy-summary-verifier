param(
    [int]$MaxBatches = 1
)

$env:EXPERIMENT_CONFIG = "config/main_faithfulness.yaml"
$ProjectPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $ProjectPython)) {
    Write-Error "Project Python was not found at $ProjectPython. Create the .venv before running coverage."
    exit 1
}

& $ProjectPython -m src.cli validate-coverage
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& $ProjectPython -m src.cli run-gemini-coverage --max-batches $MaxBatches
exit $LASTEXITCODE
