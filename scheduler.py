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
from models import Schedule, Alert, FeedingLog, Aquarium
from sqlalchemy import text
import os

# Advisory lock id used to ensure single scheduler runs when multiple instances exist
ADVISORY_LOCK_ID = 987654321


def log(message: str, level: str = "INFO"):
    """Print timestamped log message"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {
        "INFO": "\033[36m",      # Cyan
        "SUCCESS": "\033[32m",   # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "SCHEDULER": "\033[94m", # Blue
    }
    reset = "\033[0m"
    color = colors.get(level, "")
    print(f"{color}[{timestamp}] [SCHEDULER] {message}{reset}")


async def run_once():
    now = datetime.datetime.utcnow()
    
    log("=" * 70, "SCHEDULER")
    log(f"⏰ SCHEDULER CYCLE STARTING at {now.strftime('%Y-%m-%d %H:%M:%S')} UTC", "SCHEDULER")
    log("=" * 70, "SCHEDULER")

    # If using Postgres, try to acquire an advisory lock so only one scheduler instance runs
    db_url = getattr(database, "DATABASE_URL", "") or os.getenv("DB_URL", "")
    acquired_lock = False
    conn = None
    try:
        if db_url.startswith("postgresql+asyncpg://"):
            log("🔒 Attempting to acquire PostgreSQL advisory lock...", "INFO")
            # open a dedicated connection to hold the advisory lock during this run
            conn = await database.engine.connect()
            r = await conn.execute(text("SELECT pg_try_advisory_lock(:id) AS locked"), {"id": ADVISORY_LOCK_ID})
            row = r.first()
            if row and row[0] is True:
                acquired_lock = True
                log("✅ Advisory lock acquired", "SUCCESS")
            else:
                # another instance holds the lock; skip this run
                log("⚠️  Another scheduler instance is running, skipping this cycle", "WARNING")
                await conn.close()
                return
        else:
            log("ℹ️  Not using PostgreSQL, skipping advisory lock", "INFO")

        # use a session for normal work and keep it open while processing schedules
        async with database.SessionLocal() as db:
            log("📋 Fetching all schedules...", "INFO")
            res = await db.execute(select(Schedule).where(Schedule.enabled == True))
            schedules = res.scalars().all()
            
            log(f"✅ Found {len(schedules)} enabled schedule(s)", "SUCCESS")
            
            if len(schedules) == 0:
                log("⚠️  No enabled schedules found. Nothing to process.", "WARNING")
                log("💡 Create schedules via the frontend to test scheduler functionality", "INFO")
                return

            for idx, s in enumerate(schedules, 1):
                aq_id = s.aquarium_id
                
                # Get aquarium name for better logging
                aq_result = await db.execute(select(Aquarium).where(Aquarium.id == aq_id))
                aq = aq_result.scalars().first()
                aq_name = aq.name if aq else f"Aquarium-{aq_id}"
                
                log(f"\n📝 [{idx}/{len(schedules)}] Processing Schedule ID: {s.id}", "INFO")
                log(f"   🐠 Aquarium: {aq_name} (ID: {aq_id})", "INFO")
                log(f"   📌 Schedule Name: {s.name or 'Unnamed'}", "INFO")
                log(f"   🔄 Type: {s.type}", "INFO")
                
                if s.type == "interval" and s.interval_hours is not None:
                    log(f"   ⏱️  Interval: Every {s.interval_hours} hour(s)", "INFO")
                    log(f"   🍽️  Feed Volume: {s.feed_volume_grams or 'not set'}g", "INFO")
                    
                    cutoff = now - datetime.timedelta(hours=float(s.interval_hours))
                    log(f"   🕐 Cutoff time: {cutoff.strftime('%Y-%m-%d %H:%M:%S')} UTC", "INFO")
                    log(f"   🔍 Checking if feeding is due (no feed since cutoff)...", "INFO")
                    
                    # check recent feeding logs
                    recent_feed = await db.execute(
                        select(FeedingLog)
                        .where(FeedingLog.aquarium_id == aq_id)
                        .order_by(FeedingLog.ts.desc())
                        .limit(1)
                    )
                    last_feed = recent_feed.scalars().first()
                    
                    if last_feed:
                        log(f"   📊 Last feed: {last_feed.ts.strftime('%Y-%m-%d %H:%M:%S')} UTC", "INFO")
                        if last_feed.ts < cutoff:
                            log(f"   ⚠️  Last feed is BEFORE cutoff - feeding is DUE!", "WARNING")
                        else:
                            time_until_due = last_feed.ts + datetime.timedelta(hours=float(s.interval_hours))
                            log(f"   ✅ Last feed is recent (after cutoff)", "SUCCESS")
                            log(f"   ⏰ Next feed due at: {time_until_due.strftime('%Y-%m-%d %H:%M:%S')} UTC", "INFO")
                            continue
                    else:
                        log(f"   ⚠️  No feeding logs found - FIRST FEEDING DUE!", "WARNING")
                    
                    # Double-check no recent feeding log exists after cutoff
                    recent_feed_check = await db.execute(
                        select(FeedingLog)
                        .where(FeedingLog.aquarium_id == aq_id, FeedingLog.ts > cutoff)
                    )
                    if recent_feed_check.scalars().first():
                        log(f"   ✅ Found recent feed after cutoff on recheck, skipping", "SUCCESS")
                        continue
                    
                    # Check for existing CMD_FEED alerts
                    log(f"   🔍 Checking for existing CMD_FEED alerts...", "INFO")
                    recent_alert = await db.execute(
                        select(Alert)
                        .where(
                            Alert.aquarium_id == aq_id, 
                            Alert.type == 'CMD_FEED', 
                            Alert.ts > cutoff
                        )
                    )
                    existing_alert = recent_alert.scalars().first()
                    
                    if existing_alert:
                        log(f"   ℹ️  CMD_FEED alert already exists (ID: {existing_alert.id}), skipping", "INFO")
                        log(f"      Created at: {existing_alert.ts.strftime('%Y-%m-%d %H:%M:%S')} UTC", "INFO")
                    else:
                        # create an ALERT (CMD_FEED) for the device to pick up
                        msg = f"Scheduled feed: {s.feed_volume_grams or ''}g"
                        log(f"   🚀 Creating CMD_FEED alert: '{msg}'", "WARNING")
                        a = Alert(aquarium_id=aq_id, type="CMD_FEED", message=msg)
                        db.add(a)
                        await db.commit()
                        await db.refresh(a)
                        log(f"   ✅ CMD_FEED alert created successfully (Alert ID: {a.id})", "SUCCESS")
                        log(f"   📤 Device will pick this up and create feeding log", "INFO")

                elif s.type == "daily_times" and s.daily_times:
                    try:
                        times = json.loads(s.daily_times)
                        log(f"   🕐 Daily Times: {', '.join(times)}", "INFO")
                    except Exception as e:
                        log(f"   ❌ Error parsing daily_times JSON: {e}", "ERROR")
                        times = []
                    
                    log(f"   🍽️  Feed Volume: {s.feed_volume_grams or 'not set'}g", "INFO")
                    
                    now_hm = now.strftime("%H:%M")
                    log(f"   🕐 Current time (UTC): {now_hm}", "INFO")
                    
                    # exact match - acceptable for tests; in production use a tolerance window
                    if now_hm in times:
                        log(f"   ⚠️  Current time MATCHES a scheduled time!", "WARNING")
                        
                        today_start = datetime.datetime(now.year, now.month, now.day)
                        log(f"   🔍 Checking if already fed today (since {today_start.strftime('%Y-%m-%d %H:%M:%S')} UTC)...", "INFO")
                        
                        today_feed = await db.execute(
                            select(FeedingLog)
                            .where(FeedingLog.aquarium_id == aq_id, FeedingLog.ts >= today_start)
                        )
                        
                        if today_feed.scalars().first():
                            log(f"   ✅ Already fed today, skipping", "SUCCESS")
                        else:
                            log(f"   ⚠️  No feeding today yet - creating CMD_FEED alert", "WARNING")
                            
                            # avoid creating duplicate CMD_FEED alerts for today
                            recent_alert = await db.execute(
                                select(Alert)
                                .where(
                                    Alert.aquarium_id == aq_id, 
                                    Alert.type == 'CMD_FEED', 
                                    Alert.ts >= today_start
                                )
                            )
                            
                            if recent_alert.scalars().first():
                                log(f"   ℹ️  CMD_FEED alert for today already exists, skipping", "INFO")
                            else:
                                msg = f"Scheduled daily feed: {s.feed_volume_grams or ''}g"
                                log(f"   🚀 Creating CMD_FEED alert: '{msg}'", "WARNING")
                                a = Alert(aquarium_id=aq_id, type="CMD_FEED", message=msg)
                                db.add(a)
                                await db.commit()
                                await db.refresh(a)
                                log(f"   ✅ CMD_FEED alert created successfully (Alert ID: {a.id})", "SUCCESS")
                    else:
                        log(f"   ✅ Current time does not match any scheduled time", "SUCCESS")
                        next_times = [t for t in times if t > now_hm]
                        if next_times:
                            log(f"   ⏰ Next scheduled time today: {next_times[0]}", "INFO")
                        else:
                            log(f"   ⏰ No more scheduled times today. Next: {times[0]} tomorrow", "INFO")
                else:
                    log(f"   ⚠️  Unknown or incomplete schedule type", "WARNING")
            
            log("\n" + "=" * 70, "SCHEDULER")
            log("✅ SCHEDULER CYCLE COMPLETED", "SUCCESS")
            log("=" * 70 + "\n", "SCHEDULER")
            
    except Exception as e:
        log(f"❌ ERROR in scheduler: {e}", "ERROR")
        import traceback
        traceback.print_exc()
    finally:
        # release advisory lock if we acquired it
        try:
            if conn is not None and acquired_lock:
                log("🔓 Releasing advisory lock...", "INFO")
                await conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": ADVISORY_LOCK_ID})
                await conn.close()
                log("✅ Advisory lock released", "SUCCESS")
        except Exception:
            pass


async def run_loop(interval_seconds: Optional[float] = 60.0):
    log("🚀 SCHEDULER STARTING IN LOOP MODE", "SCHEDULER")
    log(f"⏱️  Interval: {interval_seconds} seconds", "INFO")
    log("=" * 70 + "\n", "SCHEDULER")
    
    cycle = 0
    while True:
        try:
            cycle += 1
            log(f"\n🔁 SCHEDULER CYCLE #{cycle}", "SCHEDULER")
            await run_once()
        except Exception as e:
            log(f"❌ ERROR in scheduler loop: {e}", "ERROR")
            import traceback
            traceback.print_exc()
        
        log(f"⏳ Sleeping for {interval_seconds} seconds...\n", "INFO")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Aquarium Feeding Scheduler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run once to test
  python scheduler.py --once
  
  # Run continuously every 60 seconds
  python scheduler.py --loop 60
  
  # Run every 10 seconds for faster testing
  python scheduler.py --loop 10
        """
    )
    parser.add_argument("--once", action="store_true", help="Run one scheduler cycle")
    parser.add_argument("--loop", type=float, default=None, help="Run scheduler loop with interval seconds")
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_once())
    elif args.loop is not None:
        asyncio.run(run_loop(args.loop))
    else:
        print("❌ ERROR: Must specify --once or --loop <seconds>")
        print("\nExamples:")
        print("  python scheduler.py --once")
        print("  python scheduler.py --loop 60")