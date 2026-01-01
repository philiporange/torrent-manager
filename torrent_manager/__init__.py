"""
Torrent Manager - Manage torrent clients via REST API.

Provides a unified interface for managing rTorrent and Transmission
clients with secure authentication and a web frontend.
"""

from .client import TorrentManagerClient
from .config import Config

__version__ = "0.1.0"
__all__ = ["TorrentManagerClient", "Config"]
