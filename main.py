from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError

from database import get_db, engine, Base
from models import User, Aquarium, SensorData, FeedingLog, Schedule, Alert
from schemas import (
    UserCreate,
    UserOut,
    UserUpdate,
    AquariumCreate,
    AquariumOut,
    SensorDataCreate,
    SensorDataOut,
    FeedingLogCreate,
    FeedingLogOut,
    ScheduleCreate,
    ScheduleOut,
    AlertCreate,
    AlertOut,
)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)

# use Argon2 to avoid bcrypt 72-byte limit
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# USER endpoints
@app.post("/users", response_model=UserOut)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    hashed = pwd_context.hash(payload.password)
    user = User(username=payload.username, email=payload.email, password_hash=hashed)
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="username or email already exists")
    return user

@app.get("/users", response_model=list[UserOut])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()

@app.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.put("/users/{user_id}", response_model=UserOut)
async def update_user(user_id: int, payload: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    data = payload.dict(exclude_none=True)
    if "password" in data:
        user.password_hash = pwd_context.hash(data.pop("password"))
    for k, v in data.items():
        setattr(user, k, v)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="username or email already exists")
    return user

@app.delete("/users/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return {"ok": True}

# AQUARIUMS
@app.post("/aquariums", response_model=AquariumOut)
async def create_aquarium(aquarium: AquariumCreate, db: AsyncSession = Depends(get_db)):
    new_aq = Aquarium(**aquarium.dict(exclude_none=True))
    db.add(new_aq)
    await db.commit()
    await db.refresh(new_aq)
    return new_aq

@app.get("/aquariums", response_model=list[AquariumOut])
async def get_aquariums(db: AsyncSession = Depends(get_db)):
    """
    Retrieve all aquariums from the database.

    Returns a list of AquariumOut objects representing all stored aquariums.
    """
    result = await db.execute(select(Aquarium))
    aquariums = result.scalars().all()
    return aquariums


@app.get("/aquariums/{aq_id}", response_model=AquariumOut)
async def get_aquarium(aq_id: int, db: AsyncSession = Depends(get_db)):
    aq = await db.get(Aquarium, aq_id)
    if not aq:
        raise HTTPException(status_code=404, detail="Aquarium not found")
    return aq

@app.put("/aquariums/{aq_id}", response_model=AquariumOut)
async def update_aquarium(aq_id: int, payload: AquariumCreate, db: AsyncSession = Depends(get_db)):
    aq = await db.get(Aquarium, aq_id)
    if not aq:
        raise HTTPException(status_code=404, detail="Aquarium not found")
    for k, v in payload.dict(exclude_none=True).items():
        setattr(aq, k, v)
    await db.commit()
    await db.refresh(aq)
    return aq

@app.delete("/aquariums/{aq_id}")
async def delete_aquarium(aq_id: int, db: AsyncSession = Depends(get_db)):
    aq = await db.get(Aquarium, aq_id)
    if not aq:
        raise HTTPException(status_code=404, detail="Aquarium not found")
    await db.delete(aq)
    await db.commit()
    return {"ok": True}

# SENSOR DATA
@app.post("/sensor_data", response_model=SensorDataOut)
async def create_sensor_data(item: SensorDataCreate, db: AsyncSession = Depends(get_db)):
    obj = SensorData(**item.dict(exclude_none=True))
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/sensor_data", response_model=list[SensorDataOut])
async def list_sensor_data(aquarium_id: int | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(SensorData)
    if aquarium_id:
        stmt = stmt.where(SensorData.aquarium_id == aquarium_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@app.get("/sensor_data/{item_id}", response_model=SensorDataOut)
async def get_sensor_data(item_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(SensorData, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorData not found")
    return obj

@app.delete("/sensor_data/{item_id}")
async def delete_sensor_data(item_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(SensorData, item_id)
    if not obj:
        raise HTTPException(status_code=404, detail="SensorData not found")
    await db.delete(obj)
    await db.commit()
    return {"ok": True}

# FEEDING LOGS
@app.post("/feeding_logs", response_model=FeedingLogOut)
async def create_feeding_log(item: FeedingLogCreate, db: AsyncSession = Depends(get_db)):
    obj = FeedingLog(**item.dict(exclude_none=True))
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/feeding_logs", response_model=list[FeedingLogOut])
async def list_feeding_logs(aquarium_id: int | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(FeedingLog)
    if aquarium_id:
        stmt = stmt.where(FeedingLog.aquarium_id == aquarium_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@app.get("/feeding_logs/{log_id}", response_model=FeedingLogOut)
async def get_feeding_log(log_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(FeedingLog, log_id)
    if not obj:
        raise HTTPException(status_code=404, detail="FeedingLog not found")
    return obj

@app.delete("/feeding_logs/{log_id}")
async def delete_feeding_log(log_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(FeedingLog, log_id)
    if not obj:
        raise HTTPException(status_code=404, detail="FeedingLog not found")
    await db.delete(obj)
    await db.commit()
    return {"ok": True}

# SCHEDULES
@app.post("/schedules", response_model=ScheduleOut)
async def create_schedule(item: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    obj = Schedule(**item.dict(exclude_none=True))
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/schedules", response_model=list[ScheduleOut])
async def list_schedules(aquarium_id: int | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Schedule)
    if aquarium_id:
        stmt = stmt.where(Schedule.aquarium_id == aquarium_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@app.get("/schedules/{sched_id}", response_model=ScheduleOut)
async def get_schedule(sched_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Schedule, sched_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return obj

@app.put("/schedules/{sched_id}", response_model=ScheduleOut)
async def update_schedule(sched_id: int, payload: ScheduleCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Schedule, sched_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Schedule not found")
    for k, v in payload.dict(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.delete("/schedules/{sched_id}")
async def delete_schedule(sched_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Schedule, sched_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(obj)
    await db.commit()
    return {"ok": True}

# ALERTS
@app.post("/alerts", response_model=AlertOut)
async def create_alert(item: AlertCreate, db: AsyncSession = Depends(get_db)):
    obj = Alert(**item.dict(exclude_none=True))
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.get("/alerts", response_model=list[AlertOut])
async def list_alerts(aquarium_id: int | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Alert)
    if aquarium_id:
        stmt = stmt.where(Alert.aquarium_id == aquarium_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@app.get("/alerts/{alert_id}", response_model=AlertOut)
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Alert, alert_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Alert not found")
    return obj

@app.put("/alerts/{alert_id}", response_model=AlertOut)
async def update_alert(alert_id: int, payload: AlertCreate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Alert, alert_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Alert not found")
    for k, v in payload.dict(exclude_none=True).items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj

@app.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Alert, alert_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(obj)
    await db.commit()
    return {"ok": True}
