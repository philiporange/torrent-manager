"""
Abstract base class defining the interface for torrent clients.

Both RTorrentClient and TransmissionClient implement this interface,
allowing them to be used interchangeably through the client factory.

Includes support for torrent labels which can be used to track torrents
with an id:<torrent_manager_id> label or any other custom labels.
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
    def add_torrent(self, path: str, start: bool = True, labels: Optional[List[str]] = None) -> bool:
        """
        Add a torrent from a local .torrent file.

        Args:
            path: Path to the .torrent file
            start: Whether to start the torrent immediately
            labels: Optional list of labels to set on the torrent

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def add_torrent_url(self, url: str, start: bool = True, labels: Optional[List[str]] = None) -> bool:
        """
        Add a torrent from a URL to a .torrent file.

        Args:
            url: HTTP/HTTPS URL to a .torrent file
            start: Whether to start the torrent immediately
            labels: Optional list of labels to set on the torrent

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def add_magnet(self, uri: str, start: bool = True, labels: Optional[List[str]] = None) -> bool:
        """
        Add a torrent from a magnet link.

        Args:
            uri: Magnet URI
            start: Whether to start the torrent immediately
            labels: Optional list of labels to set on the torrent

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

    @abstractmethod
    def get_labels(self, info_hash: str) -> List[str]:
        """
        Get labels for a torrent.

        Args:
            info_hash: The torrent's info hash

        Returns:
            List of label strings
        """
        pass

    @abstractmethod
    def set_labels(self, info_hash: str, labels: List[str]) -> Any:
        """
        Set labels for a torrent, replacing any existing labels.

        Args:
            info_hash: The torrent's info hash
            labels: List of label strings to set

        Returns:
            Result of the operation
        """
        pass

    @abstractmethod
    def add_label(self, info_hash: str, label: str) -> Any:
        """
        Add a label to a torrent without removing existing labels.

        Args:
            info_hash: The torrent's info hash
            label: Label string to add

        Returns:
            Result of the operation
        """
        pass

    @abstractmethod
    def remove_label(self, info_hash: str, label: str) -> Any:
        """
        Remove a label from a torrent.

        Args:
            info_hash: The torrent's info hash
            label: Label string to remove

        Returns:
            Result of the operation
        """
        pass
