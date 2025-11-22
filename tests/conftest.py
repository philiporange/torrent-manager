import pytest
from torrent_manager.docker_rtorrent import DockerRTorrent
from torrent_manager.rtorrent_client import RTorrentClient
from torrent_manager.config import Config

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
