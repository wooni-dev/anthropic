<#
  매일 목록 fetch 를 실행하는 작업 스케줄러 작업을 등록한다. 관리자 권한 불필요.
    등록:     .\scripts\register-task.ps1
    시각 변경: .\scripts\register-task.ps1 -Time "21:17"
    해제:     .\scripts\register-task.ps1 -Unregister
#>
param(
  [string]$Time = "09:17",
  [string]$TaskName = "Anthropic Upstream Fetch",
  [switch]$Unregister
)
$ErrorActionPreference = "Stop"

if ($Unregister) {
  if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "해제됨: $TaskName"
  } else {
    Write-Output "등록된 작업 없음: $TaskName"
  }
  return
}

$runner = Join-Path $PSScriptRoot "run-fetch.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
# StartWhenAvailable: PC 가 꺼져 있어 놓친 실행은 다음에 켜졌을 때 따라잡는다
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
  -Description "anthropic.com 글 목록을 upstream/ 에 동기화하고 바뀐 게 있으면 커밋한다." -Force | Out-Null

$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Output "등록됨: $TaskName (매일 $Time, 다음 실행 $($info.NextRunTime))"
