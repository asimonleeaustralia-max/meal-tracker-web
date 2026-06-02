"""Meal photo metadata + SAS URL issuance.

Strategy: clients upload bytes directly to Azure Blob Storage using a
short-lived SAS URL we mint here. They then PATCH the photo row with the
final blob_name so the meal-service knows where to find it.

This keeps the API process from streaming megabytes of JPEG data.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.schemas import MealPhoto as MealPhotoSchema, MealPhotoCreate

from .config import Settings, get_settings
from .deps import current_user_id, get_db
from .models import Meal, MealPhoto

router = APIRouter(prefix="/photos", tags=["photos"])


class SasUploadResponse(BaseModel):
    photo_id: uuid.UUID
    blob_name: str
    upload_url: str
    expires_at: datetime


def _generate_sas_url(blob_name: str, settings: Settings) -> tuple[str, datetime]:
    """Mint a write-only SAS URL for a single blob."""
    if not settings.blob_account_url:
        # Dev mode: return a fake URL so the contract is exercised without Azure
        expires = datetime.now(timezone.utc) + timedelta(minutes=settings.blob_sas_ttl_minutes)
        return f"http://local-dev/blob/{blob_name}", expires

    # Lazy import so dev runs without the Azure SDK if it isn't installed
    from azure.storage.blob import (
        BlobSasPermissions,
        generate_blob_sas,
    )

    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.blob_sas_ttl_minutes)
    account_name = settings.blob_account_url.split("//", 1)[1].split(".", 1)[0]

    if settings.blob_account_key:
        sas = generate_blob_sas(
            account_name=account_name,
            container_name=settings.blob_container,
            blob_name=blob_name,
            account_key=settings.blob_account_key,
            permission=BlobSasPermissions(write=True, create=True),
            expiry=expires,
        )
        url = f"{settings.blob_account_url}/{settings.blob_container}/{blob_name}?{sas}"
        return url, expires

    # If running with managed identity in Azure, use user-delegation SAS instead.
    # That requires an authenticated BlobServiceClient; left as TODO for prod.
    raise HTTPException(
        status_code=500,
        detail="Blob storage not configured for SAS minting (set BLOB_ACCOUNT_KEY or wire up MI).",
    )


@router.post("/upload-url", response_model=SasUploadResponse)
async def request_upload_url(
    payload: MealPhotoCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
    settings: Settings = Depends(get_settings),
) -> SasUploadResponse:
    # Verify the meal exists and belongs to this user
    meal = await db.get(Meal, payload.meal_id)
    if meal is None or meal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Meal not found")

    photo_id = payload.id or uuid.uuid4()
    blob_name = f"{user_id}/{payload.meal_id}/{photo_id}.jpg"

    photo = MealPhoto(
        id=photo_id,
        meal_id=payload.meal_id,
        user_id=user_id,
        width=payload.width,
        height=payload.height,
        file_name_original=payload.file_name_original,
        file_name_upload=payload.file_name_upload,
        byte_size_original=payload.byte_size_original,
        byte_size_upload=payload.byte_size_upload,
        sha256=payload.sha256,
        latitude=payload.latitude,
        longitude=payload.longitude,
        blob_name=blob_name,
    )
    db.add(photo)
    await db.flush()

    url, expires = _generate_sas_url(blob_name, settings)
    return SasUploadResponse(
        photo_id=photo_id, blob_name=blob_name, upload_url=url, expires_at=expires
    )


@router.get("/by-meal/{meal_id}", response_model=list[MealPhotoSchema])
async def list_photos_for_meal(
    meal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[MealPhotoSchema]:
    meal = await db.get(Meal, meal_id)
    if meal is None or meal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Meal not found")
    rows = (
        (await db.execute(select(MealPhoto).where(MealPhoto.meal_id == meal_id)))
        .scalars()
        .all()
    )
    return [MealPhotoSchema.model_validate(r) for r in rows]


@router.delete("/{photo_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_photo(
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> None:
    photo = await db.get(MealPhoto, photo_id)
    if photo is None or photo.user_id != user_id:
        raise HTTPException(status_code=404, detail="Photo not found")
    # Note: we don't delete the blob bytes here — schedule a janitor job in prod.
    await db.delete(photo)