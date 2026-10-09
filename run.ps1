$ErrorActionPreference = 'Stop'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

$PythonBin = $env:NAJDILAB_PYTHON
if (-not $PythonBin) {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        $PythonBin = $PythonCommand.Source
    } else {
        $BundledPython = 'C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
        if (Test-Path -LiteralPath $BundledPython) { $PythonBin = $BundledPython }
    }
}
if (-not $PythonBin) { throw 'Python 3.11+ was not found. Set NAJDILAB_PYTHON to the path of python.exe.' }
& $PythonBin -m app.server

