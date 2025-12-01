import datetime
from fastapi import APIRouter, Request, Response, HTTPException, Depends, status
from torrent_manager.auth import SessionManager, UserManager, ApiKeyManager
from torrent_manager.models import User
from torrent_manager.logger import logger
from torrent_manager.config import Config
from ..schemas import LoginRequest, RegisterRequest, CreateApiKeyRequest
from ..dependencies import get_current_user, get_client_info
from ..constants import SESSION_COOKIE_NAME, REMEMBER_ME_COOKIE_NAME

router = APIRouter(tags=["auth"])
config = Config()
COOKIE_SECURE = config.COOKIE_SECURE

def set_session_cookie(response: Response, session_id: str, expires_at: datetime.datetime):
    """
    Set session cookie with secure attributes.

    Cookie format: Set-Cookie: session=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax; Expires=<date>
    """
    # Format expires as HTTP date
    expires_str = expires_at.strftime("%a, %d %b %Y %H:%M:%S GMT")

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=COOKIE_SECURE,  # Only sent over HTTPS (disabled in tests)
        samesite="lax",  # CSRF protection
        expires=expires_str,
        path="/"
    )

def set_remember_me_cookie(response: Response, token_id: str, expires_at: datetime.datetime):
    """Set remember-me cookie with secure attributes."""
    expires_str = expires_at.strftime("%a, %d %b %Y %H:%M:%S GMT")

    response.set_cookie(
        key=REMEMBER_ME_COOKIE_NAME,
        value=token_id,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        expires=expires_str,
        path="/"
    )

def clear_session_cookie(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")

def clear_remember_me_cookie(response: Response):
    """Clear the remember-me cookie."""
    response.delete_cookie(key=REMEMBER_ME_COOKIE_NAME, path="/")


@router.post("/auth/register")
async def register(request: RegisterRequest, req: Request):
    """Register a new user account."""
    try:
        user = UserManager.create_user(
            username=request.username,
            password=request.password
        )

        return {
            "message": "User registered successfully",
            "user_id": user.id,
            "username": user.username
        }
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}"
        )


@router.post("/auth/login")
async def login(request: LoginRequest, req: Request, response: Response):
    """
    Authenticate user and create session with secure cookies.

    Optionally creates a remember-me token for longer-lived authentication.
    """
    user = UserManager.authenticate_user(request.username, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    # Get client info
    ip_address, user_agent = get_client_info(req)

    # Create session
    session_id = SessionManager.create_session(
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent
    )

    # Get session to get expires_at
    session = SessionManager.validate_session(session_id)
    set_session_cookie(response, session_id, session.expires_at)

    # Create remember-me token if requested
    if request.remember_me:
        token_id = SessionManager.create_remember_me_token(
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent
        )

        token = SessionManager.validate_remember_me_token(token_id)
        set_remember_me_cookie(response, token_id, token.expires_at)

    return {
        "message": "Login successful",
        "user_id": user.id,
        "username": user.username
    }


@router.post("/auth/logout")
async def logout(request: Request, response: Response, user: User = Depends(get_current_user)):
    """
    Logout user by deleting session and clearing cookies.
    """
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    remember_me_token = request.cookies.get(REMEMBER_ME_COOKIE_NAME)

    # Delete session
    if session_id:
        SessionManager.delete_session(session_id)
        clear_session_cookie(response)

    # Revoke remember-me token
    if remember_me_token:
        SessionManager.revoke_remember_me_token(remember_me_token)
        clear_remember_me_cookie(response)

    return {"message": "Logout successful"}


@router.get("/auth/me")
async def get_me(request: Request, user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    auth_method = getattr(request.state, "auth_method", "unknown")
    return {
        "user_id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "timestamp": user.timestamp.isoformat(),
        "auth_method": auth_method
    }

@router.post("/auth/api-keys")
async def create_api_key(
    request: CreateApiKeyRequest,
    user: User = Depends(get_current_user)
):
    """
    Create a new API key for the authenticated user.

    API keys can be used for programmatic access instead of session-based authentication.
    Pass the API key in the Authorization header: `Authorization: Bearer <api_key>`
    """
    expires_at = None
    if request.expires_days:
        expires_at = datetime.datetime.now() + datetime.timedelta(days=request.expires_days)

    api_key = ApiKeyManager.create_api_key(
        user_id=user.id,
        name=request.name,
        expires_at=expires_at
    )

    return {
        "message": "API key created successfully",
        "api_key": api_key,
        "name": request.name,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "warning": "Store this API key securely. It will not be shown again."
    }


@router.get("/auth/api-keys")
async def list_api_keys(user: User = Depends(get_current_user)):
    """
    List all API keys for the authenticated user.

    Note: The actual key values are not returned, only metadata.
    """
    keys = ApiKeyManager.list_user_api_keys(user.id)

    return [
        {
            "prefix": key.api_key[:8],  # Only show prefix
            "name": key.name,
            "created_at": key.created_at.isoformat(),
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
            "expires_at": key.expires_at.isoformat() if key.expires_at else None,
            "revoked": key.revoked
        }
        for key in keys
    ]


@router.delete("/auth/api-keys/{key_prefix}")
async def revoke_api_key(
    key_prefix: str,
    user: User = Depends(get_current_user)
):
    """
    Revoke an API key by its prefix (first 8 characters).

    The key will be marked as revoked and can no longer be used for authentication.
    """
    # Find the key by prefix
    keys = ApiKeyManager.list_user_api_keys(user.id)
    matching_key = None

    for key in keys:
        if key.api_key.startswith(key_prefix):
            matching_key = key
            break

    if not matching_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Revoke the key
    ApiKeyManager.revoke_api_key(matching_key.api_key)

    return {
        "message": "API key revoked successfully",
        "name": matching_key.name
    }
