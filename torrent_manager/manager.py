import os
import shutil
import time

from .activity import Activity
from .rtorrent_client import RTorrentClient
from .config import Config
from .logger import logger


INCOMPLETE_PATH = Config.INCOMPLETE_PATH
COMPLETE_PATH = Config.COMPLETE_PATH
MIN_SEEDING_DURATION = Config.MIN_SEEDING_DURATION
MAX_INTERVAL = Config.MAX_INTERVAL


class Manager:
    def __init__(
            self,
            client=None,
            activity_log=None,
        ):
        self.client = client or RTorrentClient()
        self.activity = activity_log or Activity()

    def add_torrent(self, path):
        pass

    def list_torrents(self):
        return self.client.list_torrents()

    def get_torrents(self):
        """Alias for list_torrents for backwards compatibility."""
        return [t['info_hash'] for t in self.client.list_torrents()]

    def get_seeding_torrents(self):
        return [t for t in self.get_torrents() if self.rtorrent.d.is_active(t) == 1 and self.rtorrent.d.complete(t) == 1]
    
    def get_seeding_duration(self, info_hash):
        return self.activity.get_seeding_duration(info_hash, max_interval=MAX_INTERVAL)

    def get_completed_torrents(self):
        return [t for t in self.get_torrents() if self.rtorrent.d.complete(t) == 1]

    def move(self, info_hash, destination=COMPLETE_PATH):
        logger.info(f"Moving {info_hash} to {destination}")
        torrent = self.client.get_torrent(info_hash)
        if torrent is None:
            return

        # Stop the torrent
        self.client.stop(info_hash)
        time.sleep(1)

        # Move torrent
        if os.path.exists(destination_path):
            shutil.rmtree(destination_path)

        if is_multi_file:
            shutil.copytree(base_path, destination_path)
        else:
            shutil.copy2(base_path, destination_path)

        # Update torrent directory in rTorrent
        self.rtorrent.d.directory.set(info_hash, destination)

        # Restart the torrent
        self.rtorrent.d.start(info_hash)
        while self.rtorrent.d.is_active(info_hash) == 0:
            time.sleep(1)

        # Remove old torrent files
        if is_multi_file:
            shutil.rmtree(base_path)
        else:
            os.remove(base_path)

    def move_completed_torrents(self):
        for info_hash in self.get_completed_torrents():
            if self.rtorrent.d.directory(info_hash) != COMPLETE_PATH:
                self.move(info_hash, COMPLETE_PATH)

    def pause_seeded(self):
        for info_hash in self.get_seeding_torrents():
            seeding_duration = self.get_seeding_duration(info_hash)
            if seeding_duration > MIN_SEEDING_DURATION:
                logger.info(f"Pausing long-seeded torrent {self.rtorrent.d.name(info_hash)}")
                self.rtorrent.d.stop(info_hash)

    def remove_old_seeded(self):
        for info_hash in self.get_torrents():
            if self.rtorrent.d.is_active(info_hash) == 0 and self.rtorrent.d.complete(info_hash) == 1:
                seeding_duration = self.get_seeding_duration(info_hash)
                if seeding_duration > MIN_SEEDING_DURATION + 3600:  # Add 1 hour buffer
                    name = self.rtorrent.d.name(info_hash)
                    logger.info(f"Removing old seeded torrent {name}")
                    self.rtorrent.d.erase(info_hash)
                    self.activity_log.purge_logs_for_torrent(info_hash)

    def log_all(self):
        for info_hash in self.get_torrents():
            is_seeding = self.rtorrent.d.is_active(info_hash) == 1 and self.rtorrent.d.complete(info_hash) == 1
            self.activity_log.log(info_hash, is_seeding=is_seeding)

    def ping(self):
        if self.rtorrent.system.client_version() is None:
            return False

        return True

    def run_maintenance(self):
        self.move_completed_torrents()
        self.pause_seeded()
        self.remove_old_seeded()
        self.log_all()
        self.activity_log.purge_old_logs()