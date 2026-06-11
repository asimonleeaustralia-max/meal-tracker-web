"""Meal photo metadata + SAS URL issuance.

Strategy: clients upload bytes directly to Azure Blob Storage using a
short-lived SAS URL we mint here. They then PATCH the photo row with the
final blob_name so the meal-service knows where to find it.

This keeps the API process from streaming megabytes of JPEG data.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.schemas import (
    MealPhoto as MealPhotoSchema,
    MealPhotoCreate,
    MealPhotoPatch,
)

from .config import Settings, get_settings
from .deps import current_user_id, get_db
from .models import Meal, MealPhoto

router = APIRouter(prefix="/photos", tags=["photos"])


def _photo_metadata(photo: MealPhoto) -> MealPhotoSchema:
    """Serialize a photo for list/sync responses (no inline image bytes)."""
    out = MealPhotoSchema.model_validate(photo)
    out.image_data_b64 = None
    return out


class SasUploadResponse(BaseModel):
    photo_id: uuid.UUID
    blob_name: str
    upload_url: str
    expires_at: datetime


class SasDownloadResponse(BaseModel):
    download_url: str
    expires_at: datetime


def _generate_sas_url(
    blob_name: str,
    settings: Settings,
    *,
    read_only: bool = False,
) -> tuple[str, datetime]:
    """Mint a SAS URL for a single blob (write for upload, read for download)."""
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
        permission = (
            BlobSasPermissions(read=True)
            if read_only
            else BlobSasPermissions(write=True, create=True)
        )
        sas = generate_blob_sas(
            account_name=account_name,
            container_name=settings.blob_container,
            blob_name=blob_name,
            account_key=settings.blob_account_key,
            permission=permission,
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


@router.get("", response_model=list[MealPhotoSchema])
async def list_photos(
    since: datetime | None = Query(
        default=None,
        description="Return photos with updated_at at or after this timestamp (sync).",
    ),
    limit: int = Query(default=500, le=2000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[MealPhotoSchema]:
    stmt = select(MealPhoto).where(MealPhoto.user_id == user_id)
    if since is not None:
        stmt = stmt.where(MealPhoto.updated_at >= since)
    stmt = (
        stmt.order_by(MealPhoto.updated_at.asc(), MealPhoto.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_photo_metadata(r) for r in rows]


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
        (await db.execute(
            select(MealPhoto)
            .where(MealPhoto.meal_id == meal_id)
            .order_by(MealPhoto.display_order, MealPhoto.created_at)
        ))
        .scalars()
        .all()
    )
    return [_photo_metadata(r) for r in rows]


@router.put("/{photo_id}", response_model=MealPhotoSchema)
async def upsert_photo(
    photo_id: uuid.UUID,
    payload: MealPhotoCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> MealPhotoSchema:
    """Metadata-only upsert by client UUID (no image bytes)."""
    meal = await db.get(Meal, payload.meal_id)
    if meal is None or meal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Meal not found")

    photo = await db.get(MealPhoto, photo_id)
    data = payload.model_dump(exclude_unset=False)
    data.pop("id", None)
    # PUT is metadata-only; inline bytes use POST /photos/inline
    data.pop("image_data_b64", None)
    data.pop("thumb_data_b64", None)
    now = datetime.now(UTC)

    if photo is None:
        if not data.get("blob_name"):
            data["blob_name"] = f"{user_id}/{payload.meal_id}/{photo_id}.jpg"
        photo = MealPhoto(
            id=photo_id,
            user_id=user_id,
            updated_at=now,
            **data,
        )
        db.add(photo)
    elif photo.user_id != user_id:
        raise HTTPException(status_code=404, detail="Photo not found")
    else:
        for key, value in data.items():
            setattr(photo, key, value)
        photo.updated_at = now

    await db.flush()
    await db.refresh(photo)
    return _photo_metadata(photo)


@router.patch("/{photo_id}", response_model=MealPhotoSchema)
async def confirm_photo_upload(
    photo_id: uuid.UUID,
    payload: MealPhotoPatch,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> MealPhotoSchema:
    """Confirm SAS upload complete or update upload metadata."""
    photo = await db.get(MealPhoto, photo_id)
    if photo is None or photo.user_id != user_id:
        raise HTTPException(status_code=404, detail="Photo not found")

    updates = payload.model_dump(exclude_unset=True)
    upload_confirmed = updates.pop("upload_confirmed", None)
    if not updates and not upload_confirmed:
        raise HTTPException(status_code=400, detail="No fields to update")

    for key, value in updates.items():
        setattr(photo, key, value)
    photo.updated_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(photo)
    return _photo_metadata(photo)


@router.get("/{photo_id}/download-url", response_model=SasDownloadResponse)
async def get_photo_download_url(
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
    settings: Settings = Depends(get_settings),
) -> SasDownloadResponse:
    """Return a short-lived read SAS URL for the photo bytes in blob storage."""
    photo = await db.get(MealPhoto, photo_id)
    if photo is None or photo.user_id != user_id:
        raise HTTPException(status_code=404, detail="Photo not found")
    if not photo.blob_name:
        raise HTTPException(
            status_code=404,
            detail="Photo has no blob storage (inline web photo)",
        )

    url, expires = _generate_sas_url(photo.blob_name, settings, read_only=True)
    return SasDownloadResponse(download_url=url, expires_at=expires)


@router.get("/{photo_id}", response_model=MealPhotoSchema)
async def get_photo(
    photo_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> MealPhotoSchema:
    """Return one photo including the full image_data_b64."""
    photo = await db.get(MealPhoto, photo_id)
    if photo is None or photo.user_id != user_id:
        raise HTTPException(status_code=404, detail="Photo not found")
    return MealPhotoSchema.model_validate(photo)


@router.post("/inline", response_model=MealPhotoSchema, status_code=status.HTTP_201_CREATED)
async def upload_inline_photo(
    payload: MealPhotoCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> MealPhotoSchema:
    """Create a MealPhoto row with the image bytes stored inline as base64.

    This bypasses the Azure Blob SAS dance and is used by the web frontend.
    """
    if not payload.image_data_b64:
        raise HTTPException(status_code=400, detail="image_data_b64 is required")
    meal = await db.get(Meal, payload.meal_id)
    if meal is None or meal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Meal not found")
    # Enforce 20-photo cap per meal
    from sqlalchemy import func as _sql_func
    existing = (await db.execute(
        select(_sql_func.count()).select_from(MealPhoto).where(MealPhoto.meal_id == payload.meal_id)
    )).scalar() or 0
    if existing >= 20:
        raise HTTPException(status_code=400, detail="Maximum 20 photos per meal")
    # Assign next display_order
    max_order_row = (await db.execute(
        select(_sql_func.max(MealPhoto.display_order)).where(MealPhoto.meal_id == payload.meal_id)
    )).scalar()
    next_order = (max_order_row + 1) if max_order_row is not None else 0
    photo = MealPhoto(
        id=payload.id or uuid.uuid4(),
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
        image_data_b64=payload.image_data_b64,
        thumb_data_b64=payload.thumb_data_b64,
        display_order=next_order,
    )
    db.add(photo)
    await db.flush()
    await db.refresh(photo)
    return MealPhotoSchema.model_validate(photo)


class ReorderRequest(BaseModel):
    photo_ids: list[uuid.UUID]


@router.put("/by-meal/{meal_id}/order", response_model=list[MealPhotoSchema])
async def reorder_photos(
    meal_id: uuid.UUID,
    payload: ReorderRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[MealPhotoSchema]:
    """Reassign display_order for every photo in this meal based on the order
    of photo_ids in the request body. The list must contain exactly the photo
    ids currently attached to this meal."""
    meal = await db.get(Meal, meal_id)
    if meal is None or meal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Meal not found")
    rows = (await db.execute(
        select(MealPhoto).where(MealPhoto.meal_id == meal_id)
    )).scalars().all()
    by_id = {r.id: r for r in rows}
    if set(payload.photo_ids) != set(by_id.keys()):
        raise HTTPException(status_code=400, detail="photo_ids must match the meal's photos exactly")
    for i, pid in enumerate(payload.photo_ids):
        by_id[pid].display_order = i
    await db.flush()
    out = []
    for pid in payload.photo_ids:
        m = MealPhotoSchema.model_validate(by_id[pid])
        m.image_data_b64 = None
        out.append(m)
    return out


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