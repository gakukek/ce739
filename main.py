import datetime
from fastapi import FastAPI, Depends, HTTPException, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from contextlib import asynccontextmanager
import asyncio

from database import get_db, engine, Base
from models import User, Aquarium, SensorData, FeedingLog, Schedule, Alert
from schemas import (
    UserOut, AquariumCreate, AquariumOut, SensorDataCreate, SensorDataOut,
    FeedingLogCreate, FeedingLogOut, ScheduleCreate, ScheduleOut, AlertCreate, AlertOut
)
import os

# ------------- Clerk Auth -------------
from auth import get_current_user  # returns clerk_user_id
import secrets

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Optionally run the scheduler in-process when RUN_SCHEDULER=1
    scheduler_task = None
    try:
        if os.getenv("RUN_SCHEDULER") == "1":
            try:
                import scheduler
                interval = float(os.getenv("SCHEDULER_INTERVAL", "60"))
                scheduler_task = asyncio.create_task(scheduler.run_loop(interval))
                print("Scheduler started in-process with interval", interval)
            except Exception as e:
                print("Failed to start in-process scheduler:", e)
        yield
    finally:
        if scheduler_task:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass

app = FastAPI(lifespan=lifespan)

# ------------- CORS -------------

# ✅ Add your production frontend URL
_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://aquascape.onrender.com",
    "https://ce739-fe.pages.dev",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],  # ✅ Add this
)

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "cors_origins": _origins,
        "jwks_url": "configured"
    }

@app.options("/{rest_of_path:path}")
async def preflight_handler(request: Request):
    response = Response(status_code=204)
    response.headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "authorization, content-type"
    return response


# ------------- User Sync -------------

@app.post("/sync-user")
async def sync_user(
    clerk_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(...)
):
    from sqlalchemy.exc import IntegrityError
    import uuid
    
    try:
        # Allow decoding token WITHOUT signature validation to extract fields
        token = authorization.split(" ")[1]
        decoded = jwt.decode(token, options={"verify_signature": False})
        
        # Debug: Log the decoded token structure (remove in production)
        print("DEBUG - Decoded token keys:", decoded.keys())
        print("DEBUG - Full decoded token:", decoded)

        # More comprehensive email extraction
        email = None
        
        # Try different possible email fields
        if "email" in decoded:
            email = decoded["email"]
        elif "primary_email" in decoded:
            email = decoded["primary_email"]
        elif "email_address" in decoded:
            email = decoded["email_address"]
        elif "email_addresses" in decoded and decoded["email_addresses"]:
            # Handle array of email objects
            email_arr = decoded["email_addresses"]
            if isinstance(email_arr, list) and len(email_arr) > 0:
                if isinstance(email_arr[0], dict):
                    email = email_arr[0].get("email_address")
                elif isinstance(email_arr[0], str):
                    email = email_arr[0]

        # Build a safe fallback username
        username = None
        
        # Try to get username from various fields
        if "username" in decoded and decoded["username"]:
            username = decoded["username"]
        elif "name" in decoded and decoded["name"]:
            username = decoded["name"]
        elif "given_name" in decoded and decoded["given_name"]:
            username = decoded["given_name"]
        elif "first_name" in decoded and decoded["first_name"]:
            username = decoded["first_name"]
        elif email:
            try:
                username = email.split("@")[0]
            except Exception:
                pass
        
        # Final fallback - use full clerk_id to avoid collisions
        if not username:
            username = f"user_{clerk_id}"

        print(f"DEBUG - Extracted email: {email}, username: {username}")

        # Check if user already exists
        result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
        user = result.scalars().first()

        if not user:
            # Try to create user, handle username collisions
            max_attempts = 5
            for attempt in range(max_attempts):
                try:
                    # Add random suffix if this is a retry
                    current_username = username if attempt == 0 else f"{username}_{uuid.uuid4().hex[:6]}"
                    
                    user = User(
                        clerk_user_id=clerk_id,
                        username=current_username
                    )
                    db.add(user)
                    await db.commit()
                    await db.refresh(user)
                    print(f"DEBUG - Created new user with id: {user.id}, username: {current_username}")
                    break
                except IntegrityError as ie:
                    await db.rollback()
                    if "users_username_key" in str(ie) and attempt < max_attempts - 1:
                        print(f"DEBUG - Username collision on attempt {attempt + 1}, retrying...")
                        continue
                    else:
                        raise
        else:
            print(f"DEBUG - User already exists with id: {user.id}")

        return {
            "status": "ok", 
            "clerk_id": clerk_id, 
            "username": user.username,
            "user_id": user.id,
            "email": email
        }
    
    except Exception as e:
        await db.rollback()
        print(f"ERROR in sync_user: {str(e)}")
        print(f"ERROR type: {type(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Sync user failed: {str(e)}")


@app.get("/me", response_model=UserOut)
async def get_me(
    clerk_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = result.scalars().first()

    if not user:
        raise HTTPException(404, "User not synced")

    return user

# ------------- Helper -------------
async def get_local_user(db, clerk_id):
    print(f"🔍 Looking up user with clerk_id: {clerk_id}")
    res = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = res.scalars().first()
    
    if not user:
        print(f"❌ User not found for clerk_id: {clerk_id}")
        # Check if user exists with different ID
        all_users = await db.execute(select(User))
        print(f"📋 All users in DB: {[u.clerk_user_id for u in all_users.scalars().all()]}")
        raise HTTPException(403, "User not synced; call /sync-user first")
    
    print(f"✅ Found user: id={user.id}, username={user.username}")
    return user

async def assert_owner(db: AsyncSession, aquarium_id: int, clerk_id: str):
    # Allow simulator to bypass ownership
    if clerk_id == "system_simulator":
        aq = await db.get(Aquarium, aquarium_id)
        if not aq:
            raise HTTPException(404, "Aquarium not found")
        return aq

    # Normal user flow
    user = await get_local_user(db, clerk_id)
    aq = await db.get(Aquarium, aquarium_id)
    if not aq:
        raise HTTPException(404, "Aquarium not found")

    if aq.user_id != user.id:
        raise HTTPException(403, "Forbidden")

    return aq


# ------------- Aquariums -------------

@app.post("/aquariums", response_model=AquariumOut)
async def create_aquarium(
    aquarium: AquariumCreate,
    clerk_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from sqlalchemy.exc import IntegrityError
    
    user = await get_local_user(db, clerk_id)
    
    # Convert the Pydantic model to dict
    aquarium_data = aquarium.dict(exclude_none=True)
    
    # Handle device_uid: convert empty string to None
    if "device_uid" in aquarium_data:
        if aquarium_data["device_uid"] == "" or aquarium_data["device_uid"] is None:
            aquarium_data["device_uid"] = None
    
    try:
        new_aq = Aquarium(**aquarium_data, user_id=user.id)
        db.add(new_aq)
        await db.commit()
        await db.refresh(new_aq)
        return new_aq
    except IntegrityError as e:
        await db.rollback()
        if "device_uid" in str(e):
            raise HTTPException(400, "Device UID already exists. Please use a unique device UID or leave it empty.")
        raise HTTPException(400, f"Database error: {str(e)}")


@app.get("/aquariums", response_model=list[AquariumOut])
async def list_aquariums(
    clerk_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if clerk_id == "system_simulator":
        result = await db.execute(select(Aquarium))
        return result.scalars().all()

    user = await get_local_user(db, clerk_id)
    result = await db.execute(
        select(Aquarium).where(Aquarium.user_id == user.id)
    )
    return result.scalars().all()


@app.put("/aquariums/{aq_id}", response_model=AquariumOut)
async def update_aquarium(aq_id: int, payload: AquariumCreate, clerk_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    aq = await assert_owner(db, aq_id, clerk_id)
    # prevent changing ownership from client payload
    updates = payload.dict(exclude_none=True)
    updates.pop("user_id", None)
    for k, v in updates.items():
        setattr(aq, k, v)
    await db.commit()
    await db.refresh(aq)
    return aq

@app.delete("/aquariums/{aq_id}")
async def delete_aquarium(aq_id: int, clerk_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    aq = await assert_owner(db, aq_id, clerk_id)
    await db.delete(aq)
    await db.commit()
    return {"ok": True}


# ------------------- SENSOR DATA -------------------
@app.post("/sensor_data")
async def create_sensor_data(
    item: SensorDataCreate,
    clerk_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await assert_owner(db, item.aquarium_id, clerk_id)
    obj = SensorData(**item.dict())
    db.add(obj)
    await db.commit()
    return obj


@app.get("/sensor_data", response_model=list[SensorDataOut])
async def list_sensor_data(
    aquarium_id: int,
    db: AsyncSession = Depends(get_db),
    clerk_id: str = Depends(get_current_user)
):
    await assert_owner(db, aquarium_id, clerk_id)
    result = await db.execute(select(SensorData).where(SensorData.aquarium_id == aquarium_id))
    return result.scalars().all()

# ------------------- FEEDING LOGS -------------------
@app.post("/feeding_logs", response_model=FeedingLogOut)
async def create_feeding_log(
    item: FeedingLogCreate,
    db: AsyncSession = Depends(get_db),
    clerk_id: str = Depends(get_current_user)
):
    await assert_owner(db, item.aquarium_id, clerk_id)
    obj = FeedingLog(**item.dict())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/feeding_logs", response_model=list[FeedingLogOut])
async def list_feeding_logs(
    aquarium_id: int,
    db: AsyncSession = Depends(get_db),
    clerk_id: str = Depends(get_current_user)
):
    await assert_owner(db, aquarium_id, clerk_id)
    result = await db.execute(select(FeedingLog).where(FeedingLog.aquarium_id == aquarium_id))
    return result.scalars().all()

# ------------------- SCHEDULES -------------------
@app.post("/schedules", response_model=ScheduleOut)
async def create_schedule(
    item: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    clerk_id: str = Depends(get_current_user)
):
    await assert_owner(db, item.aquarium_id, clerk_id)
    obj = Schedule(**item.dict())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(
    aquarium_id: int,
    db: AsyncSession = Depends(get_db),
    clerk_id: str = Depends(get_current_user)
):
    await assert_owner(db, aquarium_id, clerk_id)
    result = await db.execute(select(Schedule).where(Schedule.aquarium_id == aquarium_id))
    return result.scalars().all()

# ------------------- ALERTS -------------------
@app.post("/alerts", response_model=AlertOut)
async def create_alert(
    item: AlertCreate,
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(None),
    request: Request = None,
):
    # Devices may post alerts (danger notifications).
    # Load aquarium
    res = await db.execute(select(Aquarium).where(Aquarium.id == item.aquarium_id))
    aq = res.scalars().first()
    if not aq:
        raise HTTPException(404, "Aquarium not found")

    # Accept Authorization matching aquarium.device_uid or aquarium id string
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        if (aq.device_uid and token == aq.device_uid) or token == str(aq.id):
            obj = Alert(**item.dict())
            db.add(obj)
            await db.commit()
            await db.refresh(obj)
            return obj

    # If no Authorization header present, accept alerts in permissive mode
    if not authorization:
        obj = Alert(**item.dict())
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    # Fallback to clerk user auth. Respect test overrides if present on the app.
    override = None
    if request is not None and hasattr(request, "app"):
        override = request.app.dependency_overrides.get(get_current_user)

    if override:
        try:
            clerk_id = override()
        except TypeError:
            clerk_id = override(authorization)
        if asyncio.iscoroutine(clerk_id):
            clerk_id = await clerk_id
    else:
        clerk_id = await get_current_user(authorization)
    await assert_owner(db, item.aquarium_id, clerk_id)
    obj = Alert(**item.dict())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    aquarium_id: int,
    type: str | None = None,  # Add optional type parameter
    db: AsyncSession = Depends(get_db),
    clerk_id: str = Depends(get_current_user)
):
    await assert_owner(db, aquarium_id, clerk_id)
    
    # Build query with optional type filter
    query = select(Alert).where(Alert.aquarium_id == aquarium_id)
    if type:
        query = query.where(Alert.type == type)
    
    result = await db.execute(query)
    return result.scalars().all()

@app.patch("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    clerk_id: str = Depends(get_current_user)
):
    # Ensure the alert exists
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalars().first()
    if not alert:
        raise HTTPException(404, "Alert not found")

    # Verify caller owns the aquarium associated with this alert
    await assert_owner(db, alert.aquarium_id, clerk_id)

    # Mark as resolved
    alert.resolved = True
    alert.resolved_at = datetime.utcnow()
    await db.commit()
    await db.refresh(alert)
    return alert

@app.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    clerk_id: str = Depends(get_current_user)
):
    # Ensure the alert exists
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalars().first()
    if not alert:
        raise HTTPException(404, "Alert not found")

    # Verify caller owns the aquarium associated with this alert
    await assert_owner(db, alert.aquarium_id, clerk_id)

    await db.delete(alert)
    await db.commit()
    return {"ok": True}
