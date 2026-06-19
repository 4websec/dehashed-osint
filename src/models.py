from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.crypto import EncryptedString
from src.core.db import Base

SEED_USER_ID: int = 1


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(120), default="local")


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=SEED_USER_ID)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="open")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    targets: Mapped[list["Target"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id"))
    label: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(40), default="person")
    investigation: Mapped["Investigation"] = relationship(back_populates="targets")
    selectors: Mapped[list["Selector"]] = relationship(
        back_populates="target", cascade="all, delete-orphan"
    )


class Selector(Base):
    __tablename__ = "selectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id"))
    field_type: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(400))
    target: Mapped["Target"] = relationship(back_populates="selectors")


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id"))
    query: Mapped[str] = mapped_column(String(600))
    params: Mapped[str] = mapped_column(String(200), default="{}")
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    cost: Mapped[int] = mapped_column(Integer, default=0)
    balance_after: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    took: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResultRecord(Base):
    __tablename__ = "result_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id"))
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id"))
    raw_json: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    username: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Sensitive fields encrypted at rest via AES-GCM.
    password: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    name: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(60), nullable=True)
    phone: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    address: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    database_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), default=SEED_USER_ID)
    action: Mapped[str] = mapped_column(String(60))
    query: Mapped[str | None] = mapped_column(String(600), nullable=True)
    cost: Mapped[int] = mapped_column(Integer, default=0)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
