import pytest
import os
import time
from src.torrent_manager.config import Config

RTORRENT_RPC_URL = Config.RTORRENT_RPC_URL

@pytest.mark.usefixtures("docker_rtorrent", "rtorrent_client")
class TestRTorrentClient:
    @pytest.fixture(autouse=True)
    def setup_method(self, rtorrent_client):
        # Erase all torrents before each test
        for torrent in rtorrent_client.list_torrents():
            rtorrent_client.erase(torrent['info_hash'])
        
        # Wait for torrents to be removed
        time.sleep(2)
        
        # Verify all torrents are removed
        assert len(list(rtorrent_client.list_torrents())) == 0, "Failed to remove all torrents in setup"

    def test_add_and_remove_torrent(self, rtorrent_client):
        # Prepare test torrent file
        torrent_file = "assets/debian-12.6.0-amd64-netinst.iso.torrent"
        assert os.path.exists(torrent_file), f"Test torrent file {torrent_file} not found"

        # Get initial torrent count
        initial_torrents = list(rtorrent_client.list_torrents())
        initial_count = len(initial_torrents)

        # Add torrent
        result = rtorrent_client.add_torrent(torrent_file)
        assert result is True, "Failed to add torrent"

        # Check if torrent is added
        time.sleep(2)  # Wait for torrent to be added
        torrents = list(rtorrent_client.list_torrents())
        assert len(torrents) == initial_count + 1, "Torrent not added to the list"

        # Get the added torrent's info hash
        added_torrent = [t for t in torrents if t not in initial_torrents][0]
        info_hash = added_torrent['info_hash']

        # Verify torrent properties
        assert added_torrent['name'] == "debian-12.6.0-amd64-netinst.iso", "Incorrect torrent name"
        assert added_torrent['is_active'] == 1, "Torrent is not active"

        # Remove torrent
        rtorrent_client.erase(info_hash)
        time.sleep(2)  # Wait for torrent to be removed

        # Check if torrent is removed
        torrents = list(rtorrent_client.list_torrents())
        assert len(torrents) == initial_count, "Failed to remove torrent"

    def test_connection(self, rtorrent_client):
        version = rtorrent_client.system.client_version()
        assert version is not None, "Failed to get rTorrent version"

    def test_priority_methods(self, rtorrent_client):
        magnet_link = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fbig-buck-bunny.torrent"

        # Add torrent using magnet link
        result = rtorrent_client.add_magnet(magnet_link)
        assert result is True, "Failed to add torrent using magnet link"

        # Wait for torrent to be added and metadata to be fetched
        time.sleep(10)

        # Get the added torrent's info hash
        torrents = list(rtorrent_client.list_torrents())
        added_torrent = [t for t in torrents if t['name'] == "Big Buck Bunny"][0]
        info_hash = added_torrent['info_hash']

        # Test setting and getting torrent priority
        rtorrent_client.set_priority(info_hash, 2)  # Set to high priority
        assert rtorrent_client.get_priority(info_hash) == 2, "Failed to set high priority"

        rtorrent_client.set_priority(info_hash, 1)  # Set to normal priority
        assert rtorrent_client.get_priority(info_hash) == 1, "Failed to set normal priority"

        # Test setting and getting file priorities
        files = list(rtorrent_client.files(info_hash))
        assert len(files) == 3, "Expected 3 files in the torrent"

        file_priorities = [
            (0, 0),  # Set poster.jpg to "don't download"
            (1, 1),  # Set Big Buck Bunny.en.srt to normal priority
            (2, 2),  # Set Big Buck Bunny.mp4 to high priority
        ]

        for file_index, priority in file_priorities:
            rtorrent_client.set_file_priority(info_hash, file_index, priority)

        # Verify file priorities
        files = list(rtorrent_client.files(info_hash))
        for file, (_, expected_priority) in zip(files, file_priorities):
            assert file['priority'] == expected_priority, f"File {file['path']} has incorrect priority"

        # Remove torrent
        rtorrent_client.erase(info_hash)
        time.sleep(2)  # Wait for torrent to be removed

        # Check if torrent is removed
        torrents = list(rtorrent_client.list_torrents())
        assert all(t['info_hash'] != info_hash for t in torrents), "Failed to remove torrent"


if __name__ == '__main__':
    pytest.main()