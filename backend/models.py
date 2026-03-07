"""
Database models for SupportLens backend.
Defines the Trace data model with SQLAlchemy ORM.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum, Index

from backend.config import Base


class Category(str, Enum):
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
        user_message: The customer's support message
        bot_response: The chatbot's response
        category: Classification category for the trace
        timestamp: When the trace was recorded
        response_time_ms: Time taken to generate response in milliseconds
    """
    __tablename__ = "traces"
    
    id = Column(String(36), primary_key=True)  # UUID
    user_message = Column(String(2000), nullable=False)
    bot_response = Column(String(4000), nullable=False)
    category = Column(SQLEnum(Category), nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    response_time_ms = Column(Integer, nullable=False)
    
    # Database indexes for efficient querying
    __table_args__ = (
        Index('idx_category', 'category'),
        Index('idx_timestamp', 'timestamp'),
    )
    
    def __repr__(self) -> str:
        return f"<TraceDB(id={self.id}, category={self.category}, timestamp={self.timestamp})>"
