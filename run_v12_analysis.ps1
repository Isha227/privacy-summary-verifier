param(
    [ValidateSet("automated", "validate-humans", "prepare-adjudication")]
    [string]$Stage = "automated"
)

$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    Write-Error "The project virtual environment was not found."
    exit 1
}
Set-Location $project
$env:EXPERIMENT_CONFIG = "config/v2_prompt_intervention_v1.2.yaml"

if ($Stage -eq "automated") {
    & $python -m src.validate_v12_gemini
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m src.validate_v12_minicheck "data/v2_prompt_intervention_v1_2/evaluations/minicheck/minicheck_v12_statement_scores_FINAL.csv"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m src.analyse_v12_automated
}
elseif ($Stage -eq "validate-humans") {
    & $python -m src.validate_v12_human_phase1
}
elseif ($Stage -eq "prepare-adjudication") {
    & $python -m src.validate_v12_human_phase1
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -m src.prepare_v12_human_adjudication
}
