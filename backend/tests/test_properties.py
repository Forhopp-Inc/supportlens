"""
Property-based tests for SupportLens backend.
Uses Hypothesis library for property-based testing.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, strategies as st, settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Base, get_db
from backend.main import app
from backend.models import Category, TraceDB


# Valid category values as defined in requirements
VALID_CATEGORIES = {"Billing", "Refund", "Account_Access", "Cancellation", "General_Inquiry"}


class TestCategoryValidation:
    """
    Property 3: Category Validation
    
    For any trace stored in the system, the assigned category must be exactly 
    one of the five valid categories: Billing, Refund, Account_Access, 
    Cancellation, or General_Inquiry.
    
    **Validates: Requirements 2.2, 5.2**
    """

    def test_category_enum_contains_exactly_five_valid_values(self):
        """
        Verify the Category enum contains exactly the five valid categories.
        
        **Validates: Requirements 2.2, 5.2**
        """
        # Get all enum member values
        enum_values = {member.value for member in Category}
        
        # Verify exact match with valid categories
        assert enum_values == VALID_CATEGORIES, (
            f"Category enum values {enum_values} do not match "
            f"expected valid categories {VALID_CATEGORIES}"
        )
        
        # Verify count is exactly 5
        assert len(Category) == 5, (
            f"Expected exactly 5 categories, but found {len(Category)}"
        )

    def test_category_enum_member_names_match_values(self):
        """
        Verify each Category enum member name matches its value.
        
        **Validates: Requirements 2.2, 5.2**
        """
        for member in Category:
            assert member.name == member.value, (
                f"Category member name '{member.name}' does not match "
                f"value '{member.value}'"
            )

    @settings(max_examples=100)
    @given(category=st.sampled_from(list(Category)))
    def test_any_category_enum_member_is_valid(self, category: Category):
        """
        For any Category enum member, its value must be in the valid categories set.
        
        **Validates: Requirements 2.2, 5.2**
        """
        assert category.value in VALID_CATEGORIES, (
            f"Category '{category.value}' is not in valid categories: {VALID_CATEGORIES}"
        )

    @settings(max_examples=100)
    @given(category_value=st.sampled_from(list(VALID_CATEGORIES)))
    def test_valid_category_string_can_create_enum(self, category_value: str):
        """
        For any valid category string, it should successfully create a Category enum.
        
        **Validates: Requirements 2.2, 5.2**
        """
        # Should not raise an exception
        category = Category(category_value)
        assert category.value == category_value

    @settings(max_examples=100)
    @given(invalid_category=st.text(min_size=1, max_size=50).filter(
        lambda x: x not in VALID_CATEGORIES
    ))
    def test_invalid_category_string_raises_error(self, invalid_category: str):
        """
        For any string that is not a valid category, creating a Category enum should fail.
        
        **Validates: Requirements 2.2, 5.2**
        """
        try:
            Category(invalid_category)
            # If we get here, the invalid category was accepted (which is wrong)
            assert False, (
                f"Invalid category '{invalid_category}' was accepted but should have been rejected"
            )
        except ValueError:
            # Expected behavior - invalid category raises ValueError
            pass

    @settings(max_examples=100)
    @given(
        category=st.sampled_from(list(Category)),
        user_message=st.text(min_size=1, max_size=100),
        bot_response=st.text(min_size=1, max_size=100),
        response_time_ms=st.integers(min_value=0, max_value=10000)
    )
    def test_trace_category_is_always_valid(
        self, 
        category: Category, 
        user_message: str, 
        bot_response: str, 
        response_time_ms: int
    ):
        """
        For any trace with a Category enum value, the category must be valid.
        
        This simulates trace creation and verifies the category constraint.
        
        **Validates: Requirements 2.2, 5.2**
        """
        # Verify the category is one of the valid values
        assert category.value in VALID_CATEGORIES, (
            f"Trace category '{category.value}' is not valid"
        )
        
        # Verify the category is a proper Category enum instance
        assert isinstance(category, Category), (
            f"Category must be a Category enum instance, got {type(category)}"
        )

    def test_category_enum_is_string_subclass(self):
        """
        Verify Category enum inherits from str for JSON serialization compatibility.
        
        **Validates: Requirements 2.2, 5.2**
        """
        for member in Category:
            assert isinstance(member, str), (
                f"Category member {member} should be a string instance"
            )
            # Verify string comparison works
            assert member == member.value

    @settings(max_examples=100)
    @given(category=st.sampled_from(list(Category)))
    def test_category_serialization_round_trip(self, category: Category):
        """
        For any category, serializing to string and back should preserve the value.
        
        **Validates: Requirements 2.2, 5.2**
        """
        # Serialize to string
        serialized = category.value
        
        # Deserialize back to enum
        deserialized = Category(serialized)
        
        # Verify round-trip preserves value
        assert deserialized == category
        assert deserialized.value == category.value


# ============================================================================
# Test Fixtures for API Testing
# ============================================================================

# In-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_db():
    """
    Create a fresh in-memory SQLite database for each test.
    
    This fixture:
    1. Creates an in-memory SQLite database
    2. Creates all tables
    3. Overrides the FastAPI dependency to use the test database
    4. Yields the session for test use
    5. Cleans up after the test
    """
    # Create engine with StaticPool to share connection across threads
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Create session factory
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    # Override the get_db dependency
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield TestingSessionLocal()
    
    # Cleanup
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db):
    """
    Create a FastAPI TestClient with the test database.
    """
    return TestClient(app)


# ============================================================================
# Property 1: Trace Persistence Round-Trip
# ============================================================================

class TestTracePersistenceRoundTrip:
    """
    Property 1: Trace Persistence Round-Trip
    
    For any valid trace submission (user_message, bot_response, response_time_ms), 
    storing the trace and then retrieving it by ID should return an equivalent 
    trace with all original fields preserved plus the generated id, category, 
    and timestamp.
    
    **Validates: Requirements 2.4, 5.1**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        user_message=st.text(min_size=1, max_size=500).filter(lambda x: x.strip()),
        bot_response=st.text(min_size=1, max_size=1000).filter(lambda x: x.strip()),
        response_time_ms=st.integers(min_value=0, max_value=10000)
    )
    def test_trace_persistence_round_trip(
        self, 
        user_message: str, 
        bot_response: str, 
        response_time_ms: int
    ):
        """
        For any valid trace, storing and retrieving preserves all fields.
        
        This test:
        1. Generates random valid trace data
        2. POSTs to /traces endpoint
        3. Verifies the response contains all original fields preserved
        4. Verifies generated fields exist (id, category, timestamp)
        
        **Validates: Requirements 2.4, 5.1**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Record time before submission for timestamp validation
            time_before = datetime.utcnow()
            
            # Mock the Gemini client to avoid actual API calls
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                # Return a valid category for classification
                mock_instance.classify_trace_safe.return_value = Category.General_Inquiry
                
                # POST trace to /traces endpoint
                response = client.post("/traces", json={
                    "user_message": user_message,
                    "bot_response": bot_response,
                    "response_time_ms": response_time_ms
                })
            
            # Record time after submission
            time_after = datetime.utcnow()
            
            # Verify successful response
            assert response.status_code == 200, (
                f"Expected status 200, got {response.status_code}: {response.text}"
            )
            
            trace_data = response.json()
            
            # Verify original fields are preserved
            assert trace_data["user_message"] == user_message, (
                f"user_message mismatch: expected '{user_message}', "
                f"got '{trace_data['user_message']}'"
            )
            assert trace_data["bot_response"] == bot_response, (
                f"bot_response mismatch: expected '{bot_response}', "
                f"got '{trace_data['bot_response']}'"
            )
            assert trace_data["response_time_ms"] == response_time_ms, (
                f"response_time_ms mismatch: expected {response_time_ms}, "
                f"got {trace_data['response_time_ms']}"
            )
            
            # Verify generated fields exist
            assert "id" in trace_data and trace_data["id"], (
                "Trace must have a non-empty id"
            )
            assert isinstance(trace_data["id"], str), (
                f"id must be a string, got {type(trace_data['id'])}"
            )
            
            assert "category" in trace_data and trace_data["category"], (
                "Trace must have a category"
            )
            assert trace_data["category"] in VALID_CATEGORIES, (
                f"category '{trace_data['category']}' is not valid"
            )
            
            assert "timestamp" in trace_data and trace_data["timestamp"], (
                "Trace must have a timestamp"
            )
            # Parse timestamp and verify it's within reasonable bounds
            timestamp = datetime.fromisoformat(trace_data["timestamp"].replace("Z", "+00:00").replace("+00:00", ""))
            assert time_before - timedelta(seconds=5) <= timestamp <= time_after + timedelta(seconds=5), (
                f"Timestamp {timestamp} is not within expected range "
                f"[{time_before - timedelta(seconds=5)}, {time_after + timedelta(seconds=5)}]"
            )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        user_message=st.text(min_size=1, max_size=500).filter(lambda x: x.strip()),
        bot_response=st.text(min_size=1, max_size=1000).filter(lambda x: x.strip()),
        response_time_ms=st.integers(min_value=0, max_value=10000),
        mock_category=st.sampled_from(list(Category))
    )
    def test_trace_persistence_preserves_all_field_types(
        self,
        user_message: str,
        bot_response: str,
        response_time_ms: int,
        mock_category: Category
    ):
        """
        For any valid trace with any category, all field types are correctly preserved.
        
        This test verifies that:
        1. String fields (user_message, bot_response, id) are strings
        2. Integer field (response_time_ms) is an integer
        3. Category field is a valid category string
        4. Timestamp field is a valid ISO datetime string
        
        **Validates: Requirements 2.4, 5.1**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Mock the Gemini client with the randomly selected category
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = mock_category
                
                # POST trace to /traces endpoint
                response = client.post("/traces", json={
                    "user_message": user_message,
                    "bot_response": bot_response,
                    "response_time_ms": response_time_ms
                })
            
            assert response.status_code == 200
            trace_data = response.json()
            
            # Verify field types
            assert isinstance(trace_data["id"], str), "id must be a string"
            assert isinstance(trace_data["user_message"], str), "user_message must be a string"
            assert isinstance(trace_data["bot_response"], str), "bot_response must be a string"
            assert isinstance(trace_data["category"], str), "category must be a string"
            assert isinstance(trace_data["timestamp"], str), "timestamp must be a string"
            assert isinstance(trace_data["response_time_ms"], int), "response_time_ms must be an integer"
            
            # Verify the category matches what we mocked
            assert trace_data["category"] == mock_category.value, (
                f"Expected category '{mock_category.value}', got '{trace_data['category']}'"
            )
            
            # Verify timestamp is valid ISO format
            try:
                datetime.fromisoformat(trace_data["timestamp"].replace("Z", "+00:00").replace("+00:00", ""))
            except ValueError as e:
                assert False, f"Invalid timestamp format: {trace_data['timestamp']}, error: {e}"
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        user_message=st.text(min_size=1, max_size=500).filter(lambda x: x.strip()),
        bot_response=st.text(min_size=1, max_size=1000).filter(lambda x: x.strip()),
        response_time_ms=st.integers(min_value=0, max_value=10000)
    )
    def test_trace_response_completeness(
        self,
        user_message: str,
        bot_response: str,
        response_time_ms: int
    ):
        """
        For any trace returned by POST /traces, the response contains all required fields.
        
        Required fields: id, user_message, bot_response, category, timestamp, response_time_ms
        
        **Validates: Requirements 2.4, 5.1**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Mock the Gemini client
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = Category.Billing
                
                # POST trace to /traces endpoint
                response = client.post("/traces", json={
                    "user_message": user_message,
                    "bot_response": bot_response,
                    "response_time_ms": response_time_ms
                })
            
            assert response.status_code == 200
            trace_data = response.json()
            
            # Verify all required fields are present
            required_fields = ["id", "user_message", "bot_response", "category", "timestamp", "response_time_ms"]
            for field in required_fields:
                assert field in trace_data, f"Missing required field: {field}"
                assert trace_data[field] is not None, f"Field '{field}' is None"
            
            # Verify id is non-empty string
            assert len(trace_data["id"]) > 0, "id must be non-empty"
            
            # Verify response_time_ms is non-negative
            assert trace_data["response_time_ms"] >= 0, "response_time_ms must be non-negative"
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)


# ============================================================================
# Property 2: Unique ID Generation
# ============================================================================

class TestUniqueIDGeneration:
    """
    Property 2: Unique ID Generation
    
    For any set of traces submitted to the system, all generated trace IDs 
    should be unique—no two traces should ever share the same ID.
    
    **Validates: Requirements 2.1, 5.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(traces=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
            st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
            st.integers(min_value=0, max_value=5000)
        ),
        min_size=2,
        max_size=20
    ))
    def test_unique_id_generation(self, traces):
        """
        For any set of traces, all IDs are unique.
        
        This test:
        1. Generates a random list of 2-20 traces
        2. POSTs each trace to /traces endpoint
        3. Collects all generated IDs
        4. Verifies all IDs are unique (no duplicates)
        
        **Validates: Requirements 2.1, 5.3**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Mock the Gemini client to avoid actual API calls
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = Category.General_Inquiry
                
                # Collect all generated IDs
                generated_ids = []
                
                for user_msg, bot_resp, time_ms in traces:
                    response = client.post("/traces", json={
                        "user_message": user_msg,
                        "bot_response": bot_resp,
                        "response_time_ms": time_ms
                    })
                    
                    assert response.status_code == 200, (
                        f"Expected status 200, got {response.status_code}: {response.text}"
                    )
                    
                    trace_data = response.json()
                    generated_ids.append(trace_data["id"])
                
                # Verify all IDs are unique
                assert len(generated_ids) == len(set(generated_ids)), (
                    f"Duplicate IDs found! Generated {len(generated_ids)} traces "
                    f"but only {len(set(generated_ids))} unique IDs. "
                    f"Duplicates: {[id for id in generated_ids if generated_ids.count(id) > 1]}"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        user_message=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        bot_response=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        response_time_ms=st.integers(min_value=0, max_value=5000),
        num_duplicates=st.integers(min_value=2, max_value=10)
    )
    def test_identical_traces_get_unique_ids(
        self,
        user_message: str,
        bot_response: str,
        response_time_ms: int,
        num_duplicates: int
    ):
        """
        For identical trace data submitted multiple times, each gets a unique ID.
        
        This test verifies that even when the same exact trace data is submitted
        multiple times, each submission receives a unique ID.
        
        **Validates: Requirements 2.1, 5.3**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Mock the Gemini client to avoid actual API calls
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = Category.Billing
                
                # Submit the same trace data multiple times
                generated_ids = []
                
                for _ in range(num_duplicates):
                    response = client.post("/traces", json={
                        "user_message": user_message,
                        "bot_response": bot_response,
                        "response_time_ms": response_time_ms
                    })
                    
                    assert response.status_code == 200, (
                        f"Expected status 200, got {response.status_code}: {response.text}"
                    )
                    
                    trace_data = response.json()
                    generated_ids.append(trace_data["id"])
                
                # Verify all IDs are unique even for identical trace data
                assert len(generated_ids) == len(set(generated_ids)), (
                    f"Duplicate IDs found for identical traces! "
                    f"Submitted {num_duplicates} identical traces but got duplicate IDs. "
                    f"IDs: {generated_ids}"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        user_message=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        bot_response=st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
        response_time_ms=st.integers(min_value=0, max_value=5000)
    )
    def test_id_is_valid_uuid_format(
        self,
        user_message: str,
        bot_response: str,
        response_time_ms: int
    ):
        """
        For any trace, the generated ID should be a valid UUID string.
        
        This test verifies that generated IDs follow UUID format (36 characters
        with hyphens in the correct positions).
        
        **Validates: Requirements 2.1, 5.3**
        """
        import uuid
        
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Mock the Gemini client to avoid actual API calls
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = Category.Refund
                
                response = client.post("/traces", json={
                    "user_message": user_message,
                    "bot_response": bot_response,
                    "response_time_ms": response_time_ms
                })
                
                assert response.status_code == 200, (
                    f"Expected status 200, got {response.status_code}: {response.text}"
                )
                
                trace_data = response.json()
                trace_id = trace_data["id"]
                
                # Verify ID is a valid UUID
                try:
                    uuid.UUID(trace_id)
                except ValueError:
                    assert False, (
                        f"Generated ID '{trace_id}' is not a valid UUID format"
                    )
                
                # Verify ID is non-empty
                assert len(trace_id) > 0, "ID must be non-empty"
                
                # Verify ID is a string
                assert isinstance(trace_id, str), (
                    f"ID must be a string, got {type(trace_id)}"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)


# ============================================================================
# Property 4: Trace Ordering by Timestamp
# ============================================================================

class TestTraceOrderingByTimestamp:
    """
    Property 4: Trace Ordering by Timestamp
    
    For any GET /traces request, the returned traces should be ordered by 
    timestamp in descending order—each trace's timestamp should be greater 
    than or equal to the next trace's timestamp in the list.
    
    **Validates: Requirements 3.1**
    """

    @settings(max_examples=100, deadline=None)
    @given(num_traces=st.integers(min_value=2, max_value=15))
    def test_trace_ordering_by_timestamp(self, num_traces: int):
        """
        For any traces created, GET /traces returns them in descending timestamp order.
        
        This test:
        1. Creates multiple traces with varying timestamps
        2. Calls GET /traces endpoint
        3. Verifies returned traces are ordered by timestamp descending
        
        **Validates: Requirements 3.1**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Mock the Gemini client to avoid actual API calls
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = Category.General_Inquiry
                
                # Create multiple traces
                for i in range(num_traces):
                    response = client.post("/traces", json={
                        "user_message": f"Test message {i}",
                        "bot_response": f"Test response {i}",
                        "response_time_ms": 100 + i
                    })
                    assert response.status_code == 200, (
                        f"Expected status 200, got {response.status_code}: {response.text}"
                    )
                
                # Retrieve all traces
                response = client.get("/traces")
                assert response.status_code == 200, (
                    f"Expected status 200, got {response.status_code}: {response.text}"
                )
                
                traces = response.json()
                
                # Verify we got all traces
                assert len(traces) == num_traces, (
                    f"Expected {num_traces} traces, got {len(traces)}"
                )
                
                # Extract timestamps and verify descending order
                timestamps = [trace["timestamp"] for trace in traces]
                
                for i in range(len(timestamps) - 1):
                    current_ts = timestamps[i]
                    next_ts = timestamps[i + 1]
                    assert current_ts >= next_ts, (
                        f"Traces not in descending timestamp order: "
                        f"trace[{i}].timestamp ({current_ts}) < trace[{i+1}].timestamp ({next_ts})"
                    )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        traces_data=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.integers(min_value=0, max_value=5000)
            ),
            min_size=2,
            max_size=10
        )
    )
    def test_trace_ordering_with_random_data(self, traces_data):
        """
        For any set of random traces, GET /traces returns them in descending timestamp order.
        
        This test uses randomly generated trace data to verify ordering.
        
        **Validates: Requirements 3.1**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Mock the Gemini client to avoid actual API calls
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = Category.Billing
                
                # Create traces with random data
                for user_msg, bot_resp, time_ms in traces_data:
                    response = client.post("/traces", json={
                        "user_message": user_msg,
                        "bot_response": bot_resp,
                        "response_time_ms": time_ms
                    })
                    assert response.status_code == 200, (
                        f"Expected status 200, got {response.status_code}: {response.text}"
                    )
                
                # Retrieve all traces
                response = client.get("/traces")
                assert response.status_code == 200
                
                traces = response.json()
                
                # Verify we got all traces
                assert len(traces) == len(traces_data), (
                    f"Expected {len(traces_data)} traces, got {len(traces)}"
                )
                
                # Verify descending timestamp order
                timestamps = [trace["timestamp"] for trace in traces]
                
                for i in range(len(timestamps) - 1):
                    current_ts = timestamps[i]
                    next_ts = timestamps[i + 1]
                    assert current_ts >= next_ts, (
                        f"Traces not in descending timestamp order at index {i}: "
                        f"'{current_ts}' < '{next_ts}'"
                    )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(category=st.sampled_from(list(Category)))
    def test_trace_ordering_with_category_filter(self, category: Category):
        """
        For any category filter, GET /traces returns filtered traces in descending timestamp order.
        
        This test verifies that ordering is maintained even when filtering by category.
        
        **Validates: Requirements 3.1**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Mock the Gemini client to return the test category
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = category
                
                # Create multiple traces with the same category
                num_traces = 5
                for i in range(num_traces):
                    response = client.post("/traces", json={
                        "user_message": f"Test message {i} for {category.value}",
                        "bot_response": f"Test response {i}",
                        "response_time_ms": 100 + i * 10
                    })
                    assert response.status_code == 200
                
                # Retrieve traces filtered by category
                response = client.get(f"/traces?category={category.value}")
                assert response.status_code == 200
                
                traces = response.json()
                
                # Verify we got traces
                assert len(traces) == num_traces, (
                    f"Expected {num_traces} traces, got {len(traces)}"
                )
                
                # Verify all traces have the correct category
                for trace in traces:
                    assert trace["category"] == category.value, (
                        f"Expected category '{category.value}', got '{trace['category']}'"
                    )
                
                # Verify descending timestamp order
                timestamps = [trace["timestamp"] for trace in traces]
                
                for i in range(len(timestamps) - 1):
                    current_ts = timestamps[i]
                    next_ts = timestamps[i + 1]
                    assert current_ts >= next_ts, (
                        f"Filtered traces not in descending timestamp order: "
                        f"trace[{i}].timestamp ({current_ts}) < trace[{i+1}].timestamp ({next_ts})"
                    )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    def test_empty_traces_returns_empty_list(self):
        """
        When no traces exist, GET /traces returns an empty list (edge case).
        
        **Validates: Requirements 3.1**
        """
        # Create fresh test database and client
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
        
        try:
            client = TestClient(app)
            
            # Retrieve traces from empty database
            response = client.get("/traces")
            assert response.status_code == 200
            
            traces = response.json()
            assert traces == [], f"Expected empty list, got {traces}"
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    def test_single_trace_returns_single_item(self):
        """
        When only one trace exists, GET /traces returns a list with one item (edge case).
        
        **Validates: Requirements 3.1**
        """
        # Create fresh test database and client
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
        
        try:
            client = TestClient(app)
            
            # Mock the Gemini client
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = Category.Refund
                
                # Create a single trace
                response = client.post("/traces", json={
                    "user_message": "Single test message",
                    "bot_response": "Single test response",
                    "response_time_ms": 150
                })
                assert response.status_code == 200
                
                # Retrieve traces
                response = client.get("/traces")
                assert response.status_code == 200
                
                traces = response.json()
                assert len(traces) == 1, f"Expected 1 trace, got {len(traces)}"
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)


# ============================================================================
# Property 5: Category Filtering Correctness
# ============================================================================

class TestCategoryFilteringCorrectness:
    """
    Property 5: Category Filtering Correctness
    
    For any category filter applied to GET /traces, all returned traces should 
    have a category field matching the filter value exactly—no traces with 
    different categories should appear in the results.
    
    **Validates: Requirements 3.2, 7.4**
    """

    @settings(max_examples=100, deadline=None)
    @given(filter_category=st.sampled_from(list(Category)))
    def test_category_filtering_correctness(self, filter_category: Category):
        """
        For any category filter, all returned traces match that category exactly.
        
        This test:
        1. Creates traces with various categories
        2. Calls GET /traces with a category filter
        3. Verifies all returned traces have the exact filter category
        4. Verifies no traces with different categories appear
        
        **Validates: Requirements 3.2, 7.4**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Create traces with all different categories
            all_categories = list(Category)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                
                # Create 2 traces for each category
                for category in all_categories:
                    mock_instance.classify_trace_safe.return_value = category
                    for i in range(2):
                        response = client.post("/traces", json={
                            "user_message": f"Test message for {category.value} - {i}",
                            "bot_response": f"Test response for {category.value} - {i}",
                            "response_time_ms": 100 + i
                        })
                        assert response.status_code == 200, (
                            f"Expected status 200, got {response.status_code}: {response.text}"
                        )
                
                # Now filter by the test category
                response = client.get(f"/traces?category={filter_category.value}")
                assert response.status_code == 200, (
                    f"Expected status 200, got {response.status_code}: {response.text}"
                )
                
                traces = response.json()
                
                # Verify all returned traces match the filter category exactly
                for trace in traces:
                    assert trace["category"] == filter_category.value, (
                        f"Trace category '{trace['category']}' does not match "
                        f"filter category '{filter_category.value}'. "
                        f"Trace ID: {trace['id']}"
                    )
                
                # Verify we got the expected number of traces (2 per category)
                assert len(traces) == 2, (
                    f"Expected 2 traces for category '{filter_category.value}', "
                    f"got {len(traces)}"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        filter_category=st.sampled_from(list(Category)),
        num_matching_traces=st.integers(min_value=1, max_value=10),
        num_other_traces=st.integers(min_value=0, max_value=10)
    )
    def test_category_filter_excludes_non_matching_traces(
        self,
        filter_category: Category,
        num_matching_traces: int,
        num_other_traces: int
    ):
        """
        For any category filter, traces with different categories are excluded.
        
        This test:
        1. Creates a random number of traces with the filter category
        2. Creates a random number of traces with other categories
        3. Verifies only matching traces are returned
        4. Verifies the count matches expected matching traces
        
        **Validates: Requirements 3.2, 7.4**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Get other categories (not the filter category)
            other_categories = [c for c in Category if c != filter_category]
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                
                # Create traces with the filter category
                mock_instance.classify_trace_safe.return_value = filter_category
                for i in range(num_matching_traces):
                    response = client.post("/traces", json={
                        "user_message": f"Matching message {i}",
                        "bot_response": f"Matching response {i}",
                        "response_time_ms": 100 + i
                    })
                    assert response.status_code == 200
                
                # Create traces with other categories
                if num_other_traces > 0 and other_categories:
                    for i in range(num_other_traces):
                        # Cycle through other categories
                        other_cat = other_categories[i % len(other_categories)]
                        mock_instance.classify_trace_safe.return_value = other_cat
                        response = client.post("/traces", json={
                            "user_message": f"Other message {i}",
                            "bot_response": f"Other response {i}",
                            "response_time_ms": 200 + i
                        })
                        assert response.status_code == 200
                
                # Filter by the test category
                response = client.get(f"/traces?category={filter_category.value}")
                assert response.status_code == 200
                
                traces = response.json()
                
                # Verify count matches expected matching traces
                assert len(traces) == num_matching_traces, (
                    f"Expected {num_matching_traces} traces for category "
                    f"'{filter_category.value}', got {len(traces)}"
                )
                
                # Verify all returned traces match the filter category
                for trace in traces:
                    assert trace["category"] == filter_category.value, (
                        f"Non-matching trace found! Expected category "
                        f"'{filter_category.value}', got '{trace['category']}'"
                    )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(filter_category=st.sampled_from(list(Category)))
    def test_category_filter_returns_empty_when_no_matches(self, filter_category: Category):
        """
        For any category filter with no matching traces, returns empty list.
        
        This test:
        1. Creates traces with categories different from the filter
        2. Verifies filtering returns an empty list
        
        **Validates: Requirements 3.2, 7.4**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            # Get a different category from the filter
            other_categories = [c for c in Category if c != filter_category]
            if not other_categories:
                # Edge case: only one category exists (shouldn't happen)
                return
            
            other_category = other_categories[0]
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = other_category
                
                # Create traces with a different category
                for i in range(3):
                    response = client.post("/traces", json={
                        "user_message": f"Other category message {i}",
                        "bot_response": f"Other category response {i}",
                        "response_time_ms": 100 + i
                    })
                    assert response.status_code == 200
                
                # Filter by the test category (which has no traces)
                response = client.get(f"/traces?category={filter_category.value}")
                assert response.status_code == 200
                
                traces = response.json()
                
                # Verify empty list is returned
                assert traces == [], (
                    f"Expected empty list for category '{filter_category.value}' "
                    f"with no matching traces, got {len(traces)} traces"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        filter_category=st.sampled_from(list(Category)),
        user_messages=st.lists(
            st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
            min_size=1,
            max_size=10
        )
    )
    def test_category_filter_with_random_message_content(
        self,
        filter_category: Category,
        user_messages: list
    ):
        """
        For any category filter with random message content, filtering works correctly.
        
        This test verifies that message content does not affect category filtering.
        
        **Validates: Requirements 3.2, 7.4**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = filter_category
                
                # Create traces with random message content
                for i, user_msg in enumerate(user_messages):
                    response = client.post("/traces", json={
                        "user_message": user_msg,
                        "bot_response": f"Response to: {user_msg[:50]}",
                        "response_time_ms": 100 + i
                    })
                    assert response.status_code == 200
                
                # Filter by the category
                response = client.get(f"/traces?category={filter_category.value}")
                assert response.status_code == 200
                
                traces = response.json()
                
                # Verify count matches
                assert len(traces) == len(user_messages), (
                    f"Expected {len(user_messages)} traces, got {len(traces)}"
                )
                
                # Verify all traces match the filter category
                for trace in traces:
                    assert trace["category"] == filter_category.value, (
                        f"Trace category '{trace['category']}' does not match "
                        f"filter '{filter_category.value}'"
                    )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    def test_category_filter_case_sensitivity(self):
        """
        Verify category filter is case-sensitive (exact match required).
        
        **Validates: Requirements 3.2, 7.4**
        """
        # Create fresh test database and client
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
        
        try:
            client = TestClient(app)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = Category.Billing
                
                # Create a trace with Billing category
                response = client.post("/traces", json={
                    "user_message": "Test billing message",
                    "bot_response": "Test billing response",
                    "response_time_ms": 100
                })
                assert response.status_code == 200
                
                # Filter with exact case - should return the trace
                response = client.get("/traces?category=Billing")
                assert response.status_code == 200
                traces = response.json()
                assert len(traces) == 1, "Expected 1 trace with exact case match"
                assert traces[0]["category"] == "Billing"
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    def test_no_filter_returns_all_categories(self):
        """
        When no category filter is applied, all traces are returned regardless of category.
        
        **Validates: Requirements 3.2, 7.4**
        """
        # Create fresh test database and client
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
        
        try:
            client = TestClient(app)
            
            all_categories = list(Category)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                
                # Create one trace for each category
                for category in all_categories:
                    mock_instance.classify_trace_safe.return_value = category
                    response = client.post("/traces", json={
                        "user_message": f"Message for {category.value}",
                        "bot_response": f"Response for {category.value}",
                        "response_time_ms": 100
                    })
                    assert response.status_code == 200
                
                # Get all traces without filter
                response = client.get("/traces")
                assert response.status_code == 200
                
                traces = response.json()
                
                # Verify all categories are represented
                assert len(traces) == len(all_categories), (
                    f"Expected {len(all_categories)} traces, got {len(traces)}"
                )
                
                returned_categories = {trace["category"] for trace in traces}
                expected_categories = {c.value for c in all_categories}
                
                assert returned_categories == expected_categories, (
                    f"Expected categories {expected_categories}, "
                    f"got {returned_categories}"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)


# ============================================================================
# Property 6: Analytics Accuracy
# ============================================================================

class TestAnalyticsAccuracy:
    """
    Property 6: Analytics Accuracy
    
    For any set of traces in the database, the analytics endpoint should return:
    (a) total_count equal to the actual number of traces,
    (b) category breakdown where the sum of all category counts equals total_count 
        and percentages sum to 100%,
    (c) average_response_time_ms equal to the arithmetic mean of all trace response times.
    
    **Validates: Requirements 4.1, 4.2, 4.3**
    """

    @settings(max_examples=100, deadline=None)
    @given(
        traces_data=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.integers(min_value=0, max_value=10000),
                st.sampled_from(list(Category))
            ),
            min_size=1,
            max_size=20
        )
    )
    def test_analytics_total_count_equals_actual_trace_count(self, traces_data):
        """
        For any set of traces, total_count equals the actual number of traces.
        
        This test:
        1. Generates random traces with various categories and response times
        2. Calls GET /analytics endpoint
        3. Verifies total_count equals the number of traces created
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                
                # Create traces with specified categories
                for user_msg, bot_resp, time_ms, category in traces_data:
                    mock_instance.classify_trace_safe.return_value = category
                    response = client.post("/traces", json={
                        "user_message": user_msg,
                        "bot_response": bot_resp,
                        "response_time_ms": time_ms
                    })
                    assert response.status_code == 200, (
                        f"Expected status 200, got {response.status_code}: {response.text}"
                    )
                
                # Get analytics
                response = client.get("/analytics")
                assert response.status_code == 200, (
                    f"Expected status 200, got {response.status_code}: {response.text}"
                )
                
                analytics = response.json()
                
                # Verify total_count equals actual trace count
                expected_count = len(traces_data)
                assert analytics["total_count"] == expected_count, (
                    f"total_count mismatch: expected {expected_count}, "
                    f"got {analytics['total_count']}"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        traces_data=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.integers(min_value=0, max_value=10000),
                st.sampled_from(list(Category))
            ),
            min_size=1,
            max_size=20
        )
    )
    def test_analytics_category_counts_sum_equals_total_count(self, traces_data):
        """
        For any set of traces, sum of category counts equals total_count.
        
        This test:
        1. Generates random traces with various categories
        2. Calls GET /analytics endpoint
        3. Verifies sum of all category counts equals total_count
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                
                # Create traces with specified categories
                for user_msg, bot_resp, time_ms, category in traces_data:
                    mock_instance.classify_trace_safe.return_value = category
                    response = client.post("/traces", json={
                        "user_message": user_msg,
                        "bot_response": bot_resp,
                        "response_time_ms": time_ms
                    })
                    assert response.status_code == 200
                
                # Get analytics
                response = client.get("/analytics")
                assert response.status_code == 200
                
                analytics = response.json()
                
                # Sum all category counts
                category_sum = sum(
                    breakdown["count"] 
                    for breakdown in analytics["category_breakdown"]
                )
                
                # Verify sum equals total_count
                assert category_sum == analytics["total_count"], (
                    f"Sum of category counts ({category_sum}) does not equal "
                    f"total_count ({analytics['total_count']})"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        traces_data=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.integers(min_value=0, max_value=10000),
                st.sampled_from(list(Category))
            ),
            min_size=1,
            max_size=20
        )
    )
    def test_analytics_percentages_sum_to_100(self, traces_data):
        """
        For any set of traces, percentages sum to 100% (within floating point tolerance).
        
        This test:
        1. Generates random traces with various categories
        2. Calls GET /analytics endpoint
        3. Verifies percentages sum to 100% within tolerance of 0.01
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                
                # Create traces with specified categories
                for user_msg, bot_resp, time_ms, category in traces_data:
                    mock_instance.classify_trace_safe.return_value = category
                    response = client.post("/traces", json={
                        "user_message": user_msg,
                        "bot_response": bot_resp,
                        "response_time_ms": time_ms
                    })
                    assert response.status_code == 200
                
                # Get analytics
                response = client.get("/analytics")
                assert response.status_code == 200
                
                analytics = response.json()
                
                # Sum all percentages
                percentage_sum = sum(
                    breakdown["percentage"] 
                    for breakdown in analytics["category_breakdown"]
                )
                
                # Verify percentages sum to 100% within tolerance
                assert abs(percentage_sum - 100.0) < 0.01, (
                    f"Percentages sum to {percentage_sum}, expected 100.0 "
                    f"(tolerance: 0.01)"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        traces_data=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.integers(min_value=0, max_value=10000),
                st.sampled_from(list(Category))
            ),
            min_size=1,
            max_size=20
        )
    )
    def test_analytics_average_response_time_equals_arithmetic_mean(self, traces_data):
        """
        For any set of traces, average_response_time_ms equals arithmetic mean.
        
        This test:
        1. Generates random traces with various response times
        2. Calls GET /analytics endpoint
        3. Verifies average_response_time_ms equals the arithmetic mean
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                
                # Track response times for verification
                response_times = []
                
                # Create traces with specified response times
                for user_msg, bot_resp, time_ms, category in traces_data:
                    mock_instance.classify_trace_safe.return_value = category
                    response = client.post("/traces", json={
                        "user_message": user_msg,
                        "bot_response": bot_resp,
                        "response_time_ms": time_ms
                    })
                    assert response.status_code == 200
                    response_times.append(time_ms)
                
                # Get analytics
                response = client.get("/analytics")
                assert response.status_code == 200
                
                analytics = response.json()
                
                # Calculate expected arithmetic mean
                expected_average = sum(response_times) / len(response_times)
                
                # Verify average_response_time_ms equals arithmetic mean
                # Use small tolerance for floating point comparison
                assert abs(analytics["average_response_time_ms"] - expected_average) < 0.001, (
                    f"average_response_time_ms mismatch: expected {expected_average}, "
                    f"got {analytics['average_response_time_ms']}"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        traces_data=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.integers(min_value=0, max_value=10000),
                st.sampled_from(list(Category))
            ),
            min_size=1,
            max_size=20
        )
    )
    def test_analytics_category_counts_match_actual_distribution(self, traces_data):
        """
        For any set of traces, category counts match actual distribution.
        
        This test:
        1. Generates random traces with various categories
        2. Calls GET /analytics endpoint
        3. Verifies each category count matches the actual number of traces in that category
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                
                # Track expected category counts
                expected_counts: dict = {}
                
                # Create traces with specified categories
                for user_msg, bot_resp, time_ms, category in traces_data:
                    mock_instance.classify_trace_safe.return_value = category
                    response = client.post("/traces", json={
                        "user_message": user_msg,
                        "bot_response": bot_resp,
                        "response_time_ms": time_ms
                    })
                    assert response.status_code == 200
                    expected_counts[category.value] = expected_counts.get(category.value, 0) + 1
                
                # Get analytics
                response = client.get("/analytics")
                assert response.status_code == 200
                
                analytics = response.json()
                
                # Build actual counts from analytics response
                actual_counts = {
                    breakdown["category"]: breakdown["count"]
                    for breakdown in analytics["category_breakdown"]
                }
                
                # Verify each category count matches expected
                for category_value, expected_count in expected_counts.items():
                    actual_count = actual_counts.get(category_value, 0)
                    assert actual_count == expected_count, (
                        f"Category '{category_value}' count mismatch: "
                        f"expected {expected_count}, got {actual_count}"
                    )
                
                # Verify no extra categories in response
                for category_value in actual_counts:
                    assert category_value in expected_counts, (
                        f"Unexpected category '{category_value}' in analytics response"
                    )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    @settings(max_examples=100, deadline=None)
    @given(
        traces_data=st.lists(
            st.tuples(
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.text(min_size=1, max_size=100).filter(lambda x: x.strip()),
                st.integers(min_value=0, max_value=10000),
                st.sampled_from(list(Category))
            ),
            min_size=1,
            max_size=20
        )
    )
    def test_analytics_category_percentages_are_correct(self, traces_data):
        """
        For any set of traces, each category percentage is correctly calculated.
        
        This test:
        1. Generates random traces with various categories
        2. Calls GET /analytics endpoint
        3. Verifies each category percentage equals (count / total_count) * 100
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create fresh test database and client for each example
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
        
        try:
            client = TestClient(app)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                
                # Create traces with specified categories
                for user_msg, bot_resp, time_ms, category in traces_data:
                    mock_instance.classify_trace_safe.return_value = category
                    response = client.post("/traces", json={
                        "user_message": user_msg,
                        "bot_response": bot_resp,
                        "response_time_ms": time_ms
                    })
                    assert response.status_code == 200
                
                # Get analytics
                response = client.get("/analytics")
                assert response.status_code == 200
                
                analytics = response.json()
                total_count = analytics["total_count"]
                
                # Verify each category percentage is correctly calculated
                for breakdown in analytics["category_breakdown"]:
                    expected_percentage = (breakdown["count"] / total_count) * 100
                    actual_percentage = breakdown["percentage"]
                    
                    assert abs(actual_percentage - expected_percentage) < 0.001, (
                        f"Category '{breakdown['category']}' percentage mismatch: "
                        f"expected {expected_percentage}, got {actual_percentage}"
                    )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    def test_analytics_empty_database_returns_zeros(self):
        """
        When no traces exist, analytics returns zeros and empty breakdown.
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create fresh test database and client
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
        
        try:
            client = TestClient(app)
            
            # Get analytics from empty database
            response = client.get("/analytics")
            assert response.status_code == 200
            
            analytics = response.json()
            
            # Verify zeros and empty breakdown
            assert analytics["total_count"] == 0, (
                f"Expected total_count 0, got {analytics['total_count']}"
            )
            assert analytics["average_response_time_ms"] == 0.0, (
                f"Expected average_response_time_ms 0.0, "
                f"got {analytics['average_response_time_ms']}"
            )
            assert analytics["category_breakdown"] == [], (
                f"Expected empty category_breakdown, "
                f"got {analytics['category_breakdown']}"
            )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)

    def test_analytics_single_trace(self):
        """
        When only one trace exists, analytics returns correct values.
        
        **Validates: Requirements 4.1, 4.2, 4.3**
        """
        # Create fresh test database and client
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
        
        try:
            client = TestClient(app)
            
            with patch('backend.main.GeminiClient') as MockGeminiClient:
                mock_instance = MockGeminiClient.return_value
                mock_instance.classify_trace_safe.return_value = Category.Billing
                
                # Create a single trace
                response_time = 500
                response = client.post("/traces", json={
                    "user_message": "Single test message",
                    "bot_response": "Single test response",
                    "response_time_ms": response_time
                })
                assert response.status_code == 200
                
                # Get analytics
                response = client.get("/analytics")
                assert response.status_code == 200
                
                analytics = response.json()
                
                # Verify values for single trace
                assert analytics["total_count"] == 1, (
                    f"Expected total_count 1, got {analytics['total_count']}"
                )
                assert analytics["average_response_time_ms"] == float(response_time), (
                    f"Expected average_response_time_ms {response_time}, "
                    f"got {analytics['average_response_time_ms']}"
                )
                assert len(analytics["category_breakdown"]) == 1, (
                    f"Expected 1 category in breakdown, "
                    f"got {len(analytics['category_breakdown'])}"
                )
                
                breakdown = analytics["category_breakdown"][0]
                assert breakdown["category"] == "Billing", (
                    f"Expected category 'Billing', got '{breakdown['category']}'"
                )
                assert breakdown["count"] == 1, (
                    f"Expected count 1, got {breakdown['count']}"
                )
                assert breakdown["percentage"] == 100.0, (
                    f"Expected percentage 100.0, got {breakdown['percentage']}"
                )
            
        finally:
            # Cleanup
            app.dependency_overrides.clear()
            Base.metadata.drop_all(bind=engine)
