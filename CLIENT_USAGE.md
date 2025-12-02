# Torrent Manager Client Usage

The `TorrentManagerClient` provides programmatic access to the Torrent Manager REST API.

## Installation

```python
from torrent_manager.client import TorrentManagerClient
```

## Authentication

### API Key Authentication (Recommended for scripts)

```python
client = TorrentManagerClient(
    base_url="http://localhost:8144",
    api_key="your-api-key-here"
)
```

### Session Authentication

```python
client = TorrentManagerClient(base_url="http://localhost:8144")
client.login("username", "password", remember_me=True)
```

## Auth Methods

### register(username, password)

Register a new user account.

```python
result = client.register("myuser", "mypassword")
# Returns:
# {
#     "user_id": "abc123def456",
#     "username": "myuser"
# }
```

### login(username, password, remember_me=False)

Login and establish a session.

```python
result = client.login("myuser", "mypassword", remember_me=True)
# Returns:
# {
#     "username": "myuser",
#     "user_id": "abc123def456"
# }
```

### logout()

Logout and destroy the session.

```python
result = client.logout()
# Returns:
# {
#     "message": "Logged out successfully"
# }
```

### get_me()

Get current authenticated user info.

```python
result = client.get_me()
# Returns:
# {
#     "user_id": "abc123def456",
#     "username": "myuser",
#     "is_admin": false,
#     "auth_method": "api_key"  # or "session"
# }
```

## API Key Methods

### create_api_key(name, expires_days=None)

Create a new API key.

```python
result = client.create_api_key("My Script", expires_days=90)
# Returns:
# {
#     "api_key": "tm_abc123...xyz789",  # Full key - save this!
#     "api_key_id": "abc12345",
#     "name": "My Script",
#     "created_at": "2024-01-15T10:30:00",
#     "expires_at": "2024-04-15T10:30:00"
# }
```

### list_api_keys()

List all API keys for the current user.

```python
result = client.list_api_keys()
# Returns:
# {
#     "api_keys": [
#         {
#             "api_key_id": "abc12345",
#             "name": "My Script",
#             "created_at": "2024-01-15T10:30:00",
#             "last_used_at": "2024-01-16T08:00:00",
#             "expires_at": "2024-04-15T10:30:00",
#             "revoked": false
#         }
#     ]
# }
```

### revoke_api_key(key_prefix)

Revoke an API key by its prefix (first 8 characters).

```python
result = client.revoke_api_key("abc12345")
# Returns:
# {
#     "message": "API key revoked"
# }
```

## Server Methods

### add_server(name, server_type, host, port, ...)

Add a new torrent server configuration.

```python
result = client.add_server(
    name="My rTorrent",
    server_type="rtorrent",  # or "transmission"
    host="192.168.1.10",
    port=8080,
    username="admin",
    password="secret",
    rpc_path="/RPC2",
    use_ssl=False,
    # Optional HTTP download server settings
    http_host="192.168.1.10",
    http_port=80,
    http_path="/downloads",
    http_username="admin",
    http_password="secret",
    http_use_ssl=False
)
# Returns:
# {
#     "id": "xYz123AbC456",
#     "user_id": "abc123def456",
#     "name": "My rTorrent",
#     "server_type": "rtorrent",
#     "host": "192.168.1.10",
#     "port": 8080,
#     "username": "admin",
#     "password": "secret",
#     "rpc_path": "/RPC2",
#     "use_ssl": false,
#     "enabled": true,
#     "created_at": "2024-01-15T10:30:00",
#     "http_host": "192.168.1.10",
#     "http_port": 80,
#     "http_path": "/downloads",
#     "http_username": "admin",
#     "http_use_ssl": false,
#     "http_enabled": true
# }
```

### list_servers()

List all configured servers.

```python
result = client.list_servers()
# Returns:
# [
#     {
#         "id": "xYz123AbC456",
#         "name": "My rTorrent",
#         "server_type": "rtorrent",
#         "host": "192.168.1.10",
#         "port": 8080,
#         "rpc_path": "/RPC2",
#         "use_ssl": false,
#         "enabled": true,
#         "created_at": "2024-01-15T10:30:00",
#         "http_host": "192.168.1.10",
#         "http_port": 80,
#         "http_path": "/downloads",
#         "http_username": "admin",
#         "http_use_ssl": false,
#         "http_enabled": true
#     }
# ]
```

### get_server(server_id)

Get details of a specific server.

```python
result = client.get_server("xYz123AbC456")
# Returns: Same structure as add_server response
```

### update_server(server_id, ...)

Update a server configuration. Only provided fields are updated.

```python
result = client.update_server(
    server_id="xYz123AbC456",
    name="Renamed Server",
    enabled=False
)
# Returns: Updated server object (same structure as add_server)
```

### delete_server(server_id)

Delete a server configuration.

```python
result = client.delete_server("xYz123AbC456")
# Returns:
# {
#     "status": "deleted",
#     "message": "Server deleted successfully"
# }
```

### test_server(server_id)

Test connection to a server.

```python
result = client.test_server("xYz123AbC456")
# Returns (success):
# {
#     "status": "connected",
#     "message": "Successfully connected to My rTorrent"
# }
# Returns (failure):
# {
#     "status": "failed",
#     "message": "Connection refused"
# }
```

## Torrent Methods

### list_torrents(server_id=None)

List all torrents, optionally filtered by server.

```python
result = client.list_torrents()
# Or filter by server:
result = client.list_torrents(server_id="xYz123AbC456")
# Returns:
# [
#     {
#         "info_hash": "ABC123DEF456789012345678901234567890ABCD",
#         "name": "Ubuntu 22.04 LTS",
#         "size": 3654957056,
#         "progress": 100.0,
#         "state": "seeding",
#         "download_rate": 0,
#         "upload_rate": 125000,
#         "ratio": 2.5,
#         "peers": 5,
#         "seeds": 0,
#         "complete": true,
#         "is_private": false,
#         "server_id": "xYz123AbC456",
#         "server_name": "My rTorrent",
#         "server_type": "rtorrent",
#         "seeding_duration": 86400,
#         "seeding_threshold": 172800
#     }
# ]
```

### add_torrent(uri, server_id, start=True)

Add a torrent by info hash, magnet URI, or HTTP URL.

```python
# By magnet URI
result = client.add_torrent(
    uri="magnet:?xt=urn:btih:ABC123...",
    server_id="xYz123AbC456",
    start=True
)

# By info hash (40 hex chars or 32 base32 chars)
result = client.add_torrent(
    uri="ABC123DEF456789012345678901234567890ABCD",
    server_id="xYz123AbC456"
)

# By HTTP URL
result = client.add_torrent(
    uri="https://example.com/file.torrent",
    server_id="xYz123AbC456"
)
# Returns:
# {
#     "message": "Torrent added successfully",
#     "uri": "magnet:?xt=urn:btih:ABC123...",
#     "server_id": "xYz123AbC456",
#     "server_name": "My rTorrent"
# }
```

### add_magnet(magnet_uri, server_id, start=True)

Convenience method for adding magnet URIs.

```python
result = client.add_magnet(
    magnet_uri="magnet:?xt=urn:btih:ABC123...",
    server_id="xYz123AbC456"
)
# Returns: Same as add_torrent
```

### add_url(url, server_id, start=True)

Convenience method for adding torrents by URL.

```python
result = client.add_url(
    url="https://example.com/file.torrent",
    server_id="xYz123AbC456"
)
# Returns: Same as add_torrent
```

### upload_torrent(file_path, server_id, start=True)

Upload a .torrent file.

```python
result = client.upload_torrent(
    file_path="/path/to/file.torrent",
    server_id="xYz123AbC456",
    start=True
)
# Returns:
# {
#     "message": "Torrent uploaded and added successfully",
#     "server_id": "xYz123AbC456",
#     "server_name": "My rTorrent"
# }
```

### get_torrent(info_hash, server_id=None)

Get detailed information about a specific torrent.

```python
result = client.get_torrent("ABC123DEF456789012345678901234567890ABCD")
# Returns:
# {
#     "info_hash": "ABC123DEF456789012345678901234567890ABCD",
#     "name": "Ubuntu 22.04 LTS",
#     "size": 3654957056,
#     "progress": 100.0,
#     "state": "seeding",
#     "download_rate": 0,
#     "upload_rate": 125000,
#     "ratio": 2.5,
#     "peers": 5,
#     "seeds": 0,
#     "complete": true,
#     "is_private": false,
#     "path": "/downloads/Ubuntu 22.04 LTS",
#     "server_id": "xYz123AbC456",
#     "server_name": "My rTorrent",
#     "server_type": "rtorrent"
# }
```

### start_torrent(info_hash, server_id=None)

Start a paused torrent.

```python
result = client.start_torrent("ABC123DEF456789012345678901234567890ABCD")
# Returns:
# {
#     "message": "Torrent started",
#     "info_hash": "ABC123DEF456789012345678901234567890ABCD",
#     "server_id": "xYz123AbC456"
# }
```

### stop_torrent(info_hash, server_id=None)

Stop/pause a torrent.

```python
result = client.stop_torrent("ABC123DEF456789012345678901234567890ABCD")
# Returns:
# {
#     "message": "Torrent stopped",
#     "info_hash": "ABC123DEF456789012345678901234567890ABCD",
#     "server_id": "xYz123AbC456"
# }
```

### delete_torrent(info_hash, server_id=None)

Remove a torrent from the server (does not delete downloaded files).

```python
result = client.delete_torrent("ABC123DEF456789012345678901234567890ABCD")
# Returns:
# {
#     "message": "Torrent removed",
#     "info_hash": "ABC123DEF456789012345678901234567890ABCD",
#     "server_id": "xYz123AbC456"
# }
```

### list_torrent_files(info_hash, server_id=None)

List all files belonging to a torrent.

```python
result = client.list_torrent_files("ABC123DEF456789012345678901234567890ABCD")
# Returns:
# {
#     "info_hash": "ABC123DEF456789012345678901234567890ABCD",
#     "name": "Ubuntu 22.04 LTS",
#     "path": "/downloads/Ubuntu 22.04 LTS",
#     "server_id": "xYz123AbC456",
#     "server_name": "My rTorrent",
#     "http_enabled": true,
#     "files": [
#         {
#             "path": "ubuntu-22.04-desktop-amd64.iso",
#             "size": 3654957056,
#             "progress": 100.0,
#             "priority": 1,
#             "download_url": "/servers/xYz123AbC456/download/ubuntu-22.04-desktop-amd64.iso"
#         }
#     ]
# }
```

## Server File Methods

### list_server_files(server_id, path="")

List files and directories at a server's HTTP download location.

```python
result = client.list_server_files("xYz123AbC456", path="completed")
# Returns:
# {
#     "server_id": "xYz123AbC456",
#     "server_name": "My rTorrent",
#     "path": "completed",
#     "entries": [
#         {
#             "name": "Ubuntu 22.04 LTS",
#             "path": "completed/Ubuntu 22.04 LTS",
#             "is_dir": true,
#             "size": null,
#             "modified": "2024-01-15T10:30:00",
#             "raw_size": "-"
#         },
#         {
#             "name": "document.pdf",
#             "path": "completed/document.pdf",
#             "is_dir": false,
#             "size": 1048576,
#             "modified": "2024-01-14T08:00:00",
#             "raw_size": "1.0M"
#         }
#     ]
# }
```

### download_file(server_id, file_path, output_path=None)

Download a file from a server's HTTP download location.

```python
# Download to current directory with original filename
saved_path = client.download_file(
    server_id="xYz123AbC456",
    file_path="completed/document.pdf"
)
# Returns: "document.pdf"

# Download to specific path
saved_path = client.download_file(
    server_id="xYz123AbC456",
    file_path="completed/document.pdf",
    output_path="/home/user/downloads/my_doc.pdf"
)
# Returns: "/home/user/downloads/my_doc.pdf"
```

### download_file_stream(server_id, file_path)

Get a streaming response for large file downloads.

```python
response = client.download_file_stream("xYz123AbC456", "completed/large_file.iso")
# Returns: requests.Response with stream=True

# Use with context manager:
with open("output.iso", "wb") as f:
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)
response.close()
```

## Error Handling

All methods raise `Exception` with descriptive messages on failure.

```python
try:
    result = client.get_torrent("invalid_hash")
except Exception as e:
    print(f"Error: {e}")
    # "Error: API Error: Torrent not found"
```

Common error patterns:
- `"API Error: ..."` - Server returned an error response
- `"Could not connect to server at ..."` - Connection failed

## Complete Example

```python
from torrent_manager.client import TorrentManagerClient

# Initialize with API key
client = TorrentManagerClient(
    base_url="http://localhost:8144",
    api_key="tm_your_api_key_here"
)

# List servers
servers = client.list_servers()
if not servers:
    # Add a server
    server = client.add_server(
        name="My Server",
        server_type="rtorrent",
        host="192.168.1.10",
        port=8080
    )
    server_id = server["id"]
else:
    server_id = servers[0]["id"]

# Test connection
test = client.test_server(server_id)
print(f"Server status: {test['status']}")

# Add a torrent
result = client.add_torrent(
    uri="magnet:?xt=urn:btih:...",
    server_id=server_id
)
print(f"Added: {result['message']}")

# List torrents
torrents = client.list_torrents()
for t in torrents:
    print(f"{t['name']}: {t['progress']:.1f}% - {t['state']}")

# Get files for a torrent
if torrents:
    files = client.list_torrent_files(torrents[0]["info_hash"])
    for f in files["files"]:
        print(f"  {f['path']}: {f['size']} bytes")
```
