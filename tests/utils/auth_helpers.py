"""Authentication test helpers.

This module contains utilities for generating test tokens and other
authentication-related test helpers. These functions should ONLY be
used in test code, never in production.
"""

from datetime import datetime, timedelta, timezone

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_test_token(
    issuer: str = "https://test-issuer.example.com",
    audience: str = "m4-api",
    subject: str = "test-user",
    scopes: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    """Generate a test JWT token for development/testing.

    This function creates a self-signed JWT token for testing purposes.
    The token is signed with a randomly generated RSA key, so it cannot
    be validated against real OAuth2 providers.

    Args:
        issuer: The token issuer URL
        audience: The intended audience for the token
        subject: The subject (user ID) for the token
        scopes: List of scopes to include in the token
        expires_in: Token expiration time in seconds (default: 1 hour)

    Returns:
        A signed JWT token string

    Example:
        token = generate_test_token(
            subject="test-user-123",
            scopes=["read:mimic-data", "write:mimic-data"],
        )

    Warning:
        This function is for TESTING ONLY. Never use generated tokens
        in production environments.
    """
    if scopes is None:
        scopes = ["read:mimic-data"]

    now = datetime.now(timezone.utc)
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "scope": " ".join(scopes),
        "email": f"{subject}@example.com",
    }

    # Generate a test key (DO NOT use in production)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Sign the token
    token = jwt.encode(claims, private_pem, algorithm="RS256")

    return token