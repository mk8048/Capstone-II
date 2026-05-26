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

# --- 2c. SSH 터널 확인 (NATS 4222 / MinIO 9000) ---
# NATS / MinIO는 main-server(VM)에 떠 있고, 이 PC는 SSH 터널로 포워딩해서 붙는다.
# 포트가 안 잡혀 있으면 자동으로 터널을 올린다.
$tunnelHost = "ubuntu@210.109.82.57"
$tunnelKey  = "C:\projects\.ssh\keypairsw.pem"

$natsUp  = Test-NetConnection 127.0.0.1 -Port 4222 -InformationLevel Quiet -WarningAction SilentlyContinue
$minioUp = Test-NetConnection 127.0.0.1 -Port 9000 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($natsUp -and $minioUp) {
    Write-Host "[start] SSH tunnel already up (NATS 4222 / MinIO 9000)"
} else {
    if (-not (Test-Path $tunnelKey)) {
        Write-Warning "[start] SSH key not found at $tunnelKey; NATS/MinIO will be unavailable"
    } else {
        Write-Host "[start] SSH tunnel down; establishing -> $tunnelHost ..."
        # -fN: 인증 후 백그라운드로 포크하고 명령 안 실행. accept-new: 첫 접속 시 호스트키 자동 신뢰(프롬프트 방지)
        ssh -fN -L 4222:localhost:4222 -L 9000:localhost:9000 $tunnelHost -i $tunnelKey `
            -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10
        # 포트 올라올 때까지 대기 (최대 5초)
        for ($i = 0; $i -lt 10; $i++) {
            Start-Sleep -Milliseconds 500
            $natsUp  = Test-NetConnection 127.0.0.1 -Port 4222 -InformationLevel Quiet -WarningAction SilentlyContinue
            $minioUp = Test-NetConnection 127.0.0.1 -Port 9000 -InformationLevel Quiet -WarningAction SilentlyContinue
            if ($natsUp -and $minioUp) { break }
        }
        if ($natsUp -and $minioUp) {
            Write-Host "[start] SSH tunnel ready (NATS 4222 / MinIO 9000)"
        } else {
            Write-Warning "[start] tunnel ports not up after 5s (NATS=$natsUp MinIO=$minioUp); continuing (RTSP stream still works)"
        }
    }
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

# --- 5b. LAN IP 자동 감지 + Dashboard에 넣을 URL 표시 ---
# UDP "connect" 트릭: 실제 전송은 없고, OS가 default route 인터페이스를 선택해줌
# → WSL 가상 인터페이스 / 루프백 자동 제외
$lanIp = $null
try {
    $sock = New-Object System.Net.Sockets.Socket('InterNetwork', 'Dgram', 'Udp')
    $sock.Connect('8.8.8.8', 80)
    $lanIp = $sock.LocalEndPoint.Address.ToString()
    $sock.Close()
} catch {
    $lanIp = $null
}

# .env에서 CAMERA_ID 추출 (없으면 cam01)
$cameraId = "cam01"
$envFile = Join-Path $scriptDir ".env"
if (Test-Path $envFile) {
    $line = Get-Content $envFile | Where-Object { $_ -match "^\s*CAMERA_ID\s*=" } | Select-Object -First 1
    if ($line) {
        $cameraId = ($line -split "=", 2)[1].Trim()
    }
}

Write-Host ""
if ($lanIp) {
    Write-Host "[start] Vision PC LAN IP: $lanIp"
    Write-Host "[start] MEDIA_URL:"
    Write-Host "        http://${lanIp}:8889/${cameraId}/"
} else {
    Write-Warning "[start] LAN IP 자동 감지 실패. ipconfig로 수동 확인 필요"
}
Write-Host ""

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
