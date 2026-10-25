param([switch]$NoBrowser)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskData='D:\AI\AI Lokal Asisten\Leva\evaluation\asr-lab'
$taskUrl='http://127.0.0.1:8771/'
$taskRunning=$false
try { $taskState=Invoke-RestMethod ($taskUrl+'api/state') -TimeoutSec 2; $taskRunning=($null -ne $taskState.model_ready) } catch { }
if (-not $taskRunning) {
    New-Item -ItemType Directory -Path $taskData -Force | Out-Null
    $taskPython=(Get-Command python).Source
    $taskScript=Join-Path $PSScriptRoot 'asr_lab.py'
    $taskProcess=Start-Process -FilePath $taskPython -ArgumentList @('-B',('"{0}"' -f $taskScript)) -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskData 'server.stdout.log') -RedirectStandardError (Join-Path $taskData 'server.stderr.log') -PassThru
    $taskProcess.Id | Set-Content -LiteralPath (Join-Path $taskData 'server.pid')
    for ($taskAttempt=0; $taskAttempt -lt 20; $taskAttempt++) {
        try { $taskState=Invoke-RestMethod ($taskUrl+'api/state') -TimeoutSec 1; $taskRunning=$true; break } catch { Start-Sleep -Milliseconds 200 }
    }
    if (-not $taskRunning) { throw 'ASR Lab belum merespons. Periksa server.stderr.log di folder data.' }
}
if (-not $NoBrowser) { Start-Process $taskUrl }
Write-Output $taskUrl
