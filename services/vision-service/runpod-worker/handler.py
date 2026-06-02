"""RunPod serverless worker handler — deploy this to RunPod, NOT to Azure.

Build with:
    docker build -t <yourdockerhub>/mealtracker-vision-worker:latest .
    docker push  <yourdockerhub>/mealtracker-vision-worker:latest

Then in the RunPod console:
    1. Create a Serverless Endpoint
    2. Point it at this image, with a GPU type that fits your model
       (an RTX A4000 / L4 is fine for most VL models in the 7-13B range)
    3. Copy the endpoint URL + API key into RUNPOD_ENDPOINT_URL /
       RUNPOD_API_KEY env vars on the vision-service Container App.

The contract this worker MUST honour (matches what `vision-service` expects):

INPUT  event["input"] = {
    "image_base64": "...JPEG/PNG base64...",
    "locale": "en"
}
OUTPUT (return value) = {
    "predictions": [
        {"label": str, "confidence": float in [0,1], "estimated_grams": float | None},
        ...
    ],
    "model_version": "string identifying the model+weights",
    "inference_ms": int
}
"""
from __future__ import annotations

import base64
import io
import time

import runpod
from PIL import Image


# ─────────────────────────────────────────────────────────────────────────────
# Model loading — DO THIS ONCE AT COLD START
# ─────────────────────────────────────────────────────────────────────────────
# Replace this stub with whatever model you actually want to use:
#   - A fine-tuned CLIP / SigLIP
#   - LLaVA / MiniCPM-V / Qwen2-VL prompted to enumerate foods
#   - A specialised food-recognition model from HuggingFace
#
# Example with a HuggingFace vision-language model:
#
#     from transformers import AutoProcessor, AutoModelForVision2Seq
#     processor = AutoProcessor.from_pretrained("HuggingFaceM4/idefics2-8b")
#     model = AutoModelForVision2Seq.from_pretrained(
#         "HuggingFaceM4/idefics2-8b",
#         torch_dtype="auto",
#         device_map="auto",
#     )

MODEL_VERSION = "stub-0.0"


def _predict(image: Image.Image, locale: str) -> list[dict]:
    """Replace with real inference. Stub returns a fixed answer."""
    return [
        {"label": "grilled chicken breast", "confidence": 0.82, "estimated_grams": 180},
        {"label": "white rice cooked",      "confidence": 0.74, "estimated_grams": 150},
        {"label": "broccoli",               "confidence": 0.61, "estimated_grams": 80},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Handler
# ─────────────────────────────────────────────────────────────────────────────

def handler(event: dict) -> dict:
    started = time.monotonic()
    inp = event.get("input") or {}
    b64 = inp.get("image_base64")
    locale = inp.get("locale", "en")
    if not b64:
        return {"error": "Missing image_base64"}

    try:
        image_bytes = base64.b64decode(b64)
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        return {"error": f"Bad image: {e}"}

    predictions = _predict(image, locale)
    return {
        "predictions": predictions,
        "model_version": MODEL_VERSION,
        "inference_ms": int((time.monotonic() - started) * 1000),
    }


runpod.serverless.start({"handler": handler})
