"""
Auth layer: Authentication and Authorization (M6.11).

Layer: Application/Core — depends inward on domain/ only.

Provides:
- API Key authentication (simple, stateless)
- JWT authentication (token-based, with expiration)
- Role-based authorization (admin, user, service roles)
- Password hashing (bcrypt directly)

This is a foundation for production authentication. It provides the
mechanisms (token creation, validation, role checking) that FastAPI
dependencies can use to protect endpoints.

Design notes
------------
- API Keys are stored in-memory (hashed). A future milestone can
  persist them to a database.
- JWT tokens use HS256 with a secret key from configuration.
- Roles are simple strings: "admin", "user", "service".
- The auth module does NOT define FastAPI routes — it provides the
  building blocks (functions, classes) that routers use via Depends.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

import bcrypt

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """User roles for authorization."""

    ADMIN = "admin"
    USER = "user"
    SERVICE = "service"


# Role hierarchy: admin can do everything user can, etc.
_ROLE_HIERARCHY: dict[Role, set[Role]] = {
    Role.ADMIN: {Role.ADMIN, Role.USER, Role.SERVICE},
    Role.USER: {Role.USER},
    Role.SERVICE: {Role.SERVICE},
}


@dataclass
class User:
    """A user in the system.

    Attributes:
        user_id: unique identifier.
        username: human-readable name.
        hashed_password: bcrypt-hashed password.
        roles: list of roles assigned to the user.
        enabled: whether the user account is active.
        metadata: arbitrary additional metadata.
    """

    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    hashed_password: str = ""
    roles: list[Role] = field(default_factory=lambda: [Role.USER])
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: Role) -> bool:
        """Check if the user has the given role (or a higher role)."""
        for user_role in self.roles:
            if role in _ROLE_HIERARCHY.get(user_role, set()):
                return True
        return False


@dataclass
class APIKey:
    """An API key for authentication.

    Attributes:
        key_id: unique identifier.
        key_hash: SHA-256 hash of the raw key (the raw key is only
            shown once, at creation time).
        user_id: the user this key belongs to.
        name: human-readable name for the key.
        scopes: list of scopes/permissions.
        enabled: whether the key is active.
        created_at: ISO-8601 creation timestamp.
        expires_at: optional ISO-8601 expiration timestamp.
    """

    key_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    key_hash: str = ""
    user_id: str = ""
    name: str = ""
    scopes: list[str] = field(default_factory=list)
    enabled: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    expires_at: str = ""


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# API Key utilities
# ---------------------------------------------------------------------------


def generate_api_key() -> str:
    """Generate a new random API key.

    Returns a URL-safe base64-encoded 32-byte random string.
    """
    return secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256.

    API keys are hashed (not encrypted) so they can be verified
    without storing the raw key.
    """
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key: str, key_hash: str) -> bool:
    """Verify an API key against its hash.

    Uses constant-time comparison to prevent timing attacks.
    """
    return hmac.compare_digest(hash_api_key(key), key_hash)


# ---------------------------------------------------------------------------
# JWT utilities
# ---------------------------------------------------------------------------


class JWTHandler:
    """Create and verify JWT tokens.

    Parameters
    ----------
    secret_key:
        The secret key used to sign tokens. Should be a long,
        random string stored in configuration.
    algorithm:
        The JWT algorithm. Defaults to HS256.
    access_token_expire_minutes:
        How long access tokens are valid. Defaults to 30 minutes.
    """

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
    ) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._expire_minutes = access_token_expire_minutes

    def create_access_token(
        self,
        user_id: str,
        username: str,
        roles: list[Role],
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a JWT access token.

        Parameters
        ----------
        user_id:
            The user's unique identifier.
        username:
            The user's name (included in the token).
        roles:
            The user's roles (included for authorization).
        expires_delta:
            Custom expiration time. Defaults to the configured
            access_token_expire_minutes.
        """
        from jose import jwt

        now = datetime.now(timezone.utc)
        expire = now + (
            expires_delta
            or timedelta(minutes=self._expire_minutes)
        )
        payload = {
            "sub": user_id,
            "username": username,
            "roles": [r.value for r in roles],
            "iat": now,
            "exp": expire,
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def verify_access_token(self, token: str) -> Optional[dict[str, Any]]:
        """Verify a JWT access token and return its payload.

        Returns None if the token is invalid or expired.
        """
        from jose import JWTError, jwt

        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
            return payload
        except JWTError:
            return None


# ---------------------------------------------------------------------------
# User store (in-memory)
# ---------------------------------------------------------------------------


class UserStore:
    """In-memory user store for authentication.

    Stores users and API keys. A future milestone can replace this
    with a database-backed store.
    """

    def __init__(self) -> None:
        self._users: dict[str, User] = {}  # user_id -> User
        self._users_by_username: dict[str, User] = {}  # username -> User
        self._api_keys: dict[str, APIKey] = {}  # key_hash -> APIKey

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def create_user(
        self,
        username: str,
        password: str,
        roles: Optional[list[Role]] = None,
    ) -> User:
        """Create a new user with a hashed password.

        Raises
        ------
        ValueError:
            If a user with the same username already exists.
        """
        if username in self._users_by_username:
            raise ValueError(f"User '{username}' already exists")

        user = User(
            username=username,
            hashed_password=hash_password(password),
            roles=roles or [Role.USER],
        )
        self._users[user.user_id] = user
        self._users_by_username[user.username] = user
        logger.info("Created user: %s", username)
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        """Return a user by ID, or None."""
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Return a user by username, or None."""
        return self._users_by_username.get(username)

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user with username and password.

        Returns the user if authentication succeeds, None otherwise.
        """
        user = self._users_by_username.get(username)
        if user is None:
            return None
        if not user.enabled:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    def delete_user(self, user_id: str) -> bool:
        """Delete a user. Returns True if the user existed."""
        user = self._users.pop(user_id, None)
        if user is None:
            return False
        self._users_by_username.pop(user.username, None)
        return True

    # ------------------------------------------------------------------
    # API Keys
    # ------------------------------------------------------------------

    def create_api_key(
        self,
        user_id: str,
        name: str = "",
        scopes: Optional[list[str]] = None,
        expires_at: str = "",
    ) -> tuple[str, APIKey]:
        """Create a new API key for a user.

        Returns (raw_key, APIKey). The raw_key is shown only once.
        """
        raw_key = generate_api_key()
        key_hash = hash_api_key(raw_key)
        api_key = APIKey(
            key_hash=key_hash,
            user_id=user_id,
            name=name,
            scopes=list(scopes or []),
            expires_at=expires_at,
        )
        self._api_keys[key_hash] = api_key
        logger.info("Created API key for user: %s", user_id)
        return raw_key, api_key

    def verify_api_key(self, raw_key: str) -> Optional[APIKey]:
        """Verify an API key and return its metadata.

        Returns None if the key is invalid, disabled, or expired.
        """
        key_hash = hash_api_key(raw_key)
        api_key = self._api_keys.get(key_hash)
        if api_key is None:
            return None
        if not api_key.enabled:
            return None
        # Check expiration.
        if api_key.expires_at:
            try:
                exp = datetime.fromisoformat(api_key.expires_at)
                if datetime.now(timezone.utc) > exp:
                    return None
            except ValueError:
                pass
        return api_key

    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke (disable) an API key. Returns True if it existed."""
        for api_key in self._api_keys.values():
            if api_key.key_id == key_id:
                api_key.enabled = False
                return True
        return False

    def list_api_keys(self, user_id: str = "") -> list[APIKey]:
        """List API keys, optionally filtered by user_id."""
        keys = list(self._api_keys.values())
        if user_id:
            keys = [k for k in keys if k.user_id == user_id]
        return keys

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all users and API keys. Useful for testing."""
        self._users.clear()
        self._users_by_username.clear()
        self._api_keys.clear()
