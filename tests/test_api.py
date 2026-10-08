from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path):
    application = create_app(database_path=tmp_path / "test.db", seed_path=None)
    with TestClient(application) as test_client:
        yield test_client


def trip(trip_id="trip-1", start="2026-10-01T08:10:00+05:00", end="2026-10-01T08:32:00+05:00", amount=2400, payment="card", commission=360):
    return {"id": trip_id, "start": start, "end": end, "amount": amount, "payment": payment, "commission": commission}


def test_sample_seed_and_daily_summary(tmp_path):
    app = create_app(database_path=tmp_path / "seed.db")
    with TestClient(app) as client:
        day = client.get("/api/days/2026-10-01").json()
        assert [item["id"] for item in day["trips"]] == ["t1", "t2"]
        assert day["summary"] == {
            "trip_count": 2, "revenue": 3900, "commission": 585,
            "net": 3315, "cash": 1500, "card": 2400,
        }


def test_insert_and_idempotent_retry(client):
    payload = trip()
    initial = client.post("/api/trips", json=payload)
    assert initial.status_code == 201
    assert initial.json()["created"] is True
    duplicate = client.post("/api/trips", json=payload)
    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    day = client.get("/api/days/2026-10-01").json()
    assert day["summary"]["trip_count"] == 1
    assert day["summary"]["net"] == 2040


def test_same_id_with_changed_data_is_conflict(client):
    assert client.post("/api/trips", json=trip()).status_code == 201
    bad = client.post("/api/trips", json=trip(amount=2600))
    assert bad.status_code == 409
    assert client.get("/api/days/2026-10-01").json()["summary"]["revenue"] == 2400


@pytest.mark.parametrize("changes", [
    {"amount": 0},
    {"amount": -1},
    {"amount": 1.5},
    {"commission": -1},
    {"commission": 2500},
    {"start": "2026-10-01T08:32:00+05:00"},
    {"start": "2026-10-01T09:00:00+05:00"},
    {"start": "2026-10-01T08:10:00"},
    {"end": "2026-10-01T08:32:00"},
    {"payment": "wire"},
    {"id": " "},
    {"extra_field": "forbidden"},
])
def test_invalid_trips_rejected(client, changes):
    response = client.post("/api/trips", json={**trip(), **changes})
    assert response.status_code == 422
    assert client.get("/api/days/2026-10-01").json()["summary"]["trip_count"] == 0


def test_local_day_is_not_utc_day(client):
    # This trip is Oct 1 in Kazakhstan but Sep 30 in UTC.
    payload = trip(start="2026-10-01T00:10:00+05:00", end="2026-10-01T00:20:00+05:00")
    assert client.post("/api/trips", json=payload).status_code == 201
    assert client.get("/api/days/2026-10-01").json()["summary"]["trip_count"] == 1
    assert client.get("/api/days/2026-09-30").json()["summary"]["trip_count"] == 0


def test_equivalent_timestamps_same_trip_are_retries(client):
    assert client.post("/api/trips", json=trip()).status_code == 201
    equivalent = trip(start="2026-10-01T03:10:00+00:00", end="2026-10-01T03:32:00+00:00")
    result = client.post("/api/trips", json=equivalent)
    assert result.status_code == 200
    assert result.json()["created"] is False


def test_empty_day_and_date_validation(client):
    assert client.get("/api/days/2026-10-02").json()["summary"]["net"] == 0
    assert client.get("/api/days/2026-10-02").json()["trips"] == []
    for date in ("not-a-date", "2026-02-30", "2026-1-1"):
        assert client.get(f"/api/days/{date}").status_code == 422


def test_parallel_duplicate_requests_are_atomic(client):
    payload = trip()
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: client.post("/api/trips", json=payload), range(6)))
    assert sorted(result.status_code for result in results) == [200] * 5 + [201]
    assert client.get("/api/days/2026-10-01").json()["summary"]["trip_count"] == 1


def test_persists_between_application_restarts(tmp_path):
    path = tmp_path / "persistent.db"
    with TestClient(create_app(database_path=path, seed_path=None)) as first:
        assert first.post("/api/trips", json=trip()).status_code == 201
    with TestClient(create_app(database_path=path, seed_path=None)) as second:
        assert second.get("/api/days/2026-10-01").json()["summary"]["trip_count"] == 1


def test_homepage_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Дневник смен" in response.text
