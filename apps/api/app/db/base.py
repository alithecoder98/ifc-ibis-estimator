"""Declarative base all ORM models inherit from."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
