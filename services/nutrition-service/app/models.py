"""ORM for the nutrition reference database.

One row per canonical food (e.g. "grilled chicken breast", "white rice cooked").
Values are per-100g, matching the convention used by USDA FoodData Central and
Open Food Facts. Field names align with the iOS `Meal` entity so the
meal-service can build a meal record from these rows in a couple of lines.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from mealtracker_shared.db import Base


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Primary lookup key + searchable aliases
    label: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="internal", nullable=False)

    # All values are per 100g of edible portion.
    # macros (g, except calories=kcal, sodium=mg)
    calories: Mapped[float] = mapped_column(Float, default=0.0)
    carbohydrates: Mapped[float] = mapped_column(Float, default=0.0)
    protein: Mapped[float] = mapped_column(Float, default=0.0)
    fat: Mapped[float] = mapped_column(Float, default=0.0)
    sodium: Mapped[float] = mapped_column(Float, default=0.0)  # mg

    # carb breakdown
    sugars: Mapped[float] = mapped_column(Float, default=0.0)
    starch: Mapped[float] = mapped_column(Float, default=0.0)
    fibre: Mapped[float] = mapped_column(Float, default=0.0)

    # fat breakdown
    saturated_fat: Mapped[float] = mapped_column(Float, default=0.0)
    monounsaturated_fat: Mapped[float] = mapped_column(Float, default=0.0)
    polyunsaturated_fat: Mapped[float] = mapped_column(Float, default=0.0)
    trans_fat: Mapped[float] = mapped_column(Float, default=0.0)
    omega3: Mapped[float] = mapped_column(Float, default=0.0)
    omega6: Mapped[float] = mapped_column(Float, default=0.0)

    # protein breakdown
    animal_protein: Mapped[float] = mapped_column(Float, default=0.0)
    plant_protein: Mapped[float] = mapped_column(Float, default=0.0)

    # vitamins (mg)
    vitamin_a: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_b: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_c: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_d: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_e: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_k: Mapped[float] = mapped_column(Float, default=0.0)

    # minerals (mg)
    calcium: Mapped[float] = mapped_column(Float, default=0.0)
    iron: Mapped[float] = mapped_column(Float, default=0.0)
    potassium: Mapped[float] = mapped_column(Float, default=0.0)
    zinc: Mapped[float] = mapped_column(Float, default=0.0)
    magnesium: Mapped[float] = mapped_column(Float, default=0.0)
    iodine: Mapped[float] = mapped_column(Float, default=0.0)
    phosphorus: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
