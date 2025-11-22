import requests
import os
from urllib.parse import urljoin
from typing import Optional, List, Dict, Any

class TorrentManagerClient:
    def __init__(self, base_url: str = "http://localhost:8144", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = urljoin(self.base_url, endpoint)
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

    # Auth Methods
    def register(self, username: str, password: str) -> Dict[str, Any]:
        return self._request("POST", "/auth/register", json={
            "username": username,
            "password": password
        })

    def login(self, username: str, password: str, remember_me: bool = False) -> Dict[str, Any]:
        return self._request("POST", "/auth/login", json={
            "username": username,
            "password": password,
            "remember_me": remember_me
        })

    def logout(self) -> Dict[str, Any]:
        return self._request("POST", "/auth/logout")

    def get_me(self) -> Dict[str, Any]:
        return self._request("GET", "/auth/me")

    # API Key Methods
    def create_api_key(self, name: str, expires_days: Optional[int] = None) -> Dict[str, Any]:
        data = {"name": name}
        if expires_days is not None:
            data["expires_days"] = expires_days
        return self._request("POST", "/auth/api-keys", json=data)

    def list_api_keys(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/auth/api-keys")

    def revoke_api_key(self, key_prefix: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/auth/api-keys/{key_prefix}")

    # Torrent Methods
    def list_torrents(self) -> List[Dict[str, Any]]:
        return self._request("GET", "/torrents")

    def add_magnet(self, magnet_uri: str, start: bool = True) -> Dict[str, Any]:
        return self._request("POST", "/torrents", json={
            "uri": magnet_uri,
            "start": start
        })

    def add_url(self, url: str, start: bool = True) -> Dict[str, Any]:
        return self._request("POST", "/torrents", json={
            "uri": url,
            "start": start
        })

    def upload_torrent(self, file_path: str, start: bool = True) -> Dict[str, Any]:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, 'application/x-bittorrent')}
            # We don't set Content-Type header here, requests does it with boundary
            url = urljoin(self.base_url, "/torrents/upload")
            params = {"start": start}
            
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

    def get_torrent(self, info_hash: str) -> Dict[str, Any]:
        return self._request("GET", f"/torrents/{info_hash}")

    def start_torrent(self, info_hash: str) -> Dict[str, Any]:
        return self._request("POST", f"/torrents/{info_hash}/start")

    def stop_torrent(self, info_hash: str) -> Dict[str, Any]:
        return self._request("POST", f"/torrents/{info_hash}/stop")

    def delete_torrent(self, info_hash: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/torrents/{info_hash}")
