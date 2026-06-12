import pytest
import asyncio
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_route_message_no_prefix():
    response = client.post("/route", json={
        "content": "Hello world",
        "prefix": "none",
        "user_id": "test_user"
    })
    assert response.status_code == 200
    data = response.json()
    assert "message_id" in data

def test_route_message_with_prefix():
    response = client.post("/route", json={
        "content": "Test message",
        "prefix": "hm",
        "user_id": "test_user"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "hm"

def test_route_message_cherry_prefix():
    response = client.post("/route", json={
        "content": "Test message for Cherry",
        "prefix": "cherry",
        "user_id": "test_user"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "cherry"

def test_route_message_wb_prefix():
    response = client.post("/route", json={
        "content": "Test message for WorkBuddy",
        "prefix": "wb",
        "user_id": "test_user"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["agent"] == "wb"

def test_status_endpoint():
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "agents" in data
