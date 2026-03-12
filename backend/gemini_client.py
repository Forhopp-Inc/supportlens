"""
Gemini API client for SupportLens backend.
Provides chatbot response generation and trace classification.
"""

import logging
import re
import time
from typing import Optional

from google import genai
from google.genai import types
from google.api_core import exceptions as google_exceptions

from backend.config import get_settings
from backend.models import Category


logger = logging.getLogger(__name__)


# Classification prompt template - optimized for accuracy
CLASSIFICATION_PROMPT = """Classify this customer support message into exactly ONE category.

CATEGORIES (in priority order - use first matching):

1. CANCELLATION - Ending service:
   Keywords: cancel, close account, stop subscription, downgrade, end service, terminate
   Examples: "cancel my subscription", "close my account", "stop billing me"

2. REFUND - Money back requests:
   Keywords: refund, money back, reimburse, dispute charge, overcharged
   Examples: "I want a refund", "give me my money back", "I was charged twice"

3. BILLING - Payment/pricing questions (NOT refund requests):
   Keywords: invoice, payment, charge, cost, price, credit card, billing date
   Examples: "how much does it cost?", "update my card", "when am I billed?"

4. ACCOUNT_ACCESS - Login/access issues:
   Keywords: login, password, locked out, can't access, 2FA, authentication
   Examples: "I can't log in", "reset my password", "account locked"

5. GENERAL_INQUIRY - Everything else:
   Features, how-to, greetings, general questions
   Examples: "hi", "what features do you have?", "how does this work?"

MESSAGE: "{user_message}"

Reply with ONLY the category name: Billing, Refund, Account_Access, Cancellation, or General_Inquiry"""


# Support agent system prompt
SUPPORT_AGENT_PROMPT = """You are a friendly customer support agent for SupportLens, a SaaS billing platform.

GUIDELINES:
- Be warm, helpful, and professional
- Keep responses concise (2-4 sentences for simple questions)
- Ask clarifying questions when needed
- Offer actionable next steps
- Never make up specific account details, prices, or dates

FORMATTING RULES:
- Use plain text only - NO markdown formatting
- NO asterisks (*) for bold or italic
- For lists, use dashes (-) or numbers
- Keep paragraphs short and readable

EXAMPLE GOOD RESPONSE:
"Thanks for reaching out! To update your payment method, go to Settings then Billing then Payment Methods. You can add a new card there and set it as default. Let me know if you need any help!"

EXAMPLE BAD RESPONSE (don't do this):
"Thanks for reaching out! **To update your payment method**, go to *Settings* > *Billing*..."
"""


def clean_markdown(text: str) -> str:
    """Remove markdown formatting from text."""
    # Remove bold/italic markers
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # Clean up bullet points with asterisks
    text = re.sub(r'^\s*\*\s+', '- ', text, flags=re.MULTILINE)
    return text


class GeminiClient:
    """Client for interacting with the Gemini API."""
    
    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = "gemini-2.0-flash"
        self._valid_categories = {cat.value for cat in Category}
    
    def generate_response(
        self,
        message: str,
        history: list[dict] | None = None,
        max_retries: int = 1,
        initial_backoff: float = 1.0
    ) -> str:
        """Generate a chatbot response for a customer support message.
        
        Args:
            message: The current user message
            history: Optional conversation history as list of {"role": "user"|"assistant", "content": str}
            max_retries: Number of retry attempts
            initial_backoff: Initial backoff time in seconds
        """
        attempt = 0
        last_exception = None
        backoff = initial_backoff
        
        # Build contents with conversation history
        contents = []
        if history:
            for msg in history:
                role = "user" if msg.get("role") == "user" else "model"
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part(text=msg.get("content", ""))]
                ))
        
        # Add current message
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=message)]
        ))
        
        while attempt <= max_retries:
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=1024,
                        system_instruction=SUPPORT_AGENT_PROMPT
                    )
                )
                
                if response.text:
                    return clean_markdown(response.text.strip())
                
                raise ValueError("Empty response from Gemini API")
                
            except google_exceptions.DeadlineExceeded as e:
                logger.warning(
                    "Gemini API timeout",
                    extra={
                        "type": "llm_error",
                        "error_type": "timeout",
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "message_length": len(message),
                        "history_length": len(history) if history else 0
                    }
                )
                last_exception = e
                attempt += 1
                
            except google_exceptions.ResourceExhausted as e:
                logger.warning(
                    "Gemini API rate limited",
                    extra={
                        "type": "llm_error",
                        "error_type": "rate_limit",
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "backoff_seconds": backoff
                    }
                )
                last_exception = e
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                attempt += 1
                
            except Exception as e:
                logger.error(
                    "Gemini API error",
                    extra={
                        "type": "llm_error",
                        "error_type": type(e).__name__,
                        "attempt": attempt + 1,
                        "error_message": str(e),
                        "message_length": len(message)
                    }
                )
                last_exception = e
                attempt += 1
        
        raise last_exception or Exception("Failed to generate response")
    
    def classify_trace(
        self,
        user_message: str,
        max_retries: int = 1,
        initial_backoff: float = 1.0
    ) -> Category:
        """Classify a support message into a category using the Gemini API."""
        prompt = CLASSIFICATION_PROMPT.format(user_message=user_message)
        
        attempt = 0
        last_exception = None
        backoff = initial_backoff
        
        while attempt <= max_retries:
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.0,
                        max_output_tokens=20,
                    )
                )
                
                if response.text:
                    category_text = response.text.strip()
                    category = self._parse_category(category_text, user_message)
                    
                    # Log successful classification
                    logger.debug(
                        "Classification successful",
                        extra={
                            "type": "classification_success",
                            "category": category.value,
                            "raw_response": category_text,
                            "user_message_length": len(user_message)
                        }
                    )
                    return category
                
                raise ValueError("Empty response from Gemini API")
                
            except google_exceptions.DeadlineExceeded as e:
                logger.warning(
                    "Classification timeout",
                    extra={
                        "type": "classification_error",
                        "error_type": "timeout",
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "user_message_preview": user_message[:100]
                    }
                )
                last_exception = e
                attempt += 1
                
            except google_exceptions.ResourceExhausted as e:
                logger.warning(
                    "Classification rate limited",
                    extra={
                        "type": "classification_error",
                        "error_type": "rate_limit",
                        "attempt": attempt + 1,
                        "max_retries": max_retries,
                        "backoff_seconds": backoff
                    }
                )
                last_exception = e
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff *= 2
                attempt += 1
                
            except ValueError as e:
                logger.warning(
                    "Invalid classification response",
                    extra={
                        "type": "classification_error",
                        "error_type": "invalid_response",
                        "attempt": attempt + 1,
                        "error_message": str(e),
                        "user_message_preview": user_message[:100]
                    }
                )
                last_exception = e
                attempt += 1
                
            except Exception as e:
                logger.error(
                    "Classification failed",
                    extra={
                        "type": "classification_error",
                        "error_type": type(e).__name__,
                        "attempt": attempt + 1,
                        "error_message": str(e),
                        "user_message_preview": user_message[:100]
                    }
                )
                last_exception = e
                attempt += 1
        
        raise last_exception or Exception("Failed to classify trace")
    
    def classify_trace_safe(
        self,
        user_message: str,
        max_retries: int = 1,
        initial_backoff: float = 1.0
    ) -> Category:
        """Safely classify with fallback to General_Inquiry on any failure."""
        try:
            return self.classify_trace(
                user_message=user_message,
                max_retries=max_retries,
                initial_backoff=initial_backoff
            )
        except Exception as e:
            logger.error(f"Classification failed, fallback to General_Inquiry: {e}")
            return Category.General_Inquiry

    def _parse_category(self, category_text: str, user_message: str = "") -> Category:
        """Parse and validate a category string from the API response."""
        cleaned = category_text.strip()
        
        # Direct match
        if cleaned in self._valid_categories:
            return Category(cleaned)
        
        # Case-insensitive match
        for valid_cat in self._valid_categories:
            if cleaned.lower() == valid_cat.lower():
                return Category(valid_cat)
        
        # Handle variations (e.g., "Account Access" vs "Account_Access")
        normalized = cleaned.replace(" ", "_").replace("-", "_")
        if normalized in self._valid_categories:
            return Category(normalized)
        
        for valid_cat in self._valid_categories:
            if normalized.lower() == valid_cat.lower():
                return Category(valid_cat)
        
        # Log unexpected classification with full context for debugging
        logger.warning(
            "Unexpected LLM classification response",
            extra={
                "type": "classification_unexpected",
                "raw_response": category_text,
                "cleaned_response": cleaned,
                "normalized_response": normalized,
                "valid_categories": list(self._valid_categories),
                "user_message_preview": user_message[:100] if user_message else ""
            }
        )
        
        raise ValueError(f"Invalid category: {category_text}")
