"""
Server management routes for torrent server configuration and file access.

Provides endpoints for:
- CRUD operations on torrent server configurations
- File listing from server download directories
- Direct file downloads (via HTTP proxy or local mount)
- HLS streaming for media files via media_server integration

Streaming requires mount_path to be configured for the server, as transcoding
needs local file access. Files are transcoded to HLS format on-demand.
"""
import os
import secrets
import posixpath
from pathlib import Path
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import StreamingResponse, FileResponse
from starlette.concurrency import run_in_threadpool
from torrent_manager.models import TorrentServer, User
from torrent_manager.client_factory import get_client
from torrent_manager.logger import logger
from ..schemas import AddServerRequest, UpdateServerRequest
from ..dependencies import get_current_user, get_user_server, get_http_client

# Media streaming support
from media_server import jobs as media_jobs
from media_server.jobs import TranscodeParams

router = APIRouter(tags=["servers"])

@router.post("/servers")
async def add_server(request: AddServerRequest, user: User = Depends(get_current_user)):
    """Add a new torrent server configuration."""
    if request.server_type not in ("rtorrent", "transmission"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="server_type must be 'rtorrent' or 'transmission'"
        )

    # If this is the first server or marked as default, clear other defaults
    existing_servers = TorrentServer.select().where(TorrentServer.user_id == user.id)
    is_first = existing_servers.count() == 0
    is_default = request.is_default or is_first

    if is_default:
        TorrentServer.update(is_default=False).where(TorrentServer.user_id == user.id).execute()

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
        is_default=is_default,
        http_host=request.http_host,
        http_port=request.http_port,
        http_path=request.http_path,
        http_username=request.http_username,
        http_password=request.http_password,
        http_use_ssl=request.http_use_ssl,
        mount_path=request.mount_path,
        download_dir=request.download_dir,
        auto_download_enabled=request.auto_download_enabled,
        auto_download_path=request.auto_download_path,
        auto_delete_remote=request.auto_delete_remote,
        ssh_host=request.ssh_host,
        ssh_port=request.ssh_port,
        ssh_user=request.ssh_user,
        ssh_key_path=request.ssh_key_path
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
        "is_default": server.is_default,
        "created_at": server.created_at.isoformat(),
        "http_host": server.http_host,
        "http_port": server.http_port,
        "http_path": server.http_path,
        "http_username": server.http_username,
        "http_use_ssl": server.http_use_ssl,
        "http_enabled": bool(server.http_port),
        "mount_path": server.mount_path,
        "download_dir": server.download_dir,
        "auto_download_enabled": server.auto_download_enabled,
        "auto_download_path": server.auto_download_path,
        "auto_delete_remote": server.auto_delete_remote,
        "ssh_host": server.ssh_host,
        "ssh_port": server.ssh_port,
        "ssh_user": server.ssh_user,
        "ssh_key_path": server.ssh_key_path
    }


@router.get("/servers")
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
            "is_default": s.is_default,
            "created_at": s.created_at.isoformat(),
            "http_host": s.http_host,
            "http_port": s.http_port,
            "http_path": s.http_path,
            "http_username": s.http_username,
            "http_use_ssl": s.http_use_ssl,
            "http_enabled": bool(s.http_port),
            "mount_path": s.mount_path,
            "download_dir": s.download_dir,
            "auto_download_enabled": s.auto_download_enabled,
            "auto_download_path": s.auto_download_path,
            "auto_delete_remote": s.auto_delete_remote,
            "ssh_host": s.ssh_host,
            "ssh_port": s.ssh_port,
            "ssh_user": s.ssh_user,
            "ssh_key_path": s.ssh_key_path
        }
        for s in servers
    ]


@router.get("/servers/{server_id}")
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
        "is_default": server.is_default,
        "created_at": server.created_at.isoformat(),
        "http_host": server.http_host,
        "http_port": server.http_port,
        "http_path": server.http_path,
        "http_username": server.http_username,
        "http_use_ssl": server.http_use_ssl,
        "http_enabled": bool(server.http_port),
        "mount_path": server.mount_path,
        "download_dir": server.download_dir,
        "auto_download_enabled": server.auto_download_enabled,
        "auto_download_path": server.auto_download_path,
        "auto_delete_remote": server.auto_delete_remote,
        "ssh_host": server.ssh_host,
        "ssh_port": server.ssh_port,
        "ssh_user": server.ssh_user,
        "ssh_key_path": server.ssh_key_path
    }


@router.put("/servers/{server_id}")
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
    if request.mount_path is not None:
        server.mount_path = request.mount_path
    if request.download_dir is not None:
        server.download_dir = request.download_dir
    if request.auto_download_enabled is not None:
        server.auto_download_enabled = request.auto_download_enabled
    if request.auto_download_path is not None:
        server.auto_download_path = request.auto_download_path
    if request.auto_delete_remote is not None:
        server.auto_delete_remote = request.auto_delete_remote
    if request.ssh_host is not None:
        server.ssh_host = request.ssh_host
    if request.ssh_port is not None:
        server.ssh_port = request.ssh_port
    if request.ssh_user is not None:
        server.ssh_user = request.ssh_user
    if request.ssh_key_path is not None:
        server.ssh_key_path = request.ssh_key_path
    if request.is_default is not None:
        if request.is_default:
            # Clear other defaults when setting this one as default
            TorrentServer.update(is_default=False).where(TorrentServer.user_id == user.id).execute()
        server.is_default = request.is_default

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
        "http_enabled": bool(server.http_port),
        "is_default": server.is_default,
        "mount_path": server.mount_path,
        "download_dir": server.download_dir,
        "auto_download_enabled": server.auto_download_enabled,
        "auto_download_path": server.auto_download_path,
        "auto_delete_remote": server.auto_delete_remote,
        "ssh_host": server.ssh_host,
        "ssh_port": server.ssh_port,
        "ssh_user": server.ssh_user,
        "ssh_key_path": server.ssh_key_path
    }


@router.delete("/servers/{server_id}")
async def delete_server(server_id: str, user: User = Depends(get_current_user)):
    """Delete a server configuration."""
    server = get_user_server(server_id, user)
    server.delete_instance()
    return {"status": "deleted", "message": "Server deleted successfully"}


@router.post("/servers/{server_id}/test")
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

def _list_local_dir(mount_path: str, rel_path: str) -> list:
    """List files from a local mount path, returns list of entry dicts."""
    base = Path(mount_path)
    target = base / rel_path if rel_path else base

    if not target.exists():
        return None
    if not target.is_dir():
        return None

    # Ensure we don't traverse outside mount_path
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        return None

    entries = []
    for item in target.iterdir():
        stat = item.stat()
        rel = str(item.relative_to(base))
        entries.append({
            "name": item.name,
            "path": rel,
            "is_dir": item.is_dir(),
            "size": stat.st_size if not item.is_dir() else None,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "raw_size": None
        })
    return entries


@router.get("/servers/{server_id}/files")
async def list_server_files(
    server_id: str,
    path: str = Query("", description="Path relative to base directory"),
    user: User = Depends(get_current_user)
):
    """
    List files and directories at the server's download location.

    If mount_path is configured and available, uses local filesystem.
    Otherwise falls back to HTTP download server (requires http_port set).
    """
    server = get_user_server(server_id, user)

    # Try local mount first
    if server.mount_path:
        local_entries = _list_local_dir(server.mount_path, path)
        if local_entries is not None:
            return {
                "server_id": server_id,
                "server_name": server.name,
                "path": path,
                "source": "local",
                "entries": local_entries
            }

    # Fall back to HTTP
    client = get_http_client(server)
    try:
        entries = client.listdir(path)
        return {
            "server_id": server_id,
            "server_name": server.name,
            "path": path,
            "source": "http",
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


def _get_local_file_path(mount_path: str, file_path: str) -> Path | None:
    """Get validated local file path, or None if not available."""
    base = Path(mount_path)
    target = base / file_path

    if not target.exists() or not target.is_file():
        return None

    # Ensure we don't traverse outside mount_path
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        return None

    return target


@router.get("/servers/{server_id}/download/{file_path:path}")
async def download_file(
    server_id: str,
    file_path: str,
    request: Request,
    user: User = Depends(get_current_user)
):
    """
    Download a file from the server's download location.

    If mount_path is configured and available, serves directly from local filesystem.
    Otherwise proxies through the HTTP download server.
    Supports HTTP Range requests for media seeking.
    """
    server = get_user_server(server_id, user)

    # Get the filename for Content-Disposition header
    filename = posixpath.basename(file_path)
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path"
        )

    # Try local mount first
    if server.mount_path:
        local_path = _get_local_file_path(server.mount_path, file_path)
        if local_path:
            return FileResponse(
                path=local_path,
                filename=filename,
                media_type=None  # Let FastAPI determine content type
            )

    # Fall back to HTTP proxy
    client = get_http_client(server)
    try:
        # Build the URL for the file
        url = client._build_url(file_path, is_dir=False)

        # Forward range header if present for seeking support
        request_headers = {}
        range_header = request.headers.get("Range")
        if range_header:
            request_headers['Range'] = range_header

        # Stream the response
        response = await run_in_threadpool(
            client._session_get,
            url,
            stream=True,
            timeout=client.timeout,
            headers=request_headers
        )
        response.raise_for_status()

        # Get headers from upstream
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        content_length = response.headers.get("Content-Length")
        content_range = response.headers.get("Content-Range")
        accept_ranges = response.headers.get("Accept-Ranges", "bytes")

        def generate():
            try:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        yield chunk
            finally:
                response.close()

        headers = {
            "Accept-Ranges": accept_ranges
        }
        if content_length:
            headers["Content-Length"] = content_length
        if content_range:
            headers["Content-Range"] = content_range

        # Return 206 for partial content, 200 for full file
        status_code = 206 if content_range else 200

        return StreamingResponse(
            generate(),
            status_code=status_code,
            media_type=content_type,
            headers=headers
        )
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}"
        )


# Streaming endpoints for HLS transcoding

STREAMABLE_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".m4v",
    ".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".m4b"
}


@router.post("/servers/{server_id}/stream/{file_path:path}")
async def stream_file(
    server_id: str,
    file_path: str,
    user: User = Depends(get_current_user)
):
    """
    Start HLS streaming for a media file.

    Requires mount_path to be configured for the server. Creates a transcoding
    job that converts the file to HLS format for browser playback.

    Returns job info including the playlist URL for playback.
    """
    server = get_user_server(server_id, user)

    if not server.mount_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Streaming requires mount_path to be configured for this server"
        )

    # Validate and get local file path
    local_path = _get_local_file_path(server.mount_path, file_path)
    if not local_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on local mount"
        )

    # Check if file is a streamable media type
    if local_path.suffix.lower() not in STREAMABLE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {local_path.suffix} is not streamable"
        )

    try:
        # Queue transcoding job via media_server
        job_info = media_jobs.enqueue_job(local_path)

        return {
            "job_id": job_info.job_id,
            "playlist": job_info.playlist_url,
            "duration": job_info.duration,
            "status": job_info.status,
            "media_type": job_info.params.media_type,
            "filename": local_path.name,
            "server_id": server_id
        }
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found"
        )
    except Exception as e:
        logger.error(f"Failed to start streaming: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start streaming: {str(e)}"
        )


@router.get("/servers/{server_id}/stream/{job_id}/info")
async def get_stream_info(
    server_id: str,
    job_id: str,
    user: User = Depends(get_current_user)
):
    """
    Get status and progress of a streaming job.
    """
    # Verify user has access to this server
    get_user_server(server_id, user)

    job_info = media_jobs.get_job(job_id)
    if not job_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Streaming job not found"
        )

    return {
        "job_id": job_info.job_id,
        "playlist": job_info.playlist_url,
        "duration": job_info.duration,
        "status": job_info.status,
        "transcoded": job_info.transcoded,
        "progress": (job_info.transcoded / job_info.duration * 100) if job_info.duration > 0 else 0,
        "media_type": job_info.params.media_type
    }
