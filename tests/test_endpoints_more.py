import os
os.environ["TESTING"] = "1"

import pytest
import asyncio
from httpx import AsyncClient, ASGITransport

import database
import main
from simulator_runner import create_http_client_for_app

pytestmark = pytest.mark.asyncio


async def setup_db_and_user():
    async with database.engine.begin() as conn:
        # Ensure clean slate for this test: drop then create tables
        await conn.run_sync(database.Base.metadata.drop_all)
        await conn.run_sync(database.Base.metadata.create_all)

    async with database.SessionLocal() as session:
        # create test user id=1
        from models import User
        u = User(id=1, clerk_user_id="test_clerk_1", username="tester")
        session.add(u)
        await session.commit()


async def test_sensor_feeding_schedule_flow():
    await setup_db_and_user()
    # auth override
    main.app.dependency_overrides[main.get_current_user] = lambda: "test_clerk_1"

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # create aquarium
        resp = await ac.post("/aquariums", json={"name": "TankA", "device_uid": "dev-1", "feeding_volume_grams": 2.5})
        assert resp.status_code == 200
        aq = resp.json()
        aq_id = aq["id"]

        # post sensor data
        sd = {"aquarium_id": aq_id, "temperature_c": 25.5, "ph": 7.2}
        resp = await ac.post("/sensor_data", json=sd)
        assert resp.status_code == 200

        # list sensor data
        resp = await ac.get("/sensor_data", params={"aquarium_id": aq_id})
        assert resp.status_code == 200
        arr = resp.json()
        assert len(arr) == 1

        # create schedule
        sched = {"aquarium_id": aq_id, "type": "interval", "interval_hours": 24, "feed_volume_grams": 2.5}
        resp = await ac.post("/schedules", json=sched)
        assert resp.status_code == 200

        # list schedules
        resp = await ac.get("/schedules", params={"aquarium_id": aq_id})
        assert resp.status_code == 200
        schs = resp.json()
        assert len(schs) == 1

        # create alert and ensure feeding_logs created after simulator run_once
        resp = await ac.post("/alerts", json={"aquarium_id": aq_id, "type": "CMD_FEED", "message": "please feed"})
        assert resp.status_code == 200
        alert = resp.json()

        # run simulator run_once to process alerts
        client = await create_http_client_for_app(app=main.app)
        async with client:
            from simulator_runner import SimulatorRunner
            runner = SimulatorRunner()
            await runner.run_once(client)

        # feeding logs should exist
        resp = await ac.get("/feeding_logs", params={"aquarium_id": aq_id})
        assert resp.status_code == 200
        fls = resp.json()
        assert len(fls) >= 1

        # alerts should be gone (simulator deletes them)
        resp = await ac.get("/alerts", params={"aquarium_id": aq_id})
        assert resp.status_code == 200
        assert resp.json() == []
