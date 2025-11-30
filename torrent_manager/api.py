"""
FastAPI application with secure session-based authentication and torrent management.

Provides:
- HTTP-only secure session cookies with sliding expiration and remember-me functionality
- API key authentication for programmatic access
- Multi-server torrent management (rTorrent and Transmission)
- Full torrent management (add, start, stop, remove, list)
- File browsing and download proxy for nginx HTTP servers
- CORS middleware for frontend access
"""

import datetime
import secrets
from typing import Optional, List
from fastapi import FastAPI, Request, Response, HTTPException, Depends, status, Form, UploadFile, File, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import asyncio

from .auth import SessionManager, UserManager, ApiKeyManager
from .models import User, Session, ApiKey, TorrentServer
from .client_factory import get_client
from .logger import logger
from .config import Config
import os
import tempfile


# Cookie names
SESSION_COOKIE_NAME = "session"
REMEMBER_ME_COOKIE_NAME = "remember_me"

# Cookie security (disable Secure flag in development/testing)
config = Config()
COOKIE_SECURE = config.COOKIE_SECURE


# Request models
class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class RegisterRequest(BaseModel):
    username: str
    password: str


class CreateApiKeyRequest(BaseModel):
    name: str
    expires_days: Optional[int] = None  # Optional expiration in days


class AddTorrentRequest(BaseModel):
    uri: str  # Magnet URI or HTTP/HTTPS URL to torrent file
    server_id: str  # Which server to add the torrent to
    start: bool = True


class TorrentActionRequest(BaseModel):
    info_hash: str


class AddServerRequest(BaseModel):
    name: str
    server_type: str  # "rtorrent" or "transmission"
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    rpc_path: Optional[str] = None  # For rTorrent (e.g., "/RPC2")
    use_ssl: bool = False
    # HTTP download server configuration
    http_host: Optional[str] = None
    http_port: Optional[int] = None
    http_path: Optional[str] = None
    http_username: Optional[str] = None
    http_password: Optional[str] = None
    http_use_ssl: bool = False


class UpdateServerRequest(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    rpc_path: Optional[str] = None
    use_ssl: Optional[bool] = None
    enabled: Optional[bool] = None
    # HTTP download server configuration
    http_host: Optional[str] = None
    http_port: Optional[int] = None
    http_path: Optional[str] = None
    http_username: Optional[str] = None
    http_password: Optional[str] = None
    http_use_ssl: Optional[bool] = None


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class UpdateUserRequest(BaseModel):
    password: Optional[str] = None
    is_admin: Optional[bool] = None


from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Torrent Manager API",
    description="API for managing torrent servers (rTorrent and Transmission) with secure session-based authentication",
    version="2.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="torrent_manager/static"), name="static")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extract client IP and user agent from request."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


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


async def get_current_user(request: Request) -> User:
    """
    Dependency to get the current authenticated user.

    Supports two authentication methods:
    1. Session cookies (for browser-based authentication)
    2. API keys via Authorization header (for programmatic access)

    This checks in order:
    - API key in Authorization header (Bearer token)
    - Session cookie
    - Remember-me token (if session invalid)
    """
    # First, check for API key in Authorization header
    auth_header = request.headers.get("authorization")
    if auth_header:
        # Expected format: "Bearer <api_key>"
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            api_key = parts[1]
            key = ApiKeyManager.validate_api_key(api_key)
            if key:
                user = UserManager.get_user_by_id(key.user_id)
                if user:
                    # Store user in request state
                    request.state.user = user
                    request.state.auth_method = "api_key"
                    logger.debug(f"Authenticated user {user.username} via API key")
                    return user

    # Check for session cookie
    session_id = request.cookies.get(SESSION_COOKIE_NAME)

    # Try to validate existing session
    if session_id:
        session = SessionManager.validate_session(session_id)
        if session:
            user = UserManager.get_user_by_id(session.user_id)
            if user:
                # Store session in request state for middleware
                request.state.session = session
                request.state.user = user
                request.state.auth_method = "session"
                return user

    # If no valid session, try remember-me token
    remember_me_token = request.cookies.get(REMEMBER_ME_COOKIE_NAME)
    if remember_me_token:
        token = SessionManager.validate_remember_me_token(remember_me_token)
        if token:
            user = UserManager.get_user_by_id(token.user_id)
            if user:
                # Create new session from remember-me token
                ip_address, user_agent = get_client_info(request)
                new_session_id = SessionManager.create_session(
                    user_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent
                )

                # Store info in request state
                session = SessionManager.validate_session(new_session_id)
                request.state.session = session
                request.state.user = user
                request.state.new_session_id = new_session_id
                request.state.session_from_remember_me = True
                request.state.auth_method = "session"

                logger.info(f"Created new session from remember-me token for user {user.username}")
                return user

    # No valid authentication
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"}
    )


@app.middleware("http")
async def session_renewal_middleware(request: Request, call_next):
    """
    Middleware to handle session renewal with sliding expiration.

    On each meaningful request:
    - If user is active, reissue the cookie with new expiry (sliding window < 7 days to be ITP-safe)
    - Also handles setting session cookie when created from remember-me token
    """
    response = await call_next(request)

    # Check if we have a session to renew
    if hasattr(request.state, "session") and request.state.session:
        session = request.state.session

        # Check if session was just created from remember-me token
        if hasattr(request.state, "session_from_remember_me") and request.state.session_from_remember_me:
            # Set the new session cookie
            new_session_id = request.state.new_session_id
            set_session_cookie(response, new_session_id, session.expires_at)
        else:
            # Try to renew existing session (sliding expiration)
            renewed, new_expires_at = SessionManager.renew_session(session.session_id)

            if renewed:
                # Reissue cookie with new expiry
                set_session_cookie(response, session.session_id, new_expires_at)
                logger.debug(f"Reissued session cookie with sliding expiration")

    return response


@app.post("/auth/register")
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


@app.post("/auth/login")
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


@app.post("/auth/logout")
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


@app.get("/auth/me")
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


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency to ensure the user is an admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return user


# --- Admin Endpoints ---

@app.get("/admin/users")
async def list_users(admin: User = Depends(get_current_admin)):
    """List all users (Admin only)."""
    users = UserManager.list_users()
    return [
        {
            "id": u.id,
            "username": u.username,
            "is_admin": u.is_admin,
            "created_at": u.timestamp.isoformat()
        }
        for u in users
    ]


@app.post("/admin/users")
async def create_user_admin(
    request: CreateUserRequest,
    admin: User = Depends(get_current_admin)
):
    """Create a new user (Admin only)."""
    try:
        user = UserManager.create_user(
            username=request.username,
            password=request.password,
            is_admin=request.is_admin
        )
        return {"message": "User created", "user_id": user.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/admin/users/{user_id}")
async def update_user_admin(
    user_id: str,
    request: UpdateUserRequest,
    admin: User = Depends(get_current_admin)
):
    """Update a user (Admin only)."""
    user = UserManager.update_user(
        user_id=user_id,
        password=request.password,
        is_admin=request.is_admin
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User updated"}


@app.delete("/admin/users/{user_id}")
async def delete_user_admin(
    user_id: str,
    admin: User = Depends(get_current_admin)
):
    """Delete a user (Admin only)."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    success = UserManager.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}


@app.websocket("/admin/logs/ws")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint to stream logs."""
    # We can't use standard dependency injection easily here for auth, so we'll check the cookie manually
    # or require a token. For simplicity in this context, we'll verify the session cookie.
    
    # Verify Auth
    session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    is_admin = False
    if session_id:
        session = SessionManager.validate_session(session_id)
        if session:
            user = UserManager.get_user_by_id(session.user_id)
            if user and user.is_admin:
                is_admin = True
    
    if not is_admin:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    
    log_path = config.LOG_PATH
    if not os.path.exists(log_path):
        await websocket.send_text("Log file not found.")
        await websocket.close()
        return

    try:
        with open(log_path, "r") as f:
            # Send last 20 lines first
            lines = f.readlines()[-20:]
            for line in lines:
                await websocket.send_text(line.strip())
            
            # Tail the file
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    await websocket.send_text(line.strip())
                else:
                    await asyncio.sleep(0.5)
    except Exception as e:
        await websocket.send_text(f"Error reading log: {e}")
        await websocket.close()


@app.get("/admin/console")
async def admin_page(user: User = Depends(get_current_admin)):
    """Serve the admin console page."""
    return FileResponse("torrent_manager/static/admin.html", media_type="text/html")


@app.post("/auth/api-keys")
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


@app.get("/auth/api-keys")
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


@app.delete("/auth/api-keys/{key_prefix}")
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


# Server Management Endpoints

def get_user_server(server_id: str, user: User) -> TorrentServer:
    """Get a server by ID, ensuring it belongs to the user."""
    try:
        server = TorrentServer.get(TorrentServer.id == server_id)
        if server.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Server not found"
            )
        return server
    except TorrentServer.DoesNotExist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Server not found"
        )


@app.post("/servers")
async def add_server(request: AddServerRequest, user: User = Depends(get_current_user)):
    """Add a new torrent server configuration."""
    if request.server_type not in ("rtorrent", "transmission"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="server_type must be 'rtorrent' or 'transmission'"
        )

    server_id = secrets.token_urlsafe(16)
    server = TorrentServer.create(
        id=server_id,
        user_id=user.id,
        name=request.name,
        server_type=request.server_type,
        host=request.host,
        port=request.port,
        username=request.username,
        password=request.password,
        rpc_path=request.rpc_path,
        use_ssl=request.use_ssl,
        enabled=True,
        http_host=request.http_host,
        http_port=request.http_port,
        http_path=request.http_path,
        http_username=request.http_username,
        http_password=request.http_password,
        http_use_ssl=request.http_use_ssl
    )

    return {
        "id": server.id,
        "user_id": server.user_id,
        "name": server.name,
        "server_type": server.server_type,
        "host": server.host,
        "port": server.port,
        "username": server.username,
        "password": server.password,
        "rpc_path": server.rpc_path,
        "use_ssl": server.use_ssl,
        "enabled": server.enabled,
        "created_at": server.created_at.isoformat(),
        "http_host": server.http_host,
        "http_port": server.http_port,
        "http_path": server.http_path,
        "http_username": server.http_username,
        "http_use_ssl": server.http_use_ssl,
        "http_enabled": bool(server.http_port)
    }


@app.get("/servers")
async def list_servers(user: User = Depends(get_current_user)):
    """List all torrent servers for the current user."""
    servers = TorrentServer.select().where(TorrentServer.user_id == user.id)
    return [
        {
            "id": s.id,
            "name": s.name,
            "server_type": s.server_type,
            "host": s.host,
            "port": s.port,
            "rpc_path": s.rpc_path,
            "use_ssl": s.use_ssl,
            "enabled": s.enabled,
            "created_at": s.created_at.isoformat(),
            "http_host": s.http_host,
            "http_port": s.http_port,
            "http_path": s.http_path,
            "http_username": s.http_username,
            "http_use_ssl": s.http_use_ssl,
            "http_enabled": bool(s.http_port)
        }
        for s in servers
    ]


@app.get("/servers/{server_id}")
async def get_server(server_id: str, user: User = Depends(get_current_user)):
    """Get details of a specific server."""
    server = get_user_server(server_id, user)
    return {
        "id": server.id,
        "name": server.name,
        "server_type": server.server_type,
        "host": server.host,
        "port": server.port,
        "username": server.username,
        "rpc_path": server.rpc_path,
        "use_ssl": server.use_ssl,
        "enabled": server.enabled,
        "created_at": server.created_at.isoformat(),
        "http_host": server.http_host,
        "http_port": server.http_port,
        "http_path": server.http_path,
        "http_username": server.http_username,
        "http_use_ssl": server.http_use_ssl,
        "http_enabled": bool(server.http_port)
    }


@app.put("/servers/{server_id}")
async def update_server(
    server_id: str,
    request: UpdateServerRequest,
    user: User = Depends(get_current_user)
):
    """Update a server configuration."""
    server = get_user_server(server_id, user)

    if request.name is not None:
        server.name = request.name
    if request.host is not None:
        server.host = request.host
    if request.port is not None:
        server.port = request.port
    if request.username is not None:
        server.username = request.username
    if request.password is not None:
        server.password = request.password
    if request.rpc_path is not None:
        server.rpc_path = request.rpc_path
    if request.use_ssl is not None:
        server.use_ssl = request.use_ssl
    if request.enabled is not None:
        server.enabled = request.enabled
    if request.http_host is not None:
        server.http_host = request.http_host
    if request.http_port is not None:
        server.http_port = request.http_port
    if request.http_path is not None:
        server.http_path = request.http_path
    if request.http_username is not None:
        server.http_username = request.http_username
    if request.http_password is not None:
        server.http_password = request.http_password
    if request.http_use_ssl is not None:
        server.http_use_ssl = request.http_use_ssl

    server.save()

    return {
        "id": server.id,
        "user_id": server.user_id,
        "name": server.name,
        "server_type": server.server_type,
        "host": server.host,
        "port": server.port,
        "username": server.username,
        "password": server.password,
        "rpc_path": server.rpc_path,
        "use_ssl": server.use_ssl,
        "enabled": server.enabled,
        "created_at": server.created_at.isoformat(),
        "http_host": server.http_host,
        "http_port": server.http_port,
        "http_path": server.http_path,
        "http_username": server.http_username,
        "http_use_ssl": server.http_use_ssl,
        "http_enabled": bool(server.http_port)
    }


@app.delete("/servers/{server_id}")
async def delete_server(server_id: str, user: User = Depends(get_current_user)):
    """Delete a server configuration."""
    server = get_user_server(server_id, user)
    server.delete_instance()
    return {"status": "deleted", "message": "Server deleted successfully"}


@app.post("/servers/{server_id}/test")
async def test_server(server_id: str, user: User = Depends(get_current_user)):
    """Test connection to a server."""
    server = get_user_server(server_id, user)

    try:
        client = get_client(server)
        connected = client.check_connection()

        if connected:
            return {
                "status": "connected",
                "message": f"Successfully connected to {server.name}"
            }
        else:
            return {
                "status": "failed",
                "message": f"Could not connect to {server.name}"
            }
    except Exception as e:
        logger.error(f"Failed to test server {server_id}: {e}")
        return {
            "status": "failed",
            "message": str(e)
        }


@app.get("/login")
async def login_page():
    """Serve the login page."""
    return FileResponse("torrent_manager/static/login.html", media_type="text/html")


@app.get("/manage-servers")
async def servers_page():
    """Serve the server management page."""
    return FileResponse("torrent_manager/static/servers.html", media_type="text/html")


@app.get("/manage-api-keys")
async def api_keys_page():
    """Serve the API key management page."""
    return FileResponse("torrent_manager/static/api_keys.html", media_type="text/html")


@app.get("/")
async def root():
    """Serve the frontend index.html."""
    return FileResponse("torrent_manager/static/index.html", media_type="text/html")


@app.get("/config.js")
async def config_js():
    """Serve frontend configuration as JavaScript."""
    config = Config()
    config_js_content = f"""
// API Configuration (generated)
window.API_CONFIG = {{
    API_BASE_URL: '{config.API_BASE_URL}',
    API_HOST: '{config.API_HOST}',
    API_PORT: {config.API_PORT},
    API_BASE_PATH: '{config.API_BASE_PATH}'
}};
"""
    return Response(content=config_js_content, media_type="application/javascript")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# Torrent Management Endpoints

def find_torrent_server(info_hash: str, user: User) -> tuple:
    """Find which server has a torrent by its hash."""
    servers = TorrentServer.select().where(
        (TorrentServer.user_id == user.id) & (TorrentServer.enabled == True)
    )

    for server in servers:
        try:
            client = get_client(server)
            torrent = next(client.get_torrent(info_hash), None)
            if torrent:
                return server, client, torrent
        except Exception:
            continue

    return None, None, None


@app.get("/torrents")
async def list_torrents(
    server_id: Optional[str] = Query(None, description="Filter by server ID"),
    user: User = Depends(get_current_user)
):
    """
    List all torrents from all configured servers.

    Optionally filter by server_id to list torrents from a specific server.

    Returns detailed information about each torrent including:
    - Name, hash, size, server info
    - Progress, state (active/paused)
    - Download/upload rates
    - Peers, ratio
    """
    all_torrents = []

    if server_id:
        # Filter by specific server
        servers = [get_user_server(server_id, user)]
    else:
        # Get all enabled servers for this user
        servers = TorrentServer.select().where(
            (TorrentServer.user_id == user.id) & (TorrentServer.enabled == True)
        )

    for server in servers:
        try:
            client = get_client(server)
            torrents = list(client.list_torrents())

            # Add server info to each torrent
            for torrent in torrents:
                torrent["server_id"] = server.id
                torrent["server_name"] = server.name
                torrent["server_type"] = server.server_type

            all_torrents.extend(torrents)
        except Exception as e:
            logger.error(f"Failed to list torrents from server {server.name}: {e}")
            # Continue with other servers even if one fails

    return all_torrents


@app.post("/torrents")
async def add_torrent(request: AddTorrentRequest, user: User = Depends(get_current_user)):
    """
    Add a torrent by magnet URI or HTTP/HTTPS URL to a specific server.

    Supports:
    - Magnet URIs (magnet:?xt=urn:btih:...)
    - HTTP/HTTPS URLs to .torrent files
    """
    server = get_user_server(request.server_id, user)

    try:
        client = get_client(server)
        uri = request.uri.strip()

        if uri.startswith("magnet:"):
            result = client.add_magnet(uri, start=request.start)
        elif uri.startswith("http://") or uri.startswith("https://"):
            result = client.add_torrent_url(uri, start=request.start)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="URI must be a magnet link or HTTP/HTTPS URL"
            )

        if result:
            return {
                "message": "Torrent added successfully",
                "uri": uri,
                "server_id": server.id,
                "server_name": server.name
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to add torrent to {server.name}"
            )
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid torrent: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to add torrent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add torrent: {str(e)}"
        )


@app.post("/torrents/upload")
async def upload_torrent(
    file: UploadFile = File(...),
    server_id: str = Query(..., description="Server to add the torrent to"),
    start: bool = True,
    user: User = Depends(get_current_user)
):
    """
    Upload a .torrent file directly to a specific server.
    """
    server = get_user_server(server_id, user)
    tmp_path = None

    try:
        if not file.filename.endswith('.torrent'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must have .torrent extension"
            )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".torrent") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp.flush()
            tmp_path = tmp.name

        client = get_client(server)
        result = client.add_torrent(tmp_path, start=start)

        os.remove(tmp_path)

        if result:
            return {
                "message": "Torrent uploaded and added successfully",
                "server_id": server.id,
                "server_name": server.name
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to add torrent to {server.name}"
            )
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Invalid torrent file uploaded: {e}")
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to upload torrent: {e}")
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload torrent: {str(e)}"
        )


@app.get("/torrents/{info_hash}")
async def get_torrent_info(
    info_hash: str,
    server_id: Optional[str] = Query(None, description="Server ID (optional, will search all if not provided)"),
    user: User = Depends(get_current_user)
):
    """
    Get detailed information about a specific torrent.

    If server_id is not provided, searches across all user's servers.
    """
    if server_id:
        server = get_user_server(server_id, user)
        try:
            client = get_client(server)
            torrent = next(client.get_torrent(info_hash), None)
            if torrent:
                torrent["server_id"] = server.id
                torrent["server_name"] = server.name
                torrent["server_type"] = server.server_type
                return torrent
        except Exception as e:
            logger.error(f"Failed to get torrent: {e}")

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Torrent not found"
        )

    # Search all servers
    server, client, torrent = find_torrent_server(info_hash, user)
    if torrent:
        torrent["server_id"] = server.id
        torrent["server_name"] = server.name
        torrent["server_type"] = server.server_type
        return torrent

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Torrent not found on any server"
    )


@app.post("/torrents/{info_hash}/start")
async def start_torrent(
    info_hash: str,
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """Start a paused torrent."""
    if server_id:
        server = get_user_server(server_id, user)
        client = get_client(server)
    else:
        server, client, _ = find_torrent_server(info_hash, user)
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Torrent not found on any server"
            )

    try:
        client.start(info_hash)
        return {"message": "Torrent started", "info_hash": info_hash, "server_id": server.id}
    except Exception as e:
        logger.error(f"Failed to start torrent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start torrent: {str(e)}"
        )


@app.post("/torrents/{info_hash}/stop")
async def stop_torrent(
    info_hash: str,
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """Stop/pause a torrent."""
    if server_id:
        server = get_user_server(server_id, user)
        client = get_client(server)
    else:
        server, client, _ = find_torrent_server(info_hash, user)
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Torrent not found on any server"
            )

    try:
        client.stop(info_hash)
        return {"message": "Torrent stopped", "info_hash": info_hash, "server_id": server.id}
    except Exception as e:
        logger.error(f"Failed to stop torrent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop torrent: {str(e)}"
        )


@app.delete("/torrents/{info_hash}")
async def delete_torrent(
    info_hash: str,
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """
    Remove a torrent from the server.

    Note: This does not delete the downloaded files.
    """
    if server_id:
        server = get_user_server(server_id, user)
        client = get_client(server)
    else:
        server, client, _ = find_torrent_server(info_hash, user)
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Torrent not found on any server"
            )

    try:
        client.erase(info_hash)
        return {"message": "Torrent removed", "info_hash": info_hash, "server_id": server.id}
    except Exception as e:
        logger.error(f"Failed to remove torrent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove torrent: {str(e)}"
        )


# File Download Proxy Endpoints
from .nginx_http import HttpNginxDirectoryClient
from fastapi.responses import StreamingResponse
import posixpath


def get_http_client(server: TorrentServer) -> HttpNginxDirectoryClient:
    """Create an HTTP client for browsing and downloading files from the server."""
    if not server.http_port:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HTTP downloads not configured for this server"
        )

    host = server.http_host or server.host
    scheme = "https" if server.http_use_ssl else "http"
    path = server.http_path or "/"
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path = path + "/"

    base_url = f"{scheme}://{host}:{server.http_port}{path}"

    auth = None
    if server.http_username and server.http_password:
        auth = (server.http_username, server.http_password)

    return HttpNginxDirectoryClient(base_url=base_url, auth=auth)


@app.get("/servers/{server_id}/files")
async def list_server_files(
    server_id: str,
    path: str = Query("", description="Path relative to base directory"),
    user: User = Depends(get_current_user)
):
    """
    List files and directories at the server's HTTP download location.

    Requires the server to have HTTP download configuration (http_port set).
    The path is relative to the server's http_path base directory.
    """
    server = get_user_server(server_id, user)
    client = get_http_client(server)

    try:
        entries = client.listdir(path)
        return {
            "server_id": server_id,
            "server_name": server.name,
            "path": path,
            "entries": [
                {
                    "name": e.name,
                    "path": e.path,
                    "is_dir": e.is_dir,
                    "size": e.size,
                    "modified": e.modified.isoformat() if e.modified else None,
                    "raw_size": e.raw_size
                }
                for e in entries
            ]
        }
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}"
        )


@app.get("/servers/{server_id}/download/{file_path:path}")
async def download_file(
    server_id: str,
    file_path: str,
    user: User = Depends(get_current_user)
):
    """
    Proxy download a file from the server's HTTP download location.

    This endpoint streams the file through the API server, acting as a proxy
    so that end users don't need the server's HTTP credentials.
    """
    server = get_user_server(server_id, user)
    client = get_http_client(server)

    # Get the filename for Content-Disposition header
    filename = posixpath.basename(file_path)
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path"
        )

    try:
        # Build the URL for the file
        url = client._build_url(file_path, is_dir=False)

        # Stream the response
        response = client._session_get(url, stream=True, timeout=client.timeout)
        response.raise_for_status()

        # Get content type and length from upstream
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        content_length = response.headers.get("Content-Length")

        def generate():
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
        if content_length:
            headers["Content-Length"] = content_length

        return StreamingResponse(
            generate(),
            media_type=content_type,
            headers=headers
        )
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}"
        )


@app.get("/torrents/{info_hash}/files")
async def list_torrent_files(
    info_hash: str,
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """
    List all files belonging to a specific torrent.

    Returns the files from the torrent client along with download URLs
    if HTTP downloads are configured for the server.
    """
    if server_id:
        server = get_user_server(server_id, user)
        client = get_client(server)
        torrent = next(client.list_torrents(info_hash=info_hash, files=True), None)
    else:
        server, client, torrent = find_torrent_server(info_hash, user)

    if not torrent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Torrent not found"
        )

    # Get file list from torrent
    files = torrent.get("files", [])
    torrent_name = torrent.get("name", "")
    torrent_path = torrent.get("path", "")

    # Check if HTTP downloads are available
    http_enabled = bool(server.http_port) if server else False

    result_files = []
    for f in files:
        file_info = {
            "path": f.get("path", ""),
            "size": f.get("size", 0),
            "progress": f.get("progress", 0),
            "priority": f.get("priority", 1)
        }

        # Add download URL if HTTP is configured
        if http_enabled:
            # Construct the relative path for downloading
            # Usually files are in torrent_name/file_path
            rel_path = f.get("path", "")
            file_info["download_url"] = f"/servers/{server.id}/download/{rel_path}"

        result_files.append(file_info)

    return {
        "info_hash": info_hash,
        "name": torrent_name,
        "path": torrent_path,
        "server_id": server.id if server else None,
        "server_name": server.name if server else None,
        "http_enabled": http_enabled,
        "files": result_files
    }


# Cleanup tasks (could be run periodically with a background task)
@app.on_event("startup")
async def startup_event():
    """Run cleanup on startup."""
    logger.info("Starting Torrent Manager API")
    SessionManager.cleanup_expired_sessions()
    SessionManager.cleanup_expired_tokens()
    ApiKeyManager.cleanup_expired_keys()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
