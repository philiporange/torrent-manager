import os
import tempfile
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from torrent_manager.models import TorrentServer, User
from torrent_manager.client_factory import get_client
from torrent_manager.logger import logger
from ..schemas import AddTorrentRequest, TorrentActionRequest
from ..dependencies import get_current_user, get_user_server, find_torrent_server

router = APIRouter(tags=["torrents"])

@router.get("/torrents")
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


@router.post("/torrents")
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


@router.post("/torrents/upload")
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


@router.get("/torrents/{info_hash}")
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


@router.post("/torrents/{info_hash}/start")
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


@router.post("/torrents/{info_hash}/stop")
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


@router.delete("/torrents/{info_hash}")
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

@router.get("/torrents/{info_hash}/files")
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
