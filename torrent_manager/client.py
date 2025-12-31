"""
Python client for the Torrent Manager REST API.

Provides programmatic access to all API functionality including:
- User authentication (session-based and API key)
- API key management
- Server configuration management
- Torrent operations (add, list, start, stop, remove)
- File browsing and downloads

Usage:
    from torrent_manager.client import TorrentManagerClient

    # With API key
    client = TorrentManagerClient(api_key="your-api-key")
    torrents = client.list_torrents()

    # With session login
    client = TorrentManagerClient()
    client.login("username", "password")
    torrents = client.list_torrents()
"""

import requests
import os
from urllib.parse import urljoin
from typing import Optional, List, Dict, Any, BinaryIO


class TorrentManagerClient:
    def __init__(self, base_url: str = "http://localhost:8144", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = urljoin(self.base_url + "/", endpoint.lstrip('/'))
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}
        except requests.exceptions.HTTPError as e:
            if e.response.content:
                try:
                    error_detail = e.response.json().get('detail', str(e))
                    raise Exception(f"API Error: {error_detail}")
                except ValueError:
                    raise Exception(f"API Error: {e}")
            raise Exception(f"API Error: {e}")
        except requests.exceptions.ConnectionError:
            raise Exception(f"Could not connect to server at {self.base_url}")

    # -------------------------------------------------------------------------
    # Auth Methods
    # -------------------------------------------------------------------------

    def register(self, username: str, password: str) -> Dict[str, Any]:
        """Register a new user account."""
        return self._request("POST", "/auth/register", json={
            "username": username,
            "password": password
        })

    def login(self, username: str, password: str, remember_me: bool = False) -> Dict[str, Any]:
        """Login with username and password, establishing a session."""
        return self._request("POST", "/auth/login", json={
            "username": username,
            "password": password,
            "remember_me": remember_me
        })

    def logout(self) -> Dict[str, Any]:
        """Logout and destroy the current session."""
        return self._request("POST", "/auth/logout")

    def get_me(self) -> Dict[str, Any]:
        """Get current authenticated user info."""
        return self._request("GET", "/auth/me")

    # -------------------------------------------------------------------------
    # API Key Methods
    # -------------------------------------------------------------------------

    def create_api_key(self, name: str, expires_days: Optional[int] = None) -> Dict[str, Any]:
        """Create a new API key for programmatic access."""
        data = {"name": name}
        if expires_days is not None:
            data["expires_days"] = expires_days
        return self._request("POST", "/auth/api-keys", json=data)

    def list_api_keys(self) -> Dict[str, Any]:
        """List all API keys for the current user."""
        return self._request("GET", "/auth/api-keys")

    def revoke_api_key(self, key_prefix: str) -> Dict[str, Any]:
        """Revoke an API key by its prefix (first 8 characters)."""
        return self._request("DELETE", f"/auth/api-keys/{key_prefix}")

    # -------------------------------------------------------------------------
    # Server Methods
    # -------------------------------------------------------------------------

    def add_server(
        self,
        name: str,
        server_type: str,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        rpc_path: Optional[str] = None,
        use_ssl: bool = False,
        http_host: Optional[str] = None,
        http_port: Optional[int] = None,
        http_path: Optional[str] = None,
        http_username: Optional[str] = None,
        http_password: Optional[str] = None,
        http_use_ssl: bool = False
    ) -> Dict[str, Any]:
        """
        Add a new torrent server configuration.

        Args:
            name: Display name for the server
            server_type: "rtorrent" or "transmission"
            host: Server hostname or IP
            port: RPC port
            username: Authentication username (optional)
            password: Authentication password (optional)
            rpc_path: RPC path for rTorrent (e.g., "/RPC2")
            use_ssl: Use HTTPS for RPC
            http_host: HTTP download server host (optional)
            http_port: HTTP download server port (optional)
            http_path: Base path on HTTP server (optional)
            http_username: HTTP auth username (optional)
            http_password: HTTP auth password (optional)
            http_use_ssl: Use HTTPS for downloads
        """
        data = {
            "name": name,
            "server_type": server_type,
            "host": host,
            "port": port,
            "use_ssl": use_ssl,
            "http_use_ssl": http_use_ssl
        }
        if username is not None:
            data["username"] = username
        if password is not None:
            data["password"] = password
        if rpc_path is not None:
            data["rpc_path"] = rpc_path
        if http_host is not None:
            data["http_host"] = http_host
        if http_port is not None:
            data["http_port"] = http_port
        if http_path is not None:
            data["http_path"] = http_path
        if http_username is not None:
            data["http_username"] = http_username
        if http_password is not None:
            data["http_password"] = http_password
        return self._request("POST", "/servers", json=data)

    def list_servers(self) -> List[Dict[str, Any]]:
        """List all configured torrent servers."""
        return self._request("GET", "/servers")

    def get_server(self, server_id: str) -> Dict[str, Any]:
        """Get details of a specific server."""
        return self._request("GET", f"/servers/{server_id}")

    def update_server(
        self,
        server_id: str,
        name: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        rpc_path: Optional[str] = None,
        use_ssl: Optional[bool] = None,
        enabled: Optional[bool] = None,
        http_host: Optional[str] = None,
        http_port: Optional[int] = None,
        http_path: Optional[str] = None,
        http_username: Optional[str] = None,
        http_password: Optional[str] = None,
        http_use_ssl: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update a server configuration. Only provided fields are updated."""
        data = {}
        if name is not None:
            data["name"] = name
        if host is not None:
            data["host"] = host
        if port is not None:
            data["port"] = port
        if username is not None:
            data["username"] = username
        if password is not None:
            data["password"] = password
        if rpc_path is not None:
            data["rpc_path"] = rpc_path
        if use_ssl is not None:
            data["use_ssl"] = use_ssl
        if enabled is not None:
            data["enabled"] = enabled
        if http_host is not None:
            data["http_host"] = http_host
        if http_port is not None:
            data["http_port"] = http_port
        if http_path is not None:
            data["http_path"] = http_path
        if http_username is not None:
            data["http_username"] = http_username
        if http_password is not None:
            data["http_password"] = http_password
        if http_use_ssl is not None:
            data["http_use_ssl"] = http_use_ssl
        return self._request("PUT", f"/servers/{server_id}", json=data)

    def delete_server(self, server_id: str) -> Dict[str, Any]:
        """Delete a server configuration."""
        return self._request("DELETE", f"/servers/{server_id}")

    def test_server(self, server_id: str) -> Dict[str, Any]:
        """Test connection to a server."""
        return self._request("POST", f"/servers/{server_id}/test")

    # -------------------------------------------------------------------------
    # Torrent Methods
    # -------------------------------------------------------------------------

    def list_torrents(self, server_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all torrents.

        Args:
            server_id: Filter by specific server (optional)
        """
        params = {}
        if server_id:
            params["server_id"] = server_id
        return self._request("GET", "/torrents", params=params)

    def add_torrent(
        self,
        uri: str,
        server_id: str,
        start: bool = True,
        labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Add a torrent by info hash, magnet URI, or HTTP URL.

        Args:
            uri: Info hash (40 hex or 32 base32), magnet URI, or HTTP URL
            server_id: Server to add the torrent to
            start: Start the torrent immediately (default True)
            labels: Optional list of labels to apply to the torrent
        """
        data = {
            "uri": uri,
            "server_id": server_id,
            "start": start
        }
        if labels:
            data["labels"] = labels
        return self._request("POST", "/torrents", json=data)

    def add_magnet(
        self,
        magnet_uri: str,
        server_id: str,
        start: bool = True
    ) -> Dict[str, Any]:
        """
        Add a torrent by magnet URI.

        Args:
            magnet_uri: Magnet URI starting with "magnet:?xt=..."
            server_id: Server to add the torrent to
            start: Start the torrent immediately (default True)
        """
        return self.add_torrent(magnet_uri, server_id, start)

    def add_url(
        self,
        url: str,
        server_id: str,
        start: bool = True
    ) -> Dict[str, Any]:
        """
        Add a torrent by HTTP/HTTPS URL to a .torrent file.

        Args:
            url: HTTP or HTTPS URL to a .torrent file
            server_id: Server to add the torrent to
            start: Start the torrent immediately (default True)
        """
        return self.add_torrent(url, server_id, start)

    def upload_torrent(
        self,
        file_path: str,
        server_id: str,
        start: bool = True
    ) -> Dict[str, Any]:
        """
        Upload a .torrent file.

        Args:
            file_path: Path to the .torrent file
            server_id: Server to add the torrent to
            start: Start the torrent immediately (default True)
        """
        url = urljoin(self.base_url + "/", "/torrents/upload")
        params = {"server_id": server_id, "start": start}

        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, 'application/x-bittorrent')}
            try:
                response = self.session.post(url, files=files, params=params)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.HTTPError as e:
                if e.response.content:
                    try:
                        error_detail = e.response.json().get('detail', str(e))
                        raise Exception(f"API Error: {error_detail}")
                    except ValueError:
                        pass
                raise Exception(f"API Error: {e}")

    def get_torrent(
        self,
        info_hash: str,
        server_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed information about a specific torrent.

        Args:
            info_hash: Torrent info hash
            server_id: Server to query (optional, searches all if not provided)
        """
        params = {}
        if server_id:
            params["server_id"] = server_id
        return self._request("GET", f"/torrents/{info_hash}", params=params)

    def start_torrent(
        self,
        info_hash: str,
        server_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start a paused torrent.

        Args:
            info_hash: Torrent info hash
            server_id: Server containing the torrent (optional)
        """
        params = {}
        if server_id:
            params["server_id"] = server_id
        return self._request("POST", f"/torrents/{info_hash}/start", params=params)

    def stop_torrent(
        self,
        info_hash: str,
        server_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Stop/pause a torrent.

        Args:
            info_hash: Torrent info hash
            server_id: Server containing the torrent (optional)
        """
        params = {}
        if server_id:
            params["server_id"] = server_id
        return self._request("POST", f"/torrents/{info_hash}/stop", params=params)

    def delete_torrent(
        self,
        info_hash: str,
        server_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Remove a torrent from the server.

        Args:
            info_hash: Torrent info hash
            server_id: Server containing the torrent (optional)
        """
        params = {}
        if server_id:
            params["server_id"] = server_id
        return self._request("DELETE", f"/torrents/{info_hash}", params=params)

    def list_torrent_files(
        self,
        info_hash: str,
        server_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        List all files belonging to a torrent.

        Args:
            info_hash: Torrent info hash
            server_id: Server containing the torrent (optional)

        Returns dict with:
            - info_hash: The torrent hash
            - name: Torrent name
            - path: Download path
            - server_id: Server ID
            - server_name: Server name
            - http_enabled: Whether HTTP downloads are available
            - files: List of file info dicts
        """
        params = {}
        if server_id:
            params["server_id"] = server_id
        return self._request("GET", f"/torrents/{info_hash}/files", params=params)

    # -------------------------------------------------------------------------
    # Server File Methods
    # -------------------------------------------------------------------------

    def list_server_files(
        self,
        server_id: str,
        path: str = ""
    ) -> Dict[str, Any]:
        """
        List files and directories at a server's HTTP download location.

        Args:
            server_id: Server ID
            path: Path relative to base directory (default: root)

        Returns dict with:
            - server_id: Server ID
            - server_name: Server name
            - path: Current path
            - entries: List of file/directory entries
        """
        return self._request("GET", f"/servers/{server_id}/files", params={"path": path})

    def download_file(
        self,
        server_id: str,
        file_path: str,
        output_path: Optional[str] = None
    ) -> str:
        """
        Download a file from a server's HTTP download location.

        Args:
            server_id: Server ID
            file_path: Path to file relative to server's base directory
            output_path: Local path to save file (default: current dir with original name)

        Returns:
            Path to the downloaded file
        """
        url = urljoin(self.base_url + "/", f"/servers/{server_id}/download/{file_path}")

        try:
            response = self.session.get(url, stream=True)
            response.raise_for_status()

            # Determine output path
            if output_path is None:
                # Try to get filename from Content-Disposition header
                cd = response.headers.get('Content-Disposition', '')
                if 'filename=' in cd:
                    output_path = cd.split('filename=')[1].strip('"\'')
                else:
                    output_path = os.path.basename(file_path)

            # Write to file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)

            return output_path
        except requests.exceptions.HTTPError as e:
            if e.response.content:
                try:
                    error_detail = e.response.json().get('detail', str(e))
                    raise Exception(f"API Error: {error_detail}")
                except ValueError:
                    pass
            raise Exception(f"API Error: {e}")

    def download_file_stream(
        self,
        server_id: str,
        file_path: str
    ) -> requests.Response:
        """
        Get a streaming response for a file download.

        Args:
            server_id: Server ID
            file_path: Path to file relative to server's base directory

        Returns:
            requests.Response with stream=True (caller must close)
        """
        url = urljoin(self.base_url + "/", f"/servers/{server_id}/download/{file_path}")
        response = self.session.get(url, stream=True)
        response.raise_for_status()
        return response
