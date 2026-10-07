import datetime as dt
from decimal import Decimal

from app.models import TripIn
from app.service import summarize

DAY = dt.date(2026, 10, 1)


def trip(id, amount, payment, commission, start="2026-10-01T10:00:00+05:00", end="2026-10-01T10:30:00+05:00"):
    return TripIn(id=id, start=start, end=end, amount=amount, payment=payment, commission=commission)


def test_summary_of_mixed_day():
    summary = summarize(
        DAY,
        [
            trip("a", "1000", "cash", "150"),
            trip("b", "2000.50", "card", "300.25"),
            trip("c", "500", "cash", "0"),
        ],
    )

    assert summary.trips == 3
    assert summary.revenue == Decimal("3500.50")
    assert summary.commission == Decimal("450.25")
    assert summary.net == Decimal("3050.25")
    assert (summary.cash.trips, summary.cash.revenue) == (2, Decimal("1500"))
    assert (summary.card.trips, summary.card.revenue) == (1, Decimal("2000.50"))


def test_summary_of_empty_day_is_zero():
    summary = summarize(DAY, [])

    assert summary.date == DAY
    assert summary.trips == 0
    assert summary.revenue == summary.commission == summary.net == 0
    assert summary.cash.trips == summary.card.trips == 0
    assert summary.cash.revenue == summary.card.revenue == 0


def test_empty_day_via_api(client):
    assert client.get("/trips", params={"date": "2026-10-01"}).json() == []
    assert client.get("/summary", params={"date": "2026-10-01"}).json() == {
        "date": "2026-10-01",
        "trips": 0,
        "revenue": 0,
        "commission": 0,
        "net": 0,
        "cash": {"trips": 0, "revenue": 0},
        "card": {"trips": 0, "revenue": 0},
    }


def test_money_sums_without_float_errors(client, make_trip):
    client.post("/trips", json=make_trip(id="a", amount=0.1, commission=0))
    client.post("/trips", json=make_trip(id="b", amount=0.2, commission=0))

    assert client.get("/summary", params={"date": "2026-10-01"}).json()["revenue"] == 0.3


def test_trip_just_after_midnight_belongs_to_its_local_day(client, make_trip):
    # 00:20 по +05:00 — это 19:20 UTC предыдущего дня.
    client.post("/trips", json=make_trip(start="2026-10-02T00:20:00+05:00", end="2026-10-02T00:45:00+05:00"))

    assert client.get("/summary", params={"date": "2026-10-01"}).json()["trips"] == 0
    assert client.get("/summary", params={"date": "2026-10-02"}).json()["trips"] == 1
    trips = client.get("/trips", params={"date": "2026-10-02"}).json()
    assert [t["id"] for t in trips] == ["trip-1"]
    assert trips[0]["start"] == "2026-10-02T00:20:00+05:00"
    assert trips[0]["local_date"] == "2026-10-02"


def test_trip_just_before_midnight_in_negative_offset(client, make_trip):
    # 23:30 по -03:00 — это уже 02:30 UTC следующего дня.
    client.post("/trips", json=make_trip(start="2026-10-01T23:30:00-03:00", end="2026-10-01T23:55:00-03:00"))

    assert client.get("/summary", params={"date": "2026-10-01"}).json()["trips"] == 1
    assert client.get("/summary", params={"date": "2026-10-02"}).json()["trips"] == 0


def test_trip_crossing_midnight_counts_on_start_day(client, make_trip):
    client.post("/trips", json=make_trip(start="2026-10-01T23:40:00+05:00", end="2026-10-02T00:25:00+05:00"))

    assert client.get("/summary", params={"date": "2026-10-01"}).json()["revenue"] == 1500
    assert client.get("/summary", params={"date": "2026-10-02"}).json()["trips"] == 0


def test_trips_listed_in_start_order(client, make_trip):
    client.post("/trips", json=make_trip(id="late", start="2026-10-01T18:00:00+05:00", end="2026-10-01T18:30:00+05:00"))
    client.post("/trips", json=make_trip(id="early", start="2026-10-01T07:00:00+05:00", end="2026-10-01T07:30:00+05:00"))

    trips = client.get("/trips", params={"date": "2026-10-01"}).json()
    assert [t["id"] for t in trips] == ["early", "late"]
