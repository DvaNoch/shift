import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import create_app
from app.service import SeedError, seed_from_file
from conftest import PROJECT_SEED


def count_trips(client, day="2026-10-01"):
    return len(client.get("/trips", params={"date": day}).json())


def test_new_trip_is_created(client, make_trip):
    response = client.post("/trips", json=make_trip())

    assert response.status_code == 201
    assert response.json() == {
        "id": "trip-1",
        "start": "2026-10-01T08:10:00+05:00",
        "end": "2026-10-01T08:35:00+05:00",
        "amount": 1500,
        "payment": "cash",
        "commission": 225,
        "local_date": "2026-10-01",
    }


def test_resending_same_trip_returns_existing_record(client, make_trip):
    first = client.post("/trips", json=make_trip())
    second = client.post("/trips", json=make_trip())

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert count_trips(client) == 1


def test_resending_same_data_in_other_notation_is_not_a_conflict(client, make_trip):
    client.post("/trips", json=make_trip())
    response = client.post("/trips", json=make_trip(amount="1500.00", commission=225.0))

    assert response.status_code == 200
    assert count_trips(client) == 1


def test_same_id_with_different_data_is_conflict(client, make_trip):
    client.post("/trips", json=make_trip())
    response = client.post("/trips", json=make_trip(amount=1700))

    assert response.status_code == 409
    assert response.json()["detail"]["fields"] == ["amount"]
    # Сохранённая запись не изменилась.
    assert client.get("/trips", params={"date": "2026-10-01"}).json()[0]["amount"] == 1500


def test_same_moment_in_other_offset_is_conflict(client, make_trip):
    # Тот же момент, но другое смещение может дать другой день, поэтому это другие данные.
    client.post("/trips", json=make_trip())
    response = client.post(
        "/trips", json=make_trip(start="2026-10-01T03:10:00+00:00", end="2026-10-01T03:35:00+00:00")
    )

    assert response.status_code == 409
    assert response.json()["detail"]["fields"] == ["start", "end"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": 0},
        {"amount": -100},
        {"amount": 1.001},
        {"commission": -1},
        {"commission": 1600},
        {"end": "2026-10-01T08:10:00+05:00"},
        {"end": "2026-10-01T08:00:00+05:00"},
        {"start": "2026-10-01T08:10:00"},
        {"payment": "crypto"},
        {"id": ""},
        {"tip": 100},
    ],
    ids=[
        "zero-amount",
        "negative-amount",
        "fraction-of-tiyn",
        "negative-commission",
        "commission-above-amount",
        "end-equals-start",
        "end-before-start",
        "no-offset",
        "unknown-payment",
        "empty-id",
        "unknown-field",
    ],
)
def test_invalid_trip_is_rejected(client, make_trip, overrides):
    response = client.post("/trips", json=make_trip(**overrides))

    assert response.status_code == 422
    assert count_trips(client) == 0


def test_missing_field_is_rejected(client, make_trip):
    trip = make_trip()
    del trip["end"]

    assert client.post("/trips", json=trip).status_code == 422


@pytest.mark.parametrize("path", ["/trips", "/summary"])
@pytest.mark.parametrize("query", [{"date": "2026-13-01"}, {"date": "вчера"}, {}])
def test_bad_date_is_rejected(client, path, query):
    assert client.get(path, params=query).status_code == 422


def test_loading_file_twice_does_not_duplicate(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)
    with conn:
        first = seed_from_file(conn, PROJECT_SEED)
    with conn:
        second = seed_from_file(conn, PROJECT_SEED)
    total = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    conn.close()

    assert first == total == len(json.loads(PROJECT_SEED.read_text(encoding="utf-8")))
    assert second == 0


def test_restart_does_not_duplicate(tmp_path):
    for _ in range(2):
        with TestClient(create_app(db_path=tmp_path / "test.db", seed_path=PROJECT_SEED)) as client:
            assert count_trips(client) == 2


def test_bad_record_in_file_names_its_id(tmp_path, make_trip):
    seed = tmp_path / "bad.json"
    seed.write_text(json.dumps([make_trip(), make_trip(id="broken", amount=0)]), encoding="utf-8")
    conn = db.connect(tmp_path / "test.db")
    db.init_schema(conn)

    with pytest.raises(SeedError, match="id=broken"):
        with conn:
            seed_from_file(conn, seed)
    # Файл загружается целиком или никак.
    assert conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 0
    conn.close()
