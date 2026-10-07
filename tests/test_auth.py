from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path):
    seed = tmp_path / "empty.json"
    seed.write_text("[]", encoding="utf-8")
    app = create_app(db_path=tmp_path / "test.db", seed_path=seed, username="driver", password="secret")
    return TestClient(app)


def test_without_credentials_returns_401(tmp_path):
    with make_client(tmp_path) as c:
        for path in ["/", "/trips?date=2026-10-01", "/summary?date=2026-10-01"]:
            res = c.get(path)
            assert res.status_code == 401
            assert res.headers["WWW-Authenticate"] == "Basic"


def test_wrong_password_returns_401(tmp_path):
    with make_client(tmp_path) as c:
        assert c.get("/trips?date=2026-10-01", auth=("driver", "wrong")).status_code == 401
        assert c.get("/trips?date=2026-10-01", auth=("other", "secret")).status_code == 401


def test_correct_credentials(tmp_path, make_trip):
    with make_client(tmp_path) as c:
        auth = ("driver", "secret")
        assert c.get("/", auth=auth).status_code == 200
        assert c.post("/trips", json=make_trip(), auth=auth).status_code == 201
        assert c.get("/summary?date=2026-10-01", auth=auth).json()["trips"] == 1


def test_docs_hidden_with_password(tmp_path):
    with make_client(tmp_path) as c:
        assert c.get("/docs").status_code in (401, 404)
        assert c.get("/openapi.json").status_code in (401, 404)
