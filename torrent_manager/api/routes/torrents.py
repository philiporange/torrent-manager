import os
import re
import tempfile
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from torrent_manager.models import TorrentServer, User
from torrent_manager.client_factory import get_client
from torrent_manager.config import Config
from torrent_manager.logger import logger
from torrent_manager.magnet_link import MagnetLink
from torrent_manager.torrent_file import TorrentFile
from torrent_manager.trackers import get_cached_trackers, is_augmentation_enabled
from torrent_manager.activity import Activity
from torrent_manager.polling import get_poller
from ..schemas import AddTorrentRequest, TorrentActionRequest
from ..dependencies import get_current_user, get_user_server, find_torrent_server

router = APIRouter(tags=["torrents"])

# Regex patterns for info hash detection
INFO_HASH_HEX_PATTERN = re.compile(r'^[a-fA-F0-9]{40}$')
INFO_HASH_BASE32_PATTERN = re.compile(r'^[A-Za-z2-7]{32}$')


def is_info_hash(value: str) -> bool:
    """Check if a string is a valid info hash (40 hex chars or 32 base32 chars)."""
    return bool(INFO_HASH_HEX_PATTERN.match(value) or INFO_HASH_BASE32_PATTERN.match(value))


def info_hash_to_magnet(info_hash: str) -> str:
    """Convert an info hash to a magnet URI."""
    return f"magnet:?xt=urn:btih:{info_hash.upper()}"

@router.get("/torrents")
async def list_torrents(
    server_id: Optional[str] = Query(None, description="Filter by server ID"),
    user: User = Depends(get_current_user)
):
    """
    List all torrents from all configured servers.

    Returns cached torrent data from the background polling service.
    Optionally filter by server_id to list torrents from a specific server.

    Returns detailed information about each torrent including:
    - Name, hash, size, server info
    - Progress, state (active/paused)
    - Download/upload rates
    - Peers, ratio
    - Seeding duration and threshold (for completed torrents)
    """
    poller = get_poller()
    return poller.get_cached_torrents(user.id, server_id)


def augment_magnet_with_trackers(magnet_uri: str) -> str:
    """
    Augment a magnet URI with cached public trackers.

    Magnet links are always considered public (no private flag),
    so trackers are added if augmentation is enabled.
    """
    if not is_augmentation_enabled():
        return magnet_uri

    try:
        magnet = MagnetLink(magnet_uri)
        for tracker in get_cached_trackers():
            magnet.add_tracker(tracker)
        augmented = magnet.to_uri()
        logger.debug(f"Augmented magnet with {len(get_cached_trackers())} trackers")
        return augmented
    except Exception as e:
        logger.warning(f"Failed to augment magnet URI: {e}")
        return magnet_uri


@router.post("/torrents")
async def add_torrent(request: AddTorrentRequest, user: User = Depends(get_current_user)):
    """
    Add a torrent by info hash, magnet URI, or HTTP/HTTPS URL to a specific server.

    Supports:
    - Info hashes (40 hex chars or 32 base32 chars)
    - Magnet URIs (magnet:?xt=urn:btih:...)
    - HTTP/HTTPS URLs to .torrent files

    Public torrents (magnets, info hashes, or non-private .torrent files) are
    augmented with additional public trackers to speed up peer discovery.
    """
    server = get_user_server(request.server_id, user)

    try:
        client = get_client(server)
        uri = request.uri.strip()

        # Convert info hash to magnet URI
        if is_info_hash(uri):
            uri = info_hash_to_magnet(uri)
            logger.info(f"Converted info hash to magnet URI")

        if uri.startswith("magnet:"):
            uri = augment_magnet_with_trackers(uri)
            result = client.add_magnet(uri, start=request.start)
        elif uri.startswith("http://") or uri.startswith("https://"):
            result = client.add_torrent_url(uri, start=request.start)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Input must be an info hash, magnet link, or HTTP/HTTPS URL"
            )

        if result:
            # Immediately poll the server to update cache
            poller = get_poller()
            await poller.poll_server(server)

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

    Public torrents (non-private) are augmented with additional public
    trackers to speed up peer discovery.
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

        # Augment public torrents with additional trackers
        if is_augmentation_enabled():
            try:
                torrent = TorrentFile(tmp_path)
                if not torrent.is_private:
                    trackers = get_cached_trackers()
                    torrent.add_trackers(trackers)
                    torrent.save(tmp_path)
                    logger.debug(f"Augmented torrent with {len(trackers)} trackers")
            except Exception as e:
                logger.warning(f"Failed to augment torrent file: {e}")

        client = get_client(server)
        result = client.add_torrent(tmp_path, start=start)

        os.remove(tmp_path)

        if result:
            # Immediately poll the server to update cache
            poller = get_poller()
            await poller.poll_server(server)

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

        # Check if this completed torrent has already met its seeding threshold
        if Config.AUTO_PAUSE_SEEDING:
            torrent = next(client.list_torrents(info_hash=info_hash), None)
            if torrent and torrent.get("complete"):
                activity = Activity()
                try:
                    is_private = torrent.get("is_private", False)
                    duration = activity.calculate_seeding_duration(
                        info_hash, max_interval=Config.MAX_INTERVAL
                    )
                    threshold = (Config.PRIVATE_SEED_DURATION if is_private
                                else Config.PUBLIC_SEED_DURATION)

                    if duration >= threshold:
                        client.stop(info_hash)
                        logger.info(f"Re-paused torrent {info_hash} (already seeded {duration/3600:.1f}h)")
                finally:
                    activity.close()

        # Immediately poll the server to update cache
        poller = get_poller()
        await poller.poll_server(server)

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

        # Immediately poll the server to update cache
        poller = get_poller()
        await poller.poll_server(server)

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

        # Immediately poll the server to update cache
        poller = get_poller()
        await poller.poll_server(server)

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
