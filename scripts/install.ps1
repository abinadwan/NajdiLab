param([switch]$Check)
$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $PSScriptRoot
$PythonBin = $env:NAJDILAB_PYTHON
if (-not $PythonBin) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) { $PythonCommand = Get-Command python3 -ErrorAction SilentlyContinue }
    if ($PythonCommand) { $PythonBin = $PythonCommand.Source }
}
if (-not $PythonBin) { throw 'Python 3.11+ is required. Set NAJDILAB_PYTHON to python.exe.' }
$SetupArgs = @((Join-Path $ProjectDir 'scripts\install.py'))
if ($Check) { $SetupArgs += '--check' }
& $PythonBin @SetupArgs
exit $LASTEXITCODE
