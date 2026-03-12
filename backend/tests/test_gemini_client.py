"""
Unit tests for the Gemini API client.
Tests the GeminiClient class methods and error handling.
"""

from unittest.mock import patch

import pytest

from backend.gemini_client import (
    CLASSIFICATION_PROMPT,
    SUPPORT_AGENT_PROMPT,
    GeminiClient,
)
from backend.models import Category


class TestGeminiClientInit:
    """Tests for GeminiClient initialization."""

    def test_client_initializes_with_valid_categories(self):
        """Verify client has all valid categories for validation."""
        with patch('backend.gemini_client.genai'):
            client = GeminiClient(api_key="test-key")

            expected_categories = {
                "Billing", "Refund", "Account_Access",
                "Cancellation", "General_Inquiry"
            }
            assert client._valid_categories == expected_categories


class TestCategoryParsing:
    """Tests for category parsing logic."""

    @pytest.fixture
    def client(self):
        """Create a GeminiClient instance for testing."""
        with patch('backend.gemini_client.genai'):
            return GeminiClient(api_key="test-key")

    @pytest.mark.parametrize("category_text,expected", [
        ("Billing", Category.Billing),
        ("Refund", Category.Refund),
        ("Account_Access", Category.Account_Access),
        ("Cancellation", Category.Cancellation),
        ("General_Inquiry", Category.General_Inquiry),
    ])
    def test_parse_exact_category_match(self, client, category_text, expected):
        """Test parsing exact category matches."""
        result = client._parse_category(category_text)
        assert result == expected

    @pytest.mark.parametrize("category_text,expected", [
        ("billing", Category.Billing),
        ("BILLING", Category.Billing),
        ("Billing", Category.Billing),
        ("refund", Category.Refund),
        ("REFUND", Category.Refund),
        ("account_access", Category.Account_Access),
        ("ACCOUNT_ACCESS", Category.Account_Access),
        ("cancellation", Category.Cancellation),
        ("general_inquiry", Category.General_Inquiry),
    ])
    def test_parse_case_insensitive_match(self, client, category_text, expected):
        """Test case-insensitive category parsing."""
        result = client._parse_category(category_text)
        assert result == expected

    @pytest.mark.parametrize("category_text,expected", [
        ("Account Access", Category.Account_Access),
        ("General Inquiry", Category.General_Inquiry),
        ("Account-Access", Category.Account_Access),
        ("General-Inquiry", Category.General_Inquiry),
    ])
    def test_parse_category_with_spaces_or_dashes(self, client, category_text, expected):
        """Test parsing categories with spaces or dashes instead of underscores."""
        result = client._parse_category(category_text)
        assert result == expected

    @pytest.mark.parametrize("category_text,expected", [
        ("  Billing  ", Category.Billing),
        ("\nRefund\n", Category.Refund),
        ("  Account_Access  ", Category.Account_Access),
    ])
    def test_parse_category_with_whitespace(self, client, category_text, expected):
        """Test parsing categories with leading/trailing whitespace."""
        result = client._parse_category(category_text)
        assert result == expected

    @pytest.mark.parametrize("invalid_category", [
        "Invalid",
        "Unknown",
        "Support",
        "Technical",
        "",
        "123",
    ])
    def test_parse_invalid_category_raises_error(self, client, invalid_category):
        """Test that invalid categories raise ValueError."""
        with pytest.raises(ValueError, match="Invalid category"):
            client._parse_category(invalid_category)


class TestClassificationPrompt:
    """Tests for the classification prompt template."""

    def test_classification_prompt_contains_all_categories(self):
        """Verify the classification prompt includes all valid categories."""
        assert "Billing" in CLASSIFICATION_PROMPT
        assert "Refund" in CLASSIFICATION_PROMPT
        assert "Account_Access" in CLASSIFICATION_PROMPT
        assert "Cancellation" in CLASSIFICATION_PROMPT
        assert "General_Inquiry" in CLASSIFICATION_PROMPT

    def test_classification_prompt_has_message_placeholder(self):
        """Verify the prompt has a placeholder for the user message."""
        assert "{user_message}" in CLASSIFICATION_PROMPT

    def test_classification_prompt_format(self):
        """Test that the prompt can be formatted with a message."""
        test_message = "I need help with my invoice"
        formatted = CLASSIFICATION_PROMPT.format(user_message=test_message)
        assert test_message in formatted

    def test_classification_prompt_contains_priority_rules(self):
        """Verify the prompt contains category priority information."""
        # Check that priority order is indicated (numbered list or explicit priority)
        assert "priority order" in CLASSIFICATION_PROMPT.lower() or "1." in CLASSIFICATION_PROMPT
        # Verify categories are listed in priority order
        cancellation_pos = CLASSIFICATION_PROMPT.find("CANCELLATION")
        refund_pos = CLASSIFICATION_PROMPT.find("REFUND")
        billing_pos = CLASSIFICATION_PROMPT.find("BILLING")
        account_pos = CLASSIFICATION_PROMPT.find("ACCOUNT_ACCESS")
        general_pos = CLASSIFICATION_PROMPT.find("GENERAL_INQUIRY")

        # Cancellation should come before Refund, which should come before Billing, etc.
        assert cancellation_pos < refund_pos < billing_pos < account_pos < general_pos

    def test_classification_prompt_instructs_single_category(self):
        """Verify the prompt instructs to return only one category."""
        assert "exactly ONE category" in CLASSIFICATION_PROMPT
        assert "ONLY the category name" in CLASSIFICATION_PROMPT


class TestSupportAgentPrompt:
    """Tests for the support agent system prompt."""

    def test_support_agent_prompt_mentions_billing_platform(self):
        """Verify the prompt mentions SaaS billing platform."""
        assert "billing" in SUPPORT_AGENT_PROMPT.lower()

    def test_support_agent_prompt_mentions_customer_support(self):
        """Verify the prompt mentions customer support role."""
        assert "customer support" in SUPPORT_AGENT_PROMPT.lower()

    def test_support_agent_prompt_mentions_saas(self):
        """Verify the prompt mentions SaaS."""
        assert "SaaS" in SUPPORT_AGENT_PROMPT


class TestClassifyTraceSafeFallback:
    """Tests for classification fallback logic (Requirement 2.6)."""

    @pytest.fixture
    def client(self):
        """Create a GeminiClient instance for testing."""
        with patch('backend.gemini_client.genai'):
            return GeminiClient(api_key="test-key")

    def test_fallback_on_timeout(self, client):
        """Test fallback to General_Inquiry on API timeout."""
        from google.api_core import exceptions as google_exceptions

        with patch.object(client, 'classify_trace') as mock_classify:
            mock_classify.side_effect = google_exceptions.DeadlineExceeded("Timeout")

            result = client.classify_trace_safe("Test message")

            assert result == Category.General_Inquiry
            mock_classify.assert_called_once()

    def test_fallback_on_rate_limit(self, client):
        """Test fallback to General_Inquiry on API rate limit."""
        from google.api_core import exceptions as google_exceptions

        with patch.object(client, 'classify_trace') as mock_classify:
            mock_classify.side_effect = google_exceptions.ResourceExhausted("Rate limited")

            result = client.classify_trace_safe("Test message")

            assert result == Category.General_Inquiry
            mock_classify.assert_called_once()

    def test_fallback_on_invalid_response(self, client):
        """Test fallback to General_Inquiry on invalid API response."""
        with patch.object(client, 'classify_trace') as mock_classify:
            mock_classify.side_effect = ValueError("Invalid category: Unknown")

            result = client.classify_trace_safe("Test message")

            assert result == Category.General_Inquiry
            mock_classify.assert_called_once()

    def test_fallback_on_network_failure(self, client):
        """Test fallback to General_Inquiry on network failure."""
        with patch.object(client, 'classify_trace') as mock_classify:
            mock_classify.side_effect = ConnectionError("Network unreachable")

            result = client.classify_trace_safe("Test message")

            assert result == Category.General_Inquiry
            mock_classify.assert_called_once()

    def test_fallback_on_generic_exception(self, client):
        """Test fallback to General_Inquiry on any generic exception."""
        with patch.object(client, 'classify_trace') as mock_classify:
            mock_classify.side_effect = Exception("Unexpected error")

            result = client.classify_trace_safe("Test message")

            assert result == Category.General_Inquiry
            mock_classify.assert_called_once()

    def test_successful_classification_returns_category(self, client):
        """Test that successful classification returns the correct category."""
        with patch.object(client, 'classify_trace') as mock_classify:
            mock_classify.return_value = Category.Billing

            result = client.classify_trace_safe("I have a billing question")

            assert result == Category.Billing
            mock_classify.assert_called_once_with(
                user_message="I have a billing question",
                max_retries=1,
                initial_backoff=1.0
            )

    def test_fallback_logs_error(self, client, caplog):
        """Test that fallback logs the error for debugging."""
        import logging

        with patch.object(client, 'classify_trace') as mock_classify:
            mock_classify.side_effect = ValueError("Invalid category: BadCategory")

            with caplog.at_level(logging.ERROR):
                result = client.classify_trace_safe("Test message")

            assert result == Category.General_Inquiry
            assert "Classification failed" in caplog.text
            assert "General_Inquiry" in caplog.text
            assert "BadCategory" in caplog.text

    def test_safe_method_passes_parameters(self, client):
        """Test that classify_trace_safe passes parameters to classify_trace."""
        with patch.object(client, 'classify_trace') as mock_classify:
            mock_classify.return_value = Category.Refund

            result = client.classify_trace_safe(
                user_message="I want a refund",
                max_retries=3,
                initial_backoff=2.0
            )

            assert result == Category.Refund
            mock_classify.assert_called_once_with(
                user_message="I want a refund",
                max_retries=3,
                initial_backoff=2.0
            )
