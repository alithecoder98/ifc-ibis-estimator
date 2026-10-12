"""Declarative base all ORM models inherit from (see Phase 1.3 for the actual models)."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
