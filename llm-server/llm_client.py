import base64
import json
import requests


OLLAMA_URL = "http://localhost:11434/api/generate"


def encode_image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def clean_summary(text):
    text = text.strip()

    # LLaVA가 JSON처럼 답했을 때 처리
    try:
        parsed = json.loads(text)

        if isinstance(parsed, dict):
            if "summary" in parsed:
                return parsed["summary"]
            if "상황" in parsed:
                return parsed["상황"]

        return str(parsed)

    except json.JSONDecodeError:
        return text


def analyze_image(image_path, model_name="llava:7b"):
    image_base64 = encode_image_to_base64(image_path)

    prompt = """
    Analyze the image and describe the situation in one natural English sentence.

    Rules:
    - Output only one sentence
    - Do not use JSON
    - Do not use braces {}
    - Do not list items
    - Do not guess locations or city names
    - Describe only visible people, vehicles, and road situations
    - If crosswalk lines are visible, use the word "crosswalk"
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
    raw_summary = result.get("response", "").strip()

    summary = clean_summary(raw_summary)

    return summary
