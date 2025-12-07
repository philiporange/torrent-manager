"""
Tests for torrent server management endpoints.
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


class TestServerEndpoints:
    """Tests for server CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_add_server_success(self, authenticated_client, test_user):
        """Test adding a new server."""
        response = await authenticated_client.post(
            "/servers",
            json={
                "name": "Test rTorrent",
                "server_type": "rtorrent",
                "host": "localhost",
                "port": 9080,
                "rpc_path": "/RPC2"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test rTorrent"
        assert data["server_type"] == "rtorrent"
        assert data["host"] == "localhost"
        assert data["port"] == 9080
        assert data["rpc_path"] == "/RPC2"
        assert data["enabled"] is True
        assert "id" in data
        assert data["user_id"] == test_user.id

    @pytest.mark.asyncio
    async def test_add_transmission_server(self, authenticated_client, test_user):
        """Test adding a Transmission server."""
        response = await authenticated_client.post(
            "/servers",
            json={
                "name": "Test Transmission",
                "server_type": "transmission",
                "host": "192.168.1.100",
                "port": 9091,
                "username": "admin",
                "password": "secret"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Transmission"
        assert data["server_type"] == "transmission"
        assert data["host"] == "192.168.1.100"
        assert data["port"] == 9091
        assert data["username"] == "admin"
        assert data["password"] == "secret"

    @pytest.mark.asyncio
    async def test_add_server_unauthenticated(self, async_client):
        """Test that unauthenticated users cannot add servers."""
        response = await async_client.post(
            "/servers",
            json={
                "name": "Test Server",
                "server_type": "rtorrent",
                "host": "localhost",
                "port": 9080
            }
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_servers(self, authenticated_client, test_user):
        """Test listing user's servers."""
        # Add two servers
        await authenticated_client.post(
            "/servers",
            json={
                "name": "Server 1",
                "server_type": "rtorrent",
                "host": "host1",
                "port": 9080
            }
        )
        await authenticated_client.post(
            "/servers",
            json={
                "name": "Server 2",
                "server_type": "transmission",
                "host": "host2",
                "port": 9091
            }
        )

        # List servers
        response = await authenticated_client.get("/servers")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["name"] == "Server 1"
        assert data[1]["name"] == "Server 2"

    @pytest.mark.asyncio
    async def test_list_servers_user_isolation(self, async_client, test_user):
        """Test that users only see their own servers."""
        # Create second user
        user2 = UserManager.create_user(username="user2", password="pass2")

        # Login as first user and add server
        await async_client.post(
            "/auth/login",
            json={"username": "testuser", "password": "testpass123", "remember_me": False}
        )
        await async_client.post(
            "/servers",
            json={
                "name": "User1 Server",
                "server_type": "rtorrent",
                "host": "host1",
                "port": 9080
            }
        )

        # Logout and login as second user
        await async_client.post("/auth/logout")
        await async_client.post(
            "/auth/login",
            json={"username": "user2", "password": "pass2", "remember_me": False}
        )

        # User2 should see no servers
        response = await async_client.get("/servers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_get_server_by_id(self, authenticated_client):
        """Test getting a specific server by ID."""
        # Add server
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

        # Get server
        response = await authenticated_client.get(f"/servers/{server_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == server_id
        assert data["name"] == "Test Server"

    @pytest.mark.asyncio
    async def test_get_server_not_found(self, authenticated_client):
        """Test getting a non-existent server."""
        response = await authenticated_client.get("/servers/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_server(self, authenticated_client):
        """Test updating a server."""
        # Add server
        add_response = await authenticated_client.post(
            "/servers",
            json={
                "name": "Old Name",
                "server_type": "rtorrent",
                "host": "oldhost",
                "port": 9080
            }
        )
        server_id = add_response.json()["id"]

        # Update server
        response = await authenticated_client.put(
            f"/servers/{server_id}",
            json={
                "name": "New Name",
                "host": "newhost",
                "port": 9090,
                "enabled": False
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["host"] == "newhost"
        assert data["port"] == 9090
        assert data["enabled"] is False

    @pytest.mark.asyncio
    async def test_update_server_not_found(self, authenticated_client):
        """Test updating a non-existent server."""
        response = await authenticated_client.put(
            "/servers/nonexistent",
            json={"name": "New Name"}
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_server(self, authenticated_client):
        """Test deleting a server."""
        # Add server
        add_response = await authenticated_client.post(
            "/servers",
            json={
                "name": "To Delete",
                "server_type": "rtorrent",
                "host": "localhost",
                "port": 9080
            }
        )
        server_id = add_response.json()["id"]

        # Delete server
        response = await authenticated_client.delete(f"/servers/{server_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"

        # Verify server is deleted
        get_response = await authenticated_client.get(f"/servers/{server_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_server_not_found(self, authenticated_client):
        """Test deleting a non-existent server."""
        response = await authenticated_client.delete("/servers/nonexistent")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_test_server_endpoint(self, authenticated_client):
        """Test the server connection test endpoint."""
        # Add server (will fail connection since it doesn't exist)
        add_response = await authenticated_client.post(
            "/servers",
            json={
                "name": "Test Server",
                "server_type": "rtorrent",
                "host": "localhost",
                "port": 9999  # Non-existent port
            }
        )
        server_id = add_response.json()["id"]

        # Test connection (should fail)
        response = await authenticated_client.post(f"/servers/{server_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "message" in data
        # Connection will likely fail, but endpoint should work
        assert data["status"] in ["connected", "failed"]
