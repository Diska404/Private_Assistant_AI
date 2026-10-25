param([string]$DistRoot = '')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not $DistRoot) { $DistRoot = Join-Path $taskRoot 'program' }
$taskTools = 'D:\AI\AI Lokal Asisten\build-tools'
$taskBuild = 'D:\AI\AI Lokal Asisten\build'
$taskBinary = Join-Path $DistRoot 'Leva\Leva.exe'
if (Get-Process -Name Leva -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $taskBinary }) {
    throw 'Tutup Leva sebelum membangun ulang program.'
}
if (-not (Test-Path -LiteralPath (Join-Path $taskTools 'PyInstaller'))) {
    throw 'Build tools belum tersedia di D. Lihat APP_README.md.'
}
$taskPreviousPythonPath = $env:PYTHONPATH
Push-Location -LiteralPath $taskRoot
try {
    $env:PYTHONPATH = $taskTools
    $taskNewVoiceData = foreach ($runtimeFile in @('audio_cpp_voice.py','speech_style.py','speech_stream.py')) { '--add-data'; "$taskRoot/app/$runtimeFile;local_voice_runtime" }
    $taskAssistantData = foreach ($runtimeFile in @('feature_worker.py','fooocus_worker.py','web_tools.py','local_mic_worker.py','mic_capture.py','mic_capture_worker.py','local_audio_core.py','speech_turns.py','mic_indicator.py','mic_recovery.py','speech_asr.py','speech_resources.py','location_helper.py','semantic_memory.py','browser_runtime.py','system_controls.py')) { '--add-data'; "$taskRoot/app/$runtimeFile;assistant_runtime" }
    $taskAssistantData += @('--add-data', "$taskRoot/app/remote_speech_worker.py;assistant_runtime")
    $taskAssistantData += @('--add-data', "$taskRoot/app/personal_models.py;assistant_runtime")
    $taskAssistantData += @('--add-data', "$taskRoot/app/comfy_worker.py;assistant_runtime", '--add-data', "$taskRoot/app/image_tensor_io.py;assistant_runtime")
    $taskAssistantData += @('--add-data', "$taskRoot/app/leva_web;leva_web")
    $taskAssistantData += @('--add-data', "$taskRoot/app/capability_workflows.json;.")
    $taskAssistantData += @('--add-data', "$taskRoot/app/capability_sources.json;.")
    python -m PyInstaller --noconfirm --windowed --onedir --name Leva --paths app --paths experiments --distpath $DistRoot --workpath (Join-Path $taskBuild 'work') --specpath $taskBuild --add-data "$taskRoot/app/voice_packs.json;." --add-data "$taskRoot/app/voice_pack_worker.py;local_voice_runtime" --add-data "$taskRoot/app/voice_packs.py;local_voice_runtime" --add-data "$taskRoot/app/seed_voice_adapter.py;local_voice_runtime" --add-data "$taskRoot/app/japanese_voice.py;local_voice_runtime" --add-data "$taskRoot/app/paths.py;local_voice_runtime" @taskAssistantData @taskNewVoiceData --exclude-module numpy --exclude-module pandas --exclude-module torch --exclude-module matplotlib app\main.py
    if ($LASTEXITCODE -ne 0) { throw 'Build gagal. Periksa log PyInstaller.' }
} finally {
    $env:PYTHONPATH = $taskPreviousPythonPath
    Pop-Location
}
