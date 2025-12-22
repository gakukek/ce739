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
from unittest import runner
from datetime import datetime

import httpx


class SimulatorRunner:
    def __init__(self, base_url: str = "http://localhost", auth_header: dict | None = None, token_mapping: dict | None = None):
        """token_mapping: optional dict mapping aquarium `device_uid` or `id` to an auth token.
        If provided, requests for that aquarium will include `Authorization: Bearer <token>` header.
        """
        self.base_url = base_url
        self.auth_header = auth_header or {}
        self.token_mapping = token_mapping or {}
        self.danger_alert_created = {}  # Track which aquariums have had danger alerts created

    def log(self, message: str):
        """Print timestamped log message"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {message}")

    async def run_once(self, client: httpx.AsyncClient):
        self.log("=" * 60)
        self.log("🔄 Starting simulator cycle")
        
        # discover aquariums
        self.log("📡 Fetching aquariums list...")
        resp = await client.get("/aquariums")
        resp.raise_for_status()
        aquariums = resp.json()
        self.log(f"✅ Found {len(aquariums)} aquarium(s)")

        for aq in aquariums:
            aq_id = aq["id"]
            aq_name = aq.get("name", f"Aquarium-{aq_id}")
            self.log(f"\n🐠 Processing: {aq_name} (ID: {aq_id})")
            
            # Decide if we should create a dangerous reading
            # Force danger alert ONCE per aquarium
            should_create_danger = aq_id not in self.danger_alert_created
            
            if should_create_danger:
                # Create dangerous values
                temp = round(29.0 + random.random() * 3, 2)  # 29-32°C (dangerous)
                ph = round(5.5 + random.random() * 0.3, 2)   # 5.5-5.8 (dangerous - too low)
                self.log(f"⚠️  Generating DANGEROUS sensor data for first-time alert")
            else:
                # Normal safe values
                temp = round(24 + random.random() * 3, 2)     # 24-27°C (safe)
                ph = round(7.0 + (random.random() - 0.5) * 0.6, 2)  # 6.7-7.3 (safe)
                self.log(f"✅ Generating normal sensor data")
            
            # send a sensor data point
            sd = {
                "aquarium_id": aq_id,
                "temperature_c": temp,
                "ph": ph,
            }
            self.log(f"   📊 Sensor data: temp={temp}°C, pH={ph}")
            
            headers = {}
            # prefer device_uid token, fall back to aquarium id
            token = None
            device_uid = aq.get("device_uid")
            if device_uid and device_uid in self.token_mapping:
                token = self.token_mapping[device_uid]
                self.log(f"   🔑 Using device_uid token")
            elif str(aq_id) in self.token_mapping:
                token = self.token_mapping[str(aq_id)]
                self.log(f"   🔑 Using aquarium ID token")
            if token:
                headers["Authorization"] = f"Bearer {token}"

            # post sensor data
            self.log(f"   📤 POST /sensor_data")
            resp = await client.post("/sensor_data", json=sd, headers=headers)
            if resp.status_code == 200:
                self.log(f"   ✅ Sensor data posted successfully")
            else:
                self.log(f"   ❌ Failed to post sensor data: {resp.status_code}")
            
            # Check if sensor values are dangerous and report an alert
            try:
                temp = sd.get("temperature_c")
                ph = sd.get("ph")
                # thresholds can be configured via env vars or token_mapping; fallback to defaults
                t_thresh = float(os.getenv("SIM_DANGER_TEMP", "28.0"))
                pH_low = float(os.getenv("SIM_DANGER_PH_LOW", "6.0"))
                pH_high = float(os.getenv("SIM_DANGER_PH_HIGH", "8.5"))
                
                is_dangerous = (temp is not None and temp >= t_thresh) or \
                              (ph is not None and (ph <= pH_low or ph >= pH_high))
                
                if is_dangerous:
                    # create a danger alert
                    reasons = []
                    if temp is not None and temp >= t_thresh:
                        reasons.append(f"Temperature {temp}°C exceeds {t_thresh}°C")
                    if ph is not None and ph <= pH_low:
                        reasons.append(f"pH {ph} below safe minimum {pH_low}")
                    if ph is not None and ph >= pH_high:
                        reasons.append(f"pH {ph} above safe maximum {pH_high}")
                    
                    msg = f"⚠️ DANGER DETECTED in {aq_name}: {', '.join(reasons)}"
                    self.log(f"   🚨 {msg}")
                    
                    alert_payload = {
                        "aquarium_id": aq_id, 
                        "type": "DANGER_SENSOR", 
                        "message": msg
                    }
                    self.log(f"   📤 POST /alerts (DANGER_SENSOR)")
                    alert_resp = await client.post("/alerts", json=alert_payload, headers=headers)
                    
                    if alert_resp.status_code in [200, 201]:
                        self.log(f"   ✅ Danger alert created successfully")
                        self.danger_alert_created[aq_id] = True
                    else:
                        self.log(f"   ❌ Failed to create danger alert: {alert_resp.status_code}")
                else:
                    self.log(f"   ✅ Sensor readings are within safe range")
                    
            except Exception as e:
                self.log(f"   ❌ Error checking/creating danger alert: {e}")

            # poll alerts and handle CMD_FEED
            self.log(f"   📡 GET /alerts?aquarium_id={aq_id}")
            alerts_r = await client.get("/alerts", params={"aquarium_id": aq_id})
            alerts_r.raise_for_status()
            alerts = alerts_r.json()
            self.log(f"   📋 Found {len(alerts)} total alert(s)")
            
            # Separate alerts by type for logging
            cmd_feed_alerts = [a for a in alerts if a.get("type", "").upper().startswith("CMD_FEED")]
            danger_alerts = [a for a in alerts if a.get("type", "") == "DANGER_SENSOR"]
            other_alerts = [a for a in alerts if a not in cmd_feed_alerts and a not in danger_alerts]
            
            if danger_alerts:
                self.log(f"      ⚠️  {len(danger_alerts)} DANGER_SENSOR alert(s) present")
            if cmd_feed_alerts:
                self.log(f"      🍽️  {len(cmd_feed_alerts)} CMD_FEED alert(s) to process")
            if other_alerts:
                self.log(f"      ℹ️  {len(other_alerts)} other alert(s)")
            
            for a in alerts:
                alert_type = a.get("type", "UNKNOWN")
                alert_id = a.get("id")
                
                if alert_type and alert_type.upper().startswith("CMD_FEED"):
                    self.log(f"      🍽️  Processing CMD_FEED alert #{alert_id}")
                    # create a feeding log
                    fl = {
                        "aquarium_id": aq_id, 
                        "mode": "AUTO", 
                        "volume_grams": aq.get("feeding_volume_grams", 1)
                    }
                    self.log(f"         📤 POST /feeding_logs (volume={fl['volume_grams']}g)")
                    await client.post("/feeding_logs", json=fl, headers=headers)
                    self.log(f"         ✅ Feeding log created")
                    
                    # delete alert to ACK
                    self.log(f"         📤 DELETE /alerts/{alert_id}")
                    await client.delete(f"/alerts/{alert_id}", headers=headers)
                    self.log(f"         ✅ CMD_FEED alert acknowledged and deleted")
                elif alert_type == "DANGER_SENSOR":
                    self.log(f"      ⚠️  DANGER_SENSOR alert #{alert_id} exists: {a.get('message', 'No message')}")
                    self.log(f"         (User needs to resolve this via UI)")
                else:
                    self.log(f"      ℹ️  Other alert #{alert_id}: type={alert_type}")

        self.log("\n✅ Simulator cycle completed")
        self.log("=" * 60 + "\n")

    async def run_loop(self, client: httpx.AsyncClient, interval: float = 5.0):
        cycle_count = 0
        while True:
            try:
                cycle_count += 1
                self.log(f"\n🔁 CYCLE #{cycle_count}")
                await self.run_once(client)
            except Exception as e:
                # log errors and continue
                self.log(f"❌ ERROR in simulator cycle: {e}")
                import traceback
                traceback.print_exc()
            
            self.log(f"⏳ Waiting {interval} seconds until next cycle...\n")
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
        print("🚀 Starting Aquarium Simulator")
        print(f"📍 Target URL: {args.url}")
        print(f"⏱️  Interval: {args.interval} seconds")
        print(f"🔧 Danger thresholds: temp>={os.getenv('SIM_DANGER_TEMP', '28.0')}°C, pH<={os.getenv('SIM_DANGER_PH_LOW', '6.0')} or pH>={os.getenv('SIM_DANGER_PH_HIGH', '8.5')}")
        print("=" * 60 + "\n")
        
        async with await create_http_client_for_app(base_url=args.url) as client:
            runner = SimulatorRunner(base_url=args.url)
            await runner.run_loop(client, interval=args.interval)

    asyncio.run(main())