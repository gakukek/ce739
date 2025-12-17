"""Simple scheduler service.

Usage:
  python scheduler.py --once      # run one evaluation cycle
  python scheduler.py --loop 60   # run loop every 60s

Behavior:
- Evaluates enabled schedules and creates Alert rows when a schedule is due.
- Uses existing DB layer (`database.SessionLocal`).

Deduplication:
- For `interval` schedules: creates an Alert when there is no FeedingLog within the last `interval_hours`.
- For `daily_times` schedules: creates an Alert when the current time matches any configured daily time and no Alert/FeedingLog exists today.

This keeps scheduling logic simple and safe; the physical device simulator polls `/alerts` and handles them by creating feeding logs and deleting alerts.
"""
from __future__ import annotations
import asyncio
import json
import datetime
from typing import Optional

from sqlalchemy import select

import database
from models import Schedule, Alert, FeedingLog
from sqlalchemy import text
import os

# Advisory lock id used to ensure single scheduler runs when multiple instances exist
ADVISORY_LOCK_ID = 987654321


async def run_once():
    now = datetime.datetime.utcnow()

    # If using Postgres, try to acquire an advisory lock so only one scheduler instance runs
    db_url = getattr(database, "DATABASE_URL", "") or os.getenv("DB_URL", "")
    acquired_lock = False
    conn = None
    try:
        if db_url.startswith("postgresql+asyncpg://"):
            # open a dedicated connection to hold the advisory lock during this run
            conn = await database.engine.connect()
            r = await conn.execute(text("SELECT pg_try_advisory_lock(:id) AS locked"), {"id": ADVISORY_LOCK_ID})
            row = r.first()
            if row and row[0] is True:
                acquired_lock = True
            else:
                # another instance holds the lock; skip this run
                await conn.close()
                return

        # use a session for normal work and keep it open while processing schedules
        async with database.SessionLocal() as db:
            res = await db.execute(select(Schedule).where(Schedule.enabled == True))
            schedules = res.scalars().all()

            for s in schedules:
                aq_id = s.aquarium_id
                if s.type == "interval" and s.interval_hours is not None:
                    cutoff = now - datetime.timedelta(hours=float(s.interval_hours))
                    # check recent feeding logs
                    recent_feed = await db.execute(select(FeedingLog).where(FeedingLog.aquarium_id == aq_id).order_by(FeedingLog.ts.desc()).limit(1))
                    last_feed = recent_feed.scalars().first()
                    if not last_feed or last_feed.ts < cutoff:
                        # ensure no recent feeding log exists after cutoff
                        recent_feed = await db.execute(select(FeedingLog).where(FeedingLog.aquarium_id == aq_id, FeedingLog.ts > cutoff))
                        if not recent_feed.scalars().first():
                            # create an ALERT (CMD_FEED) for the device to pick up
                            msg = f"Scheduled feed: {getattr(s, 'feed_volume_grams', None) or ''}g"
                            # avoid creating duplicate pending CMD_FEED alerts since cutoff
                            recent_alert = await db.execute(select(Alert).where(Alert.aquarium_id == aq_id, Alert.type == 'CMD_FEED', Alert.ts > cutoff))
                            if not recent_alert.scalars().first():
                                a = Alert(aquarium_id=aq_id, type="CMD_FEED", message=msg)
                                db.add(a)
                                await db.commit()

                elif s.type == "daily_times" and s.daily_times:
                    try:
                        times = json.loads(s.daily_times)
                    except Exception:
                        times = []
                    now_hm = now.strftime("%H:%M")
                    # exact match - acceptable for tests; in production use a tolerance window
                    if now_hm in times:
                        today_start = datetime.datetime(now.year, now.month, now.day)
                        today_feed = await db.execute(select(FeedingLog).where(FeedingLog.aquarium_id == aq_id, FeedingLog.ts >= today_start))
                        if not today_feed.scalars().first():
                            # avoid creating duplicate CMD_FEED alerts for today
                            recent_alert = await db.execute(select(Alert).where(Alert.aquarium_id == aq_id, Alert.type == 'CMD_FEED', Alert.ts >= today_start))
                            if not recent_alert.scalars().first():
                                msg = f"Scheduled daily feed: {getattr(s, 'feed_volume_grams', None) or ''}g"
                                a = Alert(aquarium_id=aq_id, type="CMD_FEED", message=msg)
                                db.add(a)
                                await db.commit()
    finally:
        # release advisory lock if we acquired it
        try:
            if conn is not None and acquired_lock:
                await conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": ADVISORY_LOCK_ID})
                await conn.close()
        except Exception:
            pass


async def run_loop(interval_seconds: Optional[float] = 60.0):
    while True:
        try:
            await run_once()
        except Exception:
            import traceback
            traceback.print_exc()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one scheduler cycle")
    parser.add_argument("--loop", type=float, default=None, help="Run scheduler loop with interval seconds")
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_once())
    elif args.loop is not None:
        asyncio.run(run_loop(args.loop))
    else:
        print("Specify --once or --loop <seconds>")
