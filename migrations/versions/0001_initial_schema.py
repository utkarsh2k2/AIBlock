"""Initial schema: users, api_keys, detection_jobs, usage_records.

Revision ID: 0001
Revises:
Create Date: 2026-03-08
"""

from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types ──────────────────────────────────────────────────────────
    tier_enum = postgresql.ENUM("free", "pro", "enterprise", name="tier", create_type=False)
    tier_enum.create(op.get_bind(), checkfirst=True)

    job_status_enum = postgresql.ENUM("pending", "processing", "done", "failed", name="jobstatus", create_type=False)
    job_status_enum.create(op.get_bind(), checkfirst=True)

    content_type_enum = postgresql.ENUM("audio", name="contenttype", create_type=False)
    content_type_enum.create(op.get_bind(), checkfirst=True)

    # ── users ───────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("stripe_customer_id", sa.String(64)),
        sa.Column("stripe_subscription_id", sa.String(64)),
        sa.Column("tier", sa.Enum("free", "pro", "enterprise", name="tier"), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("stripe_customer_id", name="uq_users_stripe_customer_id"),
        sa.UniqueConstraint("stripe_subscription_id", name="uq_users_stripe_subscription_id"),
    )

    # ── api_keys ────────────────────────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False, server_default="Default"),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_prefix", sa.String(16), nullable=False),
        sa.Column("tier", sa.Enum("free", "pro", "enterprise", name="tier"), nullable=False, server_default="free"),
        sa.Column("requests_this_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("month_reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_api_keys_user_id"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    # ── detection_jobs ──────────────────────────────────────────────────────
    op.create_table(
        "detection_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("content_type", sa.Enum("audio", name="contenttype"), nullable=False, server_default="audio"),
        sa.Column("use_model", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.Enum("pending", "processing", "done", "failed", name="jobstatus"), nullable=False, server_default="pending"),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("celery_task_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer()),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="CASCADE", name="fk_detection_jobs_api_key_id"),
    )
    op.create_index("ix_detection_jobs_api_key_id", "detection_jobs", ["api_key_id"])
    op.create_index("ix_detection_jobs_created_at", "detection_jobs", ["created_at"])
    op.create_index("ix_detection_jobs_status", "detection_jobs", ["status"])

    # ── usage_records ───────────────────────────────────────────────────────
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True)),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("use_model", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("credits_used", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tier_at_time", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(["api_key_id"], ["api_keys.id"], ondelete="SET NULL", name="fk_usage_api_key_id"),
        sa.ForeignKeyConstraint(["job_id"], ["detection_jobs.id"], ondelete="SET NULL", name="fk_usage_job_id"),
    )
    op.create_index("ix_usage_records_timestamp", "usage_records", ["timestamp"])
    op.create_index("ix_usage_records_api_key_id", "usage_records", ["api_key_id"])


def downgrade() -> None:
    op.drop_table("usage_records")
    op.drop_table("detection_jobs")
    op.drop_table("api_keys")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS contenttype")
    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.execute("DROP TYPE IF EXISTS tier")
