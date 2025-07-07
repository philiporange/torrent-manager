### torrent_manager

# Project Directory Structure
```
├── tests/
├── │   test_rtorrent_client.py
├── │   test_transmission_client.py
├── │   test_torrent_file.py
├── │   conftest.py
├── │   test_activity.py
├── │   test_manager.py
├── │   __init__.py
├── │   test_docker_rtorrent.py
│   ├── __pycache__/
│   ├── │   test_activity.cpython-310-pytest-8.3.2.pyc
│   ├── │   conftest.cpython-310.pyc
│   ├── │   test_manager.cpython-310-pytest-8.3.2.pyc
│   ├── │   test_torrent_file.cpython-310-pytest-8.3.2.pyc
│   ├── │   test_rtorrent_client.cpython-310-pytest-8.3.2.pyc
│   ├── │   test_client.cpython-310-pytest-8.3.2.pyc
│   ├── │   __init__.cpython-310.pyc
│   ├── │   test_docker_rtorrent.cpython-310-pytest-8.3.2.pyc
│   ├── │   conftest.cpython-310-pytest-8.3.2.pyc
├── src/
│   ├── torrent_manager/
│   ├── │   dbs.py
│   ├── │   config.py
│   ├── │   activity.py
│   ├── │   __main__.py
│   ├── │   torrent_file.py
│   ├── │   rtorrent_client.py
│   ├── │   docker_rtorrent.py
│   ├── │   manager.py
│   ├── │   magnet_link.py
│   ├── │   transmission_client.py
│   ├── │   utils.py
│   ├── │   logger.py
│   ├── │   __init__.py
│   ├── │   models.py
│   │   ├── __pycache__/
│   │   ├── │   rtorrent_client.cpython-310.pyc
│   │   ├── │   models.cpython-310.pyc
│   │   ├── │   dbs.cpython-310.pyc
│   │   ├── │   magnet_link.cpython-310.pyc
│   │   ├── │   config.cpython-310.pyc
│   │   ├── │   client.cpython-310.pyc
│   │   ├── │   activity.cpython-310.pyc
│   │   ├── │   logger.cpython-310.pyc
│   │   ├── │   torrent_file.cpython-310.pyc
│   │   ├── │   __init__.cpython-310.pyc
│   │   ├── │   docker_rtorrent.cpython-310.pyc
│   │   ├── │   manager.cpython-310.pyc```

# README.md

# Torrent Manager

A Python application for managing torrent client instances. This tool automates common tasks such as moving completed torrents, managing seeding duration, and logging torrent activity. It provides a command-line interface for configuration and maintenance, along with utilities for torrent file operations and a database for tracking torrent-related information.

## Purpose

- Interact with torrent clients programmatically
- Track and log torrent activity
- Perform maintenance tasks:
- Move completed torrents
- Pause long-seeded torrents
- Remove old seeded torrents
- Log torrent statuses
- Provide CLI for configuration and maintenance
- Offer utilities for torrent file operations
- Manage database of torrent-related information

## Features

- Command-line interface
- Torrent activity logging
- Automated maintenance tasks
- Torrent file parsing and magnet link creation
- Database management for users, torrents, and activity

# tests/test_rtorrent_client.py
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

# tests/test_transmission_client.py
import pytest
import os
import time
from src.torrent_manager.config import Config
from src.torrent_manager.transmission_client import TransmissionClient

TRANSMISSION_HOST = Config.TRANSMISSION_HOST
TRANSMISSION_PORT = Config.TRANSMISSION_PORT
TRANSMISSION_USERNAME = Config.TRANSMISSION_USERNAME
TRANSMISSION_PASSWORD = Config.TRANSMISSION_PASSWORD

@pytest.mark.usefixtures("transmission_client")
class TestTransmissionClient:
    @pytest.fixture(autouse=True)
    def setup_method(self, transmission_client):
        # Erase all torrents before each test
        for torrent in transmission_client.list_torrents():
            transmission_client.erase(torrent['info_hash'])
        
        # Wait for torrents to be removed
        time.sleep(2)
        
        # Verify all torrents are removed
        assert len(list(transmission_client.list_torrents())) == 0, "Failed to remove all torrents in setup"

    def test_add_and_remove_torrent(self, transmission_client):
        # Prepare test torrent file
        torrent_file = "assets/debian-12.6.0-amd64-netinst.iso.torrent"
        assert os.path.exists(torrent_file), f"Test torrent file {torrent_file} not found"

        # Get initial torrent count
        initial_torrents = list(transmission_client.list_torrents())
        initial_count = len(initial_torrents)

        # Add torrent
        result = transmission_client.add_torrent(torrent_file)
        assert result is True, "Failed to add torrent"

        # Check if torrent is added
        time.sleep(2)  # Wait for torrent to be added
        torrents = list(transmission_client.list_torrents())
        assert len(torrents) == initial_count + 1, "Torrent not added to the list"

        # Get the added torrent's info hash
        added_torrent = [t for t in torrents if t not in initial_torrents][0]
        info_hash = added_torrent['info_hash']

        # Verify torrent properties
        assert added_torrent['name'] == "debian-12.6.0-amd64-netinst.iso", "Incorrect torrent name"
        assert added_torrent['is_active'] == True, "Torrent is not active"

        # Remove torrent
        transmission_client.erase(info_hash)
        time.sleep(2)  # Wait for torrent to be removed

        # Check if torrent is removed
        torrents = list(transmission_client.list_torrents())
        assert len(torrents) == initial_count, "Failed to remove torrent"

    def test_connection(self, transmission_client):
        assert transmission_client.check_methods(), "Failed to connect to Transmission"

    def test_priority_methods(self, transmission_client):
        magnet_link = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny&tr=udp%3A%2F%2Fexplodie.org%3A6969&tr=udp%3A%2F%2Ftracker.coppersurfer.tk%3A6969&tr=udp%3A%2F%2Ftracker.empire-js.us%3A1337&tr=udp%3A%2F%2Ftracker.leechers-paradise.org%3A6969&tr=udp%3A%2F%2Ftracker.opentrackr.org%3A1337&tr=wss%3A%2F%2Ftracker.btorrent.xyz&tr=wss%3A%2F%2Ftracker.fastcast.nz&tr=wss%3A%2F%2Ftracker.openwebtorrent.com&ws=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2F&xs=https%3A%2F%2Fwebtorrent.io%2Ftorrents%2Fbig-buck-bunny.torrent"

        # Add torrent using magnet link
        result = transmission_client.add_magnet(magnet_link)
        assert result is True, "Failed to add torrent using magnet link"

        # Wait for torrent to be added and metadata to be fetched
        time.sleep(10)

        # Get the added torrent's info hash
        torrents = list(transmission_client.list_torrents())
        added_torrent = [t for t in torrents if t['name'] == "Big Buck Bunny"][0]
        info_hash = added_torrent['info_hash']

        # Test setting and getting torrent priority
        transmission_client.set_priority(info_hash, 2)  # Set to high priority
        assert transmission_client.get_priority(info_hash) == 2, "Failed to set high priority"

        transmission_client.set_priority(info_hash, 1)  # Set to normal priority
        assert transmission_client.get_priority(info_hash) == 1, "Failed to set normal priority"

        # Test setting and getting file priorities
        files = list(transmission_client.files(info_hash))
        assert len(files) > 0, "Expected at least one file in the torrent"

        file_priorities = [
            (0, 0),  # Set first file to "don't download"
            (1, 1),  # Set second file to normal priority
            (2, 2),  # Set third file to high priority
        ]

        for file_index, priority in file_priorities[:len(files)]:
            transmission_client.set_file_priority(info_hash, file_index, priority)

        # Verify file priorities
        files = list(transmission_client.files(info_hash))
        for file, (_, expected_priority) in zip(files, file_priorities):
            assert file['priority'] == expected_priority, f"File {file['path']} has incorrect priority"

        # Remove torrent
        transmission_client.erase(info_hash)
        time.sleep(2)  # Wait for torrent to be removed

        # Check if torrent is removed
        torrents = list(transmission_client.list_torrents())
        assert all(t['info_hash'] != info_hash for t in torrents), "Failed to remove torrent"

if __name__ == '__main__':
    pytest.main()

# tests/test_torrent_file.py
import unittest
import os
from urllib.parse import unquote

from src.torrent_manager.torrent_file import TorrentFile


class TestTorrentFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.torrent_path = "assets/debian-12.6.0-amd64-netinst.iso.torrent"
        cls.torrent_file = TorrentFile(cls.torrent_path)

    def test_file_existence(self):
        self.assertTrue(os.path.exists(self.torrent_path), "Test torrent file does not exist")

    def test_init(self):
        self.assertIsInstance(self.torrent_file, TorrentFile)
        self.assertIn('info', self.torrent_file.torrent_data)

    def test_is_multi_file(self):
        self.assertFalse(self.torrent_file.is_multi_file)

    def test_files(self):
        files = self.torrent_file.files()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0], "debian-12.6.0-amd64-netinst.iso")

    def test_info_hash(self):
        info_hash = self.torrent_file.info_hash()
        self.assertEqual(len(info_hash), 40)  # SHA1 hash is 40 characters long
        self.assertTrue(all(c in '0123456789abcdef' for c in info_hash))

    def test_size(self):
        size = self.torrent_file.size()
        self.assertEqual(size, 661651456)

    def test_piece_length(self):
        piece_length = self.torrent_file.piece_length()
        self.assertEqual(piece_length, 262144)  # 256 KB

    def test_num_pieces(self):
        num_pieces = self.torrent_file.num_pieces()
        self.assertEqual(num_pieces, 2524)

    def test_piece_hash(self):
        first_piece_hash = self.torrent_file.piece_hash(0)
        self.assertEqual(len(first_piece_hash), 40)
        self.assertTrue(all(c in '0123456789abcdef' for c in first_piece_hash))

    def test_trackers(self):
        trackers = self.torrent_file.trackers()
        expected_trackers = [
            'http://bttracker.debian.org:6969/announce',
        ]
        for tracker in expected_trackers:
            self.assertIn(tracker, trackers)

    def test_metadata(self):
        metadata = self.torrent_file.metadata()
        self.assertIn('creation date', metadata)
        self.assertIn('comment', metadata)

    def test_magnet_link(self):
        magnet_link = self.torrent_file.magnet_link()
        magnet_link = unquote(magnet_link)

        self.assertTrue(magnet_link.startswith('magnet:?'))
        self.assertIn('xt=urn:btih:', magnet_link)
        self.assertIn('dn=debian-12.6.0-amd64-netinst.iso', magnet_link)

    def test_validate(self):
        self.assertTrue(self.torrent_file.validate())

    def test_save(self):
        temp_path = "temp_test_torrent.torrent"
        self.torrent_file.save(temp_path)
        self.assertTrue(os.path.exists(temp_path))
        
        # Clean up
        os.remove(temp_path)


if __name__ == '__main__':
    unittest.main()

# tests/conftest.py
import pytest
from src.torrent_manager.docker_rtorrent import DockerRTorrent
from src.torrent_manager.rtorrent_client import RTorrentClient
from src.torrent_manager.config import Config

@pytest.fixture(scope="session")
def docker_rtorrent():
    container = DockerRTorrent(
        ports={'80/tcp': 9080},
        is_test=True,
    )
    container.start(wait_time=15)
    yield container
    container.stop()

@pytest.fixture(scope="session")
def rtorrent_client(docker_rtorrent):
    container_ip = docker_rtorrent.get_container_ip()
    if not container_ip:
        container_ip = "localhost"
    client = RTorrentClient(f"http://{container_ip}:9080/RPC2")
    yield client


# tests/test_activity.py
import unittest
import tempfile
import os
import datetime
import time

from src.torrent_manager.activity import Activity
from src.torrent_manager.models import Status
from src.torrent_manager.dbs import sdb as db


class TestActivity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_db = tempfile.NamedTemporaryFile(delete=False)
        cls.temp_db.close()
        db.init(cls.temp_db.name)
        db.connect()
        db.create_tables([Status])
        db.close()

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.temp_db.name)

    def setUp(self):
        self.activity = Activity(self.temp_db.name)
        Status.delete().execute()  # Clear the database before each test

    def tearDown(self):
        self.activity.close()

    def test_record_torrent_status(self):
        info_hash = "test_hash"
        self.activity.record_torrent_status(info_hash)
        
        status = Status.select().where(Status.torrent_hash == info_hash).get()
        
        self.assertIsNotNone(status)
        self.assertEqual(status.torrent_hash, info_hash)
        self.assertEqual(status.status, 'seeding')
        self.assertEqual(status.progress, 1.0)

    def test_calculate_seeding_duration(self):
        info_hash = "test_hash"
        start_time = datetime.datetime.now() - datetime.timedelta(hours=2)
        
        # Record seeding at different times
        for i in range(61):
            self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=i))

        duration = self.activity.calculate_seeding_duration(info_hash)
        
        expected_duration = 60 * 60  # 60 minutes * 60 seconds
        self.assertAlmostEqual(duration, expected_duration, delta=5)

    def test_calculate_seeding_duration_with_gaps(self):
        info_hash = "test_hash"
        start_time = datetime.datetime.now() - datetime.timedelta(minutes=35)
        
        # Record seeding with gaps
        self.activity.record_torrent_status(info_hash, timestamp=start_time)
        self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=1))
        self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=2))
        # Gap
        self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=32))
        self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=33))
                
        duration = self.activity.calculate_seeding_duration(info_hash)
        expected_duration = 3 * 60  # 3 minutes * 60 seconds
        self.assertAlmostEqual(duration, expected_duration, delta=5)

    def test_get_never_seeded_torrents(self):
        self.activity.record_torrent_status("seeded_hash", is_seeding=True)
        self.activity.record_torrent_status("never_seeded_hash1", is_seeding=False)
        self.activity.record_torrent_status("never_seeded_hash2", is_seeding=False)
        
        never_seeded = self.activity.get_never_seeded_torrents()
        
        self.assertEqual(set(never_seeded), {"never_seeded_hash1", "never_seeded_hash2"})
        self.assertNotIn("seeded_hash", never_seeded)

    def test_remove_old_status_records(self):
        current_time = datetime.datetime.now()
        old_time = current_time - datetime.timedelta(days=31)
        
        self.activity.record_torrent_status("old_hash", timestamp=old_time)
        self.activity.record_torrent_status("new_hash", timestamp=current_time)
        
        self.activity.remove_old_status_records(days_to_keep=30)
        
        statuses = list(Status.select())
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].torrent_hash, "new_hash")

    def test_delete_torrent_status_history(self):
        info_hash = "test_hash"
        self.activity.record_torrent_status(info_hash)
        self.activity.record_torrent_status(info_hash)
        self.activity.record_torrent_status("other_hash")
        
        self.activity.delete_torrent_status_history(info_hash)
        
        statuses = list(Status.select())
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].torrent_hash, "other_hash")


if __name__ == '__main__':
    unittest.main()

# tests/test_manager.py
import time

import pytest
from src.torrent_manager.manager import Manager

@pytest.fixture(scope="function")
def manager(rtorrent_client):
    return Manager(rtorrent=rtorrent_client)

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

# tests/__init__.py


# tests/test_docker_rtorrent.py
import unittest
import time
import xmlrpc.client

import docker

from src.torrent_manager.docker_rtorrent import DockerRTorrent
from src.torrent_manager.config import Config



class TestDockerRTorrent(unittest.TestCase):
    def setUp(self):
        self.docker_client = docker.from_env()
        self.rtorrent = DockerRTorrent(remove=True)

    def tearDown(self):
        self.rtorrent.stop()
        self.docker_client.close()

    @unittest.skip("Not required, if accessiblity test passes")
    def test_container_creation_and_removal(self):
        # Start the container
        self.rtorrent.start()

        # Check if the container is created
        container_id = self.rtorrent.container.id
        containers = self.docker_client.containers.list(all=True)
        self.assertTrue(any(container.id == container_id for container in containers))
        
        # Stop the container
        self.rtorrent.stop()
        
        # Check if the container is removed
        containers = self.docker_client.containers.list(all=True)
        self.assertFalse(any(container.id == container_id for container in containers))

    def test_rtorrent_accessibility(self):
        self.rtorrent.start()
        
        # Wait for rTorrent to initialize
        time.sleep(20)
        
        # Create an XML-RPC client
        rpc_url = f"http://localhost:9080/RPC2"
        client = xmlrpc.client.ServerProxy(rpc_url)

        # List methods
        methods = client.system.listMethods()
        assert len(methods) > 0, "No methods found"
        assert "load.raw_start" in methods, "Method load.raw_start not found"
        
        # Try to get rTorrent version
        try:
            version = client.system.client_version()
            self.assertIsNotNone(version)
            print(f"rTorrent version: {version}")
        except Exception as e:
            self.fail(f"Failed to connect to rTorrent: {str(e)}")


if __name__ == '__main__':
    unittest.main()

# src/torrent_manager/dbs.py
from redislite import Redis
from peewee import SqliteDatabase

from .config import Config


SQLITE_DB_PATH = Config.SQLITE_DB_PATH
REDISLITE_DB_PATH = Config.REDISLITE_DB_PATH


sdb = SqliteDatabase(SQLITE_DB_PATH)
rdb = Redis(REDISLITE_DB_PATH)

# src/torrent_manager/config.py
import os
import tempfile
import dotenv


dotenv.load_dotenv()


# Defaults
DEBUG = True
VERBOSE = False
LOG_PATH = "rtorrent_manager.log"
LOG_LEVEL = "DEBUG" if DEBUG else "INFO"
LOG_ROTATION = "1 week"
LOG_RETENTION = "1 month"
DB_PATH = "activity_logs.db"
CONFIG_PATH = os.path.expanduser("~/.rtorrent_manager.conf")

HOME = os.getenv("HOME")
INCOMPLETE_DIR = "downloads"
INCOMPLETE_PATH = os.path.join(HOME, INCOMPLETE_DIR)
COMPLETE_DIR = "complete"
COMPLETE_PATH = os.path.join(HOME, COMPLETE_DIR)
MIN_SEEDING_DURATION = 24 * 3600
MAX_INTERVAL = 300

RTORRENT_RPC_URL = "http://localhost:9080/RPC2"

SQLITE_DB_PATH = tempfile.NamedTemporaryFile().name
REDISLITE_DB_PATH = tempfile.NamedTemporaryFile().name

CONTAINER_NAME = "rtorrent-manager"


class Config:
    DEBUG = os.getenv("DEBUG", DEBUG)
    VERBOSE = os.getenv("VERBOSE", VERBOSE)
    
    LOG_PATH = os.getenv("LOG_PATH", LOG_PATH)
    LOG_LEVEL = os.getenv("LOG_LEVEL", LOG_LEVEL)
    LOG_ROTATION = os.getenv("LOG_ROTATION", LOG_ROTATION)
    LOG_RETENTION = os.getenv("LOG_RETENTION", LOG_RETENTION)

    DB_PATH = os.getenv("DB_PATH", DB_PATH)
    CONFIG_PATH = os.getenv("CONFIG_PATH", CONFIG_PATH)

    INCOMPLETE_PATH = os.getenv("INCOMPLETE_PATH", INCOMPLETE_PATH)
    COMPLETE_PATH = os.getenv("COMPLETE_PATH", COMPLETE_PATH)
    MIN_SEEDING_DURATION = int(os.getenv("MIN_SEEDING_DURATION", MIN_SEEDING_DURATION))
    MAX_INTERVAL = int(os.getenv("MAX_INTERVAL", MAX_INTERVAL))

    RTORRENT_RPC_URL = os.getenv("RTORRENT_RPC_URL", RTORRENT_RPC_URL)

    SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", SQLITE_DB_PATH)
    REDISLITE_DB_PATH = os.getenv("REDISLITE_DB_PATH", REDISLITE_DB_PATH)

    CONTAINER_NAME = os.getenv("CONTAINER_NAME", CONTAINER_NAME)


class TestConfig:
    CONTAINER_NAME = "rtorrent-manager-test"
    
    LOG_PATH = tempfile.NamedTemporaryFile().name
    DB_PATH = tempfile.NamedTemporaryFile().name
    
    SQLITE_DB_PATH = tempfile.NamedTemporaryFile().name
    REDISLITE_DB_PATH = tempfile.NamedTemporaryFile().name


# src/torrent_manager/activity.py
import datetime
from peewee import fn

from .models import Status
from .config import Config
from .dbs import sdb as db


class Activity:
    def __init__(self, db_path=Config.DB_PATH):
        self.db_path = db_path
        self.db = db
        if not self.db.is_closed():
            self.db.close()
        self.db.init(self.db_path)
        self.db.connect()

    def record_torrent_status(self, info_hash, is_seeding=True, timestamp=None):
        if timestamp is None:
            timestamp = datetime.datetime.now()
        Status.create(
            torrent_hash=info_hash,
            status='seeding' if is_seeding else 'stopped',
            progress=1.0 if is_seeding else 0.0,
            seeders=0,
            leechers=0,
            down_rate=0,
            up_rate=0,
            timestamp=timestamp,
        )

    def calculate_seeding_duration(self, info_hash, max_interval=300):
        logs = (Status
                .select()
                .where(Status.torrent_hash == info_hash)
                .order_by(Status.timestamp))

        seeding_duration = 0
        last_seeding_time = None

        for log in logs:
            if log.status == 'seeding':
                if last_seeding_time is not None:
                    time_since_last_seeding = (log.timestamp - last_seeding_time).total_seconds()
                    if time_since_last_seeding < max_interval:
                        seeding_duration += time_since_last_seeding

                last_seeding_time = log.timestamp
            else:
                last_seeding_time = None

        return seeding_duration

    def get_never_seeded_torrents(self):
        subquery = (Status
                    .select(Status.torrent_hash)
                    .where(Status.status != 'seeding')
                    .group_by(Status.torrent_hash)
                    .having(fn.COUNT(fn.DISTINCT(Status.status)) == 1))
        
        return [status.torrent_hash for status in subquery]

    def remove_old_status_records(self, days_to_keep=30):
        cutoff_time = datetime.datetime.now() - datetime.timedelta(days=days_to_keep)
        Status.delete().where(Status.timestamp < cutoff_time).execute()

    def delete_torrent_status_history(self, info_hash):
        Status.delete().where(Status.torrent_hash == info_hash).execute()

    def close(self):
        if not self.db.is_closed():
            self.db.close()

# src/torrent_manager/__main__.py
import argparse
import configparser
import os
import sys

from .manager import Manager
from .config import Config
from .logger import logger


CONFIG_PATH = Config.CONFIG_PATH


def load_config():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        config.read(CONFIG_PATH)
    return config

def save_config(config):
    with open(CONFIG_PATH, 'w') as configfile:
        config.write(configfile)

def get_setting(args):
    config = load_config()
    if args.section in config and args.key in config[args.section]:
        logger(f"{args.key} = {config[args.section][args.key]}")
    else:
        logger(f"Setting {args.section}.{args.key} not found")

def set_setting(args):
    config = load_config()
    if args.section not in config:
        config[args.section] = {}
    config[args.section][args.key] = args.value
    save_config(config)
    logger(f"Setting {args.section}.{args.key} = {args.value}")

def set_defaults(config):
    for key, value in Config.__dict__.items():
        if key.isupper() and not key.startswith("__"):
            config[key] = str(value)

def run_maintenance(args):
    config = load_config()
    # Update Config with values from config file
    for section in config.sections():
        for key, value in config[section].items():
            setattr(Config, key.upper(), value)
    
    manager = Manager()
    manager.run_maintenance()

def main():
    parser = argparse.ArgumentParser(description="rTorrent Manager")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Get setting command
    get_parser = subparsers.add_parser("get", help="Get a setting")
    get_parser.add_argument("section", help="Section of the setting")
    get_parser.add_argument("key", help="Key of the setting")
    get_parser.set_defaults(func=get_setting)

    # Set setting command
    set_parser = subparsers.add_parser("set", help="Set a setting")
    set_parser.add_argument("section", help="Section of the setting")
    set_parser.add_argument("key", help="Key of the setting")
    set_parser.add_argument("value", help="Value of the setting")
    set_parser.set_defaults(func=set_setting)

    # Run maintenance command
    maintenance_parser = subparsers.add_parser("maintenance", help="Run maintenance tasks")
    maintenance_parser.set_defaults(func=run_maintenance)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

# src/torrent_manager/torrent_file.py
import hashlib
import os
from urllib.parse import urlencode

import bencode


class TorrentFile:
    def __init__(self, torrent_path):
        with open(torrent_path, 'rb') as f:
            self.torrent_data = bencode.bdecode(f.read())
        self.info = self.torrent_data['info']
        self.is_multi_file = 'files' in self.info

    def files(self):
        if self.is_multi_file:
            return [os.path.join(self.info['name'], *file['path']) for file in self.info['files']]
        else:
            return [self.info['name']]

    def info_hash(self):
        return hashlib.sha1(bencode.bencode(self.info)).hexdigest().upper()

    def size(self):
        if self.is_multi_file:
            return sum(file['length'] for file in self.info['files'])
        else:
            return self.info['length']

    def sizes(self):
        if self.is_multi_file:
            return [file['length'] for file in self.info['files']]
        else:
            return [self.info['length']]

    def piece_length(self):
        return self.info['piece length']

    def num_pieces(self):
        return len(self.info['pieces']) // 20

    def piece_hash(self, piece_index):
        return self.info['pieces'][piece_index*20:(piece_index+1)*20].hex()

    def trackers(self):
        if 'announce-list' in self.torrent_data:
            return [tracker for tier in self.torrent_data['announce-list'] for tracker in tier]
        elif 'announce' in self.torrent_data:
            return [self.torrent_data['announce']]
        else:
            return []

    def metadata(self):
        data = {}
        for key in ['creation date', 'comment', 'created by']:
            if key in self.torrent_data:
                data[key] = self.torrent_data[key]
        return data

    def magnet_link(self):
        params = {
            'xt': f"urn:btih:{self.info_hash()}",
            'dn': self.info['name'],
        }
        for i, tracker in enumerate(self.trackers()):
            params[f'tr.{i}'] = tracker
        return f"magnet:?{urlencode(params)}"

    def validate(self):
        # Top-level keys
        required_keys = ['info', 'announce']
        for key in required_keys:
            if key not in self.torrent_data:
                raise ValueError(f"Missing required key: {key}")
        
        return True

    def save(self, path):
        with open(path, 'wb') as f:
            f.write(bencode.bencode(self.torrent_data))


# src/torrent_manager/rtorrent_client.py
import os
import tempfile
import time
from typing import Any, Dict, Generator, List
from xmlrpc import client

import requests

from .config import Config
from .logger import logger
from .torrent_file import TorrentFile
from .magnet_link import MagnetLink


RTORRENT_RPC_URL = Config.RTORRENT_RPC_URL


class RTorrentClient:
    def __init__(self, url=RTORRENT_RPC_URL, view="main"):
        self.url = url
        self.client = client.ServerProxy(url)
        self.view = view

    def __getattr__(self, name):
        return getattr(self.client, name)

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

    def add_torrent(self, path, start=True, priority=1):
        # Get info_hash
        try:
            tf = TorrentFile(path)
        except Exception as e:
            logger.error(f"Failed to parse torrent file: {e}")
            return

        info_hash = tf.info_hash
        
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

        return result == 0

    def add_torrent_url(self, url, start=True, priority=1):
        path = self.download_remote_file(url)
        try:
            tf = TorrentFile(path)
        except Exception as e:
            logger.error(f"Failed to parse torrent file: {e}")
            os.remove(path)
            return
        
        with open(path, "rb") as f:
            data = f.read()
        info_hash = tf.info_hash
    
        # Add torrent
        if start:
            result = self.client.load.raw_start(self.view, client.Binary(data))
        else:
            result = self.client.load.raw(self.view, client.Binary(data))

        # Set priority
        if priority != 1:
            if self.is_multi_file(info_hash):
                for i in range(len(tf.files())):
                    self.set_file_priority(info_hash, i, priority)
            else:
                self.set_priority(info_hash, priority)

        os.remove(path)
        return result == 0
    
    def add_magnet(self, uri, start=True, priority=1):
        ml = MagnetLink(uri)
        info_hash = ml.info_hash
        
        # Add magnet
        if start:
            result = self.client.load.start("", uri)
        else:
            result = self.client.load("", uri)

        if priority != 1:
            self.set_priority(info_hash, priority)

        return result == 0

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
            
            info_hash = item["info_hash"]
            name = item["name"]
            item['is_magnet'] = name == f"{info_hash}.meta"
            item["progress"] = item["bytes_done"] / item["size"] if item["size"] > 0 else 0

            if item["is_multi_file"]:
                item["directory"] = os.path.dirname(item["base_path"])

            if files:
                item["files"] = list(self.files(info_hash))

        for item in items:
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

    def download_remote_file(self, url):
        temp_dir = tempfile.gettempdir()
        
        response = requests.get(url)
        response.raise_for_status()

        random_name = os.urandom(16).hex()
        temp_filename = random_name + ".torrent"
        temp_path = os.path.join(temp_dir, temp_filename)
        
        with open(temp_path, "wb") as f:
            response = requests.get(url)
            f.write(response.content)

        return temp_path

# src/torrent_manager/docker_rtorrent.py
import docker
import time

from .logger import logger
from .config import TestConfig


class DockerRTorrent:
    PORTS = {
        '80/tcp': 9080,
        '443/tcp': 9443,
        '5000/tcp': 5000,  # For rTorrent SCGI
        '51413/tcp': 51413,  # For BitTorrent
        '6881/udp': 6881  # For BitTorrent DHT
    }

    TEST_CONTAINER_NAME = TestConfig.CONTAINER_NAME

    
    def __init__(
        self,
        image="linuxserver/rutorrent:latest",
        name=None, ports={},
        remove=True,
        is_test=False,
    ):
        self.client = docker.from_env()
        self.image = image
        self.name = name
        self.container = None
        self.ports = self.PORTS.copy()
        self.ports.update(ports)
        self.remove = remove
        self.is_test = is_test
        if self.is_test:
            self.name = self.TEST_CONTAINER_NAME
            self.remove = True

    def start(self, wait_time=10):
        """Start the rTorrent/ruTorrent container."""
        if self.container:
            logger.info("Container is already running.")
            return

        # Check if the container is already running
        running_containers = self.client.containers.list()
        if any(c.name == self.name for c in running_containers):
            logger.info("Container is already running.")
            self.container = self.client.containers.get(self.name)
            return

        try:
            self.container = self.client.containers.run(
                self.image,
                name=self.name,
                detach=True,
                ports=self.ports,
                environment={
                    "PUID": "1000",
                    "PGID": "1000",
                    "TZ": "Etc/UTC"
                },
                remove=self.remove,
            )
            logger.info(f"Container started: {self.container.id}")
            time.sleep(wait_time)  # Wait for the container to initialize
        except docker.errors.APIError as e:
            logger.info(f"Failed to start container: {e}")

    def stop(self, wait_time=5):
        """Stop and remove the container."""
        if self.container:
            self.container.stop()
            self.container = None
            time.sleep(wait_time)  # Wait for the container to stop
            logger.info("Container stopped and removed.")
        else:
            logger.info("No container is running.")

    def get_container_ip(self):
        """Get the IP address of the container."""
        if self.container:
            ip = self.container.attrs['NetworkSettings']['IPAddress']
            ip = ip or "localhost"
            return ip
            
        return None

    def get_logs(self):
        """Get the logs from the container."""
        if self.container:
            return self.container.logs().decode('utf-8')
        return "No container is running."

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.is_test:
            self.stop()


# Usage example
if __name__ == "__main__":
    with DockerRTorrent() as env:
        print("Container is running. Press Enter to stop...")
        input()
        print(env.get_logs())

# src/torrent_manager/manager.py
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
            rtorrent=Client(),
            activity_log=None,
        ):
        self.rtorrent = rtorrent
        self.activity = activity_log or Activity()

    def get_torrents(self):
        return self.rtorrent.download_list()
    
    def get_seeding_torrents(self):
        return [t for t in self.get_torrents() if self.rtorrent.d.is_active(t) == 1 and self.rtorrent.d.complete(t) == 1]
    
    def get_seeding_duration(self, info_hash):
        return self.activity.get_seeding_duration(info_hash, max_interval=MAX_INTERVAL)

    def get_completed_torrents(self):
        return [t for t in self.get_torrents() if self.rtorrent.d.complete(t) == 1]

    def move(self, info_hash, destination=COMPLETE_PATH):
        logger.info(f"Moving {info_hash} to {destination}")
        name = self.rtorrent.d.name(info_hash)
        is_multi_file = self.rtorrent.d.is_multi_file(info_hash) == 1
        base_path = os.path.abspath(self.rtorrent.d.base_path(info_hash))
        destination_path = os.path.join(destination, name)
        destination_path = os.path.abspath(destination_path)

        # Stop the torrent
        self.rtorrent.d.stop(info_hash)
        while self.rtorrent.d.is_active(info_hash) == 1:
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

# src/torrent_manager/magnet_link.py
import re
from urllib.parse import parse_qs, urlencode
import tempfile
import time
import os


class MagnetLink:
    def __init__(self, magnet_uri):
        self.magnet_uri = magnet_uri
        self.parse_magnet_uri()

    def parse_magnet_uri(self):
        # Extract parameters from the magnet URI
        params = parse_qs(self.magnet_uri.split('?', 1)[1])
        
        self.info_hash = params.get('xt', [None])[0]
        if self.info_hash:
            self.info_hash = self.info_hash.split(':')[-1].lower()
        
        self.info_hash = self.info_hash.upper()
        
        self.name = params.get('dn', [None])[0]
        self.trackers = params.get('tr', [])
        self.size = int(params.get('xl', [0])[0])

    def to_uri(self):
        # Reconstruct the magnet URI from the parsed data
        params = {
            'xt': f'urn:btih:{self.info_hash}',
            'dn': self.name,
            'tr': self.trackers,
        }
        if self.size:
            params['xl'] = str(self.size)
        return f"magnet:?{urlencode(params, doseq=True)}"

    def info_hash(self):
        return self.info_hash

    def name(self):
        return self.name

    def size(self):
        return self.size

    def trackers(self):
        return self.trackers

    def add_tracker(self, tracker):
        if tracker not in self.trackers:
            self.trackers.append(tracker)

    def remove_tracker(self, tracker):
        if tracker in self.trackers:
            self.trackers.remove(tracker)

    @staticmethod
    def from_torrent_file(torrent_file):
        # Create a magnet link from a TorrentFile object
        info_hash = torrent_file.info_hash()
        name = torrent_file.info['name']
        trackers = torrent_file.trackers()
        size = torrent_file.size()

        params = {
            'xt': f'urn:btih:{info_hash}',
            'dn': name,
            'tr': trackers,
            'xl': str(size)
        }
        return MagnetLink(f"magnet:?{urlencode(params, doseq=True)}")

    @staticmethod
    def is_valid_magnet(magnet_uri):
        # Basic validation of a magnet URI
        pattern = r'^magnet:\?xt=urn:btih:[a-fA-F0-9]{40}.*$'
        return re.match(pattern, magnet_uri) is not None

    def download_torrent(self, path):
        import libtorrent as lt
        temp_dir = tempfile.gettempdir()

        ses = lt.session()
        params = {
            'save_path': temp_dir,
            'storage_mode': lt.storage_mode_t(2),
        }
        
        handle = lt.add_magnet_uri(ses, self.magnet_uri, params)
        while not handle.has_metadata():
            time.sleep(1)

        # Save the torrent file
        torrent_info = handle.get_torrent_info()
        filename = os.path.basename(path)
        save_path = os.path.join(temp_dir, filename)
        with open(save_path, 'wb') as f:
            f.write(lt.bencode(torrent_info.generate()))

        # Delete the handle
        ses.remove_torrent(handle)

        # Move the torrent file to the specified path
        os.rename(save_path, path)
        os.rmdir(temp_dir)

# src/torrent_manager/transmission_client.py
import os
import tempfile
from typing import Any, Dict, Generator, List

import requests
from transmission_rpc import Client as TransmissionRPCClient
from transmission_rpc.torrent import Torrent as TransmissionTorrent
        
from .config import Config
from .logger import logger
from .torrent_file import TorrentFile
from .magnet_link import MagnetLink


TRANSMISSION_HOST = Config.TRANSMISSION_HOST
TRANSMISSION_PORT = Config.TRANSMISSION_PORT
TRANSMISSION_USERNAME = Config.TRANSMISSION_USERNAME
TRANSMISSION_PASSWORD = Config.TRANSMISSION_PASSWORD


class TransmissionClient:
    def __init__(self, host=TRANSMISSION_HOST, port=TRANSMISSION_PORT, username=TRANSMISSION_USERNAME, password=TRANSMISSION_PASSWORD):
        self.client = TransmissionRPCClient(host=host, port=port, username=username, password=password)

    def _get_torrent_by_hash(self, info_hash: str) -> TransmissionTorrent:
        torrents = self.client.get_torrents()
        for torrent in torrents:
            if torrent.hashString == info_hash:
                return torrent
        raise ValueError(f"No torrent found with hash {info_hash}")

    def check_methods(self):
        # Transmission RPC doesn't have a direct equivalent to rTorrent's system.listMethods
        # We'll assume all methods are available if we can connect successfully
        try:
            self.client.session_stats()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Transmission: {e}")
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


# src/torrent_manager/utils.py
import time
import os
import shutil

from .config import Config
from .logger import logger


COMPLETE_PATH = Config.COMPLETE_PATH


def move(client, info_hash, destination=COMPLETE_PATH):
    logger.info(f"Moving {info_hash} to {destination}")
    name = client.d.name(info_hash)
    is_multi_file = client.d.is_multi_file(info_hash) == 1
    base_path = os.path.abspath(client.d.base_path(info_hash))
    destination_path = os.path.join(destination, name)
    destination_path = os.path.abspath(destination_path)

    # Stop the torrent
    client.d.stop(info_hash)
    while client.d.is_active(info_hash) == 1:  # Wait until stopped
        time.sleep(1)

    # Move torrent
    if os.path.exists(destination_path):
        shutil.rmtree(destination_path)

    if is_multi_file:
        shutil.copytree(base_path, destination_path)
    else:
        shutil.copy2(base_path, destination_path)

    # Update torrent directory in rTorrent
    client.d.directory.set(info_hash, destination)

    # Restart the torrent
    client.d.start(info_hash)
    while client.d.is_active(info_hash) == 0:
        time.sleep(1)

    # Remove old torrent files
    if is_multi_file:
        shutil.rmtree(base_path)
    else:
        os.remove(base_path)


def move_torrent(client, info_hash, new_location):
    """
    Moves a torrent's data from its current location to a new location.
    This method handles both single-file and multi-file torrents.

    Args:
        info_hash (str): The info hash of the torrent to move.
        new_location (str): The new base directory for the torrent.

    Returns:
        bool: True if the move was successful, False otherwise.
    """
    try:
        # Stop the torrent to prevent data corruption during move
        client.stop(info_hash)

        current_path = client.actual_torrent_path(info_hash)
        is_multi_file = client.is_multi_file(info_hash)
        torrent_name = client.name(info_hash)

        if is_multi_file:
            # For multi-file torrents, move the entire directory
            new_path = os.path.join(new_location, torrent_name)
            shutil.move(current_path, new_path)
        else:
            # For single-file torrents, move the file and ensure the directory exists
            os.makedirs(new_location, exist_ok=True)
            new_path = os.path.join(new_location, os.path.basename(current_path))
            shutil.move(current_path, new_path)

        # Update the torrent's directory in rTorrent
        client.d.directory.set(info_hash, new_location)

        # If it's a single-file torrent, we need to update the base_filename as well
        if not is_multi_file:
            client.d.base_filename.set(info_hash, os.path.basename(new_path))

        # Restart the torrent
        client.start(info_hash)

        logger.info(f"Successfully moved torrent {info_hash} to {new_location}")
        return True

    except Exception as e:
        logger.error(f"Failed to move torrent {info_hash}: {str(e)}")
        # Attempt to restart the torrent in case of failure
        client.start(info_hash)
        return False


# src/torrent_manager/logger.py
from loguru import logger

from .config import Config


VERBOSE = Config.VERBOSE
LOG_PATH = Config.LOG_PATH
LOG_LEVEL = Config.LOG_LEVEL
LOG_ROTATION = Config.LOG_ROTATION
LOG_RETENTION = Config.LOG_RETENTION


# Log to a file
logger.add(
    LOG_PATH,
    rotation="1 week",
    retention="1 month",
    level=LOG_LEVEL,
)

# Log to console
if VERBOSE:
    logger.add(
        sink=None,
        level=LOG_LEVEL,
    )

# src/torrent_manager/__init__.py


# src/torrent_manager/models.py
import datetime
from peewee import Model, CharField, DateTimeField, IntegerField, FloatField
from .dbs import sdb as db


class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    id = CharField(primary_key=True)
    username = CharField(index=True)
    password = CharField()
    email = CharField()
    timestamp = DateTimeField(default=datetime.datetime.now)

class UserTorrent(BaseModel):
    user = CharField(index=True)
    torrent_hash = CharField(index=True)
    timestamp = DateTimeField(default=datetime.datetime.now)

class Torrent(BaseModel):
    torrent_hash = CharField(index=True)
    name = CharField()
    path = CharField()
    files = CharField()
    size = IntegerField()
    timestamp = DateTimeField(default=datetime.datetime.now)

class Status(BaseModel):
    torrent_hash = CharField(index=True)
    status = CharField()  # e.g., 'downloading', 'seeding', 'stopped'
    progress = FloatField()  # 0.0 to 1.0
    seeders = IntegerField()
    leechers = IntegerField()
    down_rate = IntegerField()
    up_rate = IntegerField()
    timestamp = DateTimeField(default=datetime.datetime.now)

class Action(BaseModel):
    torrent_hash = CharField(index=True)
    action = CharField()  # e.g., 'add', 'stop', 'remove'
    timestamp = DateTimeField(default=datetime.datetime.now)


db.connect()
db.create_tables([User, Torrent, Status, Action])

