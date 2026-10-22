# Wrapper: arguments are passed literally, independent of the current directory.
$ErrorActionPreference = 'Stop'
$pythonPath = if ($env:DBRAIN_PYTHON) { $env:DBRAIN_PYTHON } else { Join-Path $PSScriptRoot '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $pythonPath)) {
    $pythonPath = Join-Path $PSScriptRoot '.venv/bin/python'
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Ambiente ausente. Consulte Sistema\README.md para instalar.'
}
$env:PYTHONUTF8 = '1'
# Progress goes to stderr. Under 'Stop', Windows PowerShell turns redirected native
# stderr (2>&1, as agents capture output) into a terminating error mid-update.
$ErrorActionPreference = 'Continue'
& $pythonPath (Join-Path $PSScriptRoot 'Sistema\dbrain.py') @args
exit $LASTEXITCODE
