"""Idempotent seed loader.

Runs on startup in development mode, and via `python -m app.seed` in prod
after the migration has applied. Reads `seed/foods.json` and upserts each row.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Food

log = logging.getLogger(__name__)

_SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "foods.json"


async def seed_foods(db: AsyncSession) -> int:
    if not _SEED_FILE.exists():
        log.warning("Seed file %s missing", _SEED_FILE)
        return 0

    with _SEED_FILE.open() as f:
        rows = json.load(f)

    inserted = 0
    for row in rows:
        label = row["label"]
        existing = await db.scalar(select(Food).where(Food.label == label))
        if existing is not None:
            continue
        # Only pass kwargs that are actual columns on Food.
        valid_cols = {c.name for c in Food.__table__.columns}
        food = Food(
            label=label,
            aliases=row.get("aliases", []),
            source="internal",
            **{
                k: float(v)
                for k, v in row.items()
                if k in valid_cols
                and k not in {"label", "aliases"}
                and isinstance(v, (int, float))
            },
        )
        db.add(food)
        inserted += 1

    if inserted:
        log.info("Seeded %d foods", inserted)
    return inserted
