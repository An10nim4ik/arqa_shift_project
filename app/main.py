import json
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .schemas import DayResponse, InsertResponse, TripCreate
from .storage import DuplicateTripConflict, TripStorage

ROOT = Path(__file__).resolve().parents[1]


def create_app(database_path: str | Path | None = None, seed_path: str | Path | None = ROOT / "data" / "sample_trips.json") -> FastAPI:
    database_path = database_path or os.getenv("DB_PATH", str(ROOT / "data" / "trips.db"))
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    storage = TripStorage(database_path)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        storage.initialize()
        if seed_path is not None and storage.is_empty():
            for item in json.loads(Path(seed_path).read_text(encoding="utf-8")):
                storage.add_trip(TripCreate.model_validate(item))
        yield

    api = FastAPI(title="ARQA Driver Shift Diary", version="1.0.0", lifespan=lifespan)
    api.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")

    @api.get("/", include_in_schema=False)
    def home():
        return FileResponse(ROOT / "web" / "index.html")

    @api.get("/api/days/{selected_day}", response_model=DayResponse)
    def get_day(selected_day: str):
        try:
            parsed = date.fromisoformat(selected_day)
            if parsed.isoformat() != selected_day:
                raise ValueError("Invalid ISO date")
        except ValueError:
            raise HTTPException(status_code=422, detail="Date must use YYYY-MM-DD") from None
        return storage.get_day(selected_day)

    @api.post("/api/trips", response_model=InsertResponse, status_code=201)
    def add_trip(trip: TripCreate, response: Response):
        try:
            created, saved = storage.add_trip(trip)
        except DuplicateTripConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        response.status_code = 201 if created else 200
        return {"created": created, "trip": saved}

    return api


app = create_app()
