$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir
$PythonBin = $env:NAJDILAB_PYTHON
if (-not $PythonBin) {
    $LocalPython = Join-Path $ProjectDir '.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $LocalPython -PathType Leaf) { $PythonBin = $LocalPython }
    elseif (Test-Path -LiteralPath (Join-Path $ProjectDir '.venv')) {
        throw 'Existing .venv is incomplete; repair it explicitly or select NAJDILAB_PYTHON.'
    }
    else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $PythonCommand) { $PythonCommand = Get-Command python3 -ErrorAction SilentlyContinue }
        if ($PythonCommand) { $PythonBin = $PythonCommand.Source }
    }
}
if (-not $PythonBin) { throw 'Python 3.11+ was not found. Set NAJDILAB_PYTHON to python.exe.' }
& $PythonBin (Join-Path $ProjectDir 'scripts\launch.py')
exit $LASTEXITCODE
