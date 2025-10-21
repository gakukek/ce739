import os
import time
import json
import uuid
import logging
import random
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("device-sim-http")

API_BASE = os.getenv("API_BASE_URL", "https://aquascape.onrender.com")
AQUARIUM_ID = os.getenv("AQUARIUM_ID", 1)  # if not set, simulator will create user + aquarium
DEVICE_UID = os.getenv("DEVICE_UID", f"sim-{uuid.uuid4().hex[:8]}")
PUBLISH_INTERVAL = float(os.getenv("PUBLISH_INTERVAL", "20"))  # secs between sensor posts
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "15"))  # secs between alert polls

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500,502,503,504], allowed_methods=["GET","POST","PUT","DELETE"])
session.mount("https://", HTTPAdapter(max_retries=retries))
session.mount("http://", HTTPAdapter(max_retries=retries))

def headers():
    h = {"Content-Type": "application/json"}
    return h

def iso_ts():
    return datetime.now(timezone.utc).isoformat()

def api_post(path, payload):
    url = API_BASE.rstrip("/") + "/" + path.lstrip("/")
    r = session.post(url, json=payload, headers=headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def api_get(path, params=None):
    url = API_BASE.rstrip("/") + "/" + path.lstrip("/")
    r = session.get(url, params=params, headers=headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def api_put(path, payload):
    url = API_BASE.rstrip("/") + "/" + path.lstrip("/")
    r = session.put(url, json=payload, headers=headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def api_delete(path):
    url = API_BASE.rstrip("/") + "/" + path.lstrip("/")
    r = session.delete(url, headers=headers(), timeout=10)
    r.raise_for_status()
    return r.json()

def ensure_sim_aquarium():
    global AQUARIUM_ID
    if AQUARIUM_ID:
        log.info("Using provided AQUARIUM_ID=%s", AQUARIUM_ID)
        return int(AQUARIUM_ID)
    # create a user
    username = f"sim_{uuid.uuid4().hex[:6]}"
    try:
        user = api_post("/users", {"username": username, "email": f"{username}@example.com", "password": "testp4ss"})
        user_id = user["id"]
        log.info("Created simulator user id=%s", user_id)
    except Exception as e:
        log.exception("Failed create user: %s", e)
        raise
    # create aquarium
    aq_payload = {
        "user_id": user_id,
        "name": f"{username}-tank",
        "size_litres": 50.0,
        "device_uid": DEVICE_UID,
        "feeding_volume_grams": 1.5,
        "feeding_period_hours": 24
    }
    try:
        aq = api_post("/aquariums", aq_payload)
        AQUARIUM_ID = aq["id"]
        log.info("Created simulator aquarium id=%s", AQUARIUM_ID)
        return int(AQUARIUM_ID)
    except Exception as e:
        log.exception("Failed create aquarium: %s", e)
        raise

def publish_sensor(aq_id, temp, ph):
    payload = {"aquarium_id": aq_id, "ts": iso_ts(), "temperature_c": round(temp,2), "ph": round(ph,2)}
    try:
        obj = api_post("/sensor_data", payload)
        log.info("Posted sensor_data id=%s %s", obj.get("id"), payload)
    except Exception as e:
        log.exception("Failed to POST sensor_data: %s", e)

def handle_command_alert(alert):
    """
    Expect alert.message to contain JSON with a 'cmd' key, or a simple string command.
    Examples:
      message: '{"cmd":"feed_now","volume":2.0}'
      message: '{"cmd":"update_settings","feeding_volume_grams":2.5,"feeding_period_hours":12}'
    """
    aid = alert["id"]
    msg = alert.get("message") or ""
    log.info("Processing alert id=%s type=%s message=%s", aid, alert.get("type"), msg)
    try:
        cmdobj = json.loads(msg) if msg else {"cmd": alert.get("type")}
    except Exception:
        cmdobj = {"cmd": msg}
    cmd = cmdobj.get("cmd")
    if cmd == "feed_now":
        vol = cmdobj.get("volume")
        payload = {"aquarium_id": alert["aquarium_id"], "mode":"MANUAL", "volume_grams": vol, "actor": "simulator"}
        try:
            fl = api_post("/feeding_logs", payload)
            log.info("Created feeding_log id=%s for feed_now", fl.get("id"))
        except Exception as e:
            log.exception("Failed creating feeding_log: %s", e)
    elif cmd == "update_settings":
        # fetch aquarium to copy user_id and current fields
        aq_id = alert["aquarium_id"]
        try:
            aq = api_get(f"/aquariums/{aq_id}")
        except Exception as e:
            log.exception("Failed fetching aquarium %s: %s", aq_id, e)
            return
        updates = {}
        for k in ("feeding_volume_grams","feeding_period_hours","name","size_litres"):
            if k in cmdobj:
                updates[k] = cmdobj[k]
        if not updates:
            log.warning("update_settings command contained no known fields: %s", cmdobj)
        else:
            payload = {
                "user_id": aq["user_id"],
                "name": updates.get("name", aq["name"]),
                "size_litres": updates.get("size_litres", aq.get("size_litres")),
                "device_uid": aq["device_uid"],
                "feeding_volume_grams": updates.get("feeding_volume_grams", aq.get("feeding_volume_grams")),
                "feeding_period_hours": updates.get("feeding_period_hours", aq.get("feeding_period_hours"))
            }
            try:
                updated = api_put(f"/aquariums/{aq_id}", payload)
                log.info("Updated aquarium %s: %s", aq_id, updated)
            except Exception as e:
                log.exception("Failed updating aquarium: %s", e)
    else:
        log.warning("Unknown cmd: %s", cmd)
    # ACK by deleting the alert
    try:
        api_delete(f"/alerts/{aid}")
        log.info("Deleted/ACKed alert id=%s", aid)
    except Exception as e:
        log.exception("Failed deleting alert id=%s : %s", aid, e)

def poll_and_handle_alerts(aq_id):
    try:
        alerts = api_get("/alerts", params={"aquarium_id": aq_id})
    except Exception as e:
        log.exception("Failed to fetch alerts: %s", e)
        return
    for a in alerts:
        t = (a.get("type") or "").upper()
        # treat types starting with CMD_ or plain CMD as commands
        if t.startswith("CMD") or (a.get("message") and "cmd" in (a.get("message") or "")):
            handle_command_alert(a)
        else:
            log.debug("Skipping non-command alert id=%s type=%s", a.get("id"), a.get("type"))

def run_loop():
    aq_id = ensure_sim_aquarium()
    # simple initial sensor baselines
    temp = float(os.getenv("TEMP_BASE", "25.0"))
    ph = float(os.getenv("PH_BASE", "7.2"))

    last_pub = 0.0
    last_poll = 0.0
    publish_count = 0
    while True:
        now = time.time()
        if now - last_pub >= PUBLISH_INTERVAL:
            # random walk
            temp += random.uniform(-0.2, 0.2)
            ph += random.uniform(-0.05, 0.05)
            if publish_count > 2:
                temp += random.uniform(-2, 2)
                ph += random.uniform(-2, 2)
            publish_sensor(aq_id, temp, ph)
            last_pub = now
            publish_count += 1
        if now - last_poll >= POLL_INTERVAL:
            poll_and_handle_alerts(aq_id)
            last_poll = now
        time.sleep(0.5)

if __name__ == "__main__":
    try:
        run_loop()
    except KeyboardInterrupt:
        log.info("Simulator stopped by user")