from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dialogs: Mapped[list["Dialog"]] = relationship(back_populates="user")

class Dialog(Base):
    __tablename__ = "dialogs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    contact_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user: Mapped[User] = relationship(back_populates="dialogs")
    messages: Mapped[list["Message"]] = relationship(back_populates="dialog", cascade="all, delete-orphan")
    filters: Mapped[list["FilterSnapshot"]] = relationship(back_populates="dialog", cascade="all, delete-orphan")
    api_requests: Mapped[list["ApiRequest"]] = relationship(back_populates="dialog", cascade="all, delete-orphan")
    views: Mapped[list["View"]] = relationship(back_populates="dialog", cascade="all, delete-orphan")
    viewing_requests: Mapped[list["ViewingRequest"]] = relationship(back_populates="dialog", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id"), nullable=False)
    sender: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dialog: Mapped[Dialog] = relationship(back_populates="messages")

class FilterSnapshot(Base):
    __tablename__ = "filters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id"), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dialog: Mapped[Dialog] = relationship(back_populates="filters")

class ApiRequest(Base):
    __tablename__ = "api_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id"), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON)
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dialog: Mapped[Dialog] = relationship(back_populates="api_requests")

class View(Base):
    __tablename__ = "views"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id"), nullable=False)
    listing_id: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    display_index: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dialog: Mapped[Dialog] = relationship(back_populates="views")

class ViewingRequest(Base):
    __tablename__ = "viewing_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dialog_id: Mapped[int] = mapped_column(ForeignKey("dialogs.id"), nullable=False)
    listing_id: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    dialog: Mapped[Dialog] = relationship(back_populates="viewing_requests")