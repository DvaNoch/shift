"""Пример из задания на данных trips.json."""


def test_summary_for_2026_10_01(seeded_client):
    summary = seeded_client.get("/summary", params={"date": "2026-10-01"}).json()

    assert summary["trips"] == 2
    assert summary["revenue"] == 3900
    assert summary["commission"] == 585
    assert summary["net"] == 3315
    assert summary["cash"]["revenue"] == 1500
    assert summary["card"]["revenue"] == 2400


def test_trips_for_2026_10_01(seeded_client):
    trips = seeded_client.get("/trips", params={"date": "2026-10-01"}).json()

    # t-003 начинается в 00:20 2 октября по +05:00 (в UTC это ещё 1 октября)
    # и в этот день попадать не должна.
    assert [t["id"] for t in trips] == ["t-001", "t-002"]
