"""
Background polling service for torrent servers.

Polls each configured server periodically to fetch torrent status, caching results
for quick retrieval by the frontend. Adjusts polling frequency based on activity:
- POLL_SERVER_IDLE_INTERVAL (60s) when no active downloads
- POLL_SERVER_ACTIVE_INTERVAL (15s) when downloads are in progress

The cache stores per-server torrent lists with metadata including last poll time
and activity status. Frontend requests return cached data instead of making
live RPC calls.

Completion detection: Tracks which torrents have completed to detect new completions
and trigger auto-download via the TransferService.

Error handling includes tracking consecutive failures and reducing log noise
for persistent connection issues. Errors are logged immediately on first failure,
at 5 consecutive failures, and then every 10 minutes for ongoing issues.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from .config import Config
from .logger import logger
from .models import TorrentServer, TransferJob
from .client_factory import get_client
from .activity import Activity
from .callbacks import dispatch_event, TorrentEvent


@dataclass
class ServerCache:
    """Cache entry for a single server's torrent data."""
    torrents: List[Dict[str, Any]] = field(default_factory=list)
    last_poll: float = 0.0
    has_active_downloads: bool = False
    error: Optional[str] = None
    consecutive_errors: int = 0
    last_error_logged: float = 0.0
    # Track completed torrents to detect new completions
    completed_hashes: set = field(default_factory=set)
    # Temporarily store newly completed torrents for transfer triggering
    newly_completed: List[Dict[str, Any]] = field(default_factory=list)


class TorrentPoller:
    """
    Background service that polls torrent servers and caches results.

    Maintains a per-server cache of torrent data, automatically adjusting
    poll frequency based on download activity.
    """

    def __init__(self):
        self._cache: Dict[str, ServerCache] = {}
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._running = False

    def _poll_server_sync(self, server: TorrentServer) -> ServerCache:
        """
        Synchronously poll a single server (runs in thread pool).

        Returns a ServerCache with the poll results, including any newly
        completed torrents detected since the last poll.
        """
        cache = ServerCache(last_poll=time.time())
        old_cache = self._cache.get(server.id)
        old_completed = old_cache.completed_hashes if old_cache else set()

        try:
            client = get_client(server)
            torrents = list(client.list_torrents())

            has_active_downloads = False
            current_completed = set()
            newly_completed = []

            for torrent in torrents:
                torrent["server_id"] = server.id
                torrent["server_name"] = server.name
                torrent["server_type"] = server.server_type

                info_hash = torrent.get("info_hash", "").upper()
                is_complete = torrent.get("complete", False)

                # Track completed torrents
                if is_complete:
                    current_completed.add(info_hash)
                    # Check if this is newly completed
                    if info_hash and info_hash not in old_completed:
                        newly_completed.append(torrent)
                        logger.info(f"Torrent completed: {torrent.get('name', info_hash[:8])}")

                # Check if this torrent is actively downloading
                if torrent.get("is_active") and not is_complete:
                    has_active_downloads = True

            cache.torrents = torrents
            cache.has_active_downloads = has_active_downloads
            cache.completed_hashes = current_completed
            cache.newly_completed = newly_completed
            cache.error = None
            cache.consecutive_errors = 0
            cache.last_error_logged = 0.0

        except Exception as e:
            cache.error = str(e)

            # Keep old data on error if we have it
            if old_cache:
                cache.torrents = old_cache.torrents
                cache.has_active_downloads = old_cache.has_active_downloads
                cache.completed_hashes = old_cache.completed_hashes
                cache.consecutive_errors = old_cache.consecutive_errors + 1
                cache.last_error_logged = old_cache.last_error_logged
            else:
                cache.consecutive_errors = 1

            # Log errors with reduced frequency for persistent failures
            # Log first error immediately, then every 10 minutes for persistent failures
            current_time = time.time()
            should_log = (
                cache.consecutive_errors == 1 or
                cache.consecutive_errors == 5 or  # Log at 5 consecutive failures
                (current_time - cache.last_error_logged) >= 600  # Log every 10 minutes
            )

            if should_log:
                if cache.consecutive_errors == 1:
                    logger.error(f"Failed to poll server {server.name}: {cache.error}")
                else:
                    logger.error(
                        f"Failed to poll server {server.name} "
                        f"({cache.consecutive_errors} consecutive failures): {cache.error}"
                    )
                cache.last_error_logged = current_time

        return cache

    async def poll_server(self, server: TorrentServer) -> ServerCache:
        """Poll a single server asynchronously and trigger transfers for new completions."""
        loop = asyncio.get_event_loop()
        cache = await loop.run_in_executor(
            self._executor,
            self._poll_server_sync,
            server
        )

        async with self._lock:
            self._cache[server.id] = cache

        # Trigger transfers and callbacks for newly completed torrents
        if cache.newly_completed:
            if server.auto_download_enabled:
                from .transfer import get_transfer_service
                transfer_service = get_transfer_service()

                for torrent in cache.newly_completed:
                    transfer_service.queue_transfer(
                        server=server,
                        torrent=torrent,
                        user_id=server.user_id,
                        triggered_by="auto"
                    )

            # Dispatch completion callbacks
            for torrent in cache.newly_completed:
                await dispatch_event(TorrentEvent.COMPLETED, torrent)

        return cache

    async def poll_all_servers(self) -> None:
        """Poll all enabled servers concurrently."""
        servers = list(TorrentServer.select().where(TorrentServer.enabled == True))

        if not servers:
            return

        # Poll all servers concurrently
        tasks = [self.poll_server(server) for server in servers]
        await asyncio.gather(*tasks, return_exceptions=True)

    def get_poll_interval(self) -> int:
        """
        Determine the appropriate poll interval based on current activity.

        Returns POLL_SERVER_ACTIVE_INTERVAL if any server has active downloads,
        otherwise returns POLL_SERVER_IDLE_INTERVAL.
        """
        for cache in self._cache.values():
            if cache.has_active_downloads:
                return Config.POLL_SERVER_ACTIVE_INTERVAL
        return Config.POLL_SERVER_IDLE_INTERVAL

    def get_cached_torrents(
        self,
        user_id: str,
        server_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get cached torrent data for a user's servers.

        Args:
            user_id: The user ID to get torrents for
            server_id: Optional specific server ID to filter by

        Returns:
            List of torrent dicts with seeding duration and transfer info added
        """
        all_torrents = []
        activity = Activity()

        # Get active transfer jobs for this user (pending or running)
        active_transfers = {}
        for job in TransferJob.select().where(
            (TransferJob.user_id == user_id) &
            (TransferJob.status.in_(["pending", "running"]))
        ):
            active_transfers[job.torrent_hash.upper()] = {
                "status": "transferring",
                "progress": job.progress_percent,
                "job_id": job.id
            }

        try:
            if server_id:
                servers = TorrentServer.select().where(
                    (TorrentServer.id == server_id) &
                    (TorrentServer.user_id == user_id) &
                    (TorrentServer.enabled == True)
                )
            else:
                servers = TorrentServer.select().where(
                    (TorrentServer.user_id == user_id) &
                    (TorrentServer.enabled == True)
                )

            for server in servers:
                cache = self._cache.get(server.id)
                if cache is None:
                    continue

                for torrent in cache.torrents:
                    # Make a copy to avoid modifying cache
                    t = torrent.copy()
                    info_hash = t.get("info_hash", "").upper()

                    # Add seeding duration info for completed torrents
                    if t.get("complete"):
                        is_private = t.get("is_private", False)

                        t["seeding_duration"] = activity.calculate_seeding_duration(
                            info_hash, max_interval=Config.MAX_INTERVAL
                        )
                        t["seed_threshold"] = (
                            Config.PRIVATE_SEED_DURATION if is_private
                            else Config.PUBLIC_SEED_DURATION
                        )
                    else:
                        t["seeding_duration"] = 0
                        t["seed_threshold"] = 0

                    # Add transfer info if there's an active transfer
                    if info_hash in active_transfers:
                        t["transfer"] = active_transfers[info_hash]
                    else:
                        t["transfer"] = None

                    all_torrents.append(t)
        finally:
            activity.close()

        return all_torrents

    def get_cache_age(self, server_id: str) -> Optional[float]:
        """Get the age of cached data for a server in seconds."""
        cache = self._cache.get(server_id)
        if cache is None:
            return None
        return time.time() - cache.last_poll

    def has_active_downloads(self) -> bool:
        """Check if any server has active downloads."""
        return any(cache.has_active_downloads for cache in self._cache.values())

    async def run(self) -> None:
        """Main polling loop."""
        self._running = True
        logger.info(
            f"Torrent poller started (idle: {Config.POLL_SERVER_IDLE_INTERVAL}s, "
            f"active: {Config.POLL_SERVER_ACTIVE_INTERVAL}s)"
        )

        while self._running:
            try:
                await self.poll_all_servers()

                interval = self.get_poll_interval()
                active_status = "active" if self.has_active_downloads() else "idle"
                logger.debug(f"Poll complete ({active_status}), next poll in {interval}s")

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(Config.POLL_SERVER_IDLE_INTERVAL)

        self._executor.shutdown(wait=False)
        logger.info("Torrent poller stopped")

    def stop(self) -> None:
        """Signal the polling loop to stop."""
        self._running = False


# Global poller instance
_poller: Optional[TorrentPoller] = None


def get_poller() -> TorrentPoller:
    """Get the global poller instance, creating it if needed."""
    global _poller
    if _poller is None:
        _poller = TorrentPoller()
    return _poller
