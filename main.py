from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from database import get_db, engine, Base
from models import Aquarium
from schemas import AquariumCreate, AquariumOut

app = FastAPI()

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.post("/aquariums", response_model=AquariumOut)
async def create_aquarium(aquarium: AquariumCreate, db: AsyncSession = Depends(get_db)):
    new_aq = Aquarium(**aquarium.dict())
    db.add(new_aq)
    await db.commit()
    await db.refresh(new_aq)
    return new_aq

@app.get("/aquariums", response_model=list[AquariumOut])
async def get_aquariums(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Aquarium))
    aquariums = result.scalars().all()
    return aquariums
