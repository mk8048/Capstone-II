import base64
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "ministral-3:latest"


def analyze_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "model": MODEL_NAME,
        "prompt": """
이미지를 분석해서 한국어로 답해줘.

반드시 JSON 형식으로만 출력해.

{
  "summary": "이미지 상황 요약",
  "objects": ["주요 객체1", "주요 객체2"],
  "risk_level": "low 또는 medium 또는 high",
  "risk_reason": "위험 판단 이유"
}
""",
        "images": [image_base64],
        "stream": False
    }

    response = requests.post(OLLAMA_URL, json=payload)

    if response.status_code != 200:
        print("Ollama 오류 상태코드:", response.status_code)
        print("Ollama 오류 내용:", response.text)
        raise Exception("Ollama 요청 실패")

    return response.json().get("response", "")