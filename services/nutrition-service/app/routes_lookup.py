"""Nutrition lookup endpoint.

Given a list of food labels (e.g. as returned by the vision-service),
returns per-100g nutrient values for each.

Lookup strategy, in order:
  1. Exact match on `label` (case-insensitive)
  2. Exact match on any alias
  3. Trigram-similarity fuzzy match in Postgres
  4. (Optional) Open Food Facts fallback for branded products
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException
from rapidfuzz import fuzz, process
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mealtracker_shared.schemas import (
    FoodNutrition,
    NutrientValues,
    NutritionLookupRequest,
    NutritionLookupResponse,
)

from .config import Settings, get_settings
from .deps import current_user, get_db
from .models import Food

router = APIRouter(prefix="/nutrition", tags=["nutrition"])

# Fields on Food that map straight onto NutrientValues
_NUTRIENT_FIELDS = list(NutrientValues.model_fields.keys())


def _food_to_nutrients(food: Food) -> NutrientValues:
    return NutrientValues(**{f: getattr(food, f) for f in _NUTRIENT_FIELDS})


async def _resolve_one(
    label: str, db: AsyncSession, settings: Settings
) -> FoodNutrition | None:
    q = label.strip().lower()
    if not q:
        return None

    # 1. exact label
    exact = await db.scalar(select(Food).where(func.lower(Food.label) == q))
    if exact is not None:
        return FoodNutrition(
            label=label,
            matched_food=exact.label,
            per_100g=_food_to_nutrients(exact),
            source=exact.source,
        )

    # 2. alias match
    alias_hit = await db.scalar(
        select(Food).where(func.lower(func.array_to_string(Food.aliases, ",")).contains(q))
    )
    if alias_hit is not None:
        return FoodNutrition(
            label=label,
            matched_food=alias_hit.label,
            per_100g=_food_to_nutrients(alias_hit),
            source=alias_hit.source,
        )

    # 3. fuzzy in-Python over the (presumably small) catalog
    all_labels = (await db.execute(select(Food.label))).scalars().all()
    if all_labels:
        best, score, _ = process.extractOne(q, all_labels, scorer=fuzz.WRatio) or (None, 0, 0)
        if best and score >= settings.match_threshold:
            hit = await db.scalar(select(Food).where(Food.label == best))
            if hit is not None:
                return FoodNutrition(
                    label=label,
                    matched_food=hit.label,
                    per_100g=_food_to_nutrients(hit),
                    source=hit.source,
                )

    # 4. Open Food Facts fallback (text search by product name)
    if settings.enable_openfoodfacts_fallback:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    f"{settings.openfoodfacts_base_url}/cgi/search.pl",
                    params={
                        "search_terms": label,
                        "json": 1,
                        "page_size": 1,
                        "fields": "product_name,nutriments",
                    },
                )
            r.raise_for_status()
            data = r.json()
            products = data.get("products") or []
            if products:
                p = products[0]
                n = p.get("nutriments", {})
                # OFF uses "*_100g" suffix
                def _g(k: str) -> float:
                    return float(n.get(f"{k}_100g") or 0.0)
                return FoodNutrition(
                    label=label,
                    matched_food=p.get("product_name") or label,
                    per_100g=NutrientValues(
                        calories=_g("energy-kcal"),
                        carbohydrates=_g("carbohydrates"),
                        protein=_g("proteins"),
                        fat=_g("fat"),
                        sodium=_g("sodium") * 1000,  # OFF stores g, we want mg
                        sugars=_g("sugars"),
                        fibre=_g("fiber"),
                        saturated_fat=_g("saturated-fat"),
                    ),
                    source="openfoodfacts",
                )
        except (httpx.HTTPError, ValueError):
            pass

    return None


@router.post(
    "/lookup",
    response_model=NutritionLookupResponse,
    dependencies=[Depends(current_user)],
)
async def lookup(
    payload: NutritionLookupRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> NutritionLookupResponse:
    foods: list[FoodNutrition] = []
    misses: list[str] = []
    for label in payload.labels:
        result = await _resolve_one(label, db, settings)
        if result is None:
            misses.append(label)
        else:
            foods.append(result)
    return NutritionLookupResponse(foods=foods, misses=misses)


@router.get(
    "/foods/{label}",
    response_model=FoodNutrition,
    dependencies=[Depends(current_user)],
)
async def get_food(
    label: str,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FoodNutrition:
    result = await _resolve_one(label, db, settings)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No nutrition data for '{label}'")
    return result
