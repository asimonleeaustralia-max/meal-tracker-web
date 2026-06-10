"""ORM models for the meal schema.

Each table mirrors the corresponding iOS Core Data entity from MealTracker:
  * Person → people
  * Meal → meals
  * MealPhoto → meal_photos

Field names use snake_case in SQL but the API layer maps them to/from the
Swift camelCase names so the iOS app can sync with zero translation logic.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealtracker_shared.db import Base


class Person(Base):
    __tablename__ = "people"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), default="Me", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("people.id"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Location
    latitude: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # --- Macros ---
    calories: Mapped[float] = mapped_column(Float, default=0.0)
    carbohydrates: Mapped[float] = mapped_column(Float, default=0.0)
    protein: Mapped[float] = mapped_column(Float, default=0.0)
    fat: Mapped[float] = mapped_column(Float, default=0.0)
    sodium: Mapped[float] = mapped_column(Float, default=0.0)
    calories_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    carbohydrates_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    protein_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    fat_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    sodium_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Carb breakdown ---
    starch: Mapped[float] = mapped_column(Float, default=0.0)
    sugars: Mapped[float] = mapped_column(Float, default=0.0)
    fibre: Mapped[float] = mapped_column(Float, default=0.0)
    starch_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    sugars_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    fibre_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Fat breakdown ---
    monounsaturated_fat: Mapped[float] = mapped_column(Float, default=0.0)
    polyunsaturated_fat: Mapped[float] = mapped_column(Float, default=0.0)
    saturated_fat: Mapped[float] = mapped_column(Float, default=0.0)
    trans_fat: Mapped[float] = mapped_column(Float, default=0.0)
    omega3: Mapped[float] = mapped_column(Float, default=0.0)
    omega6: Mapped[float] = mapped_column(Float, default=0.0)
    monounsaturated_fat_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    polyunsaturated_fat_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    saturated_fat_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    trans_fat_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    omega3_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    omega6_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Protein breakdown ---
    animal_protein: Mapped[float] = mapped_column(Float, default=0.0)
    plant_protein: Mapped[float] = mapped_column(Float, default=0.0)
    protein_supplements: Mapped[float] = mapped_column(Float, default=0.0)
    a2_beta_casein: Mapped[float] = mapped_column(Float, default=0.0)
    a1_beta_casein: Mapped[float] = mapped_column(Float, default=0.0)
    animal_protein_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    plant_protein_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    protein_supplements_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    a2_beta_casein_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    a1_beta_casein_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Stimulants / specials ---
    alcohol: Mapped[float] = mapped_column(Float, default=0.0)
    nicotine: Mapped[float] = mapped_column(Float, default=0.0)
    theobromine: Mapped[float] = mapped_column(Float, default=0.0)
    caffeine: Mapped[float] = mapped_column(Float, default=0.0)
    taurine: Mapped[float] = mapped_column(Float, default=0.0)
    creatine: Mapped[float] = mapped_column(Float, default=0.0)
    alcohol_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    nicotine_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    theobromine_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    caffeine_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    taurine_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    creatine_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Vitamins ---
    vitamin_a: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_b: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_c: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_d: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_e: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_k: Mapped[float] = mapped_column(Float, default=0.0)
    vitamin_a_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    vitamin_b_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    vitamin_c_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    vitamin_d_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    vitamin_e_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    vitamin_k_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Minerals ---
    calcium: Mapped[float] = mapped_column(Float, default=0.0)
    iron: Mapped[float] = mapped_column(Float, default=0.0)
    potassium: Mapped[float] = mapped_column(Float, default=0.0)
    zinc: Mapped[float] = mapped_column(Float, default=0.0)
    magnesium: Mapped[float] = mapped_column(Float, default=0.0)
    iodine: Mapped[float] = mapped_column(Float, default=0.0)
    phosphorus: Mapped[float] = mapped_column(Float, default=0.0)
    calcium_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    iron_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    potassium_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    zinc_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    magnesium_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    iodine_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)
    phosphorus_is_guess: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Provenance ---
    photo_guesser_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Sync ---
    last_sync_guid: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    photos: Mapped[list["MealPhoto"]] = relationship(
        "MealPhoto", back_populates="meal", cascade="all, delete-orphan"
    )


class MealPhoto(Base):
    __tablename__ = "meal_photos"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    meal_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("meals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )

    width: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_name_original: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_name_upload: Mapped[str | None] = mapped_column(String(255), nullable=True)
    byte_size_original: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    byte_size_upload: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    latitude: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Where the photo bytes live (Azure Blob name / path)
    blob_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Inline base64 storage (used by the web frontend's inline upload path).
    # iOS continues to use blob_name + Azure Blob Storage.
    image_data_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Small (~200px) thumbnail used in listings
    thumb_data_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Display order within a meal (assigned at upload, mutable via reorder endpoint)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )

    meal: Mapped[Meal] = relationship("Meal", back_populates="photos")
