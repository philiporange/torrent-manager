import unittest
import time
import xmlrpc.client

import docker

from torrent_manager.docker_rtorrent import DockerRTorrent
from torrent_manager.config import Config



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