"""
Tests for API key authentication system.

Tests cover API key generation, validation, revocation, and authentication.
"""

import datetime
import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from peewee import SqliteDatabase

# Disable secure cookies for testing
os.environ["COOKIE_SECURE"] = "false"

from torrent_manager.api import app
from torrent_manager.auth import ApiKeyManager, UserManager
from torrent_manager.models import User, Session, RememberMeToken, ApiKey


# Use in-memory database for tests
@pytest.fixture(autouse=True)
def setup_test_db():
    """Setup test database before each test."""
    from torrent_manager import models as model_module

    test_db = SqliteDatabase(':memory:')

    models_list = [User, Session, RememberMeToken, ApiKey]
    test_db.bind(models_list, bind_refs=False, bind_backrefs=False)

    old_db = model_module.db
    model_module.db._state.closed = True
    for model in models_list:
        model._meta.database = test_db

    test_db.connect()
    test_db.create_tables(models_list)

    yield

    test_db.drop_tables(models_list)
    test_db.close()

    for model in models_list:
        model._meta.database = old_db


@pytest_asyncio.fixture
async def async_client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_user():
    """Create a test user."""
    return UserManager.create_user(
        username="testuser",
        password="testpass123"
    )


class TestApiKeyManagement:
    """Tests for API key creation, validation, and management."""

    def test_create_api_key(self, test_user):
        """Test creating an API key."""
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Test Key"
        )

        assert api_key is not None
        assert len(api_key) > 20  # Should be a secure random token

        # Verify key in database
        key = ApiKey.get(ApiKey.api_key == api_key)
        assert key.user_id == test_user.id
        assert key.name == "Test Key"
        assert key.revoked is False
        assert key.expires_at is None

    def test_create_api_key_with_expiration(self, test_user):
        """Test creating an API key with expiration."""
        expires_at = datetime.datetime.now() + datetime.timedelta(days=30)
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Expiring Key",
            expires_at=expires_at
        )

        key = ApiKey.get(ApiKey.api_key == api_key)
        assert key.expires_at is not None

    def test_validate_api_key_success(self, test_user):
        """Test validating a valid API key."""
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Valid Key"
        )

        key = ApiKeyManager.validate_api_key(api_key)
        assert key is not None
        assert key.user_id == test_user.id

        # Check that last_used_at was updated
        assert key.last_used_at is not None

    def test_validate_api_key_expired(self, test_user):
        """Test validating an expired API key."""
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Expired Key"
        )

        # Manually expire the key
        key = ApiKey.get(ApiKey.api_key == api_key)
        key.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
        key.save()

        # Validation should fail
        result = ApiKeyManager.validate_api_key(api_key)
        assert result is None

    def test_validate_api_key_revoked(self, test_user):
        """Test validating a revoked API key."""
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Revoked Key"
        )

        # Revoke the key
        ApiKeyManager.revoke_api_key(api_key)

        # Validation should fail
        result = ApiKeyManager.validate_api_key(api_key)
        assert result is None

    def test_validate_api_key_nonexistent(self):
        """Test validating a non-existent API key."""
        result = ApiKeyManager.validate_api_key("nonexistent_key")
        assert result is None

    def test_revoke_api_key(self, test_user):
        """Test revoking an API key."""
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="To Be Revoked"
        )

        # Revoke
        result = ApiKeyManager.revoke_api_key(api_key)
        assert result is True

        # Verify it's revoked
        key = ApiKey.get(ApiKey.api_key == api_key)
        assert key.revoked is True

    def test_list_user_api_keys(self, test_user):
        """Test listing user's API keys."""
        # Create multiple keys
        ApiKeyManager.create_api_key(user_id=test_user.id, name="Key 1")
        ApiKeyManager.create_api_key(user_id=test_user.id, name="Key 2")
        ApiKeyManager.create_api_key(user_id=test_user.id, name="Key 3")

        keys = ApiKeyManager.list_user_api_keys(test_user.id)
        assert len(keys) == 3

    def test_delete_api_key(self, test_user):
        """Test permanently deleting an API key."""
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="To Be Deleted"
        )

        # Delete
        result = ApiKeyManager.delete_api_key(api_key)
        assert result is True

        # Verify it's gone
        try:
            ApiKey.get(ApiKey.api_key == api_key)
            assert False, "Key should have been deleted"
        except ApiKey.DoesNotExist:
            pass

    def test_cleanup_expired_keys(self, test_user):
        """Test cleanup of expired API keys."""
        # Create expired key
        api_key1 = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Expired Key"
        )
        key1 = ApiKey.get(ApiKey.api_key == api_key1)
        key1.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
        key1.save()

        # Create valid key
        api_key2 = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Valid Key"
        )

        # Cleanup
        ApiKeyManager.cleanup_expired_keys()

        # Expired key should be gone
        try:
            ApiKey.get(ApiKey.api_key == api_key1)
            assert False, "Expired key should have been deleted"
        except ApiKey.DoesNotExist:
            pass

        # Valid key should still exist
        key2 = ApiKey.get(ApiKey.api_key == api_key2)
        assert key2 is not None

    def test_list_user_api_keys_excludes_revoked(self, test_user):
        """Test that revoked keys are excluded from the list by default."""
        # Create multiple keys
        key1 = ApiKeyManager.create_api_key(user_id=test_user.id, name="Key 1")
        key2 = ApiKeyManager.create_api_key(user_id=test_user.id, name="Key 2")
        key3 = ApiKeyManager.create_api_key(user_id=test_user.id, name="Key 3")

        # List should show all 3 keys
        keys = ApiKeyManager.list_user_api_keys(test_user.id)
        assert len(keys) == 3

        # Revoke one key
        ApiKeyManager.revoke_api_key(key2)

        # List should now only show 2 keys (revoked key excluded by default)
        keys = ApiKeyManager.list_user_api_keys(test_user.id)
        assert len(keys) == 2
        key_names = [k.name for k in keys]
        assert "Key 1" in key_names
        assert "Key 2" not in key_names  # Revoked key should be excluded
        assert "Key 3" in key_names

        # But with include_revoked=True, should show all 3
        keys_with_revoked = ApiKeyManager.list_user_api_keys(test_user.id, include_revoked=True)
        assert len(keys_with_revoked) == 3


class TestApiKeyAuthentication:
    """Tests for API key-based authentication."""

    @pytest.mark.asyncio
    async def test_authenticate_with_api_key(self, async_client, test_user):
        """Test authenticating with an API key."""
        # Create API key
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Test Auth Key"
        )

        # Use API key to access protected endpoint
        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {api_key}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["auth_method"] == "api_key"

    @pytest.mark.asyncio
    async def test_authenticate_with_invalid_api_key(self, async_client):
        """Test authentication with invalid API key."""
        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid_key"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticate_without_bearer_prefix(self, async_client, test_user):
        """Test authentication with malformed Authorization header."""
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Test Key"
        )

        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": api_key}  # Missing "Bearer " prefix
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_access_protected_endpoint_with_api_key(self, async_client, test_user):
        """Test accessing protected endpoint with API key."""
        api_key = ApiKeyManager.create_api_key(
            user_id=test_user.id,
            name="Access Key"
        )

        response = await async_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {api_key}"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == test_user.id
        assert data["username"] == test_user.username
        assert data["auth_method"] == "api_key"


class TestApiKeyEndpoints:
    """Tests for API key management endpoints."""

    @pytest.mark.asyncio
    async def test_create_api_key_endpoint(self, async_client, test_user):
        """Test creating API key via endpoint."""
        # First login to get session
        await async_client.post("/auth/login", json={
            "username": "testuser",
            "password": "testpass123",
            "remember_me": False
        })

        # Create API key
        response = await async_client.post(
            "/auth/api-keys",
            json={"name": "My API Key"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert data["name"] == "My API Key"
        assert "warning" in data

    @pytest.mark.asyncio
    async def test_create_api_key_with_expiration(self, async_client, test_user):
        """Test creating API key with expiration."""
        await async_client.post("/auth/login", json={
            "username": "testuser",
            "password": "testpass123",
            "remember_me": False
        })

        response = await async_client.post(
            "/auth/api-keys",
            json={"name": "Expiring Key", "expires_days": 30}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_list_api_keys_endpoint(self, async_client, test_user):
        """Test listing API keys via endpoint."""
        await async_client.post("/auth/login", json={
            "username": "testuser",
            "password": "testpass123",
            "remember_me": False
        })

        # Create some keys
        await async_client.post("/auth/api-keys", json={"name": "Key 1"})
        await async_client.post("/auth/api-keys", json={"name": "Key 2"})

        # List keys
        response = await async_client.get("/auth/api-keys")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert "prefix" in data[0]
        assert "name" in data[0]

    @pytest.mark.asyncio
    async def test_revoke_api_key_endpoint(self, test_user):
        """Test revoking API key via endpoint."""
        # Use separate client instances to avoid cookie interference
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client1:
            await client1.post("/auth/login", json={
                "username": "testuser",
                "password": "testpass123",
                "remember_me": False
            })

            # Create key
            create_response = await client1.post(
                "/auth/api-keys",
                json={"name": "To Revoke"}
            )
            api_key = create_response.json()["api_key"]
            key_prefix = api_key[:8]

            # Revoke key
            revoke_response = await client1.delete(f"/auth/api-keys/{key_prefix}")

            assert revoke_response.status_code == 200
            assert revoke_response.json()["message"] == "API key revoked successfully"

        # Use a fresh client without session cookies to test API key
        transport2 = ASGITransport(app=app)
        async with AsyncClient(transport=transport2, base_url="http://test") as client2:
            # Verify key is revoked by trying to use it
            test_response = await client2.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {api_key}"}
            )
            assert test_response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_api_key_requires_auth(self, async_client):
        """Test that creating API key requires authentication."""
        response = await async_client.post(
            "/auth/api-keys",
            json={"name": "Unauthorized"}
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_api_keys_requires_auth(self, async_client):
        """Test that listing API keys requires authentication."""
        response = await async_client.get("/auth/api-keys")
        assert response.status_code == 401
