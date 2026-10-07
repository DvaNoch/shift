import datetime as dt
import os
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse

from . import db, service
from .models import Summary, Trip, TripIn

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(db_path: Path | str | None = None, seed_path: Path | str | None = None) -> FastAPI:
    db_path = Path(db_path or os.environ.get("DRIVER_SHIFTS_DB") or BASE_DIR / "driver_shifts.db")
    seed_path = Path(seed_path or os.environ.get("DRIVER_SHIFTS_SEED") or BASE_DIR / "trips.json")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        conn = db.connect(db_path)
        try:
            db.init_schema(conn)
            service.seed_once(conn, seed_path)
        finally:
            conn.close()
        yield

    app = FastAPI(title="Дневник смен водителя", lifespan=lifespan)

    def get_conn() -> Iterator[sqlite3.Connection]:
        conn = db.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    DayQuery = Query(alias="date", description="День в формате YYYY-MM-DD")

    @app.get("/trips", response_model=list[Trip])
    def list_trips(day: dt.date = DayQuery, conn: sqlite3.Connection = Depends(get_conn)):
        return service.trips_for_day(conn, day)

    @app.get("/summary", response_model=Summary)
    def day_summary(day: dt.date = DayQuery, conn: sqlite3.Connection = Depends(get_conn)):
        return service.summarize(day, service.trips_for_day(conn, day))

    @app.post(
        "/trips",
        response_model=Trip,
        status_code=201,
        responses={
            200: {"description": "Поездка уже сохранена с теми же данными"},
            409: {"description": "Поездка с этим id уже сохранена с другими данными"},
        },
    )
    def create_trip(trip: TripIn, response: Response, conn: sqlite3.Connection = Depends(get_conn)):
        try:
            with conn:
                saved, created = service.add_trip(conn, trip)
        except service.TripConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Поездка {exc.trip_id} уже сохранена с другими данными.",
                    "fields": exc.fields,
                },
            ) from exc
        if not created:
            response.status_code = 200
        return saved

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(BASE_DIR / "static" / "index.html")

    return app


app = create_app()
