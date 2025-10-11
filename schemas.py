from pydantic import BaseModel
from typing import Optional

class AquariumCreate(BaseModel):
    user_id: int
    name: str
    size_litres: Optional[float] = None

class AquariumOut(BaseModel):
    id: int
    user_id: int
    name: str
    size_litres: Optional[float]

    class Config:
        orm_mode = True
