import os
import re
import shutil
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
from torrent_manager.magnet_resolver import is_resolver_enabled, resolve_magnet, MagnetResolverError
from torrent_manager.activity import Activity
from torrent_manager.polling import get_poller
from ..schemas import AddTorrentRequest, TorrentActionRequest, SetLabelsRequest, AddLabelRequest
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


def add_torrent_from_file(client, torrent_path: str, start: bool, labels: list, augment: bool = True) -> bool:
    """
    Add a torrent from a .torrent file, optionally augmenting with public trackers.

    Args:
        client: Torrent client instance
        torrent_path: Path to the .torrent file
        start: Whether to start the torrent immediately
        labels: Labels to apply to the torrent
        augment: Whether to augment with public trackers

    Returns:
        True if successful
    """
    if augment and is_augmentation_enabled():
        try:
            torrent = TorrentFile(torrent_path)
            if not torrent.is_private:
                trackers = get_cached_trackers()
                torrent.add_trackers(trackers)
                torrent.save(torrent_path)
                logger.debug(f"Augmented torrent with {len(trackers)} trackers")
        except Exception as e:
            logger.warning(f"Failed to augment torrent file: {e}")

    return client.add_torrent(torrent_path, start=start, labels=labels)


def _cleanup_torrent_path(torrent_path: Optional[str]):
    """Clean up a temporary torrent file and its parent directory if applicable."""
    if not torrent_path:
        return
    parent_dir = os.path.dirname(torrent_path)
    if "magnet_resolve_" in parent_dir:
        shutil.rmtree(parent_dir, ignore_errors=True)
    elif os.path.exists(torrent_path):
        os.remove(torrent_path)


@router.post("/torrents")
async def add_torrent(request: AddTorrentRequest, user: User = Depends(get_current_user)):
    """
    Add a torrent by info hash, magnet URI, or HTTP/HTTPS URL to a specific server.

    Supports:
    - Info hashes (40 hex chars or 32 base32 chars)
    - Magnet URIs (magnet:?xt=urn:btih:...)
    - HTTP/HTTPS URLs to .torrent files

    Magnet URIs are first converted to .torrent files using magnet2torrent
    (downloads from cache sites or peers), then uploaded to the server.

    Public torrents (magnets, info hashes, or non-private .torrent files) are
    augmented with additional public trackers to speed up peer discovery.
    """
    server = get_user_server(request.server_id, user)
    torrent_path = None

    try:
        client = get_client(server)
        uri = request.uri.strip()

        # Convert info hash to magnet URI
        if is_info_hash(uri):
            uri = info_hash_to_magnet(uri)
            logger.info(f"Converted info hash to magnet URI")

        if uri.startswith("magnet:"):
            # Use magnet resolver to convert magnet to .torrent file
            if is_resolver_enabled():
                try:
                    logger.info(f"Resolving magnet URI to .torrent file")
                    torrent_path, info_hash = resolve_magnet(uri)
                    result = add_torrent_from_file(
                        client, torrent_path,
                        start=request.start,
                        labels=request.labels,
                        augment=True
                    )
                except MagnetResolverError as e:
                    logger.warning(f"Magnet resolution failed, falling back to direct add: {e}")
                    # Fall back to direct magnet add
                    uri = augment_magnet_with_trackers(uri)
                    result = client.add_magnet(uri, start=request.start, labels=request.labels)
            else:
                # Resolver disabled, use direct magnet add
                uri = augment_magnet_with_trackers(uri)
                result = client.add_magnet(uri, start=request.start, labels=request.labels)
        elif uri.startswith("http://") or uri.startswith("https://"):
            result = client.add_torrent_url(uri, start=request.start, labels=request.labels)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Input must be an info hash, magnet link, or HTTP/HTTPS URL"
            )

        # Clean up temporary torrent file and its directory
        _cleanup_torrent_path(torrent_path)

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
        _cleanup_torrent_path(torrent_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to add torrent: {e}")
        _cleanup_torrent_path(torrent_path)
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


def _get_info_hash_folder(server: TorrentServer, remote_path: str, info_hash: str) -> Optional[str]:
    """
    Get the local path to the info_hash folder for deletion.

    rTorrent stores data in: download_dir/<INFO_HASH>/data/<TorrentName>
    This function returns the local mount path to the <INFO_HASH>/ folder.

    Returns None if mount_path is not configured or path doesn't match expected structure.
    """
    if not server.mount_path or not server.download_dir or not remote_path:
        return None

    download_dir = server.download_dir.rstrip("/") + "/"
    if not remote_path.startswith(download_dir):
        return None

    # Get relative path: "<HASH>/data/<TorrentName>" or similar
    relative_path = remote_path[len(download_dir):]

    # Find the info_hash folder in the path (case-insensitive match)
    parts = relative_path.split("/")
    for i, part in enumerate(parts):
        if part.upper() == info_hash.upper():
            # Return path up to and including the info_hash folder
            hash_folder = "/".join(parts[:i + 1])
            local_path = os.path.join(server.mount_path, hash_folder)
            return _validate_delete_path(server.mount_path, local_path, info_hash)

    # No info_hash folder found - refuse to delete
    logger.warning(f"No info_hash folder found in path: {remote_path}")
    return None


def _validate_delete_path(mount_path: str, path: str, info_hash: str) -> Optional[str]:
    """
    Validate that a path is safe to delete.

    Returns the path if valid, None otherwise.
    Checks:
    - No '..' components (path traversal)
    - Path is within mount_path (not the mount itself or above)
    - Folder being deleted is named with the info_hash
    """
    # Normalize paths to resolve any '..' or symlinks
    mount_path = os.path.normpath(os.path.realpath(mount_path))
    path = os.path.normpath(os.path.realpath(path))

    # Check for path traversal attempts
    if ".." in path:
        logger.warning(f"Path traversal attempt blocked: {path}")
        return None

    # Path must start with mount_path
    if not path.startswith(mount_path + "/"):
        logger.warning(f"Path not within mount: {path} (mount: {mount_path})")
        return None

    # Path must not be the mount_path itself
    if path == mount_path:
        logger.warning(f"Refusing to delete mount root: {path}")
        return None

    # The folder being deleted must be named with the info_hash
    folder_name = os.path.basename(path)
    if folder_name.upper() != info_hash.upper():
        logger.warning(f"Folder name '{folder_name}' does not match info_hash '{info_hash}'")
        return None

    return path


@router.delete("/torrents/{info_hash}")
async def delete_torrent(
    info_hash: str,
    server_id: Optional[str] = Query(None, description="Server ID"),
    delete_data: bool = Query(False, description="Also delete downloaded files"),
    user: User = Depends(get_current_user)
):
    """
    Remove a torrent from the server.

    Use delete_data=true to also delete the downloaded files.
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
        # For rTorrent, handle data deletion at API level using mount_path
        # because rTorrent's XMLRPC doesn't support delete-with-data
        data_path = None
        if delete_data and server.server_type == "rtorrent" and server.mount_path:
            try:
                remote_path = client.base_path(info_hash)
                data_path = _get_info_hash_folder(server, remote_path, info_hash)
                logger.debug(f"Will delete info_hash folder: {remote_path} -> {data_path}")
            except Exception as e:
                logger.warning(f"Failed to get base path for {info_hash}: {e}")

        # For Transmission, pass delete_data directly (native support)
        # For rTorrent, pass delete_data=False since we handle it here
        if server.server_type == "transmission":
            client.erase(info_hash, delete_data=delete_data)
        else:
            client.erase(info_hash, delete_data=False)

        # Delete data for rTorrent using the local mount path
        if delete_data and data_path and os.path.exists(data_path):
            try:
                if os.path.isdir(data_path):
                    shutil.rmtree(data_path)
                else:
                    os.remove(data_path)
                logger.info(f"Deleted data for {info_hash}: {data_path}")
            except Exception as e:
                logger.error(f"Failed to delete data for {info_hash}: {e}")

        # Immediately poll the server to update cache
        poller = get_poller()
        await poller.poll_server(server)

        msg = "Torrent and data removed" if delete_data else "Torrent removed"
        return {"message": msg, "info_hash": info_hash, "server_id": server.id}
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
    torrent_base_path = torrent.get("base_path", "")

    # Check if downloads are available (HTTP or local mount)
    http_enabled = bool(server.http_port or server.mount_path) if server else False
    # Check if streaming is available (requires mount_path)
    stream_enabled = bool(server.mount_path) if server else False

    # Compute the base relative path by removing the server's download_dir prefix
    # e.g., base_path="/home/user/downloads/HASH/data/TorrentName" with
    # download_dir="/home/user/downloads/" gives "HASH/data/TorrentName"
    base_rel_path = ""
    if server and server.download_dir and torrent_base_path:
        download_dir = server.download_dir.rstrip("/") + "/"
        if torrent_base_path.startswith(download_dir):
            base_rel_path = torrent_base_path[len(download_dir):]
        else:
            # Fall back to just the torrent name if paths don't match
            base_rel_path = torrent_name
    elif torrent_name:
        # No download_dir configured, fall back to torrent name
        base_rel_path = torrent_name

    # Streamable file extensions
    streamable_exts = {
        ".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm", ".m4v",
        ".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".m4b"
    }

    result_files = []
    for f in files:
        file_info = {
            "path": f.get("path", ""),
            "size": f.get("size", 0),
            "progress": f.get("progress", 0),
            "priority": f.get("priority", 1)
        }

        # Construct the relative path for downloading/streaming
        # For multi-file torrents: base_rel_path/file_path
        # For single-file torrents: base_rel_path (which is the file)
        file_path = f.get("path", "")
        is_multi_file = torrent.get("is_multi_file", False)
        if is_multi_file and base_rel_path:
            rel_path = f"{base_rel_path}/{file_path}"
        else:
            rel_path = base_rel_path if base_rel_path else file_path

        # Add download URL if HTTP or local mount is configured
        if http_enabled:
            file_info["download_url"] = f"/servers/{server.id}/download/{rel_path}"

        # Add stream URL for streamable files if mount_path is configured
        if stream_enabled:
            file_ext = "." + rel_path.rsplit(".", 1)[-1].lower() if "." in rel_path else ""
            if file_ext in streamable_exts:
                file_info["stream_url"] = f"/servers/{server.id}/stream/{rel_path}"

        result_files.append(file_info)

    return {
        "info_hash": info_hash,
        "name": torrent_name,
        "path": torrent_base_path,
        "server_id": server.id if server else None,
        "server_name": server.name if server else None,
        "http_enabled": http_enabled,
        "stream_enabled": stream_enabled,
        "files": result_files
    }


@router.get("/torrents/{info_hash}/labels")
async def get_torrent_labels(
    info_hash: str,
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """Get labels for a specific torrent."""
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
        labels = client.get_labels(info_hash)
        return {"info_hash": info_hash, "labels": labels, "server_id": server.id}
    except Exception as e:
        logger.error(f"Failed to get labels: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get labels: {str(e)}"
        )


@router.put("/torrents/{info_hash}/labels")
async def set_torrent_labels(
    info_hash: str,
    request: SetLabelsRequest,
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """Set all labels for a torrent (replaces existing labels)."""
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
        result = client.set_labels(info_hash, request.labels)
        return {"info_hash": info_hash, "labels": request.labels, "server_id": server.id}
    except Exception as e:
        logger.error(f"Failed to set labels: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set labels: {str(e)}"
        )


@router.post("/torrents/{info_hash}/labels")
async def add_torrent_label(
    info_hash: str,
    request: AddLabelRequest,
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """Add a label to a torrent without removing existing labels."""
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
        result = client.add_label(info_hash, request.label)
        labels = client.get_labels(info_hash)
        return {"info_hash": info_hash, "labels": labels, "server_id": server.id}
    except Exception as e:
        logger.error(f"Failed to add label: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add label: {str(e)}"
        )


@router.delete("/torrents/{info_hash}/labels/{label}")
async def remove_torrent_label(
    info_hash: str,
    label: str,
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """Remove a label from a torrent."""
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
        result = client.remove_label(info_hash, label)
        labels = client.get_labels(info_hash)
        return {"info_hash": info_hash, "labels": labels, "server_id": server.id}
    except Exception as e:
        logger.error(f"Failed to remove label: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove label: {str(e)}"
        )
