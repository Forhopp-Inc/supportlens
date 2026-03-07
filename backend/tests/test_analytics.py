"""
Unit tests for GET /analytics endpoint.
Tests analytics calculations including total count, category breakdown, and average response time.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Base, get_db
from backend.main import app
from backend.models import Category, TraceDB


# In-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_db():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield TestingSessionLocal()
    
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """Create a FastAPI TestClient with the test database."""
    return TestClient(app)


class TestAnalyticsEndpoint:
    """Tests for GET /analytics endpoint."""

    def test_empty_database_returns_zeros(self, client):
        """
        When no traces exist, analytics returns zeros and empty breakdown.
        
        **Validates: Requirements 4.4**
        """
        response = client.get("/analytics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_count"] == 0
        assert data["category_breakdown"] == []
        assert data["average_response_time_ms"] == 0.0

    def test_single_trace_analytics(self, client, test_db):
        """
        With a single trace, analytics returns correct values.
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create a trace directly in the database
        trace = TraceDB(
            id="test-id-1",
            user_message="Test message",
            bot_response="Test response",
            category=Category.Billing,
            timestamp=datetime.utcnow(),
            response_time_ms=150
        )
        test_db.add(trace)
        test_db.commit()
        
        response = client.get("/analytics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_count"] == 1
        assert len(data["category_breakdown"]) == 1
        assert data["category_breakdown"][0]["category"] == "Billing"
        assert data["category_breakdown"][0]["count"] == 1
        assert data["category_breakdown"][0]["percentage"] == 100.0
        assert data["average_response_time_ms"] == 150.0

    def test_multiple_traces_same_category(self, client, test_db):
        """
        With multiple traces in the same category, analytics calculates correctly.
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create multiple traces in the same category
        for i in range(3):
            trace = TraceDB(
                id=f"test-id-{i}",
                user_message=f"Test message {i}",
                bot_response=f"Test response {i}",
                category=Category.Refund,
                timestamp=datetime.utcnow(),
                response_time_ms=100 + i * 50  # 100, 150, 200
            )
            test_db.add(trace)
        test_db.commit()
        
        response = client.get("/analytics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_count"] == 3
        assert len(data["category_breakdown"]) == 1
        assert data["category_breakdown"][0]["category"] == "Refund"
        assert data["category_breakdown"][0]["count"] == 3
        assert data["category_breakdown"][0]["percentage"] == 100.0
        # Average: (100 + 150 + 200) / 3 = 150
        assert data["average_response_time_ms"] == 150.0

    def test_multiple_categories_breakdown(self, client, test_db):
        """
        With traces in multiple categories, breakdown shows correct counts and percentages.
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create traces in different categories
        categories_data = [
            (Category.Billing, 100),
            (Category.Billing, 200),
            (Category.Refund, 150),
            (Category.Account_Access, 250),
        ]
        
        for i, (category, response_time) in enumerate(categories_data):
            trace = TraceDB(
                id=f"test-id-{i}",
                user_message=f"Test message {i}",
                bot_response=f"Test response {i}",
                category=category,
                timestamp=datetime.utcnow(),
                response_time_ms=response_time
            )
            test_db.add(trace)
        test_db.commit()
        
        response = client.get("/analytics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_count"] == 4
        
        # Convert breakdown to dict for easier assertions
        breakdown_dict = {item["category"]: item for item in data["category_breakdown"]}
        
        # Billing: 2 traces = 50%
        assert breakdown_dict["Billing"]["count"] == 2
        assert breakdown_dict["Billing"]["percentage"] == 50.0
        
        # Refund: 1 trace = 25%
        assert breakdown_dict["Refund"]["count"] == 1
        assert breakdown_dict["Refund"]["percentage"] == 25.0
        
        # Account_Access: 1 trace = 25%
        assert breakdown_dict["Account_Access"]["count"] == 1
        assert breakdown_dict["Account_Access"]["percentage"] == 25.0
        
        # Average: (100 + 200 + 150 + 250) / 4 = 175
        assert data["average_response_time_ms"] == 175.0

    def test_all_five_categories(self, client, test_db):
        """
        With traces in all five categories, breakdown includes all categories.
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create one trace per category
        all_categories = [
            Category.Billing,
            Category.Refund,
            Category.Account_Access,
            Category.Cancellation,
            Category.General_Inquiry,
        ]
        
        for i, category in enumerate(all_categories):
            trace = TraceDB(
                id=f"test-id-{i}",
                user_message=f"Test message {i}",
                bot_response=f"Test response {i}",
                category=category,
                timestamp=datetime.utcnow(),
                response_time_ms=100
            )
            test_db.add(trace)
        test_db.commit()
        
        response = client.get("/analytics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["total_count"] == 5
        assert len(data["category_breakdown"]) == 5
        
        # Each category should have 1 trace = 20%
        for item in data["category_breakdown"]:
            assert item["count"] == 1
            assert item["percentage"] == 20.0
        
        # Average: 100 (all same)
        assert data["average_response_time_ms"] == 100.0

    def test_category_breakdown_sums_to_total(self, client, test_db):
        """
        The sum of category counts equals total_count.
        
        **Validates: Requirements 4.1, 4.2**
        """
        # Create various traces
        for i in range(10):
            category = list(Category)[i % 5]  # Cycle through categories
            trace = TraceDB(
                id=f"test-id-{i}",
                user_message=f"Test message {i}",
                bot_response=f"Test response {i}",
                category=category,
                timestamp=datetime.utcnow(),
                response_time_ms=100 + i * 10
            )
            test_db.add(trace)
        test_db.commit()
        
        response = client.get("/analytics")
        
        assert response.status_code == 200
        data = response.json()
        
        # Sum of category counts should equal total
        category_sum = sum(item["count"] for item in data["category_breakdown"])
        assert category_sum == data["total_count"]

    def test_percentages_sum_to_100(self, client, test_db):
        """
        The sum of category percentages equals 100% (within floating point tolerance).
        
        **Validates: Requirements 4.2**
        """
        # Create various traces
        for i in range(7):  # Odd number to test percentage rounding
            category = list(Category)[i % 3]  # Use only 3 categories
            trace = TraceDB(
                id=f"test-id-{i}",
                user_message=f"Test message {i}",
                bot_response=f"Test response {i}",
                category=category,
                timestamp=datetime.utcnow(),
                response_time_ms=100
            )
            test_db.add(trace)
        test_db.commit()
        
        response = client.get("/analytics")
        
        assert response.status_code == 200
        data = response.json()
        
        # Sum of percentages should be approximately 100%
        percentage_sum = sum(item["percentage"] for item in data["category_breakdown"])
        assert abs(percentage_sum - 100.0) < 0.01, f"Percentages sum to {percentage_sum}, expected ~100"
