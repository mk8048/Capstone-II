# vision-server/start.ps1
# 한 번에 MediaMTX + Vision Server 띄우는 헬퍼.
# Ctrl+C로 Vision Server 종료 시 MediaMTX도 같이 정리한다.
#
# 사용: PowerShell에서 `.\start.ps1`
# (실행 정책 막히면: `powershell -ExecutionPolicy Bypass -File .\start.ps1`)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
Set-Location $scriptDir

# --- 1. MediaMTX 바이너리 위치 (winget 기본 경로 fallback) ---
$mediamtxCmd = Get-Command mediamtx -ErrorAction SilentlyContinue
if ($mediamtxCmd) {
    $mediamtxPath = $mediamtxCmd.Source
} else {
    $mediamtxPath = "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\bluenviron.mediamtx_Microsoft.Winget.Source_8wekyb3d8bbwe\mediamtx.exe"
}
if (-not (Test-Path $mediamtxPath)) {
    Write-Error "mediamtx not found. Install: winget install bluenviron.mediamtx"
    exit 1
}

# --- 2. Vision Server 파이썬 (.venv) ---
$pythonPath = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    Write-Error ".venv not found at $pythonPath. Run: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# --- 2b. ffmpeg path 명시 (PATH가 없는 셸에서도 동작하도록) ---
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpegCmd) {
    $env:FFMPEG_PATH = $ffmpegCmd.Source
} else {
    $ffmpegFallback = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg_*" -Filter "ffmpeg.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($ffmpegFallback) {
        $env:FFMPEG_PATH = $ffmpegFallback.FullName
    } else {
        Write-Warning "ffmpeg not found; stream publish will fail. Install: winget install Gyan.FFmpeg"
    }
}
if ($env:FFMPEG_PATH) {
    Write-Host "[start] FFMPEG_PATH=$($env:FFMPEG_PATH)"
}

# --- 3. 기존 MediaMTX 있으면 정리 ---
$existing = Get-Process mediamtx -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[start] MediaMTX already running (PID=$($existing.Id)), restarting..."
    $existing | Stop-Process -Force
    Start-Sleep -Milliseconds 500
}

# --- 4. MediaMTX 백그라운드 launch ---
Write-Host "[start] launching MediaMTX..."
$mediamtxProc = Start-Process -FilePath $mediamtxPath `
    -WorkingDirectory $scriptDir `
    -RedirectStandardOutput "$scriptDir\mediamtx.log" `
    -RedirectStandardError "$scriptDir\mediamtx.err.log" `
    -WindowStyle Hidden -PassThru
Write-Host "[start] MediaMTX PID=$($mediamtxProc.Id) log=mediamtx.log"

# --- 5. MediaMTX 포트 listen 대기 (RTSP 8554) ---
$ready = $false
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Milliseconds 500
    $test = Test-NetConnection 127.0.0.1 -Port 8554 -InformationLevel Quiet -WarningAction SilentlyContinue
    if ($test) { $ready = $true; break }
}
if ($ready) {
    Write-Host "[start] MediaMTX ready (RTSP 8554)"
} else {
    Write-Warning "[start] MediaMTX 8554 not listening after 5s; continuing anyway"
}

# --- 6. Vision Server foreground 실행 + finally cleanup ---
Write-Host "[start] starting Vision Server (Ctrl+C to stop both)"
Write-Host ""
try {
    & $pythonPath -u -m app.main
} finally {
    Write-Host ""
    Write-Host "[start] cleaning up MediaMTX (PID=$($mediamtxProc.Id))..."
    if (-not $mediamtxProc.HasExited) {
        Stop-Process -Id $mediamtxProc.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[start] done"
}
