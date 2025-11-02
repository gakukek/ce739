from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError

from database import get_db, engine, Base
from models import User, Aquarium, SensorData, FeedingLog, Schedule, Alert
from schemas import (
    UserOut,
    AquariumCreate, AquariumOut,
    SensorDataCreate, SensorDataOut,
    FeedingLogCreate, FeedingLogOut,
    ScheduleCreate, ScheduleOut,
    AlertCreate, AlertOut,
)

from contextlib import asynccontextmanager
from auth import get_current_user

# ------------------- DB Startup -------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)

# ------------------- CORS -------------------
import os
_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------- USER (Clerk Sync) -------------------
@app.post("/sync-user")
async def sync_user(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    existing = await db.execute(select(User).where(User.clerk_id == user_id))
    user = existing.scalars().first()

    if not user:
        user = User(clerk_id=user_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return {"status": "ok", "clerk_id": user_id}

@app.get("/me", response_model=UserOut)
async def get_me(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.clerk_id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found in DB; call /sync-user first")
    return user

# ------------------- HELPER: Ownership Enforcement -------------------
async def assert_aquarium_owner(db: AsyncSession, aq_id: int, user_id: str):
    result = await db.execute(select(Aquarium).where(Aquarium.id == aq_id))
    aq = result.scalars().first()
    if not aq:
        raise HTTPException(status_code=404, detail="Aquarium not found")
    if aq.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not allowed")
    return aq

# ------------------- AQUARIUMS -------------------
@app.post("/aquariums", response_model=AquariumOut)
async def create_aquarium(
    aquarium: AquariumCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    new_aq = Aquarium(**aquarium.dict(exclude_none=True), user_id=user_id)
    db.add(new_aq)
    await db.commit()
    await db.refresh(new_aq)
    return new_aq

@app.get("/aquariums", response_model=list[AquariumOut])
async def get_aquariums(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    result = await db.execute(select(Aquarium).where(Aquarium.user_id == user_id))
    return result.scalars().all()

@app.get("/aquariums/{aq_id}", response_model=AquariumOut)
async def get_aquarium(
    aq_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    return await assert_aquarium_owner(db, aq_id, user_id)

@app.put("/aquariums/{aq_id}", response_model=AquariumOut)
async def update_aquarium(
    aq_id: int,
    payload: AquariumCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    aq = await assert_aquarium_owner(db, aq_id, user_id)
    for k, v in payload.dict(exclude_none=True).items():
        setattr(aq, k, v)
    await db.commit()
    await db.refresh(aq)
    return aq

@app.delete("/aquariums/{aq_id}")
async def delete_aquarium(
    aq_id: int,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    aq = await assert_aquarium_owner(db, aq_id, user_id)
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
    await assert_aquarium_owner(db, item.aquarium_id, user_id)
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
    await assert_aquarium_owner(db, aquarium_id, user_id)
    result = await db.execute(select(SensorData).where(SensorData.aquarium_id == aquarium_id))
    return result.scalars().all()

# ------------------- FEEDING LOGS -------------------
@app.post("/feeding_logs", response_model=FeedingLogOut)
async def create_feeding_log(
    item: FeedingLogCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_aquarium_owner(db, item.aquarium_id, user_id)
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
    await assert_aquarium_owner(db, aquarium_id, user_id)
    result = await db.execute(select(FeedingLog).where(FeedingLog.aquarium_id == aquarium_id))
    return result.scalars().all()

# ------------------- SCHEDULES -------------------
@app.post("/schedules", response_model=ScheduleOut)
async def create_schedule(
    item: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_aquarium_owner(db, item.aquarium_id, user_id)
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
    await assert_aquarium_owner(db, aquarium_id, user_id)
    result = await db.execute(select(Schedule).where(Schedule.aquarium_id == aquarium_id))
    return result.scalars().all()

# ------------------- ALERTS -------------------
@app.post("/alerts", response_model=AlertOut)
async def create_alert(
    item: AlertCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user)
):
    await assert_aquarium_owner(db, item.aquarium_id, user_id)
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
    await assert_aquarium_owner(db, aquarium_id, user_id)
    result = await db.execute(select(Alert).where(Alert.aquarium_id == aquarium_id))
    return result.scalars().all()
