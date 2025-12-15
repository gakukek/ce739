"""Simulator runner that can run in two modes:
- test mode: uses an httpx ASGITransport client against the FastAPI app (no external auth required when test harness overrides dependencies)
- http mode: uses normal HTTP client to talk to an externally running server (requires Authorization header)

Behavior:
- polls `/aquariums` (uses the app's auth dependency) to discover registered aquariums
- for each aquarium, sends one `POST /sensor_data` payload with a random temperature/ph
- polls `/alerts` for the aquarium and if it sees an alert of type `CMD_FEED`, it will
  create a `POST /feeding_logs` and then `DELETE /alerts/{id}` to ACK it.

This runner exposes `run_once(client)` for testing (single-cycle) and an async `run_loop(client, interval)` for continuous mode.
"""
from __future__ import annotations
import asyncio
import random
from typing import Any
import os

import httpx


class SimulatorRunner:
    def __init__(self, base_url: str = "http://localhost", auth_header: dict | None = None, token_mapping: dict | None = None):
        """token_mapping: optional dict mapping aquarium `device_uid` or `id` to an auth token.
        If provided, requests for that aquarium will include `Authorization: Bearer <token>` header.
        """
        self.base_url = base_url
        self.auth_header = auth_header or {}
        self.token_mapping = token_mapping or {}

    async def run_once(self, client: httpx.AsyncClient):
        # discover aquariums
        resp = await client.get("/aquariums")
        resp.raise_for_status()
        aquariums = resp.json()

        for aq in aquariums:
            aq_id = aq["id"]
            # send a sensor data point
            sd = {
                "aquarium_id": aq_id,
                "temperature_c": round(22 + random.random() * 6, 2),
                "ph": round(7.0 + (random.random() - 0.5) * 0.6, 2),
            }
            headers = {}
            # prefer device_uid token, fall back to aquarium id
            token = None
            device_uid = aq.get("device_uid")
            if device_uid and device_uid in self.token_mapping:
                token = self.token_mapping[device_uid]
            elif str(aq_id) in self.token_mapping:
                token = self.token_mapping[str(aq_id)]
            if token:
                headers["Authorization"] = f"Bearer {token}"

            # post sensor data
            resp = await client.post("/sensor_data", json=sd, headers=headers)
            # If sensor values are dangerous, report an alert to the backend
            try:
                temp = sd.get("temperature_c")
                ph = sd.get("ph")
                # thresholds can be configured via env vars or token_mapping; fallback to defaults
                t_thresh = float(os.getenv("SIM_DANGER_TEMP", "28.0"))
                pH_low = float(os.getenv("SIM_DANGER_PH_LOW", "6.0"))
                pH_high = float(os.getenv("SIM_DANGER_PH_HIGH", "8.5"))
                if (temp is not None and temp >= t_thresh) or (ph is not None and (ph <= pH_low or ph >= pH_high)):
                    # create a danger alert
                    msg = f"Dangerous reading: temp={temp}, ph={ph}"
                    alert_payload = {"aquarium_id": aq_id, "type": "DANGER_SENSOR", "message": msg}
                    await client.post("/alerts", json=alert_payload, headers=headers)
            except Exception:
                pass

            # poll alerts and handle CMD_FEED
            alerts_r = await client.get("/alerts", params={"aquarium_id": aq_id})
            alerts_r.raise_for_status()
            alerts = alerts_r.json()
            for a in alerts:
                if a.get("type") and a["type"].upper().startswith("CMD_FEED"):
                    # create a feeding log
                    fl = {"aquarium_id": aq_id, "mode": "AUTO", "volume_grams": aq.get("feeding_volume_grams", 1)}
                    await client.post("/feeding_logs", json=fl, headers=headers)
                    # delete alert to ACK
                    await client.delete(f"/alerts/{a['id']}", headers=headers)

    async def run_loop(self, client: httpx.AsyncClient, interval: float = 5.0):
        while True:
            try:
                await self.run_once(client)
            except Exception:
                # swallow errors for now and continue
                import traceback
                traceback.print_exc()
            await asyncio.sleep(interval)


async def create_http_client_for_app(app=None, base_url: str = "http://test") -> httpx.AsyncClient:
    """Helper to create an httpx AsyncClient.
    If `app` is provided, this uses ASGITransport (test mode). Otherwise it creates a normal client and will use env AUTH.
    """
    if app is not None:
        from httpx import ASGITransport
        transport = ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url=base_url)
    else:
        headers = {}
        token = os.getenv("SIMULATOR_AUTH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return httpx.AsyncClient(base_url=base_url, headers=headers)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.getenv("API_URL", "http://localhost:8000"))
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    async def main():
        async with httpx.AsyncClient(base_url=args.url) as client:
            runner = SimulatorRunner(base_url=args.url)
            await runner.run_loop(client, interval=args.interval)

    asyncio.run(main())
