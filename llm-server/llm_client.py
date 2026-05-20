import base64
import requests


OLLAMA_URL = "http://localhost:11434/api/generate"


def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def analyze_image(image_path, model_name="llava:7b"):
    image_base64 = encode_image_to_base64(image_path)

    prompt = """
이미지를 분석해서 상황을 한 문장으로 요약해줘.
응답은 설명만 자연어로 작성해줘.
도로 위 흰색 줄무늬가 보이면 '보도부'가 아니라 '횡단보도'라고 표현해.
JSON 형식으로 쓰지 마.
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": model_name,
            "prompt": prompt,
            "images": [image_base64],
            "stream": False
        },
        timeout=120
    )

    response.raise_for_status()

    result = response.json()
    summary = result.get("response", "").strip()

    return summary
