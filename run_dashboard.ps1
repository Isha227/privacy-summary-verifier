$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "The project virtual environment was not found at $python"
    exit 1
}

Set-Location $project
& $python -m streamlit run app/privacy_summary_verifier.py
