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