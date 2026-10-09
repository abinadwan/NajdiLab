$root = 'C:\Users\Admin\AppData\Local\hermes\NajdiLab'

# لا تشغّل نسخة ثانية إذا NajdiLab شغال
$running = Get-NetTCPConnection -LocalPort 8770 -State Listen -ErrorAction SilentlyContinue
if ($running) {
    exit 0
}

Set-Location $root
& "$root\run.ps1"
