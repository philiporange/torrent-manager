"""
Magnet URI to .torrent file resolver using the magnet2torrent library.

Converts magnet URIs to .torrent files by first attempting fast HTTP downloads
from cache sites (itorrents.org, torrage.info, etc.), then falling back to
peer-based metadata download via libtorrent if cache sites don't have it.

Configuration is via the Config class (environment variables):
- MAGNET_RESOLVER_ENABLED: Enable/disable the resolver (default: true)
- MAGNET_RESOLVER_TIMEOUT: Timeout in seconds for peer download (default: 300)
- MAGNET_RESOLVER_ENABLE_DHT: Enable DHT for peer discovery (default: false)
- MAGNET_RESOLVER_PROXY_HOST: SOCKS5 proxy host for peer connections
- MAGNET_RESOLVER_PROXY_PORT: SOCKS5 proxy port for peer connections
- MAGNET_RESOLVER_HTTP_PROXY: HTTP proxy for cache site requests
"""

import os
import tempfile
from typing import Optional, Tuple

from .config import Config
from .logger import logger

# Try to import magnet2torrent - it's optional
try:
    from magnet2torrent import core as m2t_core
    from magnet2torrent import config as m2t_config
    MAGNET2TORRENT_AVAILABLE = True
except ImportError:
    MAGNET2TORRENT_AVAILABLE = False
    logger.warning("magnet2torrent not installed - magnet resolution disabled")


class MagnetResolverError(Exception):
    """Error during magnet resolution."""
    pass


class MagnetResolver:
    """
    Resolves magnet URIs to .torrent files using magnet2torrent.

    First tries fast HTTP download from cache sites, then falls back to
    peer-based metadata download if needed.
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        timeout: int = 300,
        enable_dht: bool = False,
        proxy_host: Optional[str] = None,
        proxy_port: Optional[int] = None,
        http_proxy: Optional[str] = None,
    ):
        """
        Initialize the magnet resolver.

        Args:
            output_dir: Directory to save .torrent files (default: temp dir)
            timeout: Timeout in seconds for peer download (default: 300)
            enable_dht: Enable DHT for peer discovery (default: False)
            proxy_host: SOCKS5 proxy host for peer connections
            proxy_port: SOCKS5 proxy port for peer connections
            http_proxy: HTTP proxy for cache site requests
        """
        self.output_dir = output_dir or tempfile.gettempdir()
        self.timeout = timeout
        self.enable_dht = enable_dht
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.http_proxy = http_proxy
        self._session = None

    @property
    def is_available(self) -> bool:
        """Check if magnet2torrent is available."""
        return MAGNET2TORRENT_AVAILABLE

    def _get_session(self):
        """Get or create a libtorrent session."""
        if not MAGNET2TORRENT_AVAILABLE:
            raise MagnetResolverError("magnet2torrent not installed")

        if self._session is None:
            self._session = m2t_core.create_session(
                enable_dht=self.enable_dht,
                proxy_host=self.proxy_host,
                proxy_port=self.proxy_port,
            )
        return self._session

    def resolve(self, magnet_uri: str) -> Tuple[str, str]:
        """
        Resolve a magnet URI to a .torrent file.

        First tries HTTP download from cache sites (fast), then falls back
        to peer-based metadata download (slower but reliable).

        Args:
            magnet_uri: Magnet URI or bare info hash

        Returns:
            Tuple of (torrent_file_path, info_hash)

        Raises:
            MagnetResolverError: If resolution fails
        """
        if not MAGNET2TORRENT_AVAILABLE:
            raise MagnetResolverError("magnet2torrent not installed")

        # Extract info hash from magnet URI
        if magnet_uri.startswith("magnet:"):
            # Parse info hash from magnet URI
            import re
            match = re.search(r'xt=urn:btih:([a-fA-F0-9]{40}|[a-zA-Z2-7]{32})', magnet_uri)
            if not match:
                raise MagnetResolverError(f"Invalid magnet URI: {magnet_uri}")
            info_hash = match.group(1).upper()
        else:
            # Assume it's a bare info hash
            info_hash = magnet_uri.upper()
            magnet_uri = f"magnet:?xt=urn:btih:{info_hash}"

        logger.info(f"Resolving magnet for info hash: {info_hash}")

        # Get public trackers for better peer discovery
        try:
            proxy_enabled = bool(self.proxy_host)
            public_trackers = m2t_core.get_public_trackers(proxy_enabled=proxy_enabled, quiet=True)
        except Exception as e:
            logger.warning(f"Failed to get public trackers: {e}")
            public_trackers = []

        # Use a unique temp directory for this resolution
        resolve_dir = tempfile.mkdtemp(prefix="magnet_resolve_")

        try:
            session = self._get_session()

            # Process the magnet URI - returns path on success, None on failure
            torrent_path = m2t_core.process_magnet(
                ses=session,
                magnet_uri=magnet_uri,
                output_dir=resolve_dir,
                public_trackers=public_trackers,
                http_proxy=self.http_proxy,
                quiet=True,
            )

            if not torrent_path:
                raise MagnetResolverError("Failed to resolve magnet: no torrent file created")

            # Verify it exists and has content
            if not os.path.exists(torrent_path) or os.path.getsize(torrent_path) == 0:
                raise MagnetResolverError("Created torrent file is empty or missing")

            logger.info(f"Successfully resolved magnet to: {torrent_path}")
            return torrent_path, info_hash

        except MagnetResolverError:
            # Clean up temp dir on our errors
            import shutil
            shutil.rmtree(resolve_dir, ignore_errors=True)
            raise
        except Exception as e:
            # Clean up temp dir on other errors
            import shutil
            shutil.rmtree(resolve_dir, ignore_errors=True)
            logger.error(f"Failed to resolve magnet {info_hash}: {e}")
            raise MagnetResolverError(f"Failed to resolve magnet: {e}")

    def close(self):
        """Close the libtorrent session."""
        if self._session is not None:
            # libtorrent sessions are cleaned up automatically
            self._session = None


# Global resolver instance (lazy initialization)
_resolver: Optional[MagnetResolver] = None


def get_resolver() -> MagnetResolver:
    """Get the global magnet resolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = MagnetResolver(
            timeout=Config.MAGNET_RESOLVER_TIMEOUT,
            enable_dht=Config.MAGNET_RESOLVER_ENABLE_DHT,
            proxy_host=Config.MAGNET_RESOLVER_PROXY_HOST,
            proxy_port=Config.MAGNET_RESOLVER_PROXY_PORT,
            http_proxy=Config.MAGNET_RESOLVER_HTTP_PROXY,
        )
    return _resolver


def is_resolver_enabled() -> bool:
    """Check if magnet resolution is enabled."""
    if not MAGNET2TORRENT_AVAILABLE:
        return False
    return Config.MAGNET_RESOLVER_ENABLED


def resolve_magnet(magnet_uri: str) -> Tuple[str, str]:
    """
    Resolve a magnet URI to a .torrent file.

    Convenience function using the global resolver.

    Args:
        magnet_uri: Magnet URI or bare info hash

    Returns:
        Tuple of (torrent_file_path, info_hash)

    Raises:
        MagnetResolverError: If resolution fails
    """
    return get_resolver().resolve(magnet_uri)
