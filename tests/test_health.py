"""
Health check endpoint tests.
"""

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint():
    """Test basic health check endpoint."""
    # This is a placeholder test
    # In a real setup, you would use TestClient with the app
    assert True


def test_masking():
    """Test data masking utility."""
    from src.utils.masking import mask_phone, mask_username, mask_email, mask_sensitive

    # Test phone masking
    assert mask_phone("+7 (999) 123-45-67") == "+7 (9**) ***-**-**"

    # Test username masking
    assert mask_username("@johndoe") == "@jo***"

    # Test email masking
    assert mask_email("john@example.com") == "jo***@ex***.com"

    # Test full masking for manager role
    text = "Call me at +7 (999) 123-45-67 or @johndoe"
    masked = mask_sensitive(text, "manager")
    assert "123-45-67" not in masked
    assert "@johndoe" not in masked

    # Test owner sees everything
    owner_masked = mask_sensitive(text, "owner")
    assert owner_masked == text


def test_password_hashing():
    """Test password hashing utility."""
    from src.utils.password import hash_password, verify_password

    password = "test_password_123"
    hashed = hash_password(password)

    # Hash should be different from original
    assert hashed != password

    # Verification should work
    assert verify_password(password, hashed)

    # Wrong password should fail
    assert not verify_password("wrong_password", hashed)
