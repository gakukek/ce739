from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from contextlib import asynccontextmanager

from database import get_db, engine, Base
from models import User, Aquarium, SensorData, FeedingLog, Schedule, Alert
from schemas import (
    UserOut, AquariumCreate, AquariumOut, SensorDataCreate, SensorDataOut,
    FeedingLogCreate, FeedingLogOut, ScheduleCreate, ScheduleOut, AlertCreate, AlertOut
)

# ------------- Clerk Auth -------------
from auth import get_current_user  # returns clerk_user_id

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)

# ------------- CORS -------------
import os
_origins = os.getenv("CORS_ORIGINS","http://localhost:5173,http://127.0.0.1:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------- User Sync -------------
@app.post("/sync-user")
async def sync_user(
    clerk_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = result.scalars().first()

    if not user:
        user = User(clerk_user_id=clerk_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return {"status": "ok", "clerk_id": clerk_id}

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
    res = await db.execute(select(User).where(User.clerk_user_id == clerk_id))
    user = res.scalars().first()
    if not user:
        raise HTTPException(403, "User not synced; call /sync-user first")
    return user

async def assert_owner(db, aq_id, clerk_id):
    user = await get_local_user(db, clerk_id)

    res = await db.execute(select(Aquarium).where(Aquarium.id == aq_id))
    aq = res.scalars().first()

    if not aq:
        raise HTTPException(404, "Aquarium not found")

    if aq.user_id != user.id:
        raise HTTPException(403, "Not allowed")

    return aq

# ------------- Aquariums -------------
@app.post("/aquariums", response_model=AquariumOut)
async def create_aquarium(
    aquarium: AquariumCreate,
    clerk_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user = await get_local_user(db, clerk_id)

    new_aq = Aquarium(**aquarium.dict(exclude_none=True), user_id=user.id)
    db.add(new_aq)
    await db.commit()
    await db.refresh(new_aq)
    return new_aq

@app.get("/aquariums", response_model=list[AquariumOut])
async def list_aquariums(
    clerk_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user = await get_local_user(db, clerk_id)
    result = await db.execute(select(Aquarium).where(Aquarium.user_id == user.id))
    return result.scalars().all()

@app.get("/aquariums/{aq_id}", response_model=AquariumOut)
async def get_aquarium(aq_id: int, clerk_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await assert_owner(db, aq_id, clerk_id)

@app.put("/aquariums/{aq_id}", response_model=AquariumOut)
async def update_aquarium(aq_id: int, payload: AquariumCreate, clerk_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    aq = await assert_owner(db, aq_id, clerk_id)
    for k, v in payload.dict(exclude_none=True).items():
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
@app.post("/sensor_data", response_model=SensorDataOut)
async def create_sensor_data(
    item: SensorDataCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_owner(db, item.aquarium_id, user_id)
    obj = SensorData(**item.dict())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/sensor_data", response_model=list[SensorDataOut])
async def list_sensor_data(
    aquarium_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_owner(db, aquarium_id, user_id)
    result = await db.execute(select(SensorData).where(SensorData.aquarium_id == aquarium_id))
    return result.scalars().all()

# ------------------- FEEDING LOGS -------------------
@app.post("/feeding_logs", response_model=FeedingLogOut)
async def create_feeding_log(
    item: FeedingLogCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_owner(db, item.aquarium_id, user_id)
    obj = FeedingLog(**item.dict())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/feeding_logs", response_model=list[FeedingLogOut])
async def list_feeding_logs(
    aquarium_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_owner(db, aquarium_id, user_id)
    result = await db.execute(select(FeedingLog).where(FeedingLog.aquarium_id == aquarium_id))
    return result.scalars().all()

# ------------------- SCHEDULES -------------------
@app.post("/schedules", response_model=ScheduleOut)
async def create_schedule(
    item: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_owner(db, item.aquarium_id, user_id)
    obj = Schedule(**item.dict())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(
    aquarium_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_owner(db, aquarium_id, user_id)
    result = await db.execute(select(Schedule).where(Schedule.aquarium_id == aquarium_id))
    return result.scalars().all()

# ------------------- ALERTS -------------------
@app.post("/alerts", response_model=AlertOut)
async def create_alert(
    item: AlertCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_owner(db, item.aquarium_id, user_id)
    obj = Alert(**item.dict())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    aquarium_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_owner(db, aquarium_id, user_id)
    result = await db.execute(select(Alert).where(Alert.aquarium_id == aquarium_id))
    return result.scalars().all()
