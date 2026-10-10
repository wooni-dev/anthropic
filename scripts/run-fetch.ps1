<#
  목록 fetch 를 한 번 실행하고 결과를 logs/fetch-YYYY-MM.log 에 덧붙인다.
  fetch 가 새 커밋을 만든 경우에만 GitHub 로 push 한다. (push 실패는 로그만 남기고 넘어간다)
  작업 스케줄러와 수동 실행이 함께 쓴다.  예: .\scripts\run-fetch.ps1
#>
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"

New-Item -ItemType Directory -Force (Join-Path $root "logs") | Out-Null
$log = Join-Path $root ("logs\fetch-" + (Get-Date -Format "yyyy-MM") + ".log")
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::AppendAllText($log, "[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] fetch`n", $utf8)

$before = (git rev-parse HEAD)

# PowerShell 5.1 은 python 의 stderr 를 오류 객체로 감싸므로, 출력 리디렉션은 cmd 에 맡긴다
cmd /c "python -m sync.cli fetch >> `"$log`" 2>&1"
$code = $LASTEXITCODE

if ($code -eq 0 -and (git rev-parse HEAD) -ne $before) {
  # 인증 창이 뜨지 않게 하고, 실패해도 다음 push 때 밀린 커밋이 함께 올라간다
  $env:GIT_TERMINAL_PROMPT = "0"
  cmd /c "git push -q >> `"$log`" 2>&1"
  [IO.File]::AppendAllText($log, "push exit $LASTEXITCODE`n", $utf8)
}
[IO.File]::AppendAllText($log, "exit $code`n`n", $utf8)
exit $code
