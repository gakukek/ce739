from pydantic import BaseModel
from typing import Optional, List
import datetime

class AquariumCreate(BaseModel):
    user_id: int
    name: str
    size_litres: Optional[float] = None
    device_uid: str
    feeding_volume_grams: Optional[float] = None
    feeding_period_hours: Optional[int] = None

class AquariumOut(BaseModel):
    id: int
    user_id: int
    name: str
    size_litres: Optional[float]
    device_uid: str
    feeding_volume_grams: Optional[float]
    feeding_period_hours: Optional[int]
    active_since: Optional[datetime.datetime]
    created_at: Optional[datetime.datetime]

    class Config:
        orm_mode = True

class SensorDataCreate(BaseModel):
    aquarium_id: int
    ts: Optional[datetime.datetime] = None
    temperature_c: Optional[float] = None
    ph: Optional[float] = None

class SensorDataOut(BaseModel):
    id: int
    aquarium_id: int
    ts: datetime.datetime
    temperature_c: Optional[float]
    ph: Optional[float]

    class Config:
        orm_mode = True

class FeedingLogCreate(BaseModel):
    aquarium_id: int
    ts: Optional[datetime.datetime] = None
    mode: str  # 'AUTO' or 'MANUAL'
    volume_grams: Optional[float] = None
    actor: Optional[str] = "system"

class FeedingLogOut(BaseModel):
    id: int
    aquarium_id: int
    ts: datetime.datetime
    mode: str
    volume_grams: Optional[float]
    actor: Optional[str]

    class Config:
        orm_mode = True

class ScheduleCreate(BaseModel):
    aquarium_id: int
    name: Optional[str] = None
    type: str  # 'interval' or 'daily_times'
    interval_hours: Optional[int] = None
    daily_times: Optional[List[str]] = None  # list of "HH:MM:SS"
    feed_volume_grams: Optional[float] = None
    enabled: Optional[bool] = True
    start_date: Optional[datetime.datetime] = None
    end_date: Optional[datetime.datetime] = None

class ScheduleOut(BaseModel):
    id: int
    aquarium_id: int
    name: Optional[str]
    type: str
    interval_hours: Optional[int]
    daily_times: Optional[List[str]]
    feed_volume_grams: Optional[float]
    enabled: bool
    start_date: Optional[datetime.datetime]
    end_date: Optional[datetime.datetime]

    class Config:
        orm_mode = True

class AlertCreate(BaseModel):
    aquarium_id: int
    ts: Optional[datetime.datetime] = None
    type: Optional[str] = None
    message: Optional[str] = None

class AlertOut(BaseModel):
    id: int
    aquarium_id: int
    ts: datetime.datetime
    type: Optional[str]
    message: Optional[str]
    resolved: bool
    resolved_at: Optional[datetime.datetime]

    class Config:
        orm_mode = True
