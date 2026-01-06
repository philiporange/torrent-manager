"""
Tests for transfer (auto-download) functionality.
"""

import os
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from peewee import SqliteDatabase

# Disable secure cookies for testing
os.environ["COOKIE_SECURE"] = "false"

from torrent_manager.api import app
from torrent_manager.auth import UserManager
from torrent_manager.models import (
    User, Session, RememberMeToken, TorrentServer, TransferJob, UserTorrentSettings, db
)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Setup test database before each test."""
    from torrent_manager import models as model_module

    test_db = SqliteDatabase(':memory:')

    models_list = [User, Session, RememberMeToken, TorrentServer, TransferJob, UserTorrentSettings]
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


class TestServerAutoDownloadConfig:
    """Tests for server auto-download configuration."""

    @pytest.mark.asyncio
    async def test_add_server_with_auto_download(self, authenticated_client, test_user):
        """Test adding a server with auto-download configuration."""
        response = await authenticated_client.post(
            "/servers",
            json={
                "name": "Test rTorrent",
                "server_type": "rtorrent",
                "host": "seedbox.example.com",
                "port": 9080,
                "rpc_path": "/RPC2",
                "auto_download_enabled": True,
                "auto_download_path": "/data/downloads",
                "auto_delete_remote": True,
                "ssh_host": "seedbox.example.com",
                "ssh_port": 22,
                "ssh_user": "user",
                "ssh_key_path": "/home/user/.ssh/id_rsa"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["auto_download_enabled"] is True
        assert data["auto_download_path"] == "/data/downloads"
        assert data["auto_delete_remote"] is True
        assert data["ssh_host"] == "seedbox.example.com"
        assert data["ssh_port"] == 22
        assert data["ssh_user"] == "user"
        assert data["ssh_key_path"] == "/home/user/.ssh/id_rsa"

    @pytest.mark.asyncio
    async def test_update_server_auto_download(self, authenticated_client):
        """Test updating server auto-download settings."""
        # Add server without auto-download
        add_response = await authenticated_client.post(
            "/servers",
            json={
                "name": "Test Server",
                "server_type": "rtorrent",
                "host": "localhost",
                "port": 9080
            }
        )
        server_id = add_response.json()["id"]

        # Update with auto-download settings
        response = await authenticated_client.put(
            f"/servers/{server_id}",
            json={
                "auto_download_enabled": True,
                "auto_download_path": "/data/downloads",
                "ssh_host": "localhost",
                "ssh_user": "root"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["auto_download_enabled"] is True
        assert data["auto_download_path"] == "/data/downloads"
        assert data["ssh_host"] == "localhost"
        assert data["ssh_user"] == "root"

    @pytest.mark.asyncio
    async def test_list_servers_includes_auto_download(self, authenticated_client):
        """Test that listing servers includes auto-download fields."""
        await authenticated_client.post(
            "/servers",
            json={
                "name": "Test Server",
                "server_type": "rtorrent",
                "host": "localhost",
                "port": 9080,
                "auto_download_enabled": True,
                "auto_download_path": "/downloads"
            }
        )

        response = await authenticated_client.get("/servers")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert "auto_download_enabled" in data[0]
        assert "auto_download_path" in data[0]
        assert "ssh_host" in data[0]
        assert data[0]["auto_download_enabled"] is True


class TestTransferEndpoints:
    """Tests for transfer job management endpoints."""

    @pytest.fixture
    def server_with_transfer(self, authenticated_client, test_user):
        """Create a server and a transfer job for testing."""
        import secrets

        # Create server
        server = TorrentServer.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            name="Test Server",
            server_type="rtorrent",
            host="localhost",
            port=9080,
            auto_download_enabled=True,
            auto_download_path="/data/downloads"
        )

        # Create transfer job
        job = TransferJob.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            server_id=server.id,
            torrent_hash="ABCD1234567890ABCD1234567890ABCD12345678",
            torrent_name="Test Torrent",
            remote_path="/home/user/downloads/test",
            local_path="/data/downloads/test",
            status="pending",
            total_bytes=1024 * 1024 * 100  # 100MB
        )

        return server, job

    @pytest.mark.asyncio
    async def test_list_transfers(self, authenticated_client, test_user, server_with_transfer):
        """Test listing transfer jobs."""
        server, job = server_with_transfer

        response = await authenticated_client.get("/transfers")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == job.id
        assert data[0]["torrent_name"] == "Test Torrent"
        assert data[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_list_transfers_filter_by_status(self, authenticated_client, test_user):
        """Test filtering transfers by status."""
        import secrets

        server = TorrentServer.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            name="Test Server",
            server_type="rtorrent",
            host="localhost",
            port=9080
        )

        # Create jobs with different statuses
        TransferJob.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            server_id=server.id,
            torrent_hash="AAAA",
            torrent_name="Pending Job",
            remote_path="/remote",
            local_path="/local",
            status="pending"
        )
        TransferJob.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            server_id=server.id,
            torrent_hash="BBBB",
            torrent_name="Completed Job",
            remote_path="/remote",
            local_path="/local",
            status="completed"
        )

        # Filter by pending
        response = await authenticated_client.get("/transfers?status=pending")
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "pending"

        # Filter by completed
        response = await authenticated_client.get("/transfers?status=completed")
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_transfer(self, authenticated_client, test_user, server_with_transfer):
        """Test getting a specific transfer job."""
        server, job = server_with_transfer

        response = await authenticated_client.get(f"/transfers/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == job.id
        assert data["torrent_name"] == "Test Torrent"
        assert data["remote_path"] == "/home/user/downloads/test"
        assert data["local_path"] == "/data/downloads/test"

    @pytest.mark.asyncio
    async def test_get_transfer_not_found(self, authenticated_client):
        """Test getting a non-existent transfer."""
        response = await authenticated_client.get("/transfers/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_pending_transfer(self, authenticated_client, test_user, server_with_transfer):
        """Test cancelling a pending transfer."""
        server, job = server_with_transfer

        response = await authenticated_client.delete(f"/transfers/{job.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Transfer cancelled"

        # Verify status changed
        job = TransferJob.get_by_id(job.id)
        assert job.status == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_completed_transfer_fails(self, authenticated_client, test_user):
        """Test that cancelling a completed transfer fails."""
        import secrets

        server = TorrentServer.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            name="Test Server",
            server_type="rtorrent",
            host="localhost",
            port=9080
        )

        job = TransferJob.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            server_id=server.id,
            torrent_hash="ABCD",
            torrent_name="Completed Torrent",
            remote_path="/remote",
            local_path="/local",
            status="completed"
        )

        response = await authenticated_client.delete(f"/transfers/{job.id}")

        assert response.status_code == 400
        assert "Cannot cancel job with status" in response.json()["detail"]


class TestTorrentSettingsEndpoints:
    """Tests for per-torrent settings endpoints."""

    @pytest.fixture
    def server(self, test_user):
        """Create a test server."""
        import secrets
        return TorrentServer.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            name="Test Server",
            server_type="rtorrent",
            host="localhost",
            port=9080,
            auto_download_enabled=True,
            auto_download_path="/default/path",
            auto_delete_remote=False
        )

    @pytest.mark.asyncio
    async def test_get_torrent_settings_no_override(self, authenticated_client, test_user, server):
        """Test getting settings when no override exists."""
        info_hash = "ABCD1234567890ABCD1234567890ABCD12345678"

        response = await authenticated_client.get(
            f"/torrents/{info_hash}/settings?server_id={server.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["info_hash"] == info_hash
        assert data["server_id"] == server.id
        assert data["download_path"] is None  # No override
        assert data["auto_download"] is None  # No override
        assert data["server_defaults"]["auto_download_enabled"] is True
        assert data["server_defaults"]["auto_download_path"] == "/default/path"

    @pytest.mark.asyncio
    async def test_set_torrent_settings(self, authenticated_client, test_user, server):
        """Test setting per-torrent download settings."""
        info_hash = "ABCD1234567890ABCD1234567890ABCD12345678"

        response = await authenticated_client.put(
            f"/torrents/{info_hash}/settings?server_id={server.id}",
            json={
                "download_path": "/custom/path",
                "auto_download": True,
                "auto_delete_remote": True
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["download_path"] == "/custom/path"
        assert data["auto_download"] is True
        assert data["auto_delete_remote"] is True

    @pytest.mark.asyncio
    async def test_get_torrent_settings_with_override(self, authenticated_client, test_user, server):
        """Test getting settings when an override exists."""
        info_hash = "ABCD1234567890ABCD1234567890ABCD12345678"

        # Set override
        await authenticated_client.put(
            f"/torrents/{info_hash}/settings?server_id={server.id}",
            json={"download_path": "/custom/path"}
        )

        # Get settings
        response = await authenticated_client.get(
            f"/torrents/{info_hash}/settings?server_id={server.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["download_path"] == "/custom/path"

    @pytest.mark.asyncio
    async def test_update_torrent_settings(self, authenticated_client, test_user, server):
        """Test updating existing per-torrent settings."""
        info_hash = "ABCD1234567890ABCD1234567890ABCD12345678"

        # Set initial
        await authenticated_client.put(
            f"/torrents/{info_hash}/settings?server_id={server.id}",
            json={"download_path": "/path1"}
        )

        # Update
        response = await authenticated_client.put(
            f"/torrents/{info_hash}/settings?server_id={server.id}",
            json={"download_path": "/path2", "auto_download": False}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["download_path"] == "/path2"
        assert data["auto_download"] is False


class TestTransferService:
    """Tests for the TransferService logic."""

    def test_queue_transfer_creates_job(self, test_user):
        """Test that queue_transfer creates a TransferJob."""
        import secrets
        from torrent_manager.transfer import TransferService

        server = TorrentServer.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            name="Test Server",
            server_type="rtorrent",
            host="localhost",
            port=9080,
            auto_download_enabled=True,
            auto_download_path="/data/downloads",
            download_dir="/home/user/downloads"
        )

        torrent = {
            "info_hash": "ABCD1234567890ABCD1234567890ABCD12345678",
            "name": "Test Torrent",
            "base_path": "/home/user/downloads/ABCD/data/Test Torrent",
            "size": 1024 * 1024 * 100
        }

        service = TransferService()
        job = service.queue_transfer(
            server=server,
            torrent=torrent,
            user_id=test_user.id,
            triggered_by="auto"
        )

        assert job is not None
        assert job.torrent_hash == "ABCD1234567890ABCD1234567890ABCD12345678"
        assert job.torrent_name == "Test Torrent"
        assert job.status == "pending"
        assert job.triggered_by == "auto"

    def test_queue_transfer_skips_if_disabled(self, test_user):
        """Test that queue_transfer returns None when auto-download is disabled."""
        import secrets
        from torrent_manager.transfer import TransferService

        server = TorrentServer.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            name="Test Server",
            server_type="rtorrent",
            host="localhost",
            port=9080,
            auto_download_enabled=False,  # Disabled
            auto_download_path="/data/downloads"
        )

        torrent = {
            "info_hash": "ABCD",
            "name": "Test",
            "base_path": "/home/user/downloads/test",
            "size": 1024
        }

        service = TransferService()
        job = service.queue_transfer(
            server=server,
            torrent=torrent,
            user_id=test_user.id,
            triggered_by="auto"
        )

        assert job is None

    def test_queue_transfer_skips_duplicate(self, test_user):
        """Test that queue_transfer doesn't create duplicate jobs."""
        import secrets
        from torrent_manager.transfer import TransferService

        server = TorrentServer.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            name="Test Server",
            server_type="rtorrent",
            host="localhost",
            port=9080,
            auto_download_enabled=True,
            auto_download_path="/data/downloads",
            download_dir="/home/user/downloads"
        )

        torrent = {
            "info_hash": "ABCD1234567890ABCD1234567890ABCD12345678",
            "name": "Test Torrent",
            "base_path": "/home/user/downloads/test",
            "size": 1024
        }

        service = TransferService()

        # First call creates job
        job1 = service.queue_transfer(
            server=server,
            torrent=torrent,
            user_id=test_user.id,
            triggered_by="auto"
        )
        assert job1 is not None

        # Second call should return None (duplicate)
        job2 = service.queue_transfer(
            server=server,
            torrent=torrent,
            user_id=test_user.id,
            triggered_by="auto"
        )
        assert job2 is None

    def test_queue_transfer_manual_ignores_disabled(self, test_user):
        """Test that manual transfers work even when auto-download is disabled."""
        import secrets
        from torrent_manager.transfer import TransferService

        server = TorrentServer.create(
            id=secrets.token_urlsafe(16),
            user_id=test_user.id,
            name="Test Server",
            server_type="rtorrent",
            host="localhost",
            port=9080,
            auto_download_enabled=False,  # Disabled
            auto_download_path="/data/downloads",
            download_dir="/home/user/downloads"
        )

        torrent = {
            "info_hash": "ABCD1234567890ABCD1234567890ABCD12345678",
            "name": "Test",
            "base_path": "/home/user/downloads/test",
            "size": 1024
        }

        service = TransferService()
        job = service.queue_transfer(
            server=server,
            torrent=torrent,
            user_id=test_user.id,
            triggered_by="manual"  # Manual override
        )

        assert job is not None  # Manual should work even when disabled
