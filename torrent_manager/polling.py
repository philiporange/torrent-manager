"""
Background polling service for torrent servers.

Polls each configured server periodically to fetch torrent status, caching results
for quick retrieval by the frontend. Adjusts polling frequency based on activity:
- POLL_SERVER_IDLE_INTERVAL (60s) when no active downloads
- POLL_SERVER_ACTIVE_INTERVAL (15s) when downloads are in progress

The cache stores per-server torrent lists with metadata including last poll time
and activity status. Frontend requests return cached data instead of making
live RPC calls.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor

from .config import Config
from .logger import logger
from .models import TorrentServer
from .client_factory import get_client
from .activity import Activity


@dataclass
class ServerCache:
    """Cache entry for a single server's torrent data."""
    torrents: List[Dict[str, Any]] = field(default_factory=list)
    last_poll: float = 0.0
    has_active_downloads: bool = False
    error: Optional[str] = None


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

        Returns a ServerCache with the poll results.
        """
        cache = ServerCache(last_poll=time.time())

        try:
            client = get_client(server)
            torrents = list(client.list_torrents())

            has_active_downloads = False
            for torrent in torrents:
                torrent["server_id"] = server.id
                torrent["server_name"] = server.name
                torrent["server_type"] = server.server_type

                # Check if this torrent is actively downloading
                if torrent.get("is_active") and not torrent.get("complete"):
                    has_active_downloads = True

            cache.torrents = torrents
            cache.has_active_downloads = has_active_downloads
            cache.error = None

        except Exception as e:
            logger.error(f"Failed to poll server {server.name}: {e}")
            cache.error = str(e)
            # Keep old torrents on error if we have them
            if server.id in self._cache:
                cache.torrents = self._cache[server.id].torrents
                cache.has_active_downloads = self._cache[server.id].has_active_downloads

        return cache

    async def poll_server(self, server: TorrentServer) -> ServerCache:
        """Poll a single server asynchronously."""
        loop = asyncio.get_event_loop()
        cache = await loop.run_in_executor(
            self._executor,
            self._poll_server_sync,
            server
        )

        async with self._lock:
            self._cache[server.id] = cache

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
            List of torrent dicts with seeding duration info added
        """
        all_torrents = []
        activity = Activity()

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

                    # Add seeding duration info for completed torrents
                    if t.get("complete"):
                        info_hash = t["info_hash"]
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
