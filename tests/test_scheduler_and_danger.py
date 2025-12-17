import os
os.environ["TESTING"] = "1"

import pytest
import asyncio
from httpx import AsyncClient, ASGITransport

import database
import main
from simulator_runner import create_http_client_for_app, SimulatorRunner
import scheduler

pytestmark = pytest.mark.asyncio


async def setup_db():
    async with database.engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.drop_all)
        await conn.run_sync(database.Base.metadata.create_all)


async def test_schedule_creates_alert_and_simulator_handles_it():
    await setup_db()
    # create user and aquarium
    async with database.SessionLocal() as session:
        from models import User, Aquarium, Schedule
        u = User(id=1, clerk_user_id="test_clerk_sched", username="schedder")
        session.add(u)
        await session.commit()

    # override auth
    main.app.dependency_overrides[main.get_current_user] = lambda: "test_clerk_sched"

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # create aquarium
        resp = await ac.post("/aquariums", json={"name": "SchedTank", "device_uid": "dev-s1", "feeding_volume_grams": 2.0})
        assert resp.status_code == 200
        aq = resp.json()
        aq_id = aq["id"]

        # add schedule interval=0 to force immediate
        sch = {"aquarium_id": aq_id, "type": "interval", "interval_hours": 0}
        resp = await ac.post("/schedules", json=sch)
        assert resp.status_code == 200

    # run scheduler once
    await scheduler.run_once()

    # After scheduler, there should be a CMD_FEED alert for the aquarium
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/alerts", params={"aquarium_id": aq_id})
        assert resp.status_code == 200
        alerts = resp.json()
        assert any(a.get("type") == "CMD_FEED" for a in alerts)

    # Now run the simulator once to process the alert (device should create FeedingLog and ACK)
    client = await create_http_client_for_app(app=main.app)
    async with client:
        runner = SimulatorRunner()
        await runner.run_once(client)

    # After simulator processed the CMD_FEED, there should be a FeedingLog and no CMD_FEED alerts
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/feeding_logs", params={"aquarium_id": aq_id})
        assert resp.status_code == 200
        fls = resp.json()
        assert len(fls) >= 1

        resp = await ac.get("/alerts", params={"aquarium_id": aq_id})
        assert resp.status_code == 200
        assert not any(a.get("type") == "CMD_FEED" for a in resp.json())


async def test_simulator_posts_danger_alerts():
    await setup_db()
    # create user and aquarium
    async with database.SessionLocal() as session:
        from models import User
        u = User(id=1, clerk_user_id="test_clerk_danger", username="danger")
        session.add(u)
        await session.commit()

    main.app.dependency_overrides[main.get_current_user] = lambda: "test_clerk_danger"

    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post("/aquariums", json={"name": "DangerTank", "device_uid": "dev-d1"})
        assert resp.status_code == 200
        aq = resp.json()
        aq_id = aq["id"]

    # run simulator but inject a high temperature by monkeypatching random.random
    import random as _random

    class FakeRandom:
        def random(self):
            return 1.0  # will push temperature near 28

    orig_random = _random.random
    _random.random = FakeRandom().random

    try:
        client = await create_http_client_for_app(app=main.app)
        async with client:
            runner = SimulatorRunner()
            await runner.run_once(client)
    finally:
        _random.random = orig_random

    # now alerts should include DANGER_SENSOR
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/alerts", params={"aquarium_id": aq_id})
        assert resp.status_code == 200
        alerts = resp.json()
        assert any(a.get("type") == "DANGER_SENSOR" for a in alerts)
