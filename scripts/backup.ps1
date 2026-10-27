$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $ProjectDir
$PythonBin = $env:NAJDILAB_PYTHON
if (-not $PythonBin) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) { $PythonBin = $PythonCommand.Source }
}
if (-not $PythonBin) { throw 'Python 3.11+ was not found. Set NAJDILAB_PYTHON to the path of python.exe.' }
& $PythonBin scripts\backup.py
