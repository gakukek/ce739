import os
os.environ["TESTING"] = "1"

import pytest
import asyncio
from httpx import AsyncClient
from httpx import ASGITransport

import database
from models import User
import main

pytestmark = pytest.mark.asyncio


async def create_test_user():
    async with database.SessionLocal() as session:
        # SQLite in-memory with BigInteger primary key may not auto-generate IDs the same
        # as Postgres; set an explicit id for tests to avoid NOT NULL errors.
        user = User(id=1, clerk_user_id="test_clerk_1", username="tester")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def test_alert_create_and_delete():
    # Ensure DB and tables are created before we insert records
    async with database.engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)

    # Create user directly in DB
    user = await create_test_user()

    # Override auth dependency to return our clerk id
    main.app.dependency_overrides[main.get_current_user] = lambda: "test_clerk_1"

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create aquarium (device_uid can be empty)
        resp = await ac.post("/aquariums", json={"name": "Tank1", "device_uid": ""})
        assert resp.status_code == 200, resp.text
        aq = resp.json()
        aq_id = aq["id"]

        # Create an alert
        resp = await ac.post("/alerts", json={"aquarium_id": aq_id, "type": "CMD_FEED", "message": "feed now"})
        assert resp.status_code == 200, resp.text
        alert = resp.json()
        alert_id = alert["id"]

        # Delete the alert
        resp = await ac.delete(f"/alerts/{alert_id}")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        # List alerts should be empty
        resp = await ac.get("/alerts", params={"aquarium_id": aq_id})
        assert resp.status_code == 200
        assert resp.json() == []
