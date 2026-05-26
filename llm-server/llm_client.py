"""Ollama/LLaVA client. Summarizes an image into one English sentence."""

import base64
import json
import time

import requests


OLLAMA_URL = "http://localhost:11434/api/generate"

PROMPT = """
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


def analyze_image_bytes(image_bytes, model_name="llava:7b", ollama_url=OLLAMA_URL):
    """Analyze raw image bytes. Returns (summary, inference_seconds)."""
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    start = time.monotonic()
    response = requests.post(
        ollama_url,
        json={
            "model": model_name,
            "prompt": PROMPT,
            "images": [image_base64],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    inference = time.monotonic() - start

    result = response.json()
    raw_summary = result.get("response", "").strip()
    summary = clean_summary(raw_summary)

    print(f"[llm] inference done model={model_name} duration={inference:.2f}s")
    return summary, inference


def analyze_image(image_path, model_name="llava:7b", ollama_url=OLLAMA_URL):
    """Path-based wrapper kept for the manual debug endpoint."""
    with open(image_path, "rb") as image_file:
        image_bytes = image_file.read()
    summary, _ = analyze_image_bytes(image_bytes, model_name, ollama_url)
    return summary
