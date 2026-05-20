
import asyncio
import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from collections import deque
from datetime import datetime

from flask import Flask, redirect, render_template_string, request, url_for

try:
    from nats.aio.client import Client as NATS
except ImportError:
    NATS = None

# -----------------------------
# 설정
# -----------------------------

NATS_URL = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
MEDIA_URL = os.environ.get("MEDIA_URL", "http://127.0.0.1:8889/cam01/")
MAIN_SERVER_URL = os.environ.get("MAIN_SERVER_URL", "http://127.0.0.1:8000")
TOPICS = [
    "cs.vision.control.detected",
    "cs.llm.control.update",
]
MAX_MESSAGES = 100
INITIAL_LOAD_LIMIT = 20

messages = deque(maxlen=MAX_MESSAGES)
messages_lock = threading.Lock()
nats_status = "disconnected"
nats_status_detail = "Waiting for NATS..."

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Dashboard - NATS + MediaMTX</title>
    <style>
        body { background: #0f172a; color: #e2e8f0; font-family: Inter, Arial, sans-serif; margin: 0; padding: 0; }
        header { padding: 24px; background: #111827; border-bottom: 1px solid #334155; }
        .container { display: grid; grid-template-columns: 1.3fr 0.7fr; gap: 20px; padding: 20px; }
        .card { background: #1f2937; border: 1px solid #334155; border-radius: 16px; padding: 18px; box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.05); }
        h1, h2, h3 { margin: 0 0 12px 0; }
        .small { color: #94a3b8; font-size: 0.95rem; }
        .badge { display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; background: #334155; border-radius: 999px; font-size: 0.88rem; }
        .status-vision { background: #0f766e; }
        .status-llm { background: #2563eb; }
        .table { width: 100%; border-collapse: collapse; }
        .table th, .table td { padding: 12px 10px; text-align: left; vertical-align: top; border-bottom: 1px solid #334155; }
        .table th { color: #cbd5e1; font-weight: 600; }
        .json-block { white-space: pre-wrap; word-break: break-word; font-family: Menlo, monospace; background: #111827; border: 1px solid #334155; border-radius: 10px; padding: 12px; font-size: 0.92rem; max-height: 280px; overflow: auto; }
        .video-box { width: 100%; border-radius: 16px; border: 1px solid #334155; overflow: hidden; }
        video, iframe { width: 100%; height: 320px; background: black; display: block; }
        .footer { margin-top: 20px; color: #94a3b8; font-size: 0.92rem; }
        .form input { width: 100%; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; padding: 10px 12px; border-radius: 10px; margin-top: 8px; }
        button, .form button { margin-top: 12px; width: 100%; padding: 10px 14px; border: none; border-radius: 10px; background: #2563eb; color: white; font-weight: 600; cursor: pointer; }
        button.secondary { background: #475569; }
        .pill { display: inline-block; padding: 6px 10px; border-radius: 999px; background: #334155; margin-right: 8px; margin-bottom: 8px; }
    </style>
</head>
<body>
    <header>
        <h1>Dashboard</h1>
        <p class="small">NATS 구독 + MediaMTX 스트림 표시용 테스트 페이지입니다. 환경 변수로 <code>NATS_URL</code> / <code>MEDIA_URL</code> 설정 가능.</p>
        <p class="small">NATS 상태: <strong>{{ nats_status }}</strong> / {{ nats_status_detail }}</p>
    </header>
    <div class="container">
        <section class="card">
            <h2>실시간 메시지</h2>
            <p class="small">최근 {{ message_count }}건 / 최대 {{ max_messages }}건</p>
            <div class="json-block">
{{ message_html }}
            </div>
        </section>
        <section class="card">
            <h2>MediaMTX 스트림</h2>
            <div class="video-box">
                <iframe
                    id="media-iframe"
                    src="{{ media_url }}"
                    allow="autoplay; fullscreen"
                    referrerpolicy="no-referrer"
                ></iframe>
            </div>
            <button type="button" class="secondary" onclick="loadMediaStream()">스트림 다시 불러오기</button>
            <div class="footer">
                <div class="pill">NATS_URL: {{ nats_url }}</div>
                <div class="pill">MEDIA_URL: {{ media_url }}</div>
                <div class="pill">MAIN_SERVER: {{ main_server_url }}</div>
            </div>
            <form class="form" method="post" action="/set-media-url">
                <label for="media_url">MediaMTX 스트림 URL</label>
                <input id="media_url" name="media_url" type="text" value="{{ media_url }}" />
                <button type="submit">저장</button>
            </form>
            <div class="footer">
                <p class="small">MediaMTX에서 WebRTC나 HLS URL을 제공하면 여기에서 즉시 확인할 수 있습니다.</p>
            </div>
        </section>
    </div>
    <script>
        function loadMediaStream() {
            const iframe = document.getElementById("media-iframe");
            const mediaUrl = {{ media_url_json|safe }};

            if (!mediaUrl) {
                alert("MediaMTX 스트림 URL을 먼저 입력하세요.");
                return;
            }

            // Cache-bust by re-assigning the same src; iframe forces a reload.
            iframe.src = "about:blank";
            setTimeout(() => { iframe.src = mediaUrl; }, 50);
        }
    </script>
</body>
</html>
"""


def format_message(entry):
    timestamp = entry.get("timestamp") or entry.get("received_at")
    if isinstance(timestamp, float):
        timestamp = datetime.fromtimestamp(timestamp).isoformat()
    safe_topic = entry.get("subject", "-")
    source = entry.get("payload", {}).get("source") if isinstance(entry.get("payload"), dict) else None
    source_label = source or entry.get("source") or "unknown"
    lines = []
    lines.append(f"[{timestamp}] {safe_topic} | source={source_label}")
    lines.append(json.dumps(entry.get("payload"), ensure_ascii=False, indent=2))
    return "\n".join(lines)


def append_message(subject, payload):
    """NATS/API에서 들어온 이벤트를 messages에 추가. event_id 기준 중복 skip."""
    event_id = payload.get("event_id") if isinstance(payload, dict) else None
    with messages_lock:
        if event_id:
            for existing in messages:
                if isinstance(existing.get("payload"), dict) and existing["payload"].get("event_id") == event_id:
                    return
        messages.appendleft({
            "subject": subject,
            "payload": payload,
            "received_at": datetime.now().isoformat(),
        })


def fetch_initial_events():
    """앱 시작 시 main-server에서 과거 이벤트(N건) 가져와 messages에 채움."""
    url = f"{MAIN_SERVER_URL}/events?limit={INITIAL_LOAD_LIMIT}"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            events = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[WARN] main-server 과거 이벤트 로드 실패: {exc}")
        return

    # API는 최신순(occurred_at DESC). 오래된 게 deque 아래쪽으로 가도록 reversed로 appendleft.
    for event in reversed(events):
        synthetic_payload = {
            **event,
            "source": "history",
            "timestamp": event.get("occurred_at"),
        }
        append_message("api.history.event", synthetic_payload)
    print(f"[INFO] main-server 과거 이벤트 {len(events)}건 로드 (from {MAIN_SERVER_URL})")


async def run_nats_listener():
    global nats_status, nats_status_detail

    if NATS is None:
        nats_status = "missing"
        nats_status_detail = "nats-py package not installed"
        print("[ERROR]")
        return

    while True:
        nc = NATS()
        try:
            await nc.connect(servers=[NATS_URL])
            nats_status = "connected"
            nats_status_detail = f"Connected to {NATS_URL}"
            print(f"[INFO] NATS에 연결됨: {NATS_URL}")

            async def message_handler(msg):
                subject = msg.subject
                data = msg.data.decode("utf-8", errors="replace")
                try:
                    payload = json.loads(data)
                except Exception:
                    payload = data
                append_message(subject, payload)
                print(f"[INFO] 수신: {subject} -> {payload}")

            for topic in TOPICS:
                await nc.subscribe(topic, cb=message_handler)
                print(f"[INFO] 구독 시작: {topic}")

            while True:
                await asyncio.sleep(1)

        except Exception as exc:
            nats_status = "disconnected"
            nats_status_detail = str(exc)
            print(f"[ERROR] NATS 연결 실패: {exc}")
            await asyncio.sleep(3)
            continue


def start_listener_thread():
    def _worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_nats_listener())
        finally:
            loop.close()

    thread = threading.Thread(target=_worker, daemon=True, name="nats-listener")
    thread.start()
    time.sleep(0.5)


@app.route("/", methods=["GET"])
def index():
    with messages_lock:
        current_messages = list(messages)

    rendered_messages = "\n\n---\n\n".join(format_message(entry) for entry in current_messages)
    if not rendered_messages:
        rendered_messages = "대기 중입니다... NATS 서버와 연결 후 메시지가 표시됩니다."

    return render_template_string(
        HTML_TEMPLATE,
        message_count=len(current_messages),
        max_messages=MAX_MESSAGES,
        message_html=rendered_messages,
        nats_url=NATS_URL,
        media_url=MEDIA_URL,
        media_url_json=json.dumps(MEDIA_URL),
        main_server_url=MAIN_SERVER_URL,
        nats_status=nats_status,
        nats_status_detail=nats_status_detail,
    )


@app.route("/set-media-url", methods=["POST"])
def set_media_url():
    global MEDIA_URL
    url = request.form.get("media_url", "").strip()
    if url:
        MEDIA_URL = url
    return redirect(url_for("index"))


if __name__ == "__main__":
    print("[INFO] dashboard_app 실행 중...")
    print(f"[INFO] NATS_URL={NATS_URL}")
    print(f"[INFO] MAIN_SERVER_URL={MAIN_SERVER_URL}")
    print(f"[INFO] MEDIA_URL={MEDIA_URL}")
    start_listener_thread()
    fetch_initial_events()

    dashboard_url = "http://127.0.0.1:5001"
    try:
        webbrowser.open(dashboard_url)
    except Exception:
        pass

    app.run(host="127.0.0.1", port=5001)
