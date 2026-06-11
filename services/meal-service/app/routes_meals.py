"""Meal CRUD + iOS sync endpoints."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import or_, select
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


def _stamp_meal_sync(meal: Meal) -> None:
    """Assign a fresh server sync marker and bump updated_at."""
    meal.last_sync_guid = uuid.uuid4().hex
    meal.updated_at = datetime.now(UTC)


async def _validate_person_id(
    db: AsyncSession,
    user_id: uuid.UUID,
    person_id: uuid.UUID | None,
) -> None:
    if person_id is None:
        return
    person = await db.get(Person, person_id)
    if person is None or person.user_id != user_id:
        raise HTTPException(status_code=400, detail="person_id does not belong to this user")


# ----------------------------- Meals -----------------------------

@router.get("", response_model=list[MealSchema])
async def list_meals(
    limit: int = Query(default=200, le=1000),
    offset: int = 0,
    since: datetime | None = Query(
        default=None,
        description=(
            "If provided, return meals updated or deleted at or after this timestamp (sync). "
            "Includes soft-deleted meals as tombstones (deleted_at set)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[MealSchema]:
    stmt = select(Meal).where(Meal.user_id == user_id)
    if since is not None:
        stmt = stmt.where(
            or_(Meal.updated_at >= since, Meal.deleted_at >= since)
        )
    else:
        stmt = stmt.where(Meal.deleted_at.is_(None))
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
    await _validate_person_id(db, user_id, data.get("person_id"))
    # Honour client-supplied id (iOS already has UUIDs)
    if data.get("id") is None:
        data.pop("id", None)
    meal = Meal(user_id=user_id, **data)
    _stamp_meal_sync(meal)
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
    if meal is None or meal.user_id != user_id or meal.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Meal not found")
    return MealSchema.model_validate(meal)


@router.put("/{meal_id}", response_model=MealSchema)
async def upsert_meal(
    meal_id: uuid.UUID,
    payload: MealCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> MealSchema:
    meal = await db.get(Meal, meal_id)
    data = payload.model_dump(exclude_unset=False)
    await _validate_person_id(db, user_id, data.get("person_id"))
    if meal is None:
        data.pop("id", None)
        meal = Meal(id=meal_id, user_id=user_id, **data)
        db.add(meal)
    elif meal.user_id != user_id:
        raise HTTPException(status_code=404, detail="Meal not found")
    else:
        for key, value in data.items():
            if key == "id":
                continue
            setattr(meal, key, value)
        meal.deleted_at = None
    _stamp_meal_sync(meal)
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
    if meal.deleted_at is None:
        meal.deleted_at = datetime.now(UTC)


# ----------------------------- People -----------------------------

people_router = APIRouter(prefix="/people", tags=["people"])


def _stamp_person_sync(person: Person) -> None:
    """Bump updated_at so incremental ?since= pulls pick up the change."""
    person.updated_at = datetime.now(UTC)


async def _ensure_default_person(db: AsyncSession, user_id: uuid.UUID) -> Person:
    """Create a default 'Me' person when the user has none (first-login bootstrap)."""
    existing = (
        await db.execute(
            select(Person)
            .where(
                Person.user_id == user_id,
                Person.is_removed.is_(False),
                Person.deleted_at.is_(None),
            )
            .order_by(Person.is_default.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    person = Person(user_id=user_id, name="Me", is_default=True, is_removed=False)
    db.add(person)
    await db.flush()
    return person


async def _get_default_person(db: AsyncSession, user_id: uuid.UUID) -> Person:
    """Return the user's default person, creating one if needed."""
    row = (
        await db.execute(
            select(Person).where(
                Person.user_id == user_id,
                Person.is_default.is_(True),
                Person.is_removed.is_(False),
                Person.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    return await _ensure_default_person(db, user_id)


@people_router.get("", response_model=list[PersonSchema])
async def list_people(
    since: datetime | None = Query(
        default=None,
        description=(
            "If provided, return people updated or deleted at or after this timestamp (sync). "
            "Includes removed people as tombstones (is_removed=true, deleted_at set)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[PersonSchema]:
    if since is None:
        await _ensure_default_person(db, user_id)
    stmt = select(Person).where(Person.user_id == user_id)
    if since is not None:
        stmt = stmt.where(
            or_(Person.updated_at >= since, Person.deleted_at >= since)
        )
    else:
        stmt = stmt.where(
            Person.is_removed.is_(False), Person.deleted_at.is_(None)
        )
    stmt = stmt.order_by(Person.is_default.desc(), Person.name)
    rows = (await db.execute(stmt)).scalars().all()
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


@people_router.put("/{person_id}", response_model=PersonSchema)
async def upsert_person(
    person_id: uuid.UUID,
    payload: PersonCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> PersonSchema:
    person = await db.get(Person, person_id)
    data = payload.model_dump(exclude_unset=False)
    if person is None:
        data.pop("id", None)
        person = Person(id=person_id, user_id=user_id, **data)
        if person.is_removed:
            person.deleted_at = datetime.now(UTC)
        db.add(person)
    elif person.user_id != user_id:
        raise HTTPException(status_code=404, detail="Person not found")
    else:
        for key, value in data.items():
            if key == "id":
                continue
            setattr(person, key, value)
    if person.is_removed and person.deleted_at is None:
        person.deleted_at = datetime.now(UTC)
    elif not person.is_removed:
        person.deleted_at = None
    _stamp_person_sync(person)
    await db.flush()
    await db.refresh(person)
    return PersonSchema.model_validate(person)


@people_router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_person(
    person_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(current_user_id),
) -> None:
    person = await db.get(Person, person_id)
    if person is None or person.user_id != user_id:
        raise HTTPException(status_code=404, detail="Person not found")
    if person.is_removed:
        return

    default = await _get_default_person(db, user_id)
    if default.id == person_id:
        other = (
            await db.execute(
                select(Person).where(
                    Person.user_id == user_id,
                    Person.id != person_id,
                    Person.is_removed.is_(False),
                    Person.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if other is not None:
            other.is_default = True
            _stamp_person_sync(other)
            default = other
        else:
            default = Person(user_id=user_id, name="Me", is_default=True, is_removed=False)
            db.add(default)
            await db.flush()

    meals = (
        await db.execute(select(Meal).where(Meal.person_id == person_id, Meal.user_id == user_id))
    ).scalars().all()
    for meal in meals:
        meal.person_id = default.id
        _stamp_meal_sync(meal)

    person.is_removed = True
    person.is_default = False
    person.deleted_at = datetime.now(UTC)
    _stamp_person_sync(person)
    await db.flush()
