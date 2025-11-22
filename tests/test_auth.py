"""
Tests for authentication system including session management, sliding expiration,
and remember-me functionality.
"""

import datetime
import os
import tempfile
import time
import pytest
import pytest_asyncio
from httpx import AsyncClient
from peewee import SqliteDatabase

# Disable secure cookies for testing
os.environ["COOKIE_SECURE"] = "false"

from torrent_manager.api import app, SESSION_COOKIE_NAME, REMEMBER_ME_COOKIE_NAME
from torrent_manager.auth import SessionManager, UserManager, hash_password
from torrent_manager.models import User, Session, RememberMeToken, db


# Use in-memory database for tests
@pytest.fixture(autouse=True)
def setup_test_db():
    """Setup test database before each test."""
    # Import here to avoid circular imports
    from torrent_manager import models as model_module

    # Use in-memory SQLite for tests
    test_db = SqliteDatabase(':memory:')

    # Bind models to test database
    models_list = [User, Session, RememberMeToken]
    test_db.bind(models_list, bind_refs=False, bind_backrefs=False)

    # Also update the module-level db reference so the API uses test database
    old_db = model_module.db
    model_module.db._state.closed = True
    for model in models_list:
        model._meta.database = test_db

    # Create tables
    test_db.connect()
    test_db.create_tables(models_list)

    yield

    # Cleanup
    test_db.drop_tables(models_list)
    test_db.close()

    # Restore original db
    for model in models_list:
        model._meta.database = old_db


@pytest_asyncio.fixture
async def async_client():
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_user():
    """Create a test user."""
    return UserManager.create_user(
        username="testuser",
        password="testpass123"
    )


class TestUserManagement:
    """Tests for user creation and authentication."""

    def test_create_user(self):
        """Test user creation with password hashing."""
        user = UserManager.create_user(
            username="newuser",
            password="password123"
        )

        assert user.username == "newuser"
        assert user.password != "password123"  # Password should be hashed
        assert user.id is not None

    def test_authenticate_user_success(self, test_user):
        """Test successful user authentication."""
        user = UserManager.authenticate_user("testuser", "testpass123")

        assert user is not None
        assert user.username == "testuser"
        assert user.id == test_user.id

    def test_authenticate_user_wrong_password(self, test_user):
        """Test authentication with wrong password."""
        user = UserManager.authenticate_user("testuser", "wrongpassword")
        assert user is None

    def test_authenticate_user_nonexistent(self):
        """Test authentication with non-existent user."""
        user = UserManager.authenticate_user("nonexistent", "password")
        assert user is None


class TestSessionManagement:
    """Tests for session creation, validation, and management."""

    def test_create_session(self, test_user):
        """Test session creation."""
        session_id = SessionManager.create_session(
            user_id=test_user.id,
            ip_address="127.0.0.1",
            user_agent="Test Agent"
        )

        assert session_id is not None
        assert len(session_id) > 20  # Should be a secure random token

        # Verify session in database
        session = Session.get(Session.session_id == session_id)
        assert session.user_id == test_user.id
        assert session.ip_address == "127.0.0.1"
        assert session.user_agent == "Test Agent"

    def test_validate_session_success(self, test_user):
        """Test validating a valid session."""
        session_id = SessionManager.create_session(user_id=test_user.id)
        session = SessionManager.validate_session(session_id)

        assert session is not None
        assert session.user_id == test_user.id

    def test_validate_session_expired(self, test_user):
        """Test validating an expired session."""
        session_id = SessionManager.create_session(user_id=test_user.id)

        # Manually expire the session
        session = Session.get(Session.session_id == session_id)
        session.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
        session.save()

        # Validate should return None for expired session
        result = SessionManager.validate_session(session_id)
        assert result is None

    def test_validate_session_nonexistent(self):
        """Test validating a non-existent session."""
        session = SessionManager.validate_session("nonexistent_session_id")
        assert session is None

    def test_delete_session(self, test_user):
        """Test session deletion."""
        session_id = SessionManager.create_session(user_id=test_user.id)

        # Delete session
        result = SessionManager.delete_session(session_id)
        assert result is True

        # Verify session is deleted
        session = SessionManager.validate_session(session_id)
        assert session is None


class TestSlidingExpiration:
    """Tests for session renewal with sliding expiration."""

    def test_should_renew_session_within_window(self, test_user):
        """Test that session should be renewed when within sliding window."""
        session_id = SessionManager.create_session(user_id=test_user.id)
        session = SessionManager.validate_session(session_id)

        # Session just created, should be within window
        assert SessionManager.should_renew_session(session) is True

    def test_should_not_renew_session_outside_window(self, test_user):
        """Test that session should NOT be renewed when outside sliding window."""
        session_id = SessionManager.create_session(user_id=test_user.id)

        # Manually set last activity to 8 days ago (outside 7-day window)
        session = Session.get(Session.session_id == session_id)
        session.last_activity = datetime.datetime.now() - datetime.timedelta(days=8)
        session.save()

        session = SessionManager.validate_session(session_id)
        assert SessionManager.should_renew_session(session) is False

    def test_renew_session_success(self, test_user):
        """Test successful session renewal."""
        session_id = SessionManager.create_session(user_id=test_user.id)

        # Get original expiry
        session = SessionManager.validate_session(session_id)
        original_expires_at = session.expires_at
        original_last_activity = session.last_activity

        # Wait a moment to ensure timestamps differ
        time.sleep(0.1)

        # Renew session
        renewed, new_expires_at = SessionManager.renew_session(session_id)

        assert renewed is True
        assert new_expires_at > original_expires_at

        # Verify session was updated
        session = SessionManager.validate_session(session_id)
        assert session.expires_at > original_expires_at
        assert session.last_activity > original_last_activity

    def test_renew_session_outside_window(self, test_user):
        """Test that session renewal fails when outside sliding window."""
        session_id = SessionManager.create_session(user_id=test_user.id)

        # Set last activity outside window
        session = Session.get(Session.session_id == session_id)
        session.last_activity = datetime.datetime.now() - datetime.timedelta(days=8)
        session.save()

        # Try to renew
        renewed, new_expires_at = SessionManager.renew_session(session_id)

        assert renewed is False
        assert new_expires_at is None


class TestRememberMe:
    """Tests for remember-me token functionality."""

    def test_create_remember_me_token(self, test_user):
        """Test remember-me token creation."""
        token_id = SessionManager.create_remember_me_token(
            user_id=test_user.id,
            ip_address="127.0.0.1",
            user_agent="Test Agent"
        )

        assert token_id is not None
        assert len(token_id) > 20

        # Verify token in database
        token = RememberMeToken.get(RememberMeToken.token_id == token_id)
        assert token.user_id == test_user.id
        assert token.revoked is False

    def test_validate_remember_me_token_success(self, test_user):
        """Test validating a valid remember-me token."""
        token_id = SessionManager.create_remember_me_token(user_id=test_user.id)
        token = SessionManager.validate_remember_me_token(token_id)

        assert token is not None
        assert token.user_id == test_user.id

    def test_validate_remember_me_token_expired(self, test_user):
        """Test validating an expired remember-me token."""
        token_id = SessionManager.create_remember_me_token(user_id=test_user.id)

        # Manually expire the token
        token = RememberMeToken.get(RememberMeToken.token_id == token_id)
        token.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
        token.save()

        # Validate should return None
        result = SessionManager.validate_remember_me_token(token_id)
        assert result is None

    def test_revoke_remember_me_token(self, test_user):
        """Test revoking a remember-me token."""
        token_id = SessionManager.create_remember_me_token(user_id=test_user.id)

        # Revoke token
        result = SessionManager.revoke_remember_me_token(token_id)
        assert result is True

        # Verify token is revoked
        token = SessionManager.validate_remember_me_token(token_id)
        assert token is None


class TestAPIEndpoints:
    """Tests for API authentication endpoints."""

    @pytest.mark.asyncio
    async def test_register_user(self, async_client):
        """Test user registration endpoint."""
        response = await async_client.post(
            "/auth/register",
            json={
                "username": "apiuser",
                "password": "apipass123",
                "email": "api@example.com"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "apiuser"
        assert "user_id" in data

    @pytest.mark.asyncio
    async def test_login_success(self, async_client, test_user):
        """Test successful login with session cookie."""
        response = await async_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "testpass123",
                "remember_me": False
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"

        # Check session cookie
        assert SESSION_COOKIE_NAME in response.cookies
        session_cookie = response.cookies[SESSION_COOKIE_NAME]
        assert session_cookie is not None

    @pytest.mark.asyncio
    async def test_login_with_remember_me(self, async_client, test_user):
        """Test login with remember-me functionality."""
        response = await async_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "testpass123",
                "remember_me": True
            }
        )

        assert response.status_code == 200

        # Check both cookies
        assert SESSION_COOKIE_NAME in response.cookies
        assert REMEMBER_ME_COOKIE_NAME in response.cookies

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, async_client, test_user):
        """Test login with wrong password."""
        response = await async_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "wrongpassword",
                "remember_me": False
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_authenticated(self, async_client, test_user):
        """Test getting current user info when authenticated."""
        # Login first
        login_response = await async_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "testpass123",
                "remember_me": False
            }
        )

        # Use session cookie to access protected endpoint
        response = await async_client.get("/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_get_me_unauthenticated(self, async_client):
        """Test accessing protected endpoint without authentication."""
        response = await async_client.get("/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_logout(self, async_client, test_user):
        """Test logout endpoint."""
        # Login first
        login_response = await async_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "testpass123",
                "remember_me": False
            }
        )

        # Logout
        response = await async_client.post("/auth/logout")

        assert response.status_code == 200

        # Try to access protected endpoint after logout
        response = await async_client.get("/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_protected_endpoint(self, async_client, test_user):
        """Test accessing protected torrent endpoint."""
        # Login first
        await async_client.post(
            "/auth/login",
            json={
                "username": "testuser",
                "password": "testpass123",
                "remember_me": False
            }
        )

        # Access protected endpoint
        response = await async_client.get("/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == test_user.id
        assert data["username"] == test_user.username
        assert data["auth_method"] == "session"


class TestCleanup:
    """Tests for cleanup operations."""

    def test_cleanup_expired_sessions(self, test_user):
        """Test cleaning up expired sessions."""
        # Create sessions
        session1 = SessionManager.create_session(user_id=test_user.id)
        session2 = SessionManager.create_session(user_id=test_user.id)

        # Expire first session
        session = Session.get(Session.session_id == session1)
        session.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
        session.save()

        # Cleanup
        SessionManager.cleanup_expired_sessions()

        # First session should be gone
        assert SessionManager.validate_session(session1) is None

        # Second session should still exist
        assert SessionManager.validate_session(session2) is not None

    def test_cleanup_expired_tokens(self, test_user):
        """Test cleaning up expired remember-me tokens."""
        # Create tokens
        token1 = SessionManager.create_remember_me_token(user_id=test_user.id)
        token2 = SessionManager.create_remember_me_token(user_id=test_user.id)

        # Expire and revoke first token
        token = RememberMeToken.get(RememberMeToken.token_id == token1)
        token.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
        token.save()

        # Cleanup
        SessionManager.cleanup_expired_tokens()

        # First token should be gone
        result = RememberMeToken.select().where(RememberMeToken.token_id == token1).count()
        assert result == 0

        # Second token should still exist
        assert SessionManager.validate_remember_me_token(token2) is not None
