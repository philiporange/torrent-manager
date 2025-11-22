"""
Session-based authentication with sliding expiration and remember-me functionality.

Implements secure HTTP-only session cookies with:
- Sliding expiration (resets on each user interaction)
- ITP-safe sliding window (< 7 days)
- Remember-me tokens for longer-lived authentication
- Secure, HttpOnly, SameSite=Lax cookies
"""

import datetime
import secrets
from typing import Optional, Tuple
from passlib.context import CryptContext

from .models import User, Session, RememberMeToken, ApiKey
from .logger import logger


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Session configuration (ITP-safe: < 7 days for sliding window)
SESSION_SLIDING_WINDOW_DAYS = 7
SESSION_MAX_AGE_DAYS = 30

# Remember-me configuration (longer-lived)
REMEMBER_ME_MAX_AGE_DAYS = 90


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


class SessionManager:
    """
    Manages user sessions with sliding expiration and remember-me functionality.
    """

    @staticmethod
    def create_session(
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        max_age_days: int = SESSION_MAX_AGE_DAYS
    ) -> str:
        """
        Create a new session for a user.

        Returns:
            session_id: The generated session ID
        """
        session_id = generate_secure_token()
        now = datetime.datetime.now()
        expires_at = now + datetime.timedelta(days=max_age_days)

        Session.create(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            last_activity=now,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )

        logger.info(f"Created session {session_id[:8]}... for user {user_id}")
        return session_id

    @staticmethod
    def validate_session(session_id: str) -> Optional[Session]:
        """
        Validate a session and check if it's expired.

        Returns:
            Session object if valid, None otherwise
        """
        try:
            session = Session.get(Session.session_id == session_id)
            now = datetime.datetime.now()

            # Check if session is expired
            if session.expires_at < now:
                logger.info(f"Session {session_id[:8]}... expired")
                SessionManager.delete_session(session_id)
                return None

            return session
        except Session.DoesNotExist:
            return None

    @staticmethod
    def should_renew_session(session: Session) -> bool:
        """
        Check if session should be renewed based on sliding window.

        ITP-safe: Only renew if last activity was within the sliding window (< 7 days).
        """
        now = datetime.datetime.now()
        time_since_activity = now - session.last_activity

        # Renew if activity is within the sliding window
        return time_since_activity < datetime.timedelta(days=SESSION_SLIDING_WINDOW_DAYS)

    @staticmethod
    def renew_session(session_id: str) -> Tuple[bool, Optional[datetime.datetime]]:
        """
        Renew a session by updating last activity and expiry.

        Returns:
            (renewed, new_expires_at): True if renewed with new expiry, False otherwise
        """
        session = SessionManager.validate_session(session_id)
        if not session:
            return False, None

        if not SessionManager.should_renew_session(session):
            logger.info(f"Session {session_id[:8]}... outside sliding window, not renewing")
            return False, None

        now = datetime.datetime.now()
        new_expires_at = now + datetime.timedelta(days=SESSION_MAX_AGE_DAYS)

        # Update session
        session.last_activity = now
        session.expires_at = new_expires_at
        session.save()

        logger.info(f"Renewed session {session_id[:8]}... for user {session.user_id}")
        return True, new_expires_at

    @staticmethod
    def delete_session(session_id: str) -> bool:
        """Delete a session."""
        try:
            session = Session.get(Session.session_id == session_id)
            session.delete_instance()
            logger.info(f"Deleted session {session_id[:8]}...")
            return True
        except Session.DoesNotExist:
            return False

    @staticmethod
    def cleanup_expired_sessions():
        """Remove all expired sessions from the database."""
        now = datetime.datetime.now()
        deleted = Session.delete().where(Session.expires_at < now).execute()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired sessions")

    @staticmethod
    def create_remember_me_token(
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> str:
        """
        Create a remember-me token for longer-lived authentication.

        Returns:
            token_id: The generated token ID
        """
        token_id = generate_secure_token()
        now = datetime.datetime.now()
        expires_at = now + datetime.timedelta(days=REMEMBER_ME_MAX_AGE_DAYS)

        RememberMeToken.create(
            token_id=token_id,
            user_id=user_id,
            created_at=now,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            revoked=False
        )

        logger.info(f"Created remember-me token {token_id[:8]}... for user {user_id}")
        return token_id

    @staticmethod
    def validate_remember_me_token(token_id: str) -> Optional[RememberMeToken]:
        """
        Validate a remember-me token.

        Returns:
            RememberMeToken object if valid, None otherwise
        """
        try:
            token = RememberMeToken.get(RememberMeToken.token_id == token_id)
            now = datetime.datetime.now()

            # Check if token is expired or revoked
            if token.expires_at < now or token.revoked:
                logger.info(f"Remember-me token {token_id[:8]}... invalid or expired")
                return None

            return token
        except RememberMeToken.DoesNotExist:
            return None

    @staticmethod
    def revoke_remember_me_token(token_id: str) -> bool:
        """Revoke a remember-me token."""
        try:
            token = RememberMeToken.get(RememberMeToken.token_id == token_id)
            token.revoked = True
            token.save()
            logger.info(f"Revoked remember-me token {token_id[:8]}...")
            return True
        except RememberMeToken.DoesNotExist:
            return False

    @staticmethod
    def cleanup_expired_tokens():
        """Remove all expired or revoked remember-me tokens."""
        now = datetime.datetime.now()
        deleted = RememberMeToken.delete().where(
            (RememberMeToken.expires_at < now) | (RememberMeToken.revoked == True)
        ).execute()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired/revoked remember-me tokens")


class ApiKeyManager:
    """Manages API keys for programmatic authentication."""

    @staticmethod
    def create_api_key(
        user_id: str,
        name: str,
        expires_at: Optional[datetime.datetime] = None
    ) -> str:
        """
        Create a new API key for a user.

        Args:
            user_id: The user ID to create the key for
            name: A descriptive name for the key
            expires_at: Optional expiration date

        Returns:
            api_key: The generated API key
        """
        api_key = generate_secure_token()
        now = datetime.datetime.now()

        ApiKey.create(
            api_key=api_key,
            user_id=user_id,
            name=name,
            created_at=now,
            expires_at=expires_at,
            revoked=False
        )

        logger.info(f"Created API key '{name}' ({api_key[:8]}...) for user {user_id}")
        return api_key

    @staticmethod
    def validate_api_key(api_key: str) -> Optional[ApiKey]:
        """
        Validate an API key and check if it's expired or revoked.

        Returns:
            ApiKey object if valid, None otherwise
        """
        try:
            key = ApiKey.get(ApiKey.api_key == api_key)
            now = datetime.datetime.now()

            # Check if key is revoked
            if key.revoked:
                logger.info(f"API key {api_key[:8]}... is revoked")
                return None

            # Check if key is expired
            if key.expires_at and key.expires_at < now:
                logger.info(f"API key {api_key[:8]}... is expired")
                return None

            # Update last used timestamp
            key.last_used_at = now
            key.save()

            return key
        except ApiKey.DoesNotExist:
            return None

    @staticmethod
    def revoke_api_key(api_key: str) -> bool:
        """Revoke an API key."""
        try:
            key = ApiKey.get(ApiKey.api_key == api_key)
            key.revoked = True
            key.save()
            logger.info(f"Revoked API key {api_key[:8]}...")
            return True
        except ApiKey.DoesNotExist:
            return False

    @staticmethod
    def list_user_api_keys(user_id: str, include_revoked: bool = False) -> list[ApiKey]:
        """
        List API keys for a user.

        Args:
            user_id: The user ID to list keys for
            include_revoked: If True, include revoked keys in the list (default: False)

        Returns:
            List of ApiKey objects
        """
        query = ApiKey.select().where(ApiKey.user_id == user_id)

        if not include_revoked:
            query = query.where(ApiKey.revoked == False)

        return list(query)

    @staticmethod
    def delete_api_key(api_key: str) -> bool:
        """Permanently delete an API key."""
        try:
            key = ApiKey.get(ApiKey.api_key == api_key)
            key.delete_instance()
            logger.info(f"Deleted API key {api_key[:8]}...")
            return True
        except ApiKey.DoesNotExist:
            return False

    @staticmethod
    def cleanup_expired_keys():
        """Remove all expired API keys."""
        now = datetime.datetime.now()
        deleted = ApiKey.delete().where(
            (ApiKey.expires_at < now) & (ApiKey.expires_at.is_null(False))
        ).execute()
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} expired API keys")


class UserManager:
    """Manages user accounts."""

    @staticmethod
    def create_user(username: str, password: str) -> User:
        """Create a new user with hashed password."""
        user_id = generate_secure_token(16)
        hashed_password = hash_password(password)

        user = User.create(
            id=user_id,
            username=username,
            password=hashed_password
        )

        logger.info(f"Created user {username} with ID {user_id}")
        return user

    @staticmethod
    def authenticate_user(username: str, password: str) -> Optional[User]:
        """Authenticate a user by username and password."""
        try:
            user = User.get(User.username == username)
            if verify_password(password, user.password):
                logger.info(f"User {username} authenticated successfully")
                return user
            else:
                logger.warning(f"Failed authentication attempt for user {username}")
                return None
        except User.DoesNotExist:
            logger.warning(f"Authentication attempt for non-existent user {username}")
            return None

    @staticmethod
    def get_user_by_id(user_id: str) -> Optional[User]:
        """Get a user by their ID."""
        try:
            return User.get(User.id == user_id)
        except User.DoesNotExist:
            return None
