import time

import pytest
from torrent_manager.manager import Manager

@pytest.fixture(scope="function")
def manager(rtorrent_client):
    return Manager(client=rtorrent_client)

@pytest.mark.usefixtures("docker_rtorrent", "rtorrent_client")
class TestManager:
    def test_get_torrents(self, manager):
        torrents = manager.get_torrents()
        assert isinstance(torrents, list)

    def test_rtorrent_client(self):
        # Check if the rTorrent client is working
        try:
            self.rtorrent_client.system.client_version()
            print("Connected to rTorrent")
        except client.Fault as e:
            self.fail(f"Failed to connect to rTorrent: {e}")

        # List methods
        methods = self.rtorrent_client.system.listMethods()
        assert len(methods) > 0, "No methods found"
        assert "load.raw_start" in methods, "Method load.raw_start not found"
        
    def test_add_torrent_and_check_running(self):
        # Path to the test torrent file
        torrent_file = "assets/debian-12.6.0-amd64-netinst.iso.torrent"
        
        # Ensure the torrent file exists
        self.assertTrue(os.path.exists(torrent_file), f"Test torrent file {torrent_file} not found")

        
        # List existing torrents
        torrents = self.manager.get_torrents()

        # Add the torrent
        with open(torrent_file, "rb") as f:
            torrent_data = f.read()
        
        bin_data = xmlrpc.client.Binary(torrent_data)
        result = self.rtorrent_client.load.raw_start('', bin_data)
        assert result == 0, "Failed to add torrent"

        # Get new list of torrents
        new_torrents = self.manager.get_torrents()
        delta = set(new_torrents) - set(torrents)
        assert len(delta) == 1, "Torrent not added"
        info_hash = delta.pop()
        
        # Wait for the torrent to start
        time.sleep(5)
        
        # Check if the torrent is active
        is_active = self.rtorrent_client.d.is_active(info_hash)
        self.assertEqual(is_active, 1, f"Torrent {info_hash} is not active")

        # Optionally, you can check more details about the torrent
        name = self.rtorrent_client.d.name(info_hash)
        size = self.rtorrent_client.d.size_bytes(info_hash)
        print(f"Torrent Name: {name}")
        print(f"Torrent Size: {size} bytes")

        # Stop the torrent
        self.rtorrent_client.d.stop(info_hash)
        time.sleep(5)
        

        '''
        # Check if the torrent is stopped
        is_active = self.rtorrent_client.d.is_active(info_hash)
        
        # Remove the torrent
        self.rtorrent_client.d.erase(info_hash)
        time.sleep(5)
        
        # Check if the torrent is removed
        torrents = self.manager.get_torrents()
        assert info_hash not in torrents, "Torrent not removed"
        '''


if __name__ == '__main__':
    unittest.main()