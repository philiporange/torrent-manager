"""
Factory for creating torrent client instances.

Provides a function to create the appropriate client (RTorrentClient or TransmissionClient)
based on the server configuration stored in the database.
"""

from typing import TYPE_CHECKING
from urllib.parse import quote

from .base_client import BaseTorrentClient
from .rtorrent_client import RTorrentClient
from .transmission_client import TransmissionClient

if TYPE_CHECKING:
    from .models import TorrentServer


def get_client(server: "TorrentServer") -> BaseTorrentClient:
    """
    Create a torrent client instance for the given server configuration.

    Args:
        server: TorrentServer model instance with connection details

    Returns:
        An instance of RTorrentClient or TransmissionClient

    Raises:
        ValueError: If the server type is not supported
    """
    if server.server_type == "rtorrent":
        rpc_path = server.rpc_path or "/RPC2"
        protocol = "https" if server.use_ssl else "http"

        # Build URL with embedded credentials if provided
        if server.username and server.password:
            # URL-encode the password to handle special characters
            encoded_password = quote(server.password, safe='')
            url = f"{protocol}://{server.username}:{encoded_password}@{server.host}:{server.port}{rpc_path}"
        else:
            url = f"{protocol}://{server.host}:{server.port}{rpc_path}"

        return RTorrentClient(url=url)

    elif server.server_type == "transmission":
        protocol = "https" if server.use_ssl else "http"
        path = server.rpc_path or "/transmission/rpc"
        return TransmissionClient(
            protocol=protocol,
            host=server.host,
            port=server.port,
            path=path,
            username=server.username,
            password=server.password
        )

    else:
        raise ValueError(f"Unknown server type: {server.server_type}")
