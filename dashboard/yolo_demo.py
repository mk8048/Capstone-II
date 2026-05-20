# 사진 받고 yolo에서 분석후 좌표와 이미지 설명 띄워주는 코드 



import os
import sys
import subprocess
import base64
import webbrowser
import cv2
import boto3

from ultralytics import YOLO
from flask import Flask
from botocore.client import Config

# ==============================
# 설정
# ==============================

IMAGE_PATH = "C:/test_img/test_img.jpeg"
YOLO_MODEL_PATH = "yolov8n.pt"

BUCKET_NAME = "yolo-results"
OBJECT_NAME = "detected_result.jpg"

# ==============================
# MinIO 연결
# ==============================

print("[INFO] MinIO 연결 중...")

s3 = boto3.client(
    "s3",
    endpoint_url="http://localhost:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
    config=Config(signature_version="s3v4")
)

# 버킷 확인
try:
    s3.head_bucket(Bucket=BUCKET_NAME)
except Exception:
    s3.create_bucket(Bucket=BUCKET_NAME)
    print(f"[INFO] '{BUCKET_NAME}' 버킷 생성 완료")

# ==============================
# YOLO 분석
# ==============================

print("[INFO] YOLO 분석 시작...")

model = YOLO(YOLO_MODEL_PATH)

results = model(IMAGE_PATH)

annotated_img = results[0].plot()

# 객체 이름 및 좌표 추출
detections = []

if results[0].boxes is not None and len(results[0].boxes) > 0:
    for box, cls_id in zip(results[0].boxes.xyxy.tolist(), results[0].boxes.cls.tolist()):
        name = model.names[int(cls_id)]
        x1, y1, x2, y2 = [int(v) for v in box]
        detections.append({
            "name": name,
            "coords": (x1, y1, x2, y2)
        })

# 결과 이미지 저장
cv2.imwrite(OBJECT_NAME, annotated_img)

print("[INFO] 탐지 객체:", [d["name"] for d in detections])

# ==============================
# MinIO 업로드
# ==============================

print("[INFO] MinIO 업로드 중...")

s3.upload_file(OBJECT_NAME, BUCKET_NAME, OBJECT_NAME)

# presigned url 생성
image_url = s3.generate_presigned_url(
    "get_object",
    Params={
        "Bucket": BUCKET_NAME,
        "Key": OBJECT_NAME
    },
    ExpiresIn=3600
)

print("[INFO] 이미지 URL 생성 완료")

# ==============================
# Flask 웹서버
# ==============================

app = Flask(__name__)

@app.route("/")
def home():

    if detections:
        detected = ", ".join(sorted({d["name"] for d in detections}))
        detection_list = "".join(
            f"<li><strong>{d['name']}</strong>: ({d['coords'][0]}, {d['coords'][1]}) → ({d['coords'][2]}, {d['coords'][3]})</li>"
            for d in detections
        )
    else:
        detected = "none"
        detection_list = "<li>감지된 객체가 없습니다.</li>"

    return f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <title>YOLO 분석 결과</title>

        <style>
            body {{
                background-color: #111827;
                color: white;
                font-family: Arial;
                padding: 40px;
            }}

            img {{
                width: 800px;
                border-radius: 10px;
                border: 3px solid #333;
            }}

            .box {{
                background: #1f2937;
                padding: 20px;
                border-radius: 10px;
                margin-top: 20px;
            }}

            ul {{
                margin: 0;
                padding-left: 20px;
            }}

            li {{
                line-height: 1.8;
            }}
        </style>

    </head>

    <body>

        <h1>YOLO 객체 탐지 결과</h1>

        <div class="box">
            <img src="{image_url}">
        </div>

        <div class="box">
            <h2>탐지 객체</h2>
            <p>{detected}</p>
            <ul>
                {detection_list}
            </ul>
        </div>

    </body>
    </html>
    """

# ==============================
# 서버 실행
# ==============================

url = "http://127.0.0.1:5000"

print(f"[완료] 서버 실행 중 → {url}")

# 자동 브라우저 실행
webbrowser.open(url)

app.run(host="127.0.0.1", port=5000)
