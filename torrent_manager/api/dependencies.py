from typing import Optional, Tuple
from fastapi import Request, HTTPException, status, Depends
from torrent_manager.auth import SessionManager, UserManager, ApiKeyManager
from torrent_manager.models import User, TorrentServer
from torrent_manager.client_factory import get_client
from torrent_manager.nginx_http import HttpNginxDirectoryClient
from torrent_manager.logger import logger
from .constants import SESSION_COOKIE_NAME, REMEMBER_ME_COOKIE_NAME

def get_client_info(request: Request) -> Tuple[Optional[str], Optional[str]]:
    """Extract client IP and user agent from request."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent

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

async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency to ensure the user is an admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return user

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
