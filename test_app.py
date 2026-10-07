import os
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import app, db


def test_health():
    client = app.test_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json["status"] == "UP"


def test_home():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
