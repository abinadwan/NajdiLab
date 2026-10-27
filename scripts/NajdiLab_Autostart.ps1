$ProjectDir = Split-Path -Parent $PSScriptRoot

# Do not start a second instance if NajdiLab is already listening.
$running = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue
if ($running) {
    exit 0
}

Set-Location -LiteralPath $ProjectDir
& (Join-Path $ProjectDir 'run.ps1')
