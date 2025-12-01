import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from torrent_manager.config import Config
from torrent_manager.logger import logger
from torrent_manager.auth import SessionManager, ApiKeyManager
from torrent_manager.trackers import fetch_trackers

from .routes import auth, servers, torrents, admin, pages
from .routes.auth import set_session_cookie

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

# Include routers
app.include_router(auth.router)
app.include_router(servers.router)
app.include_router(torrents.router)
app.include_router(admin.router)
app.include_router(pages.router)

# Cleanup tasks (could be run periodically with a background task)
@app.on_event("startup")
async def startup_event():
    """Run cleanup and initialization on startup."""
    logger.info("Starting Torrent Manager API")
    SessionManager.cleanup_expired_sessions()
    SessionManager.cleanup_expired_tokens()
    ApiKeyManager.cleanup_expired_keys()

    # Fetch and cache public tracker list
    await fetch_trackers()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
