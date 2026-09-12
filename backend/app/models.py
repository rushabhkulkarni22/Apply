import time
import uuid
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def uid():
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    subject: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255))
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    prior_free_usage: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class LoginSession(Base):
    __tablename__ = 'sessions'
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float)


class Profile(Base):
    __tablename__ = 'profiles'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Resume(Base):
    __tablename__ = 'resumes'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(Text, default='')
    content: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    extracted: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Job(Base):
    __tablename__ = 'jobs'
    __table_args__ = (UniqueConstraint('user_id', 'source', 'external_id'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    source: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Run(Base):
    __tablename__ = 'runs'
    __table_args__ = (UniqueConstraint('user_id', 'idempotency_key'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(40), default='QUEUED')
    mode: Mapped[str] = mapped_column(String(20))
    limit: Mapped[int] = mapped_column(Integer)
    profile_version: Mapped[int] = mapped_column(Integer)
    profile: Mapped[dict] = mapped_column(JSON)
    resume_id: Mapped[str] = mapped_column(String(32))
    daily: Mapped[bool] = mapped_column(Boolean, default=False)
    next_at: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    message: Mapped[str] = mapped_column(Text, default='Waiting for worker')


class Attempt(Base):
    __tablename__ = 'attempts'
    __table_args__ = (UniqueConstraint('user_id', 'job_id'),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('runs.id'), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey('jobs.id'))
    status: Mapped[str] = mapped_column(String(40), default='QUEUED')
    reason: Mapped[str] = mapped_column(Text, default='')
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    receipt: Mapped[str] = mapped_column(String(500), default='')
    updated_at: Mapped[float] = mapped_column(Float, default=time.time)


class Entitlement(Base):
    __tablename__ = 'entitlements'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    payment_id: Mapped[str] = mapped_column(String(100), unique=True)
    starts_at: Mapped[float] = mapped_column(Float)
    expires_at: Mapped[float] = mapped_column(Float)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Credit(Base):
    __tablename__ = 'credits'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey('attempts.id'), unique=True)
    bucket: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default='RESERVED')


class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    order_id: Mapped[str] = mapped_column(String(100), unique=True)
    payment_id: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='CREATED')
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class WebhookEvent(Base):
    __tablename__ = 'webhook_events'
    id: Mapped[str] = mapped_column(String(150), primary_key=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
