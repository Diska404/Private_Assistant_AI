$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    python -m PyInstaller --noconfirm --windowed --onedir --name Leva --paths app --paths experiments --distpath program --exclude-module numpy --exclude-module pandas --exclude-module torch --exclude-module matplotlib app\main.py
    if ($LASTEXITCODE -ne 0) { throw 'Build gagal. Periksa log PyInstaller.' }
} finally {
    Pop-Location
}
