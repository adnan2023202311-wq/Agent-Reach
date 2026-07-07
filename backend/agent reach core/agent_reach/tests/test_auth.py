"""Unit tests for auth module (M6.11)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from auth import (
    APIKey,
    JWTHandler,
    Role,
    User,
    UserStore,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)


# ---------------------------------------------------------------------------
# Password utilities
# ---------------------------------------------------------------------------


class TestPasswordUtils:
    def test_hash_and_verify(self) -> None:
        hashed = hash_password("secret123")
        assert verify_password("secret123", hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("secret123")
        assert verify_password("wrong", hashed) is False

    def test_different_hashes_for_same_password(self) -> None:
        # bcrypt uses salt, so hashes should differ.
        h1 = hash_password("secret")
        h2 = hash_password("secret")
        assert h1 != h2
        assert verify_password("secret", h1)
        assert verify_password("secret", h2)


# ---------------------------------------------------------------------------
# API Key utilities
# ---------------------------------------------------------------------------


class TestAPIKeyUtils:
    def test_generate_api_key(self) -> None:
        key = generate_api_key()
        assert len(key) > 0

    def test_generate_unique_keys(self) -> None:
        assert generate_api_key() != generate_api_key()

    def test_hash_api_key(self) -> None:
        key = "test-key"
        h1 = hash_api_key(key)
        h2 = hash_api_key(key)
        assert h1 == h2  # deterministic

    def test_verify_api_key(self) -> None:
        key = "test-key"
        key_hash = hash_api_key(key)
        assert verify_api_key(key, key_hash) is True
        assert verify_api_key("wrong-key", key_hash) is False


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------


class TestRole:
    def test_user_has_own_role(self) -> None:
        user = User(roles=[Role.USER])
        assert user.has_role(Role.USER) is True

    def test_admin_has_user_role(self) -> None:
        user = User(roles=[Role.ADMIN])
        assert user.has_role(Role.USER) is True
        assert user.has_role(Role.SERVICE) is True

    def test_user_does_not_have_admin_role(self) -> None:
        user = User(roles=[Role.USER])
        assert user.has_role(Role.ADMIN) is False


# ---------------------------------------------------------------------------
# JWT Handler
# ---------------------------------------------------------------------------


class TestJWTHandler:
    def test_create_and_verify_token(self) -> None:
        handler = JWTHandler(secret_key="test-secret")
        token = handler.create_access_token(
            user_id="u1", username="alice", roles=[Role.USER]
        )
        payload = handler.verify_access_token(token)
        assert payload is not None
        assert payload["sub"] == "u1"
        assert payload["username"] == "alice"
        assert "user" in payload["roles"]

    def test_verify_invalid_token(self) -> None:
        handler = JWTHandler(secret_key="test-secret")
        assert handler.verify_access_token("invalid-token") is None

    def test_verify_token_wrong_secret(self) -> None:
        handler1 = JWTHandler(secret_key="secret-1")
        handler2 = JWTHandler(secret_key="secret-2")
        token = handler1.create_access_token("u1", "alice", [Role.USER])
        assert handler2.verify_access_token(token) is None

    def test_token_expiration(self) -> None:
        handler = JWTHandler(secret_key="test-secret")
        # Create a token that expires immediately.
        token = handler.create_access_token(
            "u1",
            "alice",
            [Role.USER],
            expires_delta=timedelta(seconds=-1),
        )
        assert handler.verify_access_token(token) is None


# ---------------------------------------------------------------------------
# User Store
# ---------------------------------------------------------------------------


class TestUserStore:
    def test_create_user(self) -> None:
        store = UserStore()
        user = store.create_user("alice", "password123")
        assert user.username == "alice"
        assert user.user_id

    def test_create_duplicate_user_raises(self) -> None:
        store = UserStore()
        store.create_user("alice", "password123")
        with pytest.raises(ValueError, match="already exists"):
            store.create_user("alice", "other")

    def test_authenticate_success(self) -> None:
        store = UserStore()
        store.create_user("alice", "password123")
        user = store.authenticate("alice", "password123")
        assert user is not None
        assert user.username == "alice"

    def test_authenticate_wrong_password(self) -> None:
        store = UserStore()
        store.create_user("alice", "password123")
        assert store.authenticate("alice", "wrong") is None

    def test_authenticate_unknown_user(self) -> None:
        store = UserStore()
        assert store.authenticate("ghost", "password") is None

    def test_authenticate_disabled_user(self) -> None:
        store = UserStore()
        user = store.create_user("alice", "password123")
        user.enabled = False
        assert store.authenticate("alice", "password123") is None

    def test_get_user(self) -> None:
        store = UserStore()
        created = store.create_user("alice", "password")
        fetched = store.get_user(created.user_id)
        assert fetched is created

    def test_get_user_by_username(self) -> None:
        store = UserStore()
        store.create_user("alice", "password")
        user = store.get_user_by_username("alice")
        assert user is not None
        assert user.username == "alice"

    def test_delete_user(self) -> None:
        store = UserStore()
        user = store.create_user("alice", "password")
        assert store.delete_user(user.user_id) is True
        assert store.get_user(user.user_id) is None


# ---------------------------------------------------------------------------
# API Key Store
# ---------------------------------------------------------------------------


class TestAPIKeyStore:
    def test_create_api_key(self) -> None:
        store = UserStore()
        user = store.create_user("alice", "password")
        raw_key, api_key = store.create_api_key(user.user_id, name="default")
        assert len(raw_key) > 0
        assert api_key.user_id == user.user_id
        assert api_key.name == "default"

    def test_verify_api_key(self) -> None:
        store = UserStore()
        user = store.create_user("alice", "password")
        raw_key, _ = store.create_api_key(user.user_id)
        result = store.verify_api_key(raw_key)
        assert result is not None
        assert result.user_id == user.user_id

    def test_verify_invalid_api_key(self) -> None:
        store = UserStore()
        assert store.verify_api_key("invalid-key") is None

    def test_revoke_api_key(self) -> None:
        store = UserStore()
        user = store.create_user("alice", "password")
        raw_key, api_key = store.create_api_key(user.user_id)
        assert store.revoke_api_key(api_key.key_id) is True
        # After revocation, verification fails.
        assert store.verify_api_key(raw_key) is None

    def test_list_api_keys(self) -> None:
        store = UserStore()
        user = store.create_user("alice", "password")
        store.create_api_key(user.user_id, name="key1")
        store.create_api_key(user.user_id, name="key2")
        keys = store.list_api_keys(user_id=user.user_id)
        assert len(keys) == 2

    def test_clear(self) -> None:
        store = UserStore()
        user = store.create_user("alice", "password")
        store.create_api_key(user.user_id)
        store.clear()
        assert store.get_user(user.user_id) is None
        assert store.list_api_keys() == []
