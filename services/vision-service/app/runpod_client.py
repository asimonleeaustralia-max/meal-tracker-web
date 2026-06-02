"""Thin async client for RunPod serverless endpoints.

RunPod's serverless API has two flavours:
  * /runsync  → blocks up to ~30s, returns the result inline
  * /run      → returns {id}, then poll /status/{id} until COMPLETED

The expected response shape from the worker (you control this when you
build the RunPod image) is a JSON object:
{
  "output": {
    "predictions": [
      {"label": "grilled chicken breast", "confidence": 0.91, "estimated_grams": 180},
      {"label": "white rice cooked",      "confidence": 0.84, "estimated_grams": 120}
    ],
    "model_version": "food-vl-2025-04-1",
    "inference_ms": 412
  }
}
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import Settings

log = logging.getLogger(__name__)


class RunPodError(RuntimeError):
    pass


class RunPodClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._headers = {
            "Authorization": f"Bearer {settings.runpod_api_key}",
            "Content-Type": "application/json",
        }

    @property
    def configured(self) -> bool:
        return bool(self._settings.runpod_endpoint_url and self._settings.runpod_api_key)

    async def analyze(self, image_base64: str, locale: str = "en") -> dict[str, Any]:
        if not self.configured:
            if self._settings.allow_stub_mode:
                return self._stub_response()
            raise RunPodError("RunPod endpoint not configured")

        payload = {"input": {"image_base64": image_base64, "locale": locale}}

        if self._settings.runpod_async:
            return await self._run_async(payload)
        return await self._run_sync(payload)

    async def _run_sync(self, payload: dict[str, Any]) -> dict[str, Any]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(min=1, max=8),
            retry=retry_if_exception_type((httpx.HTTPError, RunPodError)),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(
                    timeout=self._settings.runpod_timeout_seconds
                ) as client:
                    resp = await client.post(
                        self._settings.runpod_endpoint_url,
                        headers=self._headers,
                        json=payload,
                    )
                    if resp.status_code >= 500:
                        raise RunPodError(f"RunPod 5xx: {resp.status_code}")
                    resp.raise_for_status()
                    body = resp.json()
                    if body.get("status") not in {"COMPLETED", "ok", None}:
                        # /runsync returns the worker output directly without status
                        # but some endpoints wrap it
                        if "output" not in body:
                            raise RunPodError(f"Unexpected RunPod body: {body}")
                    return body.get("output") or body
        raise RunPodError("RunPod call failed after retries")

    async def _run_async(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = self._settings.runpod_endpoint_url
        # /run derives from .../runsync just by swapping the verb
        run_url = base.replace("/runsync", "/run")
        status_url_tmpl = base.replace("/runsync", "/status/{job_id}").replace(
            "/run", "/status/{job_id}"
        )

        async with httpx.AsyncClient(timeout=self._settings.runpod_timeout_seconds) as client:
            r = await client.post(run_url, headers=self._headers, json=payload)
            r.raise_for_status()
            job = r.json()
            job_id = job.get("id")
            if not job_id:
                raise RunPodError(f"RunPod /run missing job id: {job}")

            for _ in range(self._settings.runpod_max_poll_attempts):
                await asyncio.sleep(self._settings.runpod_poll_interval_seconds)
                s = await client.get(
                    status_url_tmpl.format(job_id=job_id), headers=self._headers
                )
                s.raise_for_status()
                body = s.json()
                status = body.get("status")
                if status == "COMPLETED":
                    return body.get("output") or {}
                if status in {"FAILED", "CANCELLED", "TIMED_OUT"}:
                    raise RunPodError(f"RunPod job {status}: {body.get('error')}")
        raise RunPodError(f"RunPod job {job_id} did not complete in time")

    @staticmethod
    def _stub_response() -> dict[str, Any]:
        """Used when RUNPOD_* is unset and ALLOW_STUB_MODE is true."""
        return {
            "predictions": [
                {
                    "label": "grilled chicken breast",
                    "confidence": 0.82,
                    "estimated_grams": 180,
                },
                {
                    "label": "white rice cooked",
                    "confidence": 0.74,
                    "estimated_grams": 150,
                },
                {"label": "broccoli", "confidence": 0.61, "estimated_grams": 80},
            ],
            "model_version": "stub-0.0",
            "inference_ms": 0,
        }
