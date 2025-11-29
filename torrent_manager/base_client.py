"""
Abstract base class defining the interface for torrent clients.

Both RTorrentClient and TransmissionClient implement this interface,
allowing them to be used interchangeably through the client factory.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Generator, List, Optional


class BaseTorrentClient(ABC):
    """Abstract base class for torrent client implementations."""

    @abstractmethod
    def check_connection(self) -> bool:
        """Test if the connection to the torrent server is working."""
        pass

    @abstractmethod
    def list_torrents(self, info_hash: Optional[str] = None, files: bool = False) -> Generator[Dict[str, Any], None, None]:
        """
        List torrents from the server.

        Args:
            info_hash: Optional filter for a specific torrent
            files: Whether to include file details

        Yields:
            Dict with torrent information including:
            - info_hash, name, size, progress, state, is_active, complete
            - download_rate, upload_rate, peers, ratio
        """
        pass

    @abstractmethod
    def add_torrent(self, path: str, start: bool = True) -> bool:
        """
        Add a torrent from a local .torrent file.

        Args:
            path: Path to the .torrent file
            start: Whether to start the torrent immediately

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def add_torrent_url(self, url: str, start: bool = True) -> bool:
        """
        Add a torrent from a URL to a .torrent file.

        Args:
            url: HTTP/HTTPS URL to a .torrent file
            start: Whether to start the torrent immediately

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def add_magnet(self, uri: str, start: bool = True) -> bool:
        """
        Add a torrent from a magnet link.

        Args:
            uri: Magnet URI
            start: Whether to start the torrent immediately

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def start(self, info_hash: str) -> Any:
        """Start/resume a torrent."""
        pass

    @abstractmethod
    def stop(self, info_hash: str) -> Any:
        """Stop/pause a torrent."""
        pass

    @abstractmethod
    def erase(self, info_hash: str) -> Any:
        """Remove a torrent from the client."""
        pass

    @abstractmethod
    def get_torrent(self, info_hash: str) -> Generator[Dict[str, Any], None, None]:
        """Get information about a specific torrent."""
        pass
