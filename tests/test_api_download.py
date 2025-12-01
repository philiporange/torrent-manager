import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from torrent_manager.api import app, get_current_user, get_user_server, get_http_client

client = TestClient(app)

def mock_get_current_user():
    user = MagicMock()
    user.username = "testuser"
    return user

def test_download_file_success():
    # Setup mocks
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    try:
        with patch("torrent_manager.api.routes.servers.get_user_server") as mock_get_server, \
             patch("torrent_manager.api.routes.servers.get_http_client") as mock_get_http_client:

            
            mock_server = MagicMock()
            mock_server.id = "server1"
            mock_get_server.return_value = mock_server
            
            mock_http_client = MagicMock()
            mock_http_client.timeout = 30
            mock_http_client._build_url.return_value = "http://example.com/file.txt"
            
            mock_response = MagicMock()
            mock_response.headers = {"Content-Type": "text/plain", "Content-Length": "11"}
            # response.iter_content returns an iterator
            mock_response.iter_content.return_value = iter([b"hello ", b"world"])
            mock_response.close = MagicMock()
            
            mock_http_client._session_get.return_value = mock_response
            mock_get_http_client.return_value = mock_http_client
            
            # Execute request
            response = client.get("/servers/server1/download/file.txt")
            
            # Verify response
            assert response.status_code == 200
            assert response.content == b"hello world"
            assert response.headers["content-disposition"] == 'attachment; filename="file.txt"'
            
            # Verify mocked calls
            mock_http_client._session_get.assert_called_once()
            mock_response.close.assert_called() # Ensure close was called
    finally:
        app.dependency_overrides = {}

def test_download_file_error():
    # Setup mocks
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    try:
        with patch("torrent_manager.api.routes.servers.get_user_server") as mock_get_server, \
             patch("torrent_manager.api.routes.servers.get_http_client") as mock_get_http_client:

            
            mock_server = MagicMock()
            mock_get_server.return_value = mock_server
            
            mock_http_client = MagicMock()
            mock_http_client.timeout = 30
            mock_http_client._build_url.return_value = "http://example.com/file.txt"
            
            # Simulate error
            mock_http_client._session_get.side_effect = Exception("Connection error")
            mock_get_http_client.return_value = mock_http_client
            
            # Execute request
            response = client.get("/servers/server1/download/file.txt")
            
            # Verify response
            assert response.status_code == 500
            assert "Connection error" in response.json()["detail"]
    finally:
        app.dependency_overrides = {}
