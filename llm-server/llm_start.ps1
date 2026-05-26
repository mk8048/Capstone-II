# llm-server/llm_start.ps1
# LLM Server(NATS-driven)를 띄우는 헬퍼.
# Vision 탐지 이벤트(cs.vision.control.detected)를 구독 -> MinIO 프레임을 LLaVA로 요약
# -> cs.llm.control.update 발행. Ctrl+C로 종료.
#
# 사용: PowerShell에서 `.\llm_start.ps1`
# (실행 정책 막히면: `powershell -ExecutionPolicy Bypass -File .\llm_start.ps1`)

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
Set-Location $scriptDir

# --- 0. 이미 실행 중이면 중복 실행 방지 ---
# `python ... main.py` 프로세스가 있으면 두 번째 인스턴스를 띄우지 않는다.
# (같은 durable consumer를 공유하면 메시지를 나눠 가져가 버린다)
$existing = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'main\.py' }
if ($existing) {
    $pids = ($existing.ProcessId) -join ', '
    Write-Warning "[start] LLM Server already running (PID=$pids). Not starting a second instance."
    Write-Host "[start] To restart: Stop-Process -Id $pids -Force; then run this script again."
    exit 0
}

# --- 1. Python 결정 (.venv 있으면 우선, 없으면 PATH의 python) ---
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonPath = $venvPython
} else {
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $pythonPath = $pyCmd.Source
    } else {
        Write-Error "python not found. Install Python or create .venv: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
        exit 1
    }
}
Write-Host "[start] python=$pythonPath"

# --- 2. .env 확인 (MINIO_SECRET_KEY 등 필요) ---
if (-not (Test-Path (Join-Path $scriptDir ".env"))) {
    Write-Warning "[start] .env not found. Copy .env.example to .env and fill MINIO_SECRET_KEY."
}

# --- 3. SSH 터널 확인 (NATS 4222 / MinIO 9000) ---
# NATS / MinIO는 main-server(VM)에 떠 있고, 이 PC는 SSH 터널로 포워딩해서 붙는다.
# 포트가 안 잡혀 있으면 자동으로 터널을 올린다. (Vision Server vision_start.ps1과 동일)
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
        ssh -fN -L 4222:localhost:4222 -L 9000:localhost:9000 $tunnelHost -i $tunnelKey `
            -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10
        for ($i = 0; $i -lt 10; $i++) {
            Start-Sleep -Milliseconds 500
            $natsUp  = Test-NetConnection 127.0.0.1 -Port 4222 -InformationLevel Quiet -WarningAction SilentlyContinue
            $minioUp = Test-NetConnection 127.0.0.1 -Port 9000 -InformationLevel Quiet -WarningAction SilentlyContinue
            if ($natsUp -and $minioUp) { break }
        }
        if ($natsUp -and $minioUp) {
            Write-Host "[start] SSH tunnel ready (NATS 4222 / MinIO 9000)"
        } else {
            Write-Warning "[start] tunnel ports not up after 5s (NATS=$natsUp MinIO=$minioUp); continuing anyway"
        }
    }
}

# --- 4. Ollama 확인/기동 (11434) ---
# 이미 떠 있으면 그대로 쓰고(종료 시 안 건드림), 없으면 이 스크립트가 띄운다.
# $ollamaProc 가 채워지면 = 우리가 띄운 것 → 서버 종료 시 같이 정리.
$ollamaProc = $null
$ollamaUp = Test-NetConnection 127.0.0.1 -Port 11434 -InformationLevel Quiet -WarningAction SilentlyContinue
if ($ollamaUp) {
    Write-Host "[start] Ollama already up (11434) — leaving it running on exit"
} else {
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($ollamaCmd) {
        $ollamaExe = $ollamaCmd.Source
    } else {
        $ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
    }
    if (-not (Test-Path $ollamaExe)) {
        Write-Warning "[start] ollama not found ($ollamaExe). Install Ollama, then: ollama pull llava:7b"
    } else {
        Write-Host "[start] Ollama not up; starting 'ollama serve'..."
        $ollamaProc = Start-Process $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden -PassThru
        for ($i = 0; $i -lt 20; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-NetConnection 127.0.0.1 -Port 11434 -InformationLevel Quiet -WarningAction SilentlyContinue) { break }
        }
        if (Test-NetConnection 127.0.0.1 -Port 11434 -InformationLevel Quiet -WarningAction SilentlyContinue) {
            Write-Host "[start] Ollama ready (PID=$($ollamaProc.Id))"
        } else {
            Write-Warning "[start] Ollama not ready after 10s; continuing anyway"
        }
    }
}

# --- 5. LLM Server foreground 실행 + 정리 ---
# 주의: main-server가 먼저 떠 있어야 JetStream stream(CAPSTONE_EVENTS)이 존재한다.
#       없으면 LLM Server가 stream 생길 때까지 3초마다 재시도한다.
# SSH 터널(NATS/MinIO)은 공유 인프라라 종료 시 그대로 둔다.
Write-Host ""
Write-Host "[start] starting LLM Server (Ctrl+C to stop)"
Write-Host ""
try {
    & $pythonPath -u main.py
} finally {
    # 이 스크립트가 띄운 Ollama만 정리 (기존에 떠 있던 건 안 건드림)
    if ($ollamaProc -and -not $ollamaProc.HasExited) {
        Write-Host ""
        Write-Host "[start] stopping Ollama (PID=$($ollamaProc.Id)) started by this script..."
        Stop-Process -Id $ollamaProc.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "[start] done"
}
