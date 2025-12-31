"""
RTorrent XMLRPC client with comprehensive error handling and configurable timeouts.

Provides the RTorrentClient class for interacting with rTorrent via XMLRPC,
including adding torrents from files/URLs/magnets, managing torrent state,
and querying torrent information. Features detailed error messages for
invalid or malformed torrent files and configurable connection timeouts
to prevent blocking on unreachable servers.

Supports both HTTP and HTTPS connections with automatic selection of the
appropriate transport layer based on the URL scheme.

Labels are stored in d.custom1 (ruTorrent compatible) as comma-separated values.
"""

import os
import socket
import tempfile
import time
from typing import Any, Dict, Generator, List, Optional
from xmlrpc import client

import requests

from .base_client import BaseTorrentClient
from .config import Config
from .logger import logger
from .torrent_file import TorrentFile, TorrentFileError, InvalidTorrentFileError, MissingRequiredKeyError
from .magnet_link import MagnetLink


RTORRENT_RPC_URL = Config.RTORRENT_RPC_URL


class TimeoutTransport(client.Transport):
    """Custom transport with configurable timeout for HTTP XMLRPC connections."""
    def __init__(self, timeout=10, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self.timeout
        return conn


class TimeoutSafeTransport(client.SafeTransport):
    """Custom transport with configurable timeout for HTTPS XMLRPC connections."""
    def __init__(self, timeout=10, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self.timeout
        return conn


class RTorrentClient(BaseTorrentClient):
    def __init__(self, url: str = RTORRENT_RPC_URL, view: str = "main", timeout: int = 10):
        self.url = url
        self.timeout = timeout
        # Use SafeTransport for HTTPS, Transport for HTTP
        if url.startswith('https://'):
            transport = TimeoutSafeTransport(timeout=timeout)
        else:
            transport = TimeoutTransport(timeout=timeout)
        self.client = client.ServerProxy(url, transport=transport)
        self.view = view

    def __getattr__(self, name):
        return getattr(self.client, name)

    def check_connection(self) -> bool:
        """Test if the connection to rTorrent is working."""
        try:
            self.client.system.client_version()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to rTorrent at {self.url}: {e}")
            return False

    def check_methods(self):
        methods = self.client.system.listMethods()
        required_methods = [
            "load.raw_start", "load.start", "load", "d.stop", "d.start", "d.erase",
            "d.is_multi_file", "d.base_path", "download_list", "d.name", "d.size_bytes",
            "d.completed_bytes", "d.up.rate", "d.down.rate", "d.peers_connected",
            "d.ratio", "d.priority.set", "d.priority", "d.timestamp.started",
            "t.url", "d.pause", "d.resume", "d.check_hash", "d.directory",
            "d.tied_to_file", "f.path", "f.size_bytes", "f.priority", "f.priority.set"
        ]
        for method in required_methods:
            if method not in methods:
                logger.error(f"Method {method} not found")
                return False
        return True

    def add_torrent(self, path, start=True, priority=1, labels: Optional[List[str]] = None):
        # Get info_hash
        try:
            tf = TorrentFile(path)
        except InvalidTorrentFileError as e:
            logger.error(f"Invalid torrent file format: {e}")
            raise ValueError(f"Invalid torrent file: {e}")
        except MissingRequiredKeyError as e:
            logger.error(f"Torrent file missing required fields: {e}")
            raise ValueError(f"Invalid torrent file: {e}")
        except TorrentFileError as e:
            logger.error(f"Failed to read torrent file: {e}")
            raise ValueError(f"Failed to read torrent file: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing torrent file: {e}")
            raise ValueError(f"Failed to parse torrent file: {e}")

        info_hash = tf.info_hash()

        # Add torrent
        with open(path, "rb") as f:
            data = f.read()
        if start:
            result = self.client.load.raw_start("", client.Binary(data))
        else:
            result = self.client.load.raw("", client.Binary(data))

        # Set priority
        if priority != 1:
            if self.is_multi_file(info_hash):
                for i in range(len(tf.files())):
                    self.set_file_priority(info_hash, i, priority)
            else:
                self.set_priority(info_hash, priority)

        # Set labels
        if labels and result == 0:
            self.set_labels(info_hash, labels)

        return result == 0

    def add_torrent_url(self, url, start=True, priority=1, labels: Optional[List[str]] = None):
        """Add a torrent from a URL by downloading the .torrent file first.

        Note: For private trackers that validate IP addresses, the torrent server's
        IP must be registered with the tracker, or use file upload instead.
        """
        path = self._download_torrent_file(url)
        try:
            tf = TorrentFile(path)
        except InvalidTorrentFileError as e:
            logger.error(f"Invalid torrent file format from URL: {e}")
            os.remove(path)
            raise ValueError(f"Invalid torrent file from URL: {e}")
        except MissingRequiredKeyError as e:
            logger.error(f"Torrent file from URL missing required fields: {e}")
            os.remove(path)
            raise ValueError(f"Invalid torrent file from URL: {e}")
        except TorrentFileError as e:
            logger.error(f"Failed to read torrent file from URL: {e}")
            os.remove(path)
            raise ValueError(f"Failed to read torrent file from URL: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing torrent file from URL: {e}")
            os.remove(path)
            raise ValueError(f"Failed to parse torrent file from URL: {e}")

        with open(path, "rb") as f:
            data = f.read()
        info_hash = tf.info_hash()

        if start:
            result = self.client.load.raw_start(self.view, client.Binary(data))
        else:
            result = self.client.load.raw(self.view, client.Binary(data))

        if priority != 1:
            if self.is_multi_file(info_hash):
                for i in range(len(tf.files())):
                    self.set_file_priority(info_hash, i, priority)
            else:
                self.set_priority(info_hash, priority)

        # Set labels
        if labels and result == 0:
            self.set_labels(info_hash, labels)

        os.remove(path)
        return result == 0
    
    def add_magnet(self, uri, start=True, priority=1, labels: Optional[List[str]] = None):
        """Add a magnet link to rTorrent."""
        try:
            ml = MagnetLink(uri)
            info_hash = ml.info_hash

            if start:
                result = self.client.load.start("", uri)
            else:
                result = self.client.load("", uri)

            if result == 0:
                logger.debug(f"Added magnet to rTorrent: {info_hash}")
                # Small delay to let rtorrent register the torrent
                if priority != 1 or labels:
                    time.sleep(0.5)
                if priority != 1:
                    self.set_priority(info_hash, priority)
                if labels:
                    self.set_labels(info_hash, labels)
                return True

            logger.error(f"rTorrent rejected magnet: {info_hash}")
            return False

        except Exception as e:
            logger.error(f"Failed to add magnet to rTorrent: {e}", exc_info=True)
            return False

    def stop(self, info_hash):
        return self.client.d.stop(info_hash)
    
    def stop_all(self):
        for info_hash in self.list_all_info_hashes():
            self.stop(info_hash)
    
    def start(self, info_hash):
        return self.client.d.start(info_hash)

    def start_all(self):
        for info_hash in self.list_all_info_hashes():
            self.start(info_hash)

    def erase(self, info_hash, stop_first=True, wait=True):
        if stop_first:
            self.stop(info_hash)
            time.sleep(1)
        
        result = self.client.d.erase(info_hash)
        if wait:
            time.sleep(1)
        return result

    def erase_all(self):
        for info_hash in self.list_all_info_hashes():
            print(f"Erasing {info_hash}")
            self.erase(info_hash)

    def is_multi_file(self, info_hash):
        return self.client.d.is_multi_file(info_hash)
    
    def base_path(self, info_hash):
        return self.client.d.base_path(info_hash)

    def list_all_info_hashes(self):
        return self.client.download_list("")

    def list_torrents(self, info_hash="", files=False) -> Generator[Dict[str, Any], None, None]:
        keys = [
            "info_hash",
            "name",
            "base_path",  # Path to this torrent's data
            "directory",  # Download directory
            "size",
            "is_multi_file",
            "bytes_done",
            "state",
            "is_active",
            "complete",
            "ratio",
            "upload_rate",
            "download_rate",
            "peers",
            "priority",
            "is_private",
        ]
        data = self.client.d.multicall2(info_hash, self.view,
            "d.hash=",
            "d.name=",
            "d.base_path=",
            "d.directory=",
            "d.size_bytes=",
            "d.is_multi_file=",
            "d.bytes_done=",
            "d.state=",
            "d.is_active=",
            "d.complete=",
            "d.ratio=",
            "d.up.rate=",
            "d.down.rate=",
            "d.peers_connected=",
            "d.priority=",
            "d.is_private=",
        )

        # Convert data to dictionary
        items = []
        for values in data:
            item = {key: value for key, value in zip(keys, values)}
            items.append(item)
            
        # Fixes
        for item in items:
            # Boolean values
            item["is_multi_file"] = item["is_multi_file"] == 1
            item["is_active"] = item["is_active"] == 1
            item["complete"] = item["complete"] == 1
            item["is_private"] = item["is_private"] == 1

            item_hash = item["info_hash"]
            name = item["name"]
            item['is_magnet'] = name == f"{item_hash}.meta"
            item["progress"] = item["bytes_done"] / item["size"] if item["size"] > 0 else 0

            if item["is_multi_file"]:
                item["directory"] = os.path.dirname(item["base_path"])

            if files:
                item["files"] = list(self.files(item_hash))

        for item in items:
            # Filter by info_hash if one was provided
            if info_hash and item["info_hash"].upper() != info_hash.upper():
                continue
            yield item

    def get_torrent(self, info_hash) -> Generator[Dict[str, Any], None, None]:
        for torrent in self.list_torrents(info_hash):
            yield torrent

    def name(self, info_hash):
        return self.client.d.name(info_hash)
    
    def status(self, info_hash):
        return self.client.d.state(info_hash)
    
    def progress(self, info_hash):
        size = self.client.d.size_bytes(info_hash)
        completed = self.client.d.completed_bytes(info_hash)
        return completed / size if size > 0 else 0
    
    def is_active(self, info_hash):
        return self.client.d.is_active(info_hash)

    def is_complete(self, info_hash):
        return self.client.d.complete(info_hash)
    
    def download_rate(self, info_hash):
        return self.client.d.down.rate(info_hash)

    def upload_rate(self, info_hash):
        return self.client.d.up.rate(info_hash)

    def size_bytes(self, info_hash):
        return self.client.d.size_bytes(info_hash)

    def completed_bytes(self, info_hash):
        return self.client.d.completed_bytes(info_hash)

    def peers(self, info_hash):
        return self.client.d.peers_connected(info_hash)

    def ratio(self, info_hash):
        return self.client.d.ratio(info_hash)

    def set_priority(self, info_hash, priority):
        return self.client.d.priority.set(info_hash, priority)

    def get_priority(self, info_hash):
        return self.client.d.priority(info_hash)

    def creation_date(self, info_hash):
        return self.client.d.timestamp.started(info_hash)

    def tracker_url(self, info_hash):
        return self.client.t.url(info_hash, 0)

    def pause(self, info_hash):
        return self.client.d.pause(info_hash)

    def resume(self, info_hash):
        return self.client.d.resume(info_hash)

    def recheck(self, info_hash):
        return self.client.d.check_hash(info_hash)

    def set_upload_limit(self, info_hash, limit):
        return self.client.d.up.rate(info_hash, str(limit))

    def set_download_limit(self, info_hash, limit):
        return self.client.d.down.rate(info_hash, str(limit))

    def download_directory(self, info_hash):
        return self.client.d.directory(info_hash)

    def actual_torrent_path(self, info_hash):
        base_path = self.download_directory(info_hash)
        if self.is_multi_file(info_hash):
            return base_path
        else:
            file_name = self.name(info_hash)
            return os.path.join(base_path, file_name)

    def torrent_file_path(self, info_hash):
        return self.client.d.tied_to_file(info_hash)
    
    def files(self, info_hash, pattern=""):
        file_data = self.client.f.multicall(info_hash, pattern, "f.path=", "f.size_bytes=", "f.size_chunks=", "f.completed_chunks=", "f.priority=")
        for i, f in enumerate(file_data):
            path, size, size_chunks, completed_chunks, priority = f
            progress = completed_chunks / size_chunks if size_chunks > 0 else 0
            yield {
                "index": i,
                "path": path,
                "size": size,
                "priority": priority,
                "progress": progress,
            }

    def set_priority(self, info_hash, priority=0):
        return self.client.d.priority.set(info_hash, priority)

    def set_file_priority(self, info_hash, file_index, priority):
        file_id = f"{info_hash}:f{file_index}"
        return self.client.f.priority.set(file_id, priority)

    def set_file_priorities(self, info_hash, priorities):
        for file_index, priority in priorities:
            self.set_file_priority(info_hash, file_index, priority)

    def _download_torrent_file(self, url):
        """Download a .torrent file from a URL to a temporary file."""
        response = requests.get(url)
        response.raise_for_status()

        temp_dir = tempfile.gettempdir()
        random_name = os.urandom(16).hex()
        temp_path = os.path.join(temp_dir, random_name + ".torrent")

        with open(temp_path, "wb") as f:
            f.write(response.content)

        return temp_path

    def get_labels(self, info_hash: str) -> List[str]:
        """
        Get labels for a torrent using d.custom1 (ruTorrent compatible).

        Labels are stored as comma-separated values in d.custom1.
        """
        try:
            label_str = self.client.d.custom1(info_hash)
            if not label_str:
                return []
            return [l.strip() for l in label_str.split(',') if l.strip()]
        except Exception as e:
            logger.error(f"Failed to get labels for {info_hash}: {e}")
            return []

    def set_labels(self, info_hash: str, labels: List[str]) -> bool:
        """
        Set labels for a torrent using d.custom1 (ruTorrent compatible).

        Labels are stored as comma-separated values in d.custom1.
        """
        try:
            label_str = ','.join(labels)
            result = self.client.d.custom1.set(info_hash, label_str)
            return result == 0
        except Exception as e:
            logger.error(f"Failed to set labels for {info_hash}: {e}")
            return False

    def add_label(self, info_hash: str, label: str) -> bool:
        """Add a label to a torrent without removing existing labels."""
        labels = self.get_labels(info_hash)
        if label not in labels:
            labels.append(label)
            return self.set_labels(info_hash, labels)
        return True

    def remove_label(self, info_hash: str, label: str) -> bool:
        """Remove a label from a torrent."""
        labels = self.get_labels(info_hash)
        if label in labels:
            labels.remove(label)
            return self.set_labels(info_hash, labels)
        return True

    def _set_torrent_manager_id(self, info_hash: str, torrent_manager_id: str) -> bool:
        """Set the torrent manager ID label on a torrent."""
        return self.add_label(info_hash, f"id:{torrent_manager_id}")