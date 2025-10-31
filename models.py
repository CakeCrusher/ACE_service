"""SQLAlchemy database models."""
from datetime import datetime
from typing import Optional
import uuid
import json

from sqlalchemy import Column, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class PlaybookModel(Base):
    """SQLAlchemy model for playbooks."""
    __tablename__ = "playbooks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    modified_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    name = Column(String, nullable=True)
    description = Column(Text, nullable=True)


class BulletModel(Base):
    """SQLAlchemy model for bullets."""
    __tablename__ = "bullets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    playbook_id = Column(String, ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    metadata = Column(JSON, nullable=False, default=lambda: json.dumps({"helpful_count": 0, "harmful_count": 0, "neutral_count": 0}))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    modified_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class LearnJobModel(Base):
    """SQLAlchemy model for learn jobs."""
    __tablename__ = "learn_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    playbook_id = Column(String, ForeignKey("playbooks.id", ondelete="CASCADE"), nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending, running, completed, failed
    error = Column(Text, nullable=True)
    reflection = Column(JSON, nullable=True)
    curation = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    modified_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

