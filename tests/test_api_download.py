"""
Tests for torrent file download URL generation and file listing.

Verifies that download URLs are correctly constructed for both single-file
and multi-file torrents, including proper path handling.
"""

import os
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from peewee import SqliteDatabase

os.environ["COOKIE_SECURE"] = "false"

from torrent_manager.api import app
from torrent_manager.auth import UserManager
from torrent_manager.models import User, Session, RememberMeToken, TorrentServer, db


@pytest.fixture(autouse=True)
def setup_test_db():
    """Setup test database before each test."""
    from torrent_manager import models as model_module

    test_db = SqliteDatabase(':memory:')
    models_list = [User, Session, RememberMeToken, TorrentServer]
    test_db.bind(models_list, bind_refs=False, bind_backrefs=False)

    old_db = model_module.db
    model_module.db._state.closed = True
    for model in models_list:
        model._meta.database = test_db

    test_db.connect()
    test_db.create_tables(models_list)

    yield

    test_db.drop_tables(models_list)
    test_db.close()

    for model in models_list:
        model._meta.database = old_db


@pytest_asyncio.fixture
async def async_client():
    """Create async test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_user():
    """Create a test user."""
    return UserManager.create_user(
        username="testuser",
        password="testpass123"
    )


@pytest_asyncio.fixture
async def authenticated_client(async_client, test_user):
    """Create an authenticated async client."""
    await async_client.post(
        "/auth/login",
        json={
            "username": "testuser",
            "password": "testpass123",
            "remember_me": False
        }
    )
    return async_client


@pytest_asyncio.fixture
async def server_with_http(authenticated_client):
    """Create a server with HTTP download configured."""
    response = await authenticated_client.post(
        "/servers",
        json={
            "name": "Test Server",
            "server_type": "rtorrent",
            "host": "localhost",
            "port": 9080,
            "http_host": "localhost",
            "http_port": 80,
            "http_path": "/downloads"
        }
    )
    return response.json()


@pytest_asyncio.fixture
async def server_with_mount(authenticated_client):
    """Create a server with local mount configured."""
    response = await authenticated_client.post(
        "/servers",
        json={
            "name": "Mount Server",
            "server_type": "rtorrent",
            "host": "localhost",
            "port": 9080,
            "mount_path": "/mnt/seedbox"
        }
    )
    return response.json()


class TestDownloadUrlGeneration:
    """Tests for download URL generation in torrent file listings."""

    @pytest.mark.asyncio
    async def test_single_file_torrent_download_url(self, authenticated_client, server_with_http):
        """Single-file torrents should have download URL with just the filename."""
        server_id = server_with_http["id"]

        mock_torrent = {
            "info_hash": "ABC123",
            "name": "movie.mkv",
            "path": "/downloads/movie.mkv",
            "is_multi_file": False,
            "files": [
                {"path": "movie.mkv", "size": 1000000, "progress": 1.0, "priority": 1}
            ]
        }

        with patch("torrent_manager.api.routes.torrents.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_torrents.return_value = iter([mock_torrent])
            mock_get_client.return_value = mock_client

            response = await authenticated_client.get(
                f"/torrents/ABC123/files?server_id={server_id}"
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 1
        assert data["files"][0]["download_url"] == f"/servers/{server_id}/download/movie.mkv"

    @pytest.mark.asyncio
    async def test_multi_file_torrent_download_url(self, authenticated_client, server_with_http):
        """Multi-file torrents should have download URL with torrent_name/file_path."""
        server_id = server_with_http["id"]

        mock_torrent = {
            "info_hash": "DEF456",
            "name": "My Album",
            "path": "/downloads/My Album",
            "is_multi_file": True,
            "files": [
                {"path": "track01.mp3", "size": 5000000, "progress": 1.0, "priority": 1},
                {"path": "track02.mp3", "size": 4500000, "progress": 1.0, "priority": 1},
                {"path": "covers/front.jpg", "size": 100000, "progress": 1.0, "priority": 1}
            ]
        }

        with patch("torrent_manager.api.routes.torrents.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_torrents.return_value = iter([mock_torrent])
            mock_get_client.return_value = mock_client

            response = await authenticated_client.get(
                f"/torrents/DEF456/files?server_id={server_id}"
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 3
        assert data["files"][0]["download_url"] == f"/servers/{server_id}/download/My Album/track01.mp3"
        assert data["files"][1]["download_url"] == f"/servers/{server_id}/download/My Album/track02.mp3"
        assert data["files"][2]["download_url"] == f"/servers/{server_id}/download/My Album/covers/front.jpg"

    @pytest.mark.asyncio
    async def test_http_enabled_with_http_port(self, authenticated_client, server_with_http):
        """http_enabled should be true when http_port is configured."""
        server_id = server_with_http["id"]

        mock_torrent = {
            "info_hash": "GHI789",
            "name": "file.zip",
            "path": "/downloads/file.zip",
            "is_multi_file": False,
            "files": [{"path": "file.zip", "size": 1000, "progress": 1.0, "priority": 1}]
        }

        with patch("torrent_manager.api.routes.torrents.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_torrents.return_value = iter([mock_torrent])
            mock_get_client.return_value = mock_client

            response = await authenticated_client.get(
                f"/torrents/GHI789/files?server_id={server_id}"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["http_enabled"] is True
        assert "download_url" in data["files"][0]

    @pytest.mark.asyncio
    async def test_http_enabled_with_mount_path(self, authenticated_client, server_with_mount):
        """http_enabled should be true when mount_path is configured (even without http_port)."""
        server_id = server_with_mount["id"]

        mock_torrent = {
            "info_hash": "JKL012",
            "name": "file.zip",
            "path": "/downloads/file.zip",
            "is_multi_file": False,
            "files": [{"path": "file.zip", "size": 1000, "progress": 1.0, "priority": 1}]
        }

        with patch("torrent_manager.api.routes.torrents.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_torrents.return_value = iter([mock_torrent])
            mock_get_client.return_value = mock_client

            response = await authenticated_client.get(
                f"/torrents/JKL012/files?server_id={server_id}"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["http_enabled"] is True
        assert "download_url" in data["files"][0]

    @pytest.mark.asyncio
    async def test_no_download_url_without_http_or_mount(self, authenticated_client):
        """No download_url when neither http_port nor mount_path configured."""
        # Create server without HTTP or mount
        response = await authenticated_client.post(
            "/servers",
            json={
                "name": "No Download Server",
                "server_type": "rtorrent",
                "host": "localhost",
                "port": 9080
            }
        )
        server_id = response.json()["id"]

        mock_torrent = {
            "info_hash": "MNO345",
            "name": "file.zip",
            "path": "/downloads/file.zip",
            "is_multi_file": False,
            "files": [{"path": "file.zip", "size": 1000, "progress": 1.0, "priority": 1}]
        }

        with patch("torrent_manager.api.routes.torrents.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_torrents.return_value = iter([mock_torrent])
            mock_get_client.return_value = mock_client

            response = await authenticated_client.get(
                f"/torrents/MNO345/files?server_id={server_id}"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["http_enabled"] is False
        assert "download_url" not in data["files"][0]

    @pytest.mark.asyncio
    async def test_special_characters_in_torrent_name(self, authenticated_client, server_with_http):
        """Torrent names with special characters should be handled correctly."""
        server_id = server_with_http["id"]

        mock_torrent = {
            "info_hash": "PQR678",
            "name": "The Guest Room [B0FXBRPYH7]",
            "path": "/downloads/The Guest Room [B0FXBRPYH7]",
            "is_multi_file": True,
            "files": [
                {"path": "The Guest Room [B0FXBRPYH7].m4b", "size": 500000000, "progress": 1.0, "priority": 1}
            ]
        }

        with patch("torrent_manager.api.routes.torrents.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.list_torrents.return_value = iter([mock_torrent])
            mock_get_client.return_value = mock_client

            response = await authenticated_client.get(
                f"/torrents/PQR678/files?server_id={server_id}"
            )

        assert response.status_code == 200
        data = response.json()
        expected_url = f"/servers/{server_id}/download/The Guest Room [B0FXBRPYH7]/The Guest Room [B0FXBRPYH7].m4b"
        assert data["files"][0]["download_url"] == expected_url
