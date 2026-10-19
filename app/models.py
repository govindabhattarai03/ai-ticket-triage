"""Data models for support tickets.

Pydantic checks every ticket that enters the system: wrong types, missing fields
or an empty message are rejected automatically with a clear error.
These same models will later validate what the LLM returns.
"""
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field


class Category(str, Enum):
    BUG = "bug"
    BILLING = "billing"
    ACCOUNT_ACCESS = "account_access"
    FEATURE_REQUEST = "feature_request"
    OTHER = "other"


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TicketIn(BaseModel):
    """What a user sends when opening a ticket."""

    customer_email: EmailStr
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=5000)


class Ticket(TicketIn):
    """A ticket stored by the system."""

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "new"  # new -> triaged -> routed (from stage 2 onwards)
