"""
FastAPI application for Torrent Manager.

Integrates multiple background services:
- Seeding monitor for auto-pause of completed torrents (with error tracking to reduce log noise)
- Torrent poller for tracking torrent status
- Transfer service for auto-download of completed torrents
- Media streaming worker for HLS transcoding via media_server

The HLS output directory is mounted at /media for serving transcoded streams.

Error handling includes reduced-frequency logging for persistent server connection
failures to prevent log spam when servers are unreachable.
"""
import asyncio
import datetime
import mimetypes
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from torrent_manager.config import Config
from torrent_manager.logger import logger
from torrent_manager.auth import SessionManager, ApiKeyManager
from torrent_manager.trackers import fetch_trackers
from torrent_manager.polling import get_poller
from torrent_manager.transfer import get_transfer_service

# Media streaming support
from media_server.config import cfg as media_cfg
from media_server import worker as media_worker

from .routes import auth, servers, torrents, admin, pages
from .routes.auth import set_session_cookie


async def seeding_monitor_task():
    """Background task to monitor seeding duration and auto-pause torrents."""
    from torrent_manager.models import TorrentServer
    from torrent_manager.client_factory import get_client
    from torrent_manager.activity import Activity
    import time

    # Track errors per server to reduce log noise for persistent failures
    server_errors = {}

    while True:
        try:
            if Config.AUTO_PAUSE_SEEDING:
                activity = Activity()

                for server in TorrentServer.select().where(TorrentServer.enabled == True):
                    try:
                        client = get_client(server)
                        for torrent in client.list_torrents():
                            info_hash = torrent['info_hash']
                            is_seeding = torrent.get('is_active') and torrent.get('complete')
                            is_private = torrent.get('is_private', False)

                            # Record status for duration tracking
                            activity.record_torrent_status(
                                info_hash,
                                server_id=server.id,
                                is_seeding=is_seeding,
                                is_private=is_private
                            )

                            # Check for auto-pause if actively seeding
                            if is_seeding:
                                duration = activity.calculate_seeding_duration(
                                    info_hash,
                                    max_interval=Config.MAX_INTERVAL
                                )
                                threshold = (Config.PRIVATE_SEED_DURATION if is_private
                                           else Config.PUBLIC_SEED_DURATION)

                                if duration >= threshold:
                                    name = torrent.get('name', info_hash)
                                    hours = duration / 3600
                                    logger.info(
                                        f"Auto-pausing {'private' if is_private else 'public'} "
                                        f"torrent: {name} (seeded {hours:.1f}h)"
                                    )
                                    client.stop(info_hash)

                        # Clear error tracking on successful server processing
                        if server.id in server_errors:
                            del server_errors[server.id]

                    except Exception as e:
                        current_time = time.time()

                        if server.id not in server_errors:
                            server_errors[server.id] = {
                                'count': 0,
                                'last_logged': 0.0
                            }

                        server_errors[server.id]['count'] += 1
                        error_count = server_errors[server.id]['count']
                        last_logged = server_errors[server.id]['last_logged']

                        # Log errors with reduced frequency for persistent failures
                        should_log = (
                            error_count == 1 or
                            error_count == 5 or
                            (current_time - last_logged) >= 600
                        )

                        if should_log:
                            if error_count == 1:
                                logger.error(f"Error monitoring server {server.name}: {e}")
                            else:
                                logger.error(
                                    f"Error monitoring server {server.name} "
                                    f"({error_count} consecutive failures): {e}"
                                )
                            server_errors[server.id]['last_logged'] = current_time

                activity.close()
        except Exception as e:
            logger.error(f"Error in seeding monitor: {e}")

        await asyncio.sleep(Config.SEEDING_CHECK_INTERVAL)


def _start_media_worker():
    """Start media_server transcoding worker in background thread."""
    if getattr(_start_media_worker, "_started", False):
        return
    # Ensure HLS output directory exists
    media_cfg.HLS_DIR.mkdir(parents=True, exist_ok=True)
    th = threading.Thread(target=media_worker.main, name="media-worker", daemon=True)
    th.start()
    logger.info(f"Media streaming worker started (HLS dir: {media_cfg.HLS_DIR})")
    _start_media_worker._started = True


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("Starting Torrent Manager API")
    SessionManager.cleanup_expired_sessions()
    SessionManager.cleanup_expired_tokens()
    ApiKeyManager.cleanup_expired_keys()

    # Start media streaming worker
    _start_media_worker()

    # Fetch and cache public tracker list
    await fetch_trackers()

    # Start background seeding monitor
    monitor_task = asyncio.create_task(seeding_monitor_task())
    logger.info(f"Seeding monitor started (interval: {Config.SEEDING_CHECK_INTERVAL}s, "
                f"auto-pause: {Config.AUTO_PAUSE_SEEDING})")

    # Start background torrent poller
    poller = get_poller()
    poller_task = asyncio.create_task(poller.run())

    # Start background transfer service
    transfer_service = get_transfer_service()
    transfer_task = asyncio.create_task(transfer_service.run())

    yield

    # Shutdown
    transfer_service.stop()
    transfer_task.cancel()
    poller.stop()
    poller_task.cancel()
    monitor_task.cancel()
    try:
        await transfer_task
    except asyncio.CancelledError:
        pass
    try:
        await poller_task
    except asyncio.CancelledError:
        pass
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    logger.info("Torrent Manager API shutdown complete")


app = FastAPI(
    title="Torrent Manager API",
    description="API for managing torrent servers (rTorrent and Transmission) with secure session-based authentication",
    version="2.0.0",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="torrent_manager/static"), name="static")

# Mount HLS media output for streaming
media_cfg.HLS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_cfg.HLS_DIR), check_dir=False), name="hls_media")

# Register HLS MIME types
mimetypes.add_type("application/vnd.apple.mpegurl", ".m3u8")
mimetypes.add_type("video/mp2t", ".ts")

# Add CORS middleware - allow all origins (private tool)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def session_renewal_middleware(request: Request, call_next):
    """
    Middleware to handle session renewal with sliding expiration.

    Only renews session cookie on index page loads to reduce overhead.
    Always handles setting session cookie when created from remember-me token.
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
        # Only renew on index page loads
        elif request.url.path == "/":
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
