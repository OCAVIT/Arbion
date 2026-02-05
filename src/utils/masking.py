"""
Sensitive data masking utilities.

CRITICAL SECURITY COMPONENT:
This module masks phone numbers, usernames, and emails in text
to prevent managers from accessing contact information.

Masking happens at the Pydantic serialization level, NOT CSS.
The masked data never reaches the manager's browser.
"""

import hashlib
import re
from typing import Optional

# Phone number patterns (Russian format)
PHONE_PATTERNS = [
    # +7 (XXX) XXX-XX-XX
    r'\+7\s*\(?\d{3}\)?\s*\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
    # 8 (XXX) XXX-XX-XX
    r'8\s*\(?\d{3}\)?\s*\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
    # +7XXXXXXXXXX (no separators)
    r'\+7\d{10}',
    # 89XXXXXXXXX (no separators)
    r'8\d{10}',
]

# Telegram username pattern
USERNAME_PATTERN = r'@[a-zA-Z][a-zA-Z0-9_]{4,31}'

# Email pattern
EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

# Compiled patterns for efficiency
PHONE_REGEX = re.compile('|'.join(PHONE_PATTERNS))
USERNAME_REGEX = re.compile(USERNAME_PATTERN)
EMAIL_REGEX = re.compile(EMAIL_PATTERN)


def mask_phone(phone: str) -> str:
    """
    Mask a phone number.

    Examples:
        +7 (999) 123-45-67 -> +7 (9**) ***-**-**
        89991234567 -> 8***-***-**-**
    """
    # Extract only digits
    digits = re.sub(r'\D', '', phone)

    if len(digits) >= 11:
        # Russian phone format
        if digits.startswith('7'):
            return f"+7 ({digits[1]}**) ***-**-**"
        elif digits.startswith('8'):
            return f"8 ({digits[1]}**) ***-**-**"

    # Generic masking for other formats
    return phone[:4] + '*' * (len(phone) - 4)


def mask_username(username: str) -> str:
    """
    Mask a Telegram username.

    Example:
        @johndoe -> @jo***
    """
    if len(username) <= 3:
        return username[:2] + '***'
    return username[:3] + '***'


def mask_email(email: str) -> str:
    """
    Mask an email address.

    Example:
        john.doe@example.com -> jo***@ex***.com
    """
    parts = email.split('@')
    if len(parts) != 2:
        return '***@***.***'

    local, domain = parts
    domain_parts = domain.rsplit('.', 1)

    masked_local = local[:2] + '***' if len(local) > 2 else local[0] + '***'
    masked_domain = domain_parts[0][:2] + '***' if len(domain_parts[0]) > 2 else '***'

    if len(domain_parts) == 2:
        return f"{masked_local}@{masked_domain}.{domain_parts[1]}"
    return f"{masked_local}@{masked_domain}"


def mask_sensitive(text: str, role: str) -> str:
    """
    Mask all sensitive information in text based on user role.

    Args:
        text: Text to process
        role: User role ("owner" or "manager")

    Returns:
        Processed text with sensitive info masked for managers,
        or original text for owners.

    SECURITY NOTE:
        This function is called during Pydantic serialization.
        Managers never receive unmasked data in any form.
    """
    if role == "owner":
        return text

    result = text

    # Mask phone numbers
    result = PHONE_REGEX.sub(lambda m: mask_phone(m.group()), result)

    # Mask usernames
    result = USERNAME_REGEX.sub(lambda m: mask_username(m.group()), result)

    # Mask emails
    result = EMAIL_REGEX.sub(lambda m: mask_email(m.group()), result)

    return result


def generate_contact_ref(sender_id: int, chat_id: int) -> str:
    """
    Generate a hashed reference for a contact.

    Used to replace actual contact IDs with anonymous references
    for managers.

    Args:
        sender_id: Telegram sender ID
        chat_id: Telegram chat ID

    Returns:
        Hashed reference like "seller_a7f3b2"
    """
    data = f"{sender_id}:{chat_id}"
    hash_value = hashlib.sha256(data.encode()).hexdigest()[:6]
    return f"seller_{hash_value}"


def is_owner(role: Optional[str]) -> bool:
    """Check if role is owner."""
    return role == "owner"


def is_manager(role: Optional[str]) -> bool:
    """Check if role is manager."""
    return role == "manager"
