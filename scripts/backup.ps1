$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $ProjectDir
$PythonBin = $env:NAJDILAB_PYTHON
if (-not $PythonBin) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) { $PythonBin = $PythonCommand.Source }
    else { $PythonBin = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' }
}
& $PythonBin scripts\backup.py
