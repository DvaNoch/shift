from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PROJECT_SEED = Path(__file__).resolve().parent.parent / "trips.json"


@pytest.fixture
def client(tmp_path):
    """Приложение с пустой временной базой."""
    seed = tmp_path / "empty.json"
    seed.write_text("[]", encoding="utf-8")
    with TestClient(create_app(db_path=tmp_path / "test.db", seed_path=seed)) as c:
        yield c


@pytest.fixture
def seeded_client(tmp_path):
    """Приложение с временной базой, заполненной из trips.json проекта."""
    with TestClient(create_app(db_path=tmp_path / "test.db", seed_path=PROJECT_SEED)) as c:
        yield c


@pytest.fixture
def make_trip():
    def factory(**overrides):
        trip = {
            "id": "trip-1",
            "start": "2026-10-01T08:10:00+05:00",
            "end": "2026-10-01T08:35:00+05:00",
            "amount": 1500,
            "payment": "cash",
            "commission": 225,
        }
        trip.update(overrides)
        return trip

    return factory
