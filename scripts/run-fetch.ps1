<#
  목록 fetch 를 한 번 실행하고 결과를 logs/fetch-YYYY-MM.log 에 덧붙인다.
  작업 스케줄러와 수동 실행이 함께 쓴다.  예: .\scripts\run-fetch.ps1
#>
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"

New-Item -ItemType Directory -Force (Join-Path $root "logs") | Out-Null
$log = Join-Path $root ("logs\fetch-" + (Get-Date -Format "yyyy-MM") + ".log")
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::AppendAllText($log, "[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] fetch`n", $utf8)

# PowerShell 5.1 은 python 의 stderr 를 오류 객체로 감싸므로, 출력 리디렉션은 cmd 에 맡긴다
cmd /c "python -m sync.cli fetch >> `"$log`" 2>&1"
$code = $LASTEXITCODE
[IO.File]::AppendAllText($log, "exit $code`n`n", $utf8)
exit $code
