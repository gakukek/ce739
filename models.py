from datetime import datetime
from sqlalchemy import (
    Column,
    BigInteger,
    DateTime,
    String,
    Numeric,
    ForeignKey,
    TIMESTAMP,
    func,
    Text,
    Boolean,
    Integer,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)
    clerk_user_id = Column(String, unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)

    aquariums = relationship("Aquarium", back_populates="owner")


class Aquarium(Base):
    __tablename__ = "aquariums"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    size_litres = Column(Numeric(6, 2), nullable=True)
    
    device_uid = Column(String, nullable=True, unique=False) 
    
    feeding_volume_grams = Column(Numeric(7, 2), nullable=True)
    feeding_period_hours = Column(Integer, nullable=True)
    active_since = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="aquariums")
    sensor_data = relationship("SensorData", back_populates="aquarium", cascade="all, delete-orphan")
    feeding_logs = relationship("FeedingLog", back_populates="aquarium", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="aquarium", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="aquarium", cascade="all, delete-orphan")


class SensorData(Base):
    __tablename__ = "sensor_data"
    id = Column(BigInteger, primary_key=True, index=True)
    aquarium_id = Column(BigInteger, ForeignKey("aquariums.id", ondelete="CASCADE"))
    ts = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    temperature_c = Column(Numeric(5,2))
    ph = Column(Numeric(4,2))

    aquarium = relationship("Aquarium", back_populates="sensor_data")

class FeedingLog(Base):
    __tablename__ = "feeding_logs"
    id = Column(BigInteger, primary_key=True, index=True)
    aquarium_id = Column(BigInteger, ForeignKey("aquariums.id", ondelete="CASCADE"))
    ts = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    mode = Column(String(10), nullable=False)
    volume_grams = Column(Numeric(7,2))
    actor = Column(String(64), default="system")

    __table_args__ = (
        CheckConstraint("mode IN ('AUTO','MANUAL')", name="ck_feeding_logs_mode"),
    )

    aquarium = relationship("Aquarium", back_populates="feeding_logs")

class Schedule(Base):
    __tablename__ = "schedules"
    id = Column(BigInteger, primary_key=True, index=True)
    aquarium_id = Column(BigInteger, ForeignKey("aquariums.id", ondelete="CASCADE"))
    name = Column(String(100))
    type = Column(String(20), nullable=False)
    interval_hours = Column(Integer)
    # store daily times as text (e.g. JSON array or CSV)
    daily_times = Column(Text)
    feed_volume_grams = Column(Numeric(7,2))
    enabled = Column(Boolean, default=True)
    start_date = Column(TIMESTAMP(timezone=True))
    end_date = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        CheckConstraint("type IN ('interval','daily_times')", name="ck_schedules_type"),
    )

    aquarium = relationship("Aquarium", back_populates="schedules")

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(BigInteger, primary_key=True, index=True)
    aquarium_id = Column(BigInteger, ForeignKey("aquariums.id", ondelete="CASCADE"))
    ts = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    type = Column(String(50))
    message = Column(Text)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(TIMESTAMP(timezone=True))

    aquarium = relationship("Aquarium", back_populates="alerts")

