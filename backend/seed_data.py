"""
Seed data module for SupportLens backend.
Provides 20+ realistic seed traces for demonstration purposes.
"""

import uuid
from datetime import datetime, timedelta
from random import randint

from backend.models import Category, TraceDB


def get_seed_traces() -> list[TraceDB]:
    """
    Generate seed traces with realistic SaaS billing support scenarios.
    
    Returns:
        List of 25 TraceDB objects distributed across all five categories.
    """
    base_time = datetime.utcnow()
    traces = []
    
    # Billing traces (5)
    billing_data = [
        (
            "Why was I charged twice this month?",
            "I apologize for the confusion. Looking at your account, I can see there was a duplicate charge on the 15th. This appears to be a system error during our payment processing. I've initiated a refund for the duplicate charge, which should appear in your account within 3-5 business days. Is there anything else I can help you with?"
        ),
        (
            "How do I update my credit card information?",
            "You can update your payment method by going to Settings > Billing > Payment Methods. Click 'Add New Card' to enter your new credit card details, then set it as your default payment method. Your old card can be removed once the new one is verified. Let me know if you need any help navigating there!"
        ),
        (
            "Can you explain the charges on my latest invoice?",
            "Of course! Your latest invoice includes: $49.99 for your Pro plan subscription, $12.50 for additional storage (25GB overage), and $8.00 for API calls exceeding your plan limit. The total comes to $70.49. Would you like me to break down any of these charges further?"
        ),
        (
            "What payment methods do you accept?",
            "We accept all major credit cards (Visa, Mastercard, American Express, Discover), debit cards, and PayPal. For enterprise customers, we also offer invoice-based billing with NET 30 terms. Would you like to set up a different payment method for your account?"
        ),
        (
            "When is my next billing date?",
            "Your next billing date is on the 1st of next month. You're currently on the Pro plan at $49.99/month. You'll receive an email reminder 3 days before the charge. Would you like to make any changes to your subscription before then?"
        ),
    ]
    
    for i, (user_msg, bot_resp) in enumerate(billing_data):
        traces.append(TraceDB(
            id=str(uuid.uuid4()),
            user_message=user_msg,
            bot_response=bot_resp,
            category=Category.Billing,
            timestamp=base_time - timedelta(hours=i * 2),
            response_time_ms=randint(150, 450)
        ))
    
    # Refund traces (5)
    refund_data = [
        (
            "I want a refund for last month's subscription",
            "I understand you'd like a refund for last month. I can see your account was active during that period. Could you tell me more about why you're requesting a refund? If there was a service issue, I'd like to make sure we address that as well. Our refund policy allows for full refunds within 14 days of charge."
        ),
        (
            "The service didn't work as advertised, I need my money back",
            "I'm sorry to hear the service didn't meet your expectations. I'd like to understand what specific issues you encountered so we can improve. In the meantime, I've submitted a refund request for your last payment of $49.99. You should see this credited back within 5-7 business days."
        ),
        (
            "Can I get a partial refund for the days I didn't use?",
            "We offer prorated refunds for annual subscriptions when cancelled mid-term. For monthly plans, we don't typically offer partial refunds, but I can make an exception given your situation. I've calculated a prorated amount of $23.50 for the unused portion. Shall I process this refund?"
        ),
        (
            "I was charged after I thought I cancelled",
            "I apologize for this frustrating experience. Looking at your account history, I can see the cancellation request was submitted but didn't fully process due to a technical issue. I've immediately cancelled your subscription and initiated a full refund of $49.99. This will appear in your account within 3-5 business days."
        ),
        (
            "How long does it take to get a refund?",
            "Refunds typically take 5-7 business days to appear in your account, depending on your bank or credit card provider. Once I process the refund on our end, you'll receive a confirmation email with a reference number. Would you like me to initiate a refund for you today?"
        ),
    ]
    
    for i, (user_msg, bot_resp) in enumerate(refund_data):
        traces.append(TraceDB(
            id=str(uuid.uuid4()),
            user_message=user_msg,
            bot_response=bot_resp,
            category=Category.Refund,
            timestamp=base_time - timedelta(hours=10 + i * 2),
            response_time_ms=randint(200, 500)
        ))

    # Account Access traces (5)
    account_access_data = [
        (
            "I can't log into my account",
            "I'm sorry you're having trouble logging in. Let's troubleshoot this together. First, please try clearing your browser cache and cookies, then attempt to log in again. If that doesn't work, try the 'Forgot Password' link on the login page. If you're still having issues, I can manually send a password reset link to your registered email."
        ),
        (
            "My account is locked after too many failed attempts",
            "Your account has been temporarily locked for security after multiple failed login attempts. This lock will automatically lift in 30 minutes. If you need immediate access, I can verify your identity and unlock it now. Please confirm the last 4 digits of the phone number on your account."
        ),
        (
            "How do I reset my password?",
            "To reset your password, click the 'Forgot Password' link on the login page and enter your email address. You'll receive a reset link within a few minutes. The link expires after 24 hours for security. If you don't see the email, please check your spam folder. Would you like me to send a reset link now?"
        ),
        (
            "I'm having trouble with two-factor authentication",
            "I understand 2FA can sometimes be tricky. If you're not receiving the code, make sure your authenticator app's time is synced correctly. If you've lost access to your authenticator, I can help you reset 2FA after verifying your identity. Do you have access to your backup codes?"
        ),
        (
            "Someone else might have access to my account",
            "Account security is our top priority. I've immediately logged out all active sessions on your account. I recommend changing your password right away and enabling two-factor authentication if you haven't already. I can also provide a log of recent account activity for you to review. Would you like me to send that?"
        ),
    ]
    
    for i, (user_msg, bot_resp) in enumerate(account_access_data):
        traces.append(TraceDB(
            id=str(uuid.uuid4()),
            user_message=user_msg,
            bot_response=bot_resp,
            category=Category.Account_Access,
            timestamp=base_time - timedelta(hours=20 + i * 2),
            response_time_ms=randint(180, 420)
        ))
    
    # Cancellation traces (5)
    cancellation_data = [
        (
            "I want to cancel my subscription",
            "I'm sorry to hear you want to cancel. Before I process this, may I ask what's prompting your decision? We value your feedback and might be able to address any concerns. If you'd still like to proceed, I can cancel your subscription effective at the end of your current billing period."
        ),
        (
            "How do I downgrade my plan?",
            "You can downgrade your plan by going to Settings > Subscription > Change Plan. Select the plan you'd like to switch to, and the change will take effect at your next billing cycle. Note that some features may become unavailable on lower-tier plans. Would you like me to walk you through the differences between plans?"
        ),
        (
            "I need to close my account completely",
            "I understand you want to close your account. Before I proceed, please note that this action is permanent and all your data will be deleted after 30 days. If you have any active subscriptions, they'll be cancelled immediately. Would you like to export your data before I close the account?"
        ),
        (
            "Can I pause my subscription instead of cancelling?",
            "Great question! Yes, we offer a pause feature that lets you suspend your subscription for up to 3 months. During this time, you won't be charged, and your data will be preserved. You can resume anytime. Would you like me to pause your subscription instead of cancelling?"
        ),
        (
            "What happens to my data if I cancel?",
            "When you cancel, your data remains accessible until the end of your current billing period. After that, your account enters a 30-day grace period where data is preserved but inaccessible. After 30 days, all data is permanently deleted. You can export your data anytime before the final deletion."
        ),
    ]
    
    for i, (user_msg, bot_resp) in enumerate(cancellation_data):
        traces.append(TraceDB(
            id=str(uuid.uuid4()),
            user_message=user_msg,
            bot_response=bot_resp,
            category=Category.Cancellation,
            timestamp=base_time - timedelta(hours=30 + i * 2),
            response_time_ms=randint(160, 380)
        ))
    
    # General Inquiry traces (5)
    general_inquiry_data = [
        (
            "What features are included in the Pro plan?",
            "The Pro plan includes: unlimited projects, 100GB storage, priority support, advanced analytics, API access with 10,000 calls/month, team collaboration for up to 10 members, and custom integrations. You also get access to our beta features program. Would you like more details on any specific feature?"
        ),
        (
            "How does your pricing work?",
            "We offer three tiers: Starter at $19/month for individuals, Pro at $49/month for small teams, and Enterprise with custom pricing for larger organizations. All plans are billed monthly or annually (with 20% discount for annual). Each tier includes different feature sets and usage limits. Which plan interests you most?"
        ),
        (
            "Do you have an API I can use?",
            "Yes! We have a comprehensive REST API available on Pro and Enterprise plans. The API allows you to programmatically access all platform features, including data export, user management, and automation. Documentation is available at docs.example.com/api. Would you like me to generate an API key for you?"
        ),
        (
            "Can I integrate with Slack?",
            "Absolutely! We have a native Slack integration that allows you to receive notifications, create items, and run commands directly from Slack. You can set it up in Settings > Integrations > Slack. The integration supports both public and private channels. Need help configuring it?"
        ),
        (
            "What's the difference between your plans?",
            "The main differences are: Starter is for individuals with basic features and 10GB storage. Pro adds team collaboration, 100GB storage, API access, and priority support. Enterprise includes unlimited everything, SSO, dedicated support, and custom SLAs. I'd recommend Pro for most small to medium teams. What's your team size?"
        ),
    ]
    
    for i, (user_msg, bot_resp) in enumerate(general_inquiry_data):
        traces.append(TraceDB(
            id=str(uuid.uuid4()),
            user_message=user_msg,
            bot_response=bot_resp,
            category=Category.General_Inquiry,
            timestamp=base_time - timedelta(hours=40 + i * 2),
            response_time_ms=randint(140, 350)
        ))
    
    return traces


def load_seed_data(db_session) -> int:
    """
    Load seed data into the database if it's empty.
    
    Args:
        db_session: SQLAlchemy database session
        
    Returns:
        Number of seed traces loaded (0 if database already had data)
    """
    # Check if database already has traces
    existing_count = db_session.query(TraceDB).count()
    
    if existing_count > 0:
        return 0
    
    # Load seed traces
    seed_traces = get_seed_traces()
    
    for trace in seed_traces:
        db_session.add(trace)
    
    db_session.commit()
    
    return len(seed_traces)
