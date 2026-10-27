param([switch]$Stop, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
$runtimeDir = Join-Path (Split-Path $projectDir -Parent) 'temp\chainlit-runtime'
$url = 'http://127.0.0.1:8000'
$stateFile = Join-Path $runtimeDir 'service.json'

function Get-ServiceHealth {
    try {
        $info = Invoke-RestMethod "$url/hardware-claw-health" -TimeoutSec 2
        if ($info.service -eq 'hardware-claw-chainlit') { return $info }
    } catch { }
    return $null
}

try {
    New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
    $health = Get-ServiceHealth
    if ($Stop) {
        if (-not $health) { Write-Host 'Agent is not running.'; exit 0 }
        $server = Get-CimInstance Win32_Process -Filter "ProcessId = $($health.pid)"
        $parent = if ($server) { Get-CimInstance Win32_Process -Filter "ProcessId = $($server.ParentProcessId)" }
        $fromProject = $server.ExecutablePath -eq $pythonExe -or ($parent -and $parent.ExecutablePath -eq $pythonExe)
        if (-not $server -or $server.CommandLine -notlike '*chainlit*run*app.py*' -or -not $fromProject) {
            throw 'Process identity mismatch. No process was stopped.'
        }
        Stop-Process -Id $health.pid
        Write-Host 'Agent stopped.'
        exit 0
    }
    if (-not $health) {
        if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Project Python is missing.' }
        $listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
        if ($listener) { throw 'Port 8000 is occupied by another service.' }
        $env:CHAINLIT_APP_ROOT = $runtimeDir
        $env:PYTHONUTF8 = '1'
        $env:PYTHONDONTWRITEBYTECODE = '1'
        $env:LANGSMITH_TRACING = 'false'
        $env:LANGCHAIN_TRACING_V2 = 'false'
        $env:DO_NOT_TRACK = '1'
        New-Item -ItemType Directory -Path (Join-Path $runtimeDir '.chainlit') -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $projectDir 'chainlit-config.toml') -Destination (Join-Path $runtimeDir '.chainlit\config.toml')
        Copy-Item -LiteralPath (Join-Path $projectDir 'chainlit.md') -Destination (Join-Path $runtimeDir 'chainlit.md')
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $outLog = Join-Path $runtimeDir "$stamp-stdout.log"
        $errLog = Join-Path $runtimeDir "$stamp-stderr.log"
        $process = Start-Process -FilePath $pythonExe -ArgumentList '-X utf8 -B -m chainlit run app.py --host 127.0.0.1 --port 8000 --headless' -WorkingDirectory $projectDir -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
        @{launcher_pid=$process.Id; stdout=$outLog; stderr=$errLog} | ConvertTo-Json | Set-Content -LiteralPath $stateFile -Encoding UTF8
        $deadline = (Get-Date).AddSeconds(45)
        do {
            Start-Sleep -Milliseconds 500
            $health = Get-ServiceHealth
            if ($health) { break }
            $process.Refresh()
            if ($process.HasExited) { throw "Agent exited. See $errLog" }
        } while ((Get-Date) -lt $deadline)
        if (-not $health) {
            if (-not $process.HasExited) { Stop-Process -Id $process.Id }
            throw "Startup timed out. See $errLog"
        }
    }
    Write-Host "Agent ready: $url"
    if (-not $NoBrowser) { Start-Process $url }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
