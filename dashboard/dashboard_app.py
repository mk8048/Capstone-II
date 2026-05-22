import asyncio
import base64
import json
import os
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime

from flask import Flask, jsonify, redirect, render_template_string, request, url_for

try:
    from nats.aio.client import Client as NATS
except ImportError:
    NATS = None


NATS_URL = os.environ.get("NATS_URL", "nats://127.0.0.1:4222")
MEDIA_URL = os.environ.get("MEDIA_URL", "http://127.0.0.1:8889/cam01/")
TOPICS = [
    "cs.vision.control.detected",
    "cs.llm.control.update",
]
MAX_EVENTS = 100
DEFAULT_CAMERA_LOCATIONS = {
    "cam01": "Lab Entrance",
}

events = deque(maxlen=MAX_EVENTS)
events_by_id = {}
events_lock = threading.Lock()
nats_status = "disconnected"
nats_status_detail = "Waiting for NATS..."

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Dashboard - NATS + Camera</title>
    <style>
        * { box-sizing: border-box; }
        body { background: #0f172a; color: #e2e8f0; font-family: Inter, Arial, sans-serif; margin: 0; }
        header { padding: 22px 24px; background: #111827; border-bottom: 1px solid #334155; }
        h1, h2, h3, p { margin: 0; }
        h1 { font-size: 2rem; }
        h2 { font-size: 1.25rem; margin-bottom: 14px; }
        h3 { font-size: 1rem; margin-bottom: 10px; }
        .small { color: #94a3b8; font-size: 0.92rem; line-height: 1.5; }
        .topline { margin-top: 12px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .pill { display: inline-flex; align-items: center; padding: 6px 10px; border-radius: 999px; background: #334155; color: #cbd5e1; font-size: 0.86rem; }
        .ok { color: #86efac; }
        .container { display: grid; grid-template-columns: minmax(420px, 1fr) minmax(420px, 0.95fr); gap: 20px; padding: 20px; }
        .card { background: #1f2937; border: 1px solid #334155; border-radius: 12px; padding: 18px; box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.05); }
        .video-box { width: 100%; border-radius: 10px; border: 1px solid #334155; overflow: hidden; background: #020617; aspect-ratio: 16 / 9; }
        iframe { width: 100%; height: 100%; border: 0; background: #020617; display: block; }
        button { width: 100%; margin-top: 12px; padding: 11px 14px; border: 0; border-radius: 8px; background: #2563eb; color: white; font-weight: 700; cursor: pointer; }
        button.secondary { background: #475569; }
        .form { margin-top: 14px; }
        .form label { display: block; margin-bottom: 8px; color: #cbd5e1; font-size: 0.9rem; }
        .form input { width: 100%; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; padding: 10px 12px; border-radius: 8px; }
        .events-head { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; margin-bottom: 12px; }
        .event-list { display: grid; gap: 12px; max-height: calc(100vh - 180px); overflow: auto; padding-right: 4px; }
        .event-card { background: #111827; border: 1px solid #334155; border-radius: 10px; padding: 14px; }
        .event-title { display: flex; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
        .event-id { font-weight: 700; color: #f8fafc; word-break: break-word; }
        .subject { color: #93c5fd; font-size: 0.82rem; white-space: nowrap; }
        .grid { display: grid; grid-template-columns: 128px 1fr; gap: 8px 12px; font-size: 0.92rem; }
        .label { color: #94a3b8; }
        .value { color: #e2e8f0; word-break: break-word; }
        .objects { display: flex; gap: 6px; flex-wrap: wrap; }
        .tag { display: inline-flex; padding: 4px 8px; border-radius: 999px; background: #0f766e; color: #ccfbf1; font-size: 0.82rem; }
        .warn { color: #fbbf24; }
        .image-wrap { position: relative; margin-top: 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; overflow: hidden; min-height: 160px; display: grid; place-items: center; }
        .image-wrap img { width: 100%; display: block; }
        .placeholder { padding: 28px 16px; text-align: center; color: #94a3b8; line-height: 1.5; }
        .bbox { position: absolute; border: 2px solid #f59e0b; background: rgba(245, 158, 11, 0.08); }
        .raw { white-space: pre-wrap; word-break: break-word; font-family: Consolas, Menlo, monospace; background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 10px; margin-top: 10px; color: #cbd5e1; font-size: 0.82rem; }
        @media (max-width: 980px) {
            .container { grid-template-columns: 1fr; }
            .event-list { max-height: none; }
        }
    </style>
</head>
<body>
    <header>
        <h1>Dashboard</h1>
        <div class="topline">
            <span class="pill">NATS: <strong id="nats-status" class="ok">{{ nats_status }}</strong></span>
            <span class="pill" id="nats-status-detail">{{ nats_status_detail }}</span>
            <span class="pill">NATS_URL: {{ nats_url }}</span>
            <span class="pill">MEDIA_URL: {{ media_url }}</span>
        </div>
    </header>

    <main class="container">
        <section class="card">
            <h2>카메라 영상</h2>
            <div class="video-box">
                <iframe id="media-iframe" src="about:blank" allow="autoplay; fullscreen" referrerpolicy="no-referrer"></iframe>
            </div>
            <button type="button" onclick="loadMediaStream()">영상 불러오기</button>
            <form class="form" method="post" action="/set-media-url">
                <label for="media_url">MediaMTX WebRTC / HLS URL</label>
                <input id="media_url" name="media_url" type="text" value="{{ media_url }}" />
                <button type="submit" class="secondary">URL 저장</button>
            </form>
            <p class="small" style="margin-top:12px;">페이지를 열 때는 영상 URL을 자동 요청하지 않습니다. 인증 팝업이 필요한 MediaMTX라면 버튼을 눌렀을 때만 요청됩니다.</p>
        </section>

        <section class="card">
            <div class="events-head">
                <h2>실시간 탐지 이벤트</h2>
                <span class="small">최근 <span id="event-count">{{ event_count }}</span>건 / 최대 {{ max_events }}건 <span id="poll-indicator"></span></span>
            </div>
            <div id="event-list" class="event-list"></div>
        </section>
    </main>

    <script>
        const MEDIA_URL = {{ media_url_json|safe }};
        const POLL_INTERVAL_MS = 3000;

        function loadMediaStream() {
            const iframe = document.getElementById("media-iframe");
            if (!MEDIA_URL) {
                alert("MediaMTX 스트림 URL을 먼저 입력하세요.");
                return;
            }
            iframe.src = "about:blank";
            setTimeout(() => { iframe.src = MEDIA_URL; }, 50);
        }

        function escapeHtml(value) {
            return String(value ?? "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#039;");
        }

        function renderImage(event) {
            if (event.image_src) {
                const boxes = (event.bboxes || []).map((box) => {
                    const [x, y, w, h] = box.bbox || [0, 0, 0, 0];
                    return `<div class="bbox" title="${escapeHtml(box.label)}"
                        style="left:${x}%; top:${y}%; width:${w}%; height:${h}%;"></div>`;
                }).join("");
                return `<div class="image-wrap"><img src="${escapeHtml(event.image_src)}" alt="탐지 이미지" />${boxes}</div>`;
            }
            return `<div class="image-wrap"><div class="placeholder">
                탐지 이미지 미수신<br />
                <span class="small">${escapeHtml(event.image_key || "image_url, image_base64, image_key 중 하나가 들어오면 표시됩니다.")}</span>
            </div></div>`;
        }

        function renderEvent(event) {
            const objects = event.objects.length
                ? event.objects.map((obj) => `<span class="tag">${escapeHtml(obj.class_name)} ${escapeHtml(obj.confidence_text)}</span>`).join("")
                : `<span class="warn">미수신</span>`;
            const bboxText = event.bboxes.length
                ? event.bboxes.map((box) => `${box.label}: [${box.raw.join(", ")}]`).join(" / ")
                : "미수신";
            const llmSummary = event.llm_summary || "미수신";

            return `<article class="event-card">
                <div class="event-title">
                    <div class="event-id">${escapeHtml(event.event_id)}</div>
                    <div class="subject">${escapeHtml(event.subject)}</div>
                </div>
                <div class="grid">
                    <div class="label">탐지 시간</div><div class="value">${escapeHtml(event.detected_at || "미수신")}</div>
                    <div class="label">카메라 위치</div><div class="value">${escapeHtml(event.camera_location || "미수신")}</div>
                    <div class="label">탐지 객체 종류</div><div class="value objects">${objects}</div>
                    <div class="label">confidence</div><div class="value">${escapeHtml(event.confidence || "미수신")}</div>
                    <div class="label">bbox 표시</div><div class="value">${escapeHtml(bboxText)}</div>
                    <div class="label">LLM 요약</div><div class="value">${escapeHtml(llmSummary)}</div>
                </div>
                ${renderImage(event)}
                <details>
                    <summary class="small" style="margin-top:10px; cursor:pointer;">원본 NATS payload</summary>
                    <div class="raw">${escapeHtml(JSON.stringify(event.raw_payloads, null, 2))}</div>
                </details>
            </article>`;
        }

        async function pollEvents() {
            const indicator = document.getElementById("poll-indicator");
            try {
                const resp = await fetch("/messages", { cache: "no-store" });
                if (!resp.ok) {
                    indicator.textContent = `(polling failed: ${resp.status})`;
                    return;
                }
                const data = await resp.json();
                document.getElementById("nats-status").textContent = data.nats_status;
                document.getElementById("nats-status-detail").textContent = data.nats_status_detail;
                document.getElementById("event-count").textContent = data.count;
                const list = document.getElementById("event-list");
                list.innerHTML = data.events.length
                    ? data.events.map(renderEvent).join("")
                    : `<div class="event-card small">대기 중입니다. NATS 메시지가 들어오면 탐지 이벤트가 표시됩니다.</div>`;
                indicator.textContent = `(updated ${new Date().toLocaleTimeString()})`;
            } catch (error) {
                indicator.textContent = "(polling error)";
                console.warn(error);
            }
        }

        pollEvents();
        setInterval(pollEvents, POLL_INTERVAL_MS);
    </script>
</body>
</html>
"""


def camera_locations():
    raw = os.environ.get("CAMERA_LOCATIONS")
    if not raw:
        return DEFAULT_CAMERA_LOCATIONS
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return DEFAULT_CAMERA_LOCATIONS
    return {**DEFAULT_CAMERA_LOCATIONS, **parsed}


def iso_now():
    return datetime.now().isoformat(timespec="seconds")


def normalize_bbox_for_display(bbox):
    if not isinstance(bbox, list) or len(bbox) != 4:
        return None
    try:
        x, y, w, h = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return None
    # If the detector sends pixel coordinates, keep a usable rough overlay.
    if max(x, y, w, h) > 1:
        x, y, w, h = x / 640 * 100, y / 360 * 100, w / 640 * 100, h / 360 * 100
    else:
        x, y, w, h = x * 100, y * 100, w * 100, h * 100
    x = max(0, min(100, x))
    y = max(0, min(100, y))
    w = max(0, min(100 - x, w))
    h = max(0, min(100 - y, h))
    return [round(x, 2), round(y, 2), round(w, 2), round(h, 2)]


def image_src_from_payload(payload):
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    image_url = data.get("image_url") or payload.get("image_url")
    if image_url:
        return image_url
    image_base64 = data.get("image_base64") or payload.get("image_base64")
    if image_base64:
        if str(image_base64).startswith("data:"):
            return image_base64
        return "data:image/jpeg;base64," + image_base64
    return None


def image_key_from_payload(payload):
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    return data.get("image_key") or payload.get("image_key")


def extract_objects(payload):
    if not isinstance(payload, dict):
        return []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    objects = data.get("objects")
    if not isinstance(objects, list):
        return []
    extracted = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        confidence = obj.get("confidence")
        confidence_text = "-"
        if isinstance(confidence, (int, float)):
            confidence_text = f"{confidence:.2f}"
        extracted.append(
            {
                "class_name": obj.get("class_name") or obj.get("label") or "unknown",
                "confidence": confidence,
                "confidence_text": confidence_text,
                "bbox": obj.get("bbox"),
            }
        )
    return extracted


def event_id_from_payload(subject, payload):
    if isinstance(payload, dict) and payload.get("event_id"):
        return str(payload["event_id"])
    return f"{subject}:{iso_now()}"


def update_event(subject, payload):
    event_id = event_id_from_payload(subject, payload)
    locations = camera_locations()
    with events_lock:
        event = events_by_id.get(event_id)
        if event is None:
            event = {
                "event_id": event_id,
                "subject": subject,
                "detected_at": None,
                "camera_id": None,
                "camera_location": None,
                "objects": [],
                "confidence": None,
                "image_src": None,
                "image_key": None,
                "bboxes": [],
                "llm_summary": None,
                "raw_payloads": [],
                "received_at": iso_now(),
            }
            events_by_id[event_id] = event
            events.appendleft(event)

        event["subject"] = subject
        event["raw_payloads"].append({"subject": subject, "payload": payload, "received_at": iso_now()})

        if isinstance(payload, dict):
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            camera_id = payload.get("camera_id") or event.get("camera_id")
            event["camera_id"] = camera_id
            event["camera_location"] = (
                payload.get("camera_location")
                or payload.get("location")
                or data.get("camera_location")
                or locations.get(camera_id)
                or camera_id
            )
            event["detected_at"] = payload.get("timestamp") or event.get("detected_at") or event["received_at"]

            objects = extract_objects(payload)
            if objects:
                event["objects"] = objects
                event["bboxes"] = []
                for obj in objects:
                    normalized = normalize_bbox_for_display(obj.get("bbox"))
                    if normalized:
                        event["bboxes"].append(
                            {
                                "label": obj["class_name"],
                                "bbox": normalized,
                                "raw": obj.get("bbox"),
                            }
                        )

            max_confidence = data.get("max_confidence") or payload.get("max_confidence")
            if isinstance(max_confidence, (int, float)):
                event["confidence"] = f"{max_confidence:.2f}"
            elif objects:
                confidences = [obj["confidence"] for obj in objects if isinstance(obj["confidence"], (int, float))]
                if confidences:
                    event["confidence"] = f"{max(confidences):.2f}"

            image_src = image_src_from_payload(payload)
            if image_src:
                event["image_src"] = image_src
            image_key = image_key_from_payload(payload)
            if image_key:
                event["image_key"] = image_key

            summary = data.get("summary") or payload.get("summary")
            if summary:
                event["llm_summary"] = summary

        return event


async def run_nats_listener():
    global nats_status, nats_status_detail

    if NATS is None:
        nats_status = "missing"
        nats_status_detail = "nats-py package not installed"
        print("[ERROR] nats-py package not installed")
        return

    while True:
        nc = NATS()
        try:
            await nc.connect(servers=[NATS_URL])
            nats_status = "connected"
            nats_status_detail = f"Connected to {NATS_URL}"
            print(f"[INFO] NATS connected: {NATS_URL}")

            async def message_handler(msg):
                subject = msg.subject
                data = msg.data.decode("utf-8", errors="replace")
                try:
                    payload = json.loads(data)
                except json.JSONDecodeError:
                    payload = {"message": data}
                update_event(subject, payload)
                print(f"[INFO] received: {subject} -> {payload}")

            for topic in TOPICS:
                await nc.subscribe(topic, cb=message_handler)
                print(f"[INFO] subscribed: {topic}")

            while True:
                await asyncio.sleep(1)

        except Exception as exc:
            nats_status = "disconnected"
            nats_status_detail = str(exc)
            print(f"[ERROR] NATS connection failed: {exc}")
            await asyncio.sleep(3)


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
    with events_lock:
        event_count = len(events)
    return render_template_string(
        HTML_TEMPLATE,
        event_count=event_count,
        max_events=MAX_EVENTS,
        nats_url=NATS_URL,
        media_url=MEDIA_URL,
        media_url_json=json.dumps(MEDIA_URL),
        nats_status=nats_status,
        nats_status_detail=nats_status_detail,
    )


@app.route("/messages", methods=["GET"])
def messages_json():
    with events_lock:
        current = [dict(event) for event in events]
    return jsonify(
        {
            "events": current,
            "count": len(current),
            "max": MAX_EVENTS,
            "nats_status": nats_status,
            "nats_status_detail": nats_status_detail,
        }
    )


@app.route("/set-media-url", methods=["POST"])
def set_media_url():
    global MEDIA_URL
    url = request.form.get("media_url", "").strip()
    if url:
        MEDIA_URL = url
    return redirect(url_for("index"))


if __name__ == "__main__":
    print("[INFO] dashboard_app running...")
    print(f"[INFO] NATS_URL={NATS_URL}")
    print(f"[INFO] MEDIA_URL={MEDIA_URL}")
    start_listener_thread()

    dashboard_url = "http://127.0.0.1:5001"
    try:
        webbrowser.open(dashboard_url)
    except Exception:
        pass

    app.run(host="127.0.0.1", port=5001)
