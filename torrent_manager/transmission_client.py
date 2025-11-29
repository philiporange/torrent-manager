"""
Transmission RPC client for managing torrents.

Provides the TransmissionClient class for interacting with Transmission via RPC,
implementing the same interface as RTorrentClient for interchangeable use.
"""

import os
import tempfile
from typing import Any, Dict, Generator, List, Optional

import requests
from transmission_rpc import Client as TransmissionRPCClient
from transmission_rpc.torrent import Torrent as TransmissionTorrent

from .base_client import BaseTorrentClient
from .config import Config
from .logger import logger
from .torrent_file import TorrentFile
from .magnet_link import MagnetLink


TRANSMISSION_HOST = Config.TRANSMISSION_HOST
TRANSMISSION_PORT = Config.TRANSMISSION_PORT
TRANSMISSION_USERNAME = Config.TRANSMISSION_USERNAME
TRANSMISSION_PASSWORD = Config.TRANSMISSION_PASSWORD


class TransmissionClient(BaseTorrentClient):
    def __init__(
        self,
        protocol: str = "http",
        host: str = TRANSMISSION_HOST,
        port: int = TRANSMISSION_PORT,
        path: str = "/transmission/rpc",
        username: Optional[str] = TRANSMISSION_USERNAME,
        password: Optional[str] = TRANSMISSION_PASSWORD
    ):
        self.host = host
        self.port = port
        self.client = TransmissionRPCClient(
            protocol=protocol,
            host=host,
            port=port,
            path=path,
            username=username or None,
            password=password or None
        )

    def _get_torrent_by_hash(self, info_hash: str) -> TransmissionTorrent:
        torrents = self.client.get_torrents()
        for torrent in torrents:
            if torrent.hashString.lower() == info_hash.lower():
                return torrent
        raise ValueError(f"No torrent found with hash {info_hash}")

    def check_connection(self) -> bool:
        """Test if the connection to Transmission is working."""
        try:
            self.client.session_stats()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Transmission at {self.host}:{self.port}: {e}")
            return False

    def add_torrent(self, path, start=True, priority=1):
        tf = TorrentFile(path)
        info_hash = tf.info_hash
        file_count = len(tf.files())
        
        params = {
            'paused': not start,
        }

        # Set priority
        if priority == 0:
            params['files_unwanted'] = list(range(file_count))
        elif priority == 2:
            params['priority_high'] = list(range(file_count))

        # Add torrent
        with open(path, "rb") as f:
            torrent_data = f.read()
        
        torrent = self.client.add_torrent(torrent_data, **params)
        
        return torrent is not None

    def add_torrent_url(self, url, start=True, priority=1):
        path = self.download_remote_file(url)
        result = self.add_torrent(path, start, priority)
        os.remove(path)
        return result

    def add_magnet(self, uri, start=True):
        torrent = self.client.add_torrent(uri, paused=not start)
        if not torrent:
            return False

        return True

    def stop(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        return self.client.stop_torrent(torrent.id)

    def stop_all(self):
        for torrent in self.client.get_torrents():
            self.client.stop_torrent(torrent.id)

    def start(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        return self.client.start_torrent(torrent.id)

    def start_all(self):
        for torrent in self.client.get_torrents():
            self.client.start_torrent(torrent.id)

    def erase(self, info_hash, delete_data=False):
        torrent = self._get_torrent_by_hash(info_hash)
        return self.client.remove_torrent(torrent.id, delete_data=delete_data)

    def erase_all(self, delete_data=False):
        for torrent in self.client.get_torrents():
            self.client.remove_torrent(torrent.id, delete_data=delete_data)

    def is_multi_file(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        return len(torrent.files()) > 1

    def base_path(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        return torrent.download_dir

    def list_all_info_hashes(self):
        return [torrent.hashString for torrent in self.client.get_torrents()]

    def list_torrents(self, info_hash=None, files=False) -> Generator[Dict[str, Any], None, None]:
        if info_hash:
            torrents = [self._get_torrent_by_hash(info_hash)]
        else:
            torrents = self.client.get_torrents()

        for torrent in torrents:
            item = {
                "info_hash": torrent.hashString,
                "name": torrent.name,
                "base_path": torrent.download_dir,
                "directory": torrent.download_dir,
                "size": torrent.total_size,
                "is_multi_file": len(torrent.files()) > 1,
                "bytes_done": torrent.progress * torrent.total_size / 100,
                "state": torrent.status,
                "is_active": torrent.status in ['downloading', 'seeding'],
                "complete": torrent.progress == 100,
                "ratio": torrent.ratio,
                "upload_rate": torrent.rate_upload,
                "download_rate": torrent.rate_download,
                "peers": torrent.peers_connected,
                "priority": self._get_torrent_priority(torrent),
                "progress": torrent.progress / 100,
                "is_magnet": torrent.magnet_link is not None,
            }

            if files:
                item["files"] = list(self.files(torrent.hashString))

            yield item

    def get_torrent(self, info_hash) -> Generator[Dict[str, Any], None, None]:
        yield from self.list_torrents(info_hash)

    def name(self, info_hash):
        return self._get_torrent_by_hash(info_hash).name

    def status(self, info_hash):
        return self._get_torrent_by_hash(info_hash).status

    def progress(self, info_hash):
        return self._get_torrent_by_hash(info_hash).progress / 100

    def is_active(self, info_hash):
        status = self.status(info_hash)
        return status in ['downloading', 'seeding']

    def is_complete(self, info_hash):
        return self._get_torrent_by_hash(info_hash).progress == 100

    def download_rate(self, info_hash):
        return self._get_torrent_by_hash(info_hash).rate_download

    def upload_rate(self, info_hash):
        return self._get_torrent_by_hash(info_hash).rate_upload

    def size_bytes(self, info_hash):
        return self._get_torrent_by_hash(info_hash).total_size

    def completed_bytes(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        return int(torrent.progress * torrent.total_size / 100)

    def peers(self, info_hash):
        return self._get_torrent_by_hash(info_hash).peers_connected

    def ratio(self, info_hash):
        return self._get_torrent_by_hash(info_hash).ratio

    def set_priority(self, info_hash, priority):
        torrent = self._get_torrent_by_hash(info_hash)
        file_count = len(torrent.files())
        
        if priority == 0:
            self.client.change_torrent(torrent.id, files_unwanted=list(range(file_count)))
        elif priority == 1:
            self.client.change_torrent(torrent.id, files_wanted=list(range(file_count)), priority_normal=list(range(file_count)))
        elif priority == 2:
            self.client.change_torrent(torrent.id, files_wanted=list(range(file_count)), priority_high=list(range(file_count)))

    def get_priority(self, info_hash):
        return self._get_torrent_priority(self._get_torrent_by_hash(info_hash))

    def _get_torrent_priority(self, torrent):
        if all(not file['wanted'] for file in torrent.files()):
            return 0
        elif any(file['priority'] == 'high' for file in torrent.files()):
            return 2
        else:
            return 1

    def creation_date(self, info_hash):
        return self._get_torrent_by_hash(info_hash).date_added

    def tracker_url(self, info_hash):
        trackers = self._get_torrent_by_hash(info_hash).trackers
        return trackers[0]['announce'] if trackers else None

    def pause(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        return self.client.stop_torrent(torrent.id)

    def resume(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        return self.client.start_torrent(torrent.id)

    def recheck(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        return self.client.verify_torrent(torrent.id)

    def set_upload_limit(self, info_hash, limit):
        torrent = self._get_torrent_by_hash(info_hash)
        return self.client.change_torrent(torrent.id, uploadLimit=limit)

    def set_download_limit(self, info_hash, limit):
        torrent = self._get_torrent_by_hash(info_hash)
        return self.client.change_torrent(torrent.id, downloadLimit=limit)

    def download_directory(self, info_hash):
        return self._get_torrent_by_hash(info_hash).download_dir

    def actual_torrent_path(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        if len(torrent.files()) > 1:
            return torrent.download_dir
        else:
            return os.path.join(torrent.download_dir, torrent.name)

    def torrent_file_path(self, info_hash):
        # Transmission doesn't provide direct access to the .torrent file path
        # This method might not be directly implementable
        return None

    def files(self, info_hash):
        torrent = self._get_torrent_by_hash(info_hash)
        for i, file in enumerate(torrent.files()):
            priority = 0 if not file['wanted'] else (2 if file['priority'] == 'high' else 1)
            yield {
                "index": i,
                "path": file['name'],
                "size": file['size'],
                "priority": priority,
                "progress": file['completed'] / file['size'] if file['size'] > 0 else 0,
            }

    def set_file_priority(self, info_hash, file_index, priority):
        torrent = self._get_torrent_by_hash(info_hash)
        if priority == 0:
            self.client.change_torrent(torrent.id, files_unwanted=[file_index])
        elif priority == 1:
            self.client.change_torrent(torrent.id, files_wanted=[file_index], priority_normal=[file_index])
        elif priority == 2:
            self.client.change_torrent(torrent.id, files_wanted=[file_index], priority_high=[file_index])

    def set_file_priorities(self, info_hash, priorities):
        torrent = self._get_torrent_by_hash(info_hash)
        files_unwanted = []
        files_normal = []
        files_high = []
        for file_index, priority in priorities:
            if priority == 0:
                files_unwanted.append(file_index)
            elif priority == 1:
                files_normal.append(file_index)
            elif priority == 2:
                files_high.append(file_index)
        
        self.client.change_torrent(torrent.id, 
                                   files_unwanted=files_unwanted,
                                   priority_normal=files_normal,
                                   priority_high=files_high)

    def download_remote_file(self, url):
        temp_dir = tempfile.gettempdir()
        
        response = requests.get(url)
        response.raise_for_status()

        random_name = os.urandom(16).hex()
        temp_filename = random_name + ".torrent"
        temp_path = os.path.join(temp_dir, temp_filename)
        
        with open(temp_path, "wb") as f:
            f.write(response.content)

        return temp_path
