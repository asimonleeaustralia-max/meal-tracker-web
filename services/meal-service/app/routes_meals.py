"""Meal CRUD + iOS sync endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.schemas import (
    Meal as MealSchema,
    MealCreate,
    Person as PersonSchema,
    PersonCreate,
)

from .deps import current_user_id, get_db
from .models import Meal, Person

router = APIRouter(prefix="/meals", tags=["meals"])


# ----------------------------- Meals -----------------------------

@router.get("", response_model=list[MealSchema])
async def list_meals(
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    since: datetime | None = Query(
        default=None,
        description="If provided, only return meals updated at or after this timestamp (sync).",
    ),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[MealSchema]:
    stmt = select(Meal).where(Meal.user_id == user_id)
    if since is not None:
        stmt = stmt.where(Meal.updated_at >= since)
    stmt = stmt.order_by(Meal.date.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return [MealSchema.model_validate(r) for r in rows]


@router.post("", response_model=MealSchema, status_code=status.HTTP_201_CREATED)
async def create_meal(
    payload: MealCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> MealSchema:
    data = payload.model_dump(exclude_unset=False, exclude_none=False)
    # Honour client-supplied id (iOS already has UUIDs)
    if data.get("id") is None:
        data.pop("id", None)
    meal = Meal(user_id=user_id, **data)
    db.add(meal)
    await db.flush()
    await db.refresh(meal)
    return MealSchema.model_validate(meal)


@router.get("/{meal_id}", response_model=MealSchema)
async def get_meal(
    meal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> MealSchema:
    meal = await db.get(Meal, meal_id)
    if meal is None or meal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Meal not found")
    return MealSchema.model_validate(meal)


@router.put("/{meal_id}", response_model=MealSchema)
async def replace_meal(
    meal_id: uuid.UUID,
    payload: MealCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> MealSchema:
    meal = await db.get(Meal, meal_id)
    if meal is None or meal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Meal not found")
    for key, value in payload.model_dump(exclude_unset=False).items():
        if key == "id":
            continue
        setattr(meal, key, value)
    await db.flush()
    await db.refresh(meal)
    return MealSchema.model_validate(meal)


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_meal(
    meal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> None:
    meal = await db.get(Meal, meal_id)
    if meal is None or meal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Meal not found")
    await db.delete(meal)


# ----------------------------- People -----------------------------

people_router = APIRouter(prefix="/people", tags=["people"])


@people_router.get("", response_model=list[PersonSchema])
async def list_people(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[PersonSchema]:
    rows = (
        (
            await db.execute(
                select(Person)
                .where(Person.user_id == user_id, Person.is_removed.is_(False))
                .order_by(Person.is_default.desc(), Person.name)
            )
        )
        .scalars()
        .all()
    )
    return [PersonSchema.model_validate(r) for r in rows]


@people_router.post("", response_model=PersonSchema, status_code=status.HTTP_201_CREATED)
async def create_person(
    payload: PersonCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> PersonSchema:
    data = payload.model_dump()
    if data.get("id") is None:
        data.pop("id", None)
    person = Person(user_id=user_id, **data)
    db.add(person)
    await db.flush()
    await db.refresh(person)
    return PersonSchema.model_validate(person)
