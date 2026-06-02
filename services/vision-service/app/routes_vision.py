"""Vision analysis endpoints.

POST /vision/analyze       → call RunPod with image bytes
POST /vision/analyze-meal  → one-shot: call RunPod then nutrition-service,
                              return a payload the iOS app can drop straight
                              into the Meal form.
"""
from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mealtracker_shared.schemas import (
    NutrientValues,
    VisionAnalyzeRequest,
    VisionAnalyzeResponse,
    VisionPrediction,
)

from .config import Settings, get_settings
from .deps import current_user, current_user_id
from .runpod_client import RunPodClient, RunPodError

_bearer_passthrough = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/vision", tags=["vision"])


def _get_client(settings: Settings = Depends(get_settings)) -> RunPodClient:
    return RunPodClient(settings)


@router.post(
    "/analyze",
    response_model=VisionAnalyzeResponse,
    dependencies=[Depends(current_user)],
)
async def analyze(
    payload: VisionAnalyzeRequest,
    client: RunPodClient = Depends(_get_client),
) -> VisionAnalyzeResponse:
    started = time.monotonic()
    try:
        output = await client.analyze(payload.image_base64, payload.locale or "en")
    except RunPodError as e:
        raise HTTPException(status_code=502, detail=f"Vision backend error: {e}") from e

    preds_raw = output.get("predictions", [])
    predictions = [VisionPrediction(**p) for p in preds_raw]
    return VisionAnalyzeResponse(
        predictions=predictions,
        model_version=output.get("model_version", "unknown"),
        inference_ms=int(output.get("inference_ms", (time.monotonic() - started) * 1000)),
    )


# ---------------- combined vision + nutrition convenience endpoint ----------------

@router.post(
    "/analyze-meal",
    dependencies=[Depends(current_user)],
)
async def analyze_meal(
    payload: VisionAnalyzeRequest,
    settings: Settings = Depends(get_settings),
    client: RunPodClient = Depends(_get_client),
    user_id=Depends(current_user_id),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_passthrough),
) -> dict:
    """Run the photo through the vision model AND resolve the nutrition values
    for each label in one call.  Saves the client an extra round trip.

    Returns:
      {
        "predictions":   [VisionPrediction, …],
        "model_version": "...",
        "inference_ms":  412,
        "nutrition":     {"foods": [...], "misses": [...]}  # per-100g values
      }
    """
    started = time.monotonic()
    try:
        output = await client.analyze(payload.image_base64, payload.locale or "en")
    except RunPodError as e:
        raise HTTPException(status_code=502, detail=f"Vision backend error: {e}") from e
    preds = [VisionPrediction(**p) for p in output.get("predictions", [])]

    nutrition: dict = {"foods": [], "misses": []}
    if preds and creds is not None:
        labels = [p.label for p in preds]
        async with httpx.AsyncClient(timeout=10) as nc:
            try:
                r = await nc.post(
                    f"{settings.nutrition_service_url}/nutrition/lookup",
                    json={"labels": labels},
                    headers={"Authorization": f"Bearer {creds.credentials}"},
                )
                r.raise_for_status()
                nutrition = r.json()
            except httpx.HTTPError:
                nutrition = {"foods": [], "misses": labels}

    return {
        "predictions": [p.model_dump() for p in preds],
        "model_version": output.get("model_version", "unknown"),
        "inference_ms": int(output.get("inference_ms", (time.monotonic() - started) * 1000)),
        "nutrition": nutrition,
    }
