"""FastAPI app: serves the API under /api and the frontend at /."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import get_db
from .space_events import SPACE_EVENTS

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Upper Air Ledger API", version="0.1.0")

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _read_collection(name: str, limit: int = 500) -> list[dict]:
    """Read documents from a MongoDB collection (without the internal _id)."""
    db = get_db()
    if db is None:
        raise HTTPException(503, "MongoDB is not configured. Set MONGO_URI.")
    try:
        return list(db[name].find({}, {"_id": 0}).limit(limit))
    except Exception as exc:
        logging.exception("MongoDB read failed")
        raise HTTPException(502, f"MongoDB read failed: {exc}") from exc


def _save_scenario(result: dict) -> None:
    """Keep the latest live scenario in MongoDB. Never breaks the API if it fails."""
    db = get_db()
    if db is None:
        return
    try:
        db.scenarios.replace_one(
            {"_key": "latest"},
            {**result, "_key": "latest", "saved_at": datetime.now(timezone.utc)},
            upsert=True,
        )
    except Exception:
        logging.exception("Could not save scenario to MongoDB")


@app.get("/api/health")
def health() -> dict:
    return {
        "mode": settings.mode,
        "mongo_configured": get_db() is not None,
        "sources": {
            "opensky": bool(settings.opensky_client_id),
            "aircraft_db": settings.opensky_aircraft_db.exists(),
            "contrails_org": bool(settings.contrails_org_url),
        },
    }


@app.get("/api/db-health")
def db_health() -> dict:
    db = get_db()
    if db is None:
        raise HTTPException(503, "MongoDB is not configured. Set MONGO_URI.")
    try:
        db.client.admin.command("ping")
    except Exception as exc:
        raise HTTPException(502, f"Could not reach MongoDB: {exc}") from exc
    return {"ok": True, "collections": db.list_collection_names()}


@app.get("/api/scenario")
async def scenario() -> dict:
    if not settings.live:
        raise HTTPException(404, "Demo mode: the frontend simulates the scenario. Set UAL_MODE=live to build one.")
    from .pipeline.scenario import cached_scenario  # heavy imports only in live mode

    try:
        result = await run_in_threadpool(cached_scenario, settings)
    except Exception as exc:
        logging.exception("Scenario build failed")
        raise HTTPException(502, f"Could not build the live scenario: {exc}") from exc
    await run_in_threadpool(_save_scenario, result)
    return result


@app.get("/api/space-events")
def space_events() -> list[dict]:
    return SPACE_EVENTS


@app.get("/api/flights")
def flights() -> list[dict]:
    return _read_collection("flights")


@app.get("/api/contrails")
def contrails() -> list[dict]:
    return _read_collection("contrails")


@app.get("/api/matches")
def matches() -> list[dict]:
    return _read_collection("matches")


if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
