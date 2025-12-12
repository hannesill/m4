"""
OAuth2 Authentication Module for M4 MCP Server
Provides secure authentication using OAuth2 with JWT tokens.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from m4.config import logger


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class TokenValidationError(Exception):
    """Raised when token validation fails."""

    pass


class OAuth2Config:
    """OAuth2 configuration management."""

    def __init__(self):
        self.enabled = os.getenv("M4_OAUTH2_ENABLED", "false").lower() == "true"

        # OAuth2 Provider Configuration
        self.issuer_url = os.getenv("M4_OAUTH2_ISSUER_URL", "")
        self.client_id = os.getenv("M4_OAUTH2_CLIENT_ID", "")
        self.client_secret = os.getenv("M4_OAUTH2_CLIENT_SECRET", "")
        self.audience = os.getenv("M4_OAUTH2_AUDIENCE", "")

        # Scopes required for access
        self.required_scopes = self._parse_scopes(
            os.getenv("M4_OAUTH2_REQUIRED_SCOPES", "read:mimic-data")
        )

        # Token validation settings
        self.validate_exp = (
            os.getenv("M4_OAUTH2_VALIDATE_EXP", "true").lower() == "true"
        )
        self.validate_aud = (
            os.getenv("M4_OAUTH2_VALIDATE_AUD", "true").lower() == "true"
        )
        self.validate_iss = (
            os.getenv("M4_OAUTH2_VALIDATE_ISS", "true").lower() == "true"
        )

        # JWKS settings
        self.jwks_url = os.getenv("M4_OAUTH2_JWKS_URL", "")
        self.jwks_cache_ttl = int(
            os.getenv("M4_OAUTH2_JWKS_CACHE_TTL", "3600")
        )  # 1 hour

        # Rate limiting
        self.rate_limit_enabled = (
            os.getenv("M4_OAUTH2_RATE_LIMIT_ENABLED", "true").lower() == "true"
        )
        self.rate_limit_requests = int(
            os.getenv("M4_OAUTH2_RATE_LIMIT_REQUESTS", "100")
        )
        self.rate_limit_window = int(
            os.getenv("M4_OAUTH2_RATE_LIMIT_WINDOW", "3600")
        )  # 1 hour

        # Cache for JWKS and validation
        self._jwks_cache = {}
        self._jwks_cache_time = 0
        self._rate_limit_cache = {}

        if self.enabled:
            self._validate_config()

    def _parse_scopes(self, scopes_str: str) -> set[str]:
        """Parse comma-separated scopes string."""
        return set(scope.strip() for scope in scopes_str.split(",") if scope.strip())

    def _validate_config(self):
        """Validate OAuth2 configuration."""
        if not self.issuer_url:
            raise ValueError("M4_OAUTH2_ISSUER_URL is required when OAuth2 is enabled")

        if not self.audience:
            raise ValueError("M4_OAUTH2_AUDIENCE is required when OAuth2 is enabled")

        if not self.jwks_url:
            # Auto-discover JWKS URL from issuer
            # Note: Using f-string instead of urljoin to preserve path components
            self.jwks_url = f"{self.issuer_url.rstrip('/')}/.well-known/jwks.json"

        logger.info(f"OAuth2 authentication enabled with issuer: {self.issuer_url}")


class OAuth2Validator:
    """OAuth2 token validator."""

    # Maximum number of users to track in rate limit cache (LRU eviction)
    MAX_RATE_LIMIT_CACHE_SIZE = 10000

    def __init__(self, config: OAuth2Config):
        self.config = config
        self.http_client = httpx.Client(timeout=30.0)
        self._jwks_cache: dict[str, Any] = {}

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self.http_client:
            self.http_client.close()

    def __del__(self) -> None:
        """Destructor to ensure HTTP client is closed."""
        self.close()

    def __enter__(self) -> "OAuth2Validator":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def validate_token(self, token: str) -> dict[str, Any]:
        """
        Validate an OAuth2 access token.

        Args:
            token: The access token to validate

        Returns:
            Decoded token claims

        Raises:
            TokenValidationError: If token is invalid
        """
        try:
            # Get JWKS for token validation
            jwks = self._get_jwks()

            # Decode token header to get key ID
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            if not kid:
                raise TokenValidationError("Token missing key ID (kid)")

            # Find the appropriate key
            key = self._find_key(jwks, kid)
            if not key:
                raise TokenValidationError(f"No key found for kid: {kid}")

            # Convert JWK to PEM format for verification
            public_key = self._jwk_to_pem(key)

            # Validate token
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256", "ES256"],
                audience=self.config.audience if self.config.validate_aud else None,
                issuer=self.config.issuer_url if self.config.validate_iss else None,
                options={
                    "verify_exp": self.config.validate_exp,
                    "verify_aud": self.config.validate_aud,
                    "verify_iss": self.config.validate_iss,
                },
            )

            # Validate scopes
            self._validate_scopes(payload)

            # Check rate limits
            if self.config.rate_limit_enabled:
                self._check_rate_limit(payload)

            return payload

        except jwt.ExpiredSignatureError:
            raise TokenValidationError("Token has expired")
        except jwt.InvalidAudienceError:
            raise TokenValidationError("Invalid token audience")
        except jwt.InvalidIssuerError:
            raise TokenValidationError("Invalid token issuer")
        except jwt.InvalidTokenError as e:
            raise TokenValidationError(f"Invalid token: {e}")
        except Exception as e:
            raise TokenValidationError(f"Token validation failed: {e}")

    def _get_jwks(self) -> dict[str, Any]:
        """Get JWKS (JSON Web Key Set) from the OAuth2 provider."""
        current_time = time.time()

        # Check cache
        if (
            self._jwks_cache
            and current_time - self.config._jwks_cache_time < self.config.jwks_cache_ttl
        ):
            return self.config._jwks_cache

        # Fetch JWKS
        try:
            response = self.http_client.get(self.config.jwks_url)
            response.raise_for_status()
            jwks = response.json()

            # Cache the result
            self.config._jwks_cache = jwks
            self.config._jwks_cache_time = current_time

            return jwks

        except Exception as e:
            raise TokenValidationError(f"Failed to fetch JWKS: {e}")

    def _find_key(self, jwks: dict[str, Any], kid: str) -> dict[str, Any] | None:
        """Find a key in JWKS by key ID."""
        keys = jwks.get("keys", [])
        for key in keys:
            if key.get("kid") == kid:
                return key
        return None

    def _jwk_to_pem(self, jwk: dict[str, Any]) -> bytes:
        """Convert JWK to PEM format."""
        try:
            # Use python-jose for JWK to PEM conversion
            from jose.utils import base64url_decode

            if jwk.get("kty") == "RSA":
                # RSA key
                n = base64url_decode(jwk["n"])
                e = base64url_decode(jwk["e"])

                # Create RSA public key
                public_numbers = rsa.RSAPublicNumbers(
                    int.from_bytes(e, byteorder="big"),
                    int.from_bytes(n, byteorder="big"),
                )
                public_key = public_numbers.public_key()

                # Convert to PEM
                pem = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                return pem
            else:
                raise TokenValidationError(f"Unsupported key type: {jwk.get('kty')}")

        except Exception as e:
            raise TokenValidationError(f"Failed to convert JWK to PEM: {e}")

    def _validate_scopes(self, payload: dict[str, Any]):
        """Validate that token has required scopes."""
        if not self.config.required_scopes:
            return

        token_scopes = set()

        # Check different possible scope claims
        scope_claim = payload.get("scope", "")
        if isinstance(scope_claim, str):
            token_scopes = set(scope_claim.split())
        elif isinstance(scope_claim, list):
            token_scopes = set(scope_claim)

        # Also check 'scp' claim (some providers use this)
        scp_claim = payload.get("scp", [])
        if isinstance(scp_claim, list):
            token_scopes.update(scp_claim)

        # Check if required scopes are present
        missing_scopes = self.config.required_scopes - token_scopes
        if missing_scopes:
            raise TokenValidationError(f"Missing required scopes: {missing_scopes}")

    def _check_rate_limit(self, payload: dict[str, Any]) -> None:
        """Check rate limits for the user.

        Includes periodic cleanup of all expired entries and LRU eviction
        when cache exceeds MAX_RATE_LIMIT_CACHE_SIZE to prevent memory leaks.
        """
        user_id = payload.get("sub", "unknown")
        current_time = time.time()
        window_start = current_time - self.config.rate_limit_window

        # Periodic cleanup: every 100 requests, clean all expired entries
        # This prevents memory leaks from users who never return
        cache = self.config._rate_limit_cache
        total_entries = sum(len(v) for v in cache.values())
        if total_entries > 0 and total_entries % 100 == 0:
            self._cleanup_expired_rate_limits(window_start)

        # Clean old entries for this specific user
        user_requests = cache.get(user_id, [])
        user_requests = [
            req_time for req_time in user_requests if req_time > window_start
        ]

        # Check if limit exceeded
        if len(user_requests) >= self.config.rate_limit_requests:
            raise TokenValidationError("Rate limit exceeded")

        # Add current request
        user_requests.append(current_time)
        cache[user_id] = user_requests

        # LRU eviction: if cache is too large, remove oldest entries
        if len(cache) > self.MAX_RATE_LIMIT_CACHE_SIZE:
            self._evict_oldest_rate_limit_entries()

    def _cleanup_expired_rate_limits(self, window_start: float) -> None:
        """Remove all expired entries from the rate limit cache.

        This prevents memory leaks from users who make requests once
        and never return.

        Args:
            window_start: Timestamp before which entries are considered expired
        """
        cache = self.config._rate_limit_cache
        users_to_remove = []

        for user_id, requests in cache.items():
            # Filter to only valid requests
            valid_requests = [t for t in requests if t > window_start]
            if valid_requests:
                cache[user_id] = valid_requests
            else:
                users_to_remove.append(user_id)

        # Remove users with no valid requests
        for user_id in users_to_remove:
            del cache[user_id]

    def _evict_oldest_rate_limit_entries(self) -> None:
        """Evict oldest entries when cache exceeds maximum size.

        Uses LRU-like eviction based on the most recent request time
        for each user.
        """
        cache = self.config._rate_limit_cache
        if len(cache) <= self.MAX_RATE_LIMIT_CACHE_SIZE:
            return

        # Sort users by their most recent request time (oldest first)
        users_by_recency = sorted(
            cache.keys(),
            key=lambda uid: max(cache[uid]) if cache[uid] else 0,
        )

        # Remove oldest 10% of entries
        num_to_remove = max(1, len(cache) // 10)
        for user_id in users_by_recency[:num_to_remove]:
            del cache[user_id]


# Global instances
_oauth2_config = None
_oauth2_validator = None


def init_oauth2():
    """Initialize OAuth2 authentication."""
    global _oauth2_config, _oauth2_validator

    _oauth2_config = OAuth2Config()
    if _oauth2_config.enabled:
        _oauth2_validator = OAuth2Validator(_oauth2_config)
        logger.info("OAuth2 authentication initialized")
    else:
        logger.info("OAuth2 authentication disabled")


def require_oauth2(func):
    """Decorator to require OAuth2 authentication for MCP tools."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if not _oauth2_config or not _oauth2_config.enabled:
            # If OAuth2 is disabled, allow access
            return func(*args, **kwargs)

        if not _oauth2_validator:
            logger.error("OAuth2 is enabled but validator is not initialized")
            return "Error: Authentication system not properly configured"

        # Extract token from environment (in real implementation, this would come from request headers)
        token = os.getenv("M4_OAUTH2_TOKEN", "")
        if not token:
            return "Error: Missing OAuth2 access token"

        # Remove "Bearer " prefix if present
        if token.startswith("Bearer "):
            token = token[7:]

        try:
            # Basic token structure check (JWT has 3 parts separated by dots)
            if not token or len(token.split(".")) != 3:
                return "Error: Invalid token format"

            # Validate the token using the OAuth2 validator (synchronous)
            _oauth2_validator.validate_token(token)

            return func(*args, **kwargs)

        except TokenValidationError as e:
            logger.warning(f"OAuth2 token validation failed: {e}")
            return f"Error: {e}"
        except Exception as e:
            logger.error(f"OAuth2 authentication error: {e}")
            return "Error: Authentication system error"

    return wrapper


def get_oauth2_config() -> OAuth2Config | None:
    """Get the current OAuth2 configuration."""
    return _oauth2_config


def is_oauth2_enabled() -> bool:
    """Check if OAuth2 authentication is enabled."""
    return _oauth2_config is not None and _oauth2_config.enabled


def generate_test_token(
    issuer: str = "https://test-issuer.example.com",
    audience: str = "m4-api",
    subject: str = "test-user",
    scopes: list[str] | None = None,
    expires_in: int = 3600,
) -> str:
    """
    Generate a test JWT token for development/testing.

    WARNING: This should only be used for testing!
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
