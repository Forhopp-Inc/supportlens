"""
Database models for SupportLens backend.
Defines the Trace data model with SQLAlchemy ORM.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy import Enum as SQLEnum

from backend.config import Base


class Category(StrEnum):
    """Support ticket classification categories."""
    Billing = "Billing"
    Refund = "Refund"
    Account_Access = "Account_Access"
    Cancellation = "Cancellation"
    General_Inquiry = "General_Inquiry"


class TraceDB(Base):
    """
    SQLAlchemy ORM model for storing support conversation traces.

    Attributes:
        id: Unique UUID identifier for the trace
        session_id: UUID linking messages in the same conversation
        user_message: The customer's support message
        bot_response: The chatbot's response
        category: Classification category for the trace
        timestamp: When the trace was recorded
        response_time_ms: Time taken to generate response in milliseconds
    """
    __tablename__ = "traces"

    id = Column(String(36), primary_key=True)  # UUID
    session_id = Column(String(36), nullable=True, index=True)  # Conversation session UUID
    user_message = Column(String(2000), nullable=False)
    bot_response = Column(String(4000), nullable=False)
    category = Column(SQLEnum(Category), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    response_time_ms = Column(Integer, nullable=False)

    # Database indexes for efficient querying
    __table_args__ = (
        Index('idx_category', 'category'),
        Index('idx_timestamp', 'timestamp'),
        Index('idx_session_id', 'session_id'),
    )

    def __repr__(self) -> str:
        return f"<TraceDB(id={self.id}, session_id={self.session_id}, category={self.category})>"
