import os
import re
import tempfile
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from torrent_manager.models import TorrentServer, TransferJob, UserTorrentSettings, User
from torrent_manager.client_factory import get_client
from torrent_manager.config import Config
from torrent_manager.logger import logger
from torrent_manager.torrent_file import TorrentFile
from torrent_manager.trackers import get_cached_trackers, is_augmentation_enabled
from torrent_manager.activity import Activity
from torrent_manager.polling import get_poller
from torrent_manager.callbacks import dispatch_event, TorrentEvent
from torrent_manager.torrent_adder import add_torrent_to_server
from ..schemas import (
    AddTorrentRequest, TorrentActionRequest, SetLabelsRequest, AddLabelRequest,
    StartTransferRequest, UpdateTorrentSettingsRequest
)
from ..dependencies import get_current_user, get_user_server, find_torrent_server

router = APIRouter(tags=["torrents"])


def check_server_available(server):
    """
    Check if a server is available (not in circuit breaker cooldown).

    Raises HTTPException if the server is in cooldown.
    """
    import time
    poller = get_poller()
    cache = poller._cache.get(server.id)
    if cache and cache.skip_until > 0 and cache.skip_until > time.time():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Server {server.name} is temporarily unavailable (in cooldown until {time.ctime(cache.skip_until)}). Recent error: {cache.error}"
        )


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

@router.post("/torrents")
async def add_torrent(request: AddTorrentRequest, user: User = Depends(get_current_user)):
    """Add a torrent by info hash, magnet URI, or HTTP/HTTPS URL to a specific server."""
    server = get_user_server(request.server_id, user)
    check_server_available(server)

    try:
        result = await add_torrent_to_server(
            server,
            request.uri,
            start=request.start,
            labels=request.labels,
            user_id=user.id,
        )
        return {
            "message": "Torrent added successfully",
            "uri": result["uri"],
            "server_id": server.id,
            "server_name": server.name,
        }
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
    check_server_available(server)
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

        # Parse torrent to get name and augment if needed
        torrent_name = None
        try:
            torrent = TorrentFile(tmp_path)
            torrent_name = torrent.info.get('name')

            # Augment public torrents with additional trackers
            if is_augmentation_enabled() and not torrent.is_private:
                trackers = get_cached_trackers()
                torrent.add_trackers(trackers)
                torrent.save(tmp_path)
                logger.debug(f"Augmented torrent with {len(trackers)} trackers")
        except Exception as e:
            logger.warning(f"Failed to parse/augment torrent file: {e}")

        client = get_client(server)
        result = client.add_torrent(tmp_path, start=start)

        os.remove(tmp_path)

        if result:
            # Immediately poll the server to update cache
            poller = get_poller()
            await poller.poll_server(server)

            # Dispatch callback for newly added torrent
            torrents = poller.get_cached_torrents(user.id, server.id)
            if torrents:
                # The most recently added torrent is likely the one we just uploaded
                await dispatch_event(TorrentEvent.ADDED, torrents[-1])

            return {
                "message": "Torrent uploaded and added successfully",
                "server_id": server.id,
                "server_name": server.name,
                "torrent_name": torrent_name
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


@router.post("/torrents/upload/batch")
async def upload_torrents_batch(
    files: list[UploadFile] = File(...),
    server_id: str = Query(..., description="Server to add torrents to"),
    start: bool = True,
    user: User = Depends(get_current_user)
):
    """
    Upload multiple .torrent files at once to a specific server.

    Returns detailed results for each file including success/failure status.
    Processing continues even if some files fail.
    """
    server = get_user_server(server_id, user)
    check_server_available(server)
    client = get_client(server)

    results = []
    success_count = 0
    failure_count = 0

    for file in files:
        tmp_path = None
        result_entry = {
            "filename": file.filename,
            "success": False,
            "message": "",
            "torrent_name": None
        }

        try:
            if not file.filename.endswith('.torrent'):
                result_entry["message"] = "File must have .torrent extension"
                failure_count += 1
                results.append(result_entry)
                continue

            with tempfile.NamedTemporaryFile(delete=False, suffix=".torrent") as tmp:
                content = await file.read()
                tmp.write(content)
                tmp.flush()
                tmp_path = tmp.name

            # Try to get torrent name for better feedback
            torrent_name = None
            try:
                torrent = TorrentFile(tmp_path)
                torrent_name = torrent.info.get('name')
                result_entry["torrent_name"] = torrent_name

                # Augment public torrents with additional trackers
                if is_augmentation_enabled() and not torrent.is_private:
                    trackers = get_cached_trackers()
                    torrent.add_trackers(trackers)
                    torrent.save(tmp_path)
            except Exception as e:
                logger.warning(f"Failed to parse/augment torrent file {file.filename}: {e}")

            add_result = client.add_torrent(tmp_path, start=start)

            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

            if add_result:
                result_entry["success"] = True
                result_entry["message"] = "Added successfully"
                success_count += 1
            else:
                result_entry["message"] = "Failed to add torrent to client"
                failure_count += 1

        except Exception as e:
            logger.error(f"Failed to upload torrent {file.filename}: {e}")
            result_entry["message"] = str(e)
            failure_count += 1
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

        results.append(result_entry)

    # Poll server once after all uploads
    if success_count > 0:
        poller = get_poller()
        await poller.poll_server(server)

    return {
        "total": len(files),
        "success_count": success_count,
        "failure_count": failure_count,
        "server_id": server.id,
        "server_name": server.name,
        "results": results
    }


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
        check_server_available(server)
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
        check_server_available(server)
        client = get_client(server)
    else:
        server, client, _ = find_torrent_server(info_hash, user)
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Torrent not found on any server"
            )
        check_server_available(server)

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

        # Dispatch started callback
        torrents = poller.get_cached_torrents(user.id, server.id)
        for t in torrents:
            if t.get("info_hash", "").upper() == info_hash.upper():
                await dispatch_event(TorrentEvent.STARTED, t)
                break

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
        check_server_available(server)
        client = get_client(server)
    else:
        server, client, _ = find_torrent_server(info_hash, user)
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Torrent not found on any server"
            )
        check_server_available(server)

    try:
        client.stop(info_hash)

        # Immediately poll the server to update cache
        poller = get_poller()
        await poller.poll_server(server)

        # Dispatch stopped callback
        torrents = poller.get_cached_torrents(user.id, server.id)
        for t in torrents:
            if t.get("info_hash", "").upper() == info_hash.upper():
                await dispatch_event(TorrentEvent.STOPPED, t)
                break

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
        check_server_available(server)
        client = get_client(server)
    else:
        server, client, _ = find_torrent_server(info_hash, user)
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Torrent not found on any server"
            )
        check_server_available(server)

    try:
        # Capture torrent info before deletion for callback
        poller = get_poller()
        torrents = poller.get_cached_torrents(user.id, server.id)
        torrent_info = next(
            (t for t in torrents if t.get("info_hash", "").upper() == info_hash.upper()),
            None
        )

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
        await poller.poll_server(server)

        # Dispatch removed callback with the info we captured before deletion
        if torrent_info:
            await dispatch_event(TorrentEvent.REMOVED, torrent_info)

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


# === Transfer Endpoints ===

@router.get("/transfers")
async def list_transfers(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    server_id: Optional[str] = Query(None, description="Filter by server"),
    user: User = Depends(get_current_user)
):
    """
    List all transfer jobs for the current user.

    Optionally filter by status (pending, running, completed, failed, cancelled)
    or by server_id.
    """
    query = TransferJob.select().where(TransferJob.user_id == user.id)

    if status_filter:
        query = query.where(TransferJob.status == status_filter)
    if server_id:
        query = query.where(TransferJob.server_id == server_id)

    jobs = list(query.order_by(TransferJob.created_at.desc()).limit(100))

    return [
        {
            "id": j.id,
            "server_id": j.server_id,
            "torrent_hash": j.torrent_hash,
            "torrent_name": j.torrent_name,
            "remote_path": j.remote_path,
            "local_path": j.local_path,
            "status": j.status,
            "progress_percent": j.progress_percent,
            "progress_bytes": j.progress_bytes,
            "total_bytes": j.total_bytes,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "error": j.error,
            "retry_count": j.retry_count,
            "max_retries": j.max_retries,
            "auto_delete_after": j.auto_delete_after,
            "triggered_by": j.triggered_by
        }
        for j in jobs
    ]


@router.post("/transfers")
async def start_transfer(
    request: StartTransferRequest,
    user: User = Depends(get_current_user)
):
    """
    Manually trigger a file transfer for a completed torrent.

    Downloads the torrent data from the remote server to local storage
    using rsync over SSH.
    """
    server = get_user_server(request.server_id, user)

    # Get torrent info from cache
    poller = get_poller()
    torrents = poller.get_cached_torrents(user.id, request.server_id)

    torrent = next(
        (t for t in torrents if t["info_hash"].upper() == request.torrent_hash.upper()),
        None
    )

    if not torrent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Torrent not found"
        )

    if not torrent.get("complete"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Torrent is not complete"
        )

    from torrent_manager.transfer import get_transfer_service
    transfer_service = get_transfer_service()
    job = transfer_service.queue_transfer(
        server=server,
        torrent=torrent,
        user_id=user.id,
        triggered_by="manual",
        download_path_override=request.download_path
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transfer already in progress or no download path configured"
        )

    return {"message": "Transfer queued", "job_id": job.id}


@router.get("/transfers/{job_id}")
async def get_transfer(
    job_id: str,
    user: User = Depends(get_current_user)
):
    """Get details of a specific transfer job."""
    job = TransferJob.get_or_none(
        (TransferJob.id == job_id) &
        (TransferJob.user_id == user.id)
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer job not found"
        )

    return {
        "id": job.id,
        "server_id": job.server_id,
        "torrent_hash": job.torrent_hash,
        "torrent_name": job.torrent_name,
        "remote_path": job.remote_path,
        "local_path": job.local_path,
        "status": job.status,
        "progress_percent": job.progress_percent,
        "progress_bytes": job.progress_bytes,
        "total_bytes": job.total_bytes,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "error": job.error,
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
        "auto_delete_after": job.auto_delete_after,
        "triggered_by": job.triggered_by
    }


@router.delete("/transfers/{job_id}")
async def cancel_transfer(
    job_id: str,
    user: User = Depends(get_current_user)
):
    """Cancel a pending or running transfer job."""
    job = TransferJob.get_or_none(
        (TransferJob.id == job_id) &
        (TransferJob.user_id == user.id)
    )

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transfer job not found"
        )

    if job.status not in ("pending", "running"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job with status: {job.status}"
        )

    job.status = "cancelled"
    job.save()

    # If running, the TransferService will handle the cancellation
    from torrent_manager.transfer import get_transfer_service
    transfer_service = get_transfer_service()
    if job.id in transfer_service._active_jobs:
        transfer_service._active_jobs[job.id].cancel()

    return {"message": "Transfer cancelled", "job_id": job.id}


# === Per-Torrent Settings Endpoints ===

@router.get("/torrents/{info_hash}/settings")
async def get_torrent_settings(
    info_hash: str,
    server_id: str = Query(..., description="Server ID"),
    user: User = Depends(get_current_user)
):
    """
    Get per-torrent download settings.

    Returns both the per-torrent overrides (if any) and the server defaults.
    """
    server = get_user_server(server_id, user)

    settings = UserTorrentSettings.get_or_none(
        (UserTorrentSettings.user_id == user.id) &
        (UserTorrentSettings.server_id == server_id) &
        (UserTorrentSettings.torrent_hash == info_hash.upper())
    )

    return {
        "info_hash": info_hash,
        "server_id": server_id,
        "download_path": settings.download_path if settings else None,
        "auto_download": settings.auto_download if settings else None,
        "auto_delete_remote": settings.auto_delete_remote if settings else None,
        "server_defaults": {
            "auto_download_enabled": server.auto_download_enabled,
            "auto_download_path": server.auto_download_path,
            "auto_delete_remote": server.auto_delete_remote
        }
    }


@router.put("/torrents/{info_hash}/settings")
async def update_torrent_settings(
    info_hash: str,
    request: UpdateTorrentSettingsRequest,
    server_id: str = Query(..., description="Server ID"),
    user: User = Depends(get_current_user)
):
    """
    Update per-torrent download settings.

    These settings override the server defaults for this specific torrent.
    Set a field to null to inherit from server defaults.
    """
    server = get_user_server(server_id, user)

    settings, created = UserTorrentSettings.get_or_create(
        user_id=user.id,
        server_id=server_id,
        torrent_hash=info_hash.upper()
    )

    if request.download_path is not None:
        settings.download_path = request.download_path if request.download_path else None
    if request.auto_download is not None:
        settings.auto_download = request.auto_download
    if request.auto_delete_remote is not None:
        settings.auto_delete_remote = request.auto_delete_remote

    settings.save()

    return {
        "info_hash": info_hash,
        "server_id": server_id,
        "download_path": settings.download_path,
        "auto_download": settings.auto_download,
        "auto_delete_remote": settings.auto_delete_remote
    }


# === Media Metadata Endpoints ===

@router.get("/torrents/{info_hash}/metadata")
async def get_torrent_metadata(
    info_hash: str,
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """
    Get media identification and metadata for a torrent.

    Returns the identified media (movie/TV show), confidence level,
    and any retrieved metadata.
    """
    from torrent_manager.metadata_service import get_metadata_service
    from torrent_manager.models import TorrentMetadata

    # Find server if not specified
    if not server_id:
        server, _, _ = find_torrent_server(info_hash, user)
        if server:
            server_id = server.id

    if not server_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Torrent not found on any server"
        )

    service = get_metadata_service()
    status_data = service.get_status(info_hash, server_id)

    if not status_data:
        return {
            "info_hash": info_hash,
            "server_id": server_id,
            "status": "not_processed",
            "message": "Metadata not yet processed for this torrent"
        }

    return status_data


@router.post("/torrents/{info_hash}/identify")
async def identify_torrent_metadata(
    info_hash: str,
    server_id: Optional[str] = Query(None, description="Server ID"),
    force: bool = Query(False, description="Re-identify even if already processed"),
    user: User = Depends(get_current_user)
):
    """
    Trigger media identification for a torrent.

    Identifies the media content from the torrent name and files,
    retrieves metadata from TMDB/IMDB, and writes metadata files
    to the torrent's metadata/ directory.
    """
    from torrent_manager.metadata_service import get_metadata_service

    # Find server and torrent
    if server_id:
        server = get_user_server(server_id, user)
    else:
        server, _, _ = find_torrent_server(info_hash, user)
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Torrent not found on any server"
            )

    # Get torrent info from cache
    poller = get_poller()
    torrents = poller.get_cached_torrents(user.id, server.id)
    torrent = next(
        (t for t in torrents if t["info_hash"].upper() == info_hash.upper()),
        None
    )

    if not torrent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Torrent not found in cache"
        )

    # Get file list
    files = None
    from torrent_manager.models import Torrent as TorrentModel
    db_torrent = TorrentModel.get_or_none(
        (TorrentModel.torrent_hash == info_hash.upper()) &
        (TorrentModel.server_id == server.id)
    )
    if db_torrent and db_torrent.files:
        files = db_torrent.files if isinstance(db_torrent.files, list) else None

    # Get labels (may contain media ID like "id:imdb:tt0133093")
    labels = torrent.get("labels", [])

    # Process
    service = get_metadata_service()
    result = await service.process_torrent(
        torrent_hash=info_hash,
        torrent_name=torrent.get("name", ""),
        server=server,
        files=files,
        labels=labels,
        force=force
    )

    return {
        "info_hash": info_hash,
        "server_id": server.id,
        "status": result.status,
        "identification": {
            "media_id": result.identification.media_id if result.identification else None,
            "media_type": result.identification.media_type if result.identification else None,
            "title": result.identification.title if result.identification else None,
            "year": result.identification.year if result.identification else None,
            "confidence": result.identification.confidence if result.identification else None,
            "confidence_level": result.identification.confidence_level if result.identification else None,
        } if result.identification else None,
        "files_written": result.files_written,
        "error": result.error
    }


@router.put("/torrents/{info_hash}/metadata")
async def set_torrent_metadata(
    info_hash: str,
    media_id: str = Query(..., description="Media ID (e.g., id:imdb:tt0133093)"),
    server_id: Optional[str] = Query(None, description="Server ID"),
    user: User = Depends(get_current_user)
):
    """
    Manually set the media identification for a torrent.

    Use this to correct an incorrect identification or to manually
    identify a torrent that couldn't be automatically identified.
    """
    from torrent_manager.metadata_service import get_metadata_service
    from torrent_manager.models import TorrentMetadata
    from datetime import datetime

    # Find server
    if server_id:
        server = get_user_server(server_id, user)
    else:
        server, _, _ = find_torrent_server(info_hash, user)
        if not server:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Torrent not found on any server"
            )

    # Validate media_id format
    if not media_id.startswith("id:"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid media_id format. Expected: id:imdb:ttXXXXXXX or id:tmdb:movie:XXXXX"
        )

    service = get_metadata_service()

    # Fetch metadata for the provided ID
    metadata_result = service.fetch_metadata(media_id)

    if not metadata_result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not fetch metadata for {media_id}: {metadata_result.error}"
        )

    # Parse media_id for database record
    parts = media_id.split(":")
    imdb_id = None
    tmdb_id = None
    if len(parts) >= 3:
        if parts[1] == "imdb":
            imdb_id = parts[2]
        elif parts[1] == "tmdb" and len(parts) >= 4:
            try:
                tmdb_id = int(parts[3])
            except ValueError:
                pass

    # Get or create metadata record
    record, created = TorrentMetadata.get_or_create(
        torrent_hash=info_hash.upper(),
        server_id=server.id
    )

    # Update record
    record.media_id = media_id
    record.media_type = metadata_result.metadata.get("media_type", "unknown")
    record.title = metadata_result.metadata.get("title")
    record.year = metadata_result.metadata.get("year")
    record.imdb_id = imdb_id
    record.tmdb_id = tmdb_id
    record.confidence = 1.0  # Manual = full confidence
    record.confidence_level = "MANUAL"
    record.status = "manual"
    record.error = None
    record.identified_at = datetime.now()
    record.updated_at = datetime.now()
    record.save()

    # Write metadata files
    from torrent_manager.metadata_service import IdentificationResult
    identification = IdentificationResult(
        success=True,
        media_id=media_id,
        media_type=record.media_type,
        title=record.title,
        year=record.year,
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        confidence=1.0,
        confidence_level="MANUAL",
        raw_result={"manual": True, "media_id": media_id}
    )

    files_written = await service.write_metadata_files(
        server, info_hash, identification, metadata_result
    )

    record.metadata_written_at = datetime.now()
    record.save()

    return {
        "info_hash": info_hash,
        "server_id": server.id,
        "media_id": media_id,
        "title": record.title,
        "year": record.year,
        "files_written": files_written,
        "message": "Metadata manually set"
    }
