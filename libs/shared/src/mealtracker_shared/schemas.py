"""Cross-service Pydantic schemas.

These represent the **public contracts** between services and the iOS/web
clients. Each service's internal ORM models are private to that service.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# -------------------- Auth --------------------

class UserPublic(BaseModel):
    """User as seen by other services / clients."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr | None = None
    display_name: str | None = None
    provider: str = "local"  # local | google | apple | facebook
    is_admin: bool = False
    created_at: datetime


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access_token expires
    session_id: uuid.UUID | None = None


class ActivityEventIn(BaseModel):
    session_id: uuid.UUID | None = None
    event_type: str
    path: str | None = None
    language: str | None = None
    bytes_saved: int | None = None
    metadata: dict | None = None


class LoginSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    login_method: str
    ip_address: str | None = None
    user_agent: str | None = None
    language: str | None = None
    client: str
    logged_in_at: datetime
    logged_out_at: datetime | None = None
    last_seen_at: datetime | None = None
    duration_seconds: int | None = None


class ActivityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str | None = None
    session_id: uuid.UUID | None = None
    event_type: str
    path: str | None = None
    ip_address: str | None = None
    language: str | None = None
    bytes_saved: int | None = None
    metadata_json: dict | None = None
    created_at: datetime


class AdminUserStats(BaseModel):
    user_id: uuid.UUID
    email: str | None = None
    display_name: str | None = None
    login_count: int = 0
    last_login_at: datetime | None = None
    last_login_method: str | None = None
    total_session_seconds: int = 0
    activity_event_count: int = 0
    meal_count: int = 0
    photo_count: int = 0
    data_bytes_saved: int = 0
    preferred_language: str | None = None
    last_ip: str | None = None


class AdminOverview(BaseModel):
    total_users: int
    total_logins: int
    total_activity_events: int
    active_sessions: int
    unique_ips_24h: int
    logins_24h: int
    events_24h: int


# -------------------- Meal (mirrors iOS Core Data `Meal`) --------------------
# Field names match the Swift Meal class so iOS sync is a 1:1 codable mapping.

class NutrientWithGuess(BaseModel):
    """A nutrient value paired with the iOS `*IsGuess` accuracy flag."""

    value: float = 0.0
    is_guess: bool = False


class MealBase(BaseModel):
    """Field-for-field mirror of the Swift `Meal` Core Data entity."""

    model_config = ConfigDict(from_attributes=True)

    title: str = ""
    date: datetime
    person_id: uuid.UUID | None = None

    # Location
    latitude: float = 0.0
    longitude: float = 0.0

    # --- Macros (matches Swift Meal: Double / Bool isGuess) ---
    calories: float = 0.0
    carbohydrates: float = 0.0
    protein: float = 0.0
    fat: float = 0.0
    sodium: float = 0.0

    calories_is_guess: bool = False
    carbohydrates_is_guess: bool = False
    protein_is_guess: bool = False
    fat_is_guess: bool = False
    sodium_is_guess: bool = False

    # --- Carbohydrate breakdown ---
    starch: float = 0.0
    sugars: float = 0.0
    fibre: float = 0.0
    starch_is_guess: bool = False
    sugars_is_guess: bool = False
    fibre_is_guess: bool = False

    # --- Fat breakdown ---
    monounsaturated_fat: float = 0.0
    polyunsaturated_fat: float = 0.0
    saturated_fat: float = 0.0
    trans_fat: float = 0.0
    omega3: float = 0.0
    omega6: float = 0.0
    monounsaturated_fat_is_guess: bool = False
    polyunsaturated_fat_is_guess: bool = False
    saturated_fat_is_guess: bool = False
    trans_fat_is_guess: bool = False
    omega3_is_guess: bool = False
    omega6_is_guess: bool = False

    # --- Protein breakdown ---
    animal_protein: float = 0.0
    plant_protein: float = 0.0
    protein_supplements: float = 0.0
    a2_beta_casein: float = 0.0
    a1_beta_casein: float = 0.0
    animal_protein_is_guess: bool = False
    plant_protein_is_guess: bool = False
    protein_supplements_is_guess: bool = False
    a2_beta_casein_is_guess: bool = False
    a1_beta_casein_is_guess: bool = False

    # --- Stimulants / specials ---
    alcohol: float = 0.0
    nicotine: float = 0.0
    theobromine: float = 0.0
    caffeine: float = 0.0
    taurine: float = 0.0
    creatine: float = 0.0
    alcohol_is_guess: bool = False
    nicotine_is_guess: bool = False
    theobromine_is_guess: bool = False
    caffeine_is_guess: bool = False
    taurine_is_guess: bool = False
    creatine_is_guess: bool = False

    # --- Vitamins (mg) ---
    vitamin_a: float = 0.0
    vitamin_b: float = 0.0
    vitamin_c: float = 0.0
    vitamin_d: float = 0.0
    vitamin_e: float = 0.0
    vitamin_k: float = 0.0
    vitamin_a_is_guess: bool = False
    vitamin_b_is_guess: bool = False
    vitamin_c_is_guess: bool = False
    vitamin_d_is_guess: bool = False
    vitamin_e_is_guess: bool = False
    vitamin_k_is_guess: bool = False

    # --- Minerals (mg) ---
    calcium: float = 0.0
    iron: float = 0.0
    potassium: float = 0.0
    zinc: float = 0.0
    magnesium: float = 0.0
    iodine: float = 0.0
    phosphorus: float = 0.0
    calcium_is_guess: bool = False
    iron_is_guess: bool = False
    potassium_is_guess: bool = False
    zinc_is_guess: bool = False
    magnesium_is_guess: bool = False
    iodine_is_guess: bool = False
    phosphorus_is_guess: bool = False

    # --- Provenance (matches Swift) ---
    photo_guesser_type: str | None = None  # "barcode" | "ocr" | "featureprint" | "visual"
    product_name: str | None = None


class MealCreate(MealBase):
    """Payload for POST /meals."""

    id: uuid.UUID | None = None  # client-generated UUIDs supported (iOS sends them)


class MealUpdate(BaseModel):
    """All fields optional for PATCH."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    date: datetime | None = None
    # ... only the fields most likely to change post-creation are exposed here;
    # full-record updates go through PUT /meals/{id} with MealCreate.


class Meal(MealBase):
    id: uuid.UUID
    user_id: uuid.UUID
    last_sync_guid: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


# -------------------- Person (mirrors iOS Core Data `Person`) --------------------

class PersonBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str = "Me"
    is_default: bool = False
    is_removed: bool = False


class PersonCreate(PersonBase):
    id: uuid.UUID | None = None


class Person(PersonBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


# -------------------- MealPhoto (mirrors iOS Core Data `MealPhoto`) --------------------

class MealPhotoBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    width: int = 0
    height: int = 0
    file_name_original: str | None = None
    file_name_upload: str | None = None
    byte_size_original: int = 0
    byte_size_upload: int = 0
    sha256: str | None = None
    latitude: float = 0.0
    longitude: float = 0.0
    # Azure Blob path (set by upload-url); null for inline web photos
    blob_name: str | None = None
    # Inline base64-encoded JPEG. Used by the web frontend's "inline" upload path;
    # iOS app continues to use the SAS blob flow and leaves this null.
    image_data_b64: str | None = None
    # Small (~200px) thumbnail for listings; cheap to ship in bulk
    thumb_data_b64: str | None = None
    # Display order within a meal (lower = first)
    display_order: int = 0


class MealPhotoCreate(MealPhotoBase):
    id: uuid.UUID | None = None
    meal_id: uuid.UUID


class MealPhotoPatch(BaseModel):
    """Payload for PATCH /photos/{id} — confirm SAS upload or tweak metadata."""

    model_config = ConfigDict(extra="ignore")

    upload_confirmed: bool | None = None
    byte_size_upload: int | None = None
    sha256: str | None = None
    display_order: int | None = None


class MealPhoto(MealPhotoBase):
    id: uuid.UUID
    meal_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SyncChangesResponse(BaseModel):
    """Incremental pull bundle for iOS — one round-trip for all entity types."""

    meals: list[Meal]
    people: list[Person]
    photos: list[MealPhoto]
    server_time: datetime


# -------------------- Vision (RunPod) --------------------

class VisionPrediction(BaseModel):
    """A single food the vision model thinks is in the photo."""

    label: str = Field(..., description="Canonical food name, e.g. 'grilled chicken breast'")
    confidence: float = Field(..., ge=0.0, le=1.0)
    estimated_grams: float | None = None


class VisionAnalyzeRequest(BaseModel):
    image_base64: str = Field(..., description="JPEG/PNG image as base64 string")
    locale: str | None = "en"


class VisionAnalyzeResponse(BaseModel):
    predictions: list[VisionPrediction]
    model_version: str
    inference_ms: int


# -------------------- Nutrition lookup --------------------

class NutritionLookupRequest(BaseModel):
    labels: list[str] = Field(..., min_length=1)


class NutrientValues(BaseModel):
    """Per-100g nutrient profile for a food. Matches iOS Meal fields."""

    # macros
    calories: float = 0.0
    carbohydrates: float = 0.0
    protein: float = 0.0
    fat: float = 0.0
    sodium: float = 0.0
    # breakdown
    sugars: float = 0.0
    starch: float = 0.0
    fibre: float = 0.0
    saturated_fat: float = 0.0
    monounsaturated_fat: float = 0.0
    polyunsaturated_fat: float = 0.0
    trans_fat: float = 0.0
    omega3: float = 0.0
    omega6: float = 0.0
    animal_protein: float = 0.0
    plant_protein: float = 0.0
    # vitamins
    vitamin_a: float = 0.0
    vitamin_b: float = 0.0
    vitamin_c: float = 0.0
    vitamin_d: float = 0.0
    vitamin_e: float = 0.0
    vitamin_k: float = 0.0
    # minerals
    calcium: float = 0.0
    iron: float = 0.0
    potassium: float = 0.0
    zinc: float = 0.0
    magnesium: float = 0.0
    iodine: float = 0.0
    phosphorus: float = 0.0


class FoodNutrition(BaseModel):
    label: str
    matched_food: str  # the actual DB entry that matched (may differ from query)
    per_100g: NutrientValues
    source: str = "internal"  # "internal" | "openfoodfacts" | "usda"


class NutritionLookupResponse(BaseModel):
    foods: list[FoodNutrition]
    misses: list[str] = Field(default_factory=list)
