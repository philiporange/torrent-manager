"""
Shared torrent add helpers used by both the public API and background services.

This module centralizes URI normalization, optional magnet resolution and
tracker augmentation, torrent client insertion, immediate cache refresh, and
best-effort callback dispatch so background automation behaves like user-driven
adds.
"""

import os
import re
import shutil
from typing import Any, Dict, List, Optional

from .callbacks import TorrentEvent, dispatch_event
from .client_factory import get_client
from .logger import logger
from .magnet_link import MagnetLink
from .magnet_resolver import MagnetResolverError, is_resolver_enabled, resolve_magnet
from .polling import get_poller
from .torrent_file import TorrentFile
from .trackers import get_cached_trackers, is_augmentation_enabled

INFO_HASH_HEX_PATTERN = re.compile(r"^[a-fA-F0-9]{40}$")
INFO_HASH_BASE32_PATTERN = re.compile(r"^[A-Za-z2-7]{32}$")


def is_info_hash(value: str) -> bool:
    """Check if a string is a valid info hash (40 hex chars or 32 base32 chars)."""
    return bool(INFO_HASH_HEX_PATTERN.match(value) or INFO_HASH_BASE32_PATTERN.match(value))


def info_hash_to_magnet(info_hash: str) -> str:
    """Convert an info hash to a magnet URI."""
    return f"magnet:?xt=urn:btih:{info_hash.upper()}"


def augment_magnet_with_trackers(magnet_uri: str) -> str:
    """Add cached public trackers to a magnet URI when tracker augmentation is enabled."""
    if not is_augmentation_enabled():
        return magnet_uri

    try:
        magnet = MagnetLink(magnet_uri)
        for tracker in get_cached_trackers():
            magnet.add_tracker(tracker)
        return magnet.to_uri()
    except Exception as exc:
        logger.warning(f"Failed to augment magnet URI: {exc}")
        return magnet_uri


def add_torrent_from_file(client, torrent_path: str, start: bool, labels: Optional[List[str]], augment: bool = True) -> bool:
    """Add a torrent file to a client after optional public tracker augmentation."""
    if augment and is_augmentation_enabled():
        try:
            torrent = TorrentFile(torrent_path)
            if not torrent.is_private:
                trackers = get_cached_trackers()
                torrent.add_trackers(trackers)
                torrent.save(torrent_path)
        except Exception as exc:
            logger.warning(f"Failed to augment torrent file: {exc}")

    return client.add_torrent(torrent_path, start=start, labels=labels)


def _cleanup_torrent_path(torrent_path: Optional[str]) -> None:
    """Remove temporary torrent files and magnet resolver work directories."""
    if not torrent_path:
        return

    parent_dir = os.path.dirname(torrent_path)
    if "magnet_resolve_" in parent_dir:
        shutil.rmtree(parent_dir, ignore_errors=True)
    elif os.path.exists(torrent_path):
        os.remove(torrent_path)


async def add_torrent_to_server(
    server,
    uri: str,
    *,
    start: bool = True,
    labels: Optional[List[str]] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Add a torrent URI to a configured server and refresh the cached torrent view."""
    torrent_path = None
    normalized_uri = uri.strip()
    info_hash = None

    try:
        client = get_client(server)

        if is_info_hash(normalized_uri):
            info_hash = normalized_uri.upper()
            normalized_uri = info_hash_to_magnet(normalized_uri)

        if normalized_uri.startswith("magnet:"):
            try:
                info_hash = info_hash or MagnetLink(normalized_uri).info_hash
            except Exception:
                pass

            if is_resolver_enabled():
                try:
                    torrent_path, resolved_info_hash = resolve_magnet(normalized_uri)
                    info_hash = info_hash or resolved_info_hash.upper()
                    added = add_torrent_from_file(
                        client,
                        torrent_path,
                        start=start,
                        labels=labels,
                        augment=True,
                    )
                except MagnetResolverError as exc:
                    logger.warning(f"Magnet resolution failed, falling back to direct add: {exc}")
                    normalized_uri = augment_magnet_with_trackers(normalized_uri)
                    added = client.add_magnet(normalized_uri, start=start, labels=labels)
            else:
                normalized_uri = augment_magnet_with_trackers(normalized_uri)
                added = client.add_magnet(normalized_uri, start=start, labels=labels)
        elif normalized_uri.startswith("http://") or normalized_uri.startswith("https://"):
            added = client.add_torrent_url(normalized_uri, start=start, labels=labels)
        else:
            raise ValueError("Input must be an info hash, magnet link, or HTTP/HTTPS URL")

        if not added:
            raise RuntimeError(f"Failed to add torrent to {server.name}")

        _cleanup_torrent_path(torrent_path)

        poller = get_poller()
        await poller.poll_server(server)

        matched_torrent = None
        if user_id:
            torrents = poller.get_cached_torrents(user_id, server.id)
            if info_hash:
                matched_torrent = next((item for item in torrents if item.get("info_hash", "").upper() == info_hash.upper()), None)
            if not matched_torrent:
                matched_torrent = next((item for item in torrents if item.get("name") and item.get("name") in normalized_uri), None)
            if matched_torrent:
                await dispatch_event(TorrentEvent.ADDED, matched_torrent)

        return {
            "uri": normalized_uri,
            "info_hash": info_hash,
            "server_id": server.id,
            "server_name": server.name,
            "torrent": matched_torrent,
        }
    except Exception:
        _cleanup_torrent_path(torrent_path)
        raise
