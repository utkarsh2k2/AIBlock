"""SQLAlchemy 2.0 ORM models for AIBlock.

Tables:
  users           — registered users (created via Stripe checkout or API)
  api_keys        — API keys issued to users; hashed for storage
  detection_jobs  — async detection requests (enqueued, processing, done, failed)
  usage_records   — append-only log of billed API calls (one row per job)
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

import enum


class Tier(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ContentType(str, enum.Enum):
    AUDIO = "audio"
    # Future:
    # VIDEO = "video"
    # TEXT  = "text"
    # IMAGE = "image"


# ── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), nullable=False, default=Tier.FREE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    api_keys: Mapped[list["APIKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} tier={self.tier}>"


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="Default")
    # key_hash: SHA-256 hex of the raw key — never store the raw key
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # key_prefix: first 12 chars of raw key for display (e.g. "abl_live_abc1")
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), nullable=False, default=Tier.FREE)
    requests_this_month: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    month_reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="api_keys")
    jobs: Mapped[list["DetectionJob"]] = relationship(back_populates="api_key", cascade="all, delete-orphan")
    usage_records: Mapped[list["UsageRecord"]] = relationship(back_populates="api_key")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @staticmethod
    def generate() -> tuple[str, "APIKey"]:
        """Generate a new raw key + an unsaved APIKey instance (user_id must be set).

        Returns (raw_key, api_key_instance).
        The raw key is shown to the user once; only the hash is stored.
        Format: abl_live_<40 random hex chars>
        """
        raw = f"abl_live_{secrets.token_hex(20)}"
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        return raw, APIKey(key_hash=key_hash, key_prefix=raw[:12])

    @staticmethod
    def hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def __repr__(self) -> str:
        return f"<APIKey {self.key_prefix}... tier={self.tier} active={self.is_active}>"


class DetectionJob(Base):
    __tablename__ = "detection_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("api_keys.id", ondelete="CASCADE"), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType), nullable=False, default=ContentType.AUDIO)
    use_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), nullable=False, default=JobStatus.PENDING)
    result: Mapped[Optional[dict]] = mapped_column(JSONB)
    error: Mapped[Optional[str]] = mapped_column(Text)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    api_key: Mapped["APIKey"] = relationship(back_populates="jobs")
    usage_record: Mapped[Optional["UsageRecord"]] = relationship(back_populates="job", uselist=False)

    def __repr__(self) -> str:
        return f"<DetectionJob {self.id} status={self.status} platform={self.platform}>"


class UsageRecord(Base):
    """Immutable usage log — one row per billed API call.

    Used for analytics, billing reconciliation, and abuse detection.
    """
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    api_key_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("detection_jobs.id", ondelete="SET NULL"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    use_model: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credits_used: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tier_at_time: Mapped[str] = mapped_column(String(16), nullable=False)

    api_key: Mapped[Optional["APIKey"]] = relationship(back_populates="usage_records")
    job: Mapped[Optional["DetectionJob"]] = relationship(back_populates="usage_record")
