"""
User model for authentication and task ownership management.

This module handles user authentication, account management, and task ownership
within the Common Chronicle application. Users represent the authenticated
entities who can create and manage timeline generation tasks.

Architecture:
    User → Task → Viewpoint → Events

Key Features:
    - Secure bcrypt password hashing
    - Username-based identification
    - Task ownership and access control
    - Automatic timestamp tracking
"""

from sqlalchemy import Column, Index, String
from sqlalchemy.orm import relationship

from app.models.base import SCHEMA_NAME, Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    """
    User account for authentication and task ownership.

    Represents a registered user who can create and manage timeline generation
    tasks. Provides secure authentication through bcrypt password hashing.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_username", "username", unique=True),
        {"schema": SCHEMA_NAME},
    )

    username = Column(
        String(50),
        nullable=False,
        comment="Unique username for user identification and login",
    )

    hashed_password = Column(
        String(255),
        nullable=False,
        comment="Bcrypt hashed password for secure authentication",
    )

    tasks = relationship(
        "Task",
        back_populates="owner",
        cascade="all, delete-orphan",
        doc="Tasks created by this user",
    )

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"
