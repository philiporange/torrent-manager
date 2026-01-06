# Torrent Manager

A Python application for managing torrent client instances with a secure REST API. This tool automates common tasks such as moving completed torrents, managing seeding duration, and logging torrent activity. It provides both a command-line interface and a FastAPI-based REST API with secure session-based authentication.

## Purpose

- Interact with torrent clients programmatically via API or CLI
- Track and log torrent activity
- Perform maintenance tasks:
  - Move completed torrents
  - Pause long-seeded torrents
  - Remove old seeded torrents
  - Log torrent statuses
- Provide secure REST API with session-based authentication
- Offer utilities for torrent file operations
- Manage database of torrent-related information

## Features

### Core Features
- Web frontend for browser-based torrent management
- Command-line interface for torrent management
- FastAPI REST API with interactive documentation
- Torrent activity logging and monitoring
- Automated maintenance tasks
- Torrent file parsing and magnet link creation
- Database management for users, torrents, and activity

### Authentication & Security
- **Two authentication methods:**
  - Session-based (cookies) for browser/interactive use
  - API keys (Bearer tokens) for programmatic access
- Server-set, HTTP-only secure session cookies
- Sliding expiration (resets on each user interaction)
- ITP-safe sliding window (< 7 days)
- Remember-me tokens for longer-lived authentication
- API keys with optional expiration and revocation
- Bcrypt password hashing
- CSRF protection via SameSite=Lax cookies
- Secure cookie attributes (HttpOnly, Secure, SameSite)

### Lifecycle Callbacks
- Hook into torrent lifecycle events with custom Python scripts
- Events: added, started, stopped, completed, removed, error, transfer_started, transfer_completed
- Callbacks receive comprehensive torrent data including all database records
- Auto-loaded from `~/.torrent_manager/callbacks/` directory

## Quick Start

### Start the API Server

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python run.py

# Or with auto-reload for development
python -m torrent_manager.server --reload
```

The API will be available at http://localhost:8144 with interactive documentation at http://localhost:8144/docs

### Start the rTorrent Docker Container

```bash
# Start rTorrent server
python rtorrent_server.py start

# Check status
python rtorrent_server.py status

# Stop server
python rtorrent_server.py stop
```

### Use the Web Frontend

A simple web interface is available for managing torrents through your browser:

```bash
# Make sure the API server is running
python run.py

# Open index.html in your browser
# Or serve it with a simple HTTP server:
python -m http.server 8080

# Then navigate to:
# http://localhost:8080/index.html
```

The web frontend provides:
- User registration and login with beautiful UI
- Real-time torrent list with auto-refresh (5-second polling)
- Add torrents via magnet URI, HTTP URL, or file upload
- Control torrents (start, stop, remove)
- Live progress tracking with download/upload speeds
- API key creation and management
- Secure session-based authentication
- Responsive design for mobile and desktop

Note: For local development without HTTPS, you may need to disable the secure cookie flag:
```bash
export COOKIE_SECURE=false
python -m torrent_manager.server --reload
```

## API Documentation

See [AUTHENTICATION.md](AUTHENTICATION.md) for detailed documentation on the authentication system.

### Authentication Endpoints

- `POST /auth/register` - Register a new user
- `POST /auth/login` - Login and create session
- `POST /auth/logout` - Logout and destroy session
- `GET /auth/me` - Get current authenticated user

### API Key Management

- `POST /auth/api-keys` - Create a new API key
- `GET /auth/api-keys` - List your API keys
- `DELETE /auth/api-keys/{prefix}` - Revoke an API key

### Torrent Management Endpoints

All torrent endpoints require authentication (session or API key).

- `GET /torrents` - List all torrents with detailed information
- `POST /torrents` - Add torrent by magnet URI or HTTP/HTTPS URL
- `POST /torrents/upload` - Upload and add a .torrent file

**Note on private trackers:** When adding torrents via URL, the torrent manager server downloads the `.torrent` file. Some private trackers validate that the requesting IP matches your account. If you encounter "IP does not match" errors, either register the torrent manager server's IP with the tracker, or use file upload instead (download the `.torrent` in your browser, then upload it).
- `GET /torrents/{info_hash}` - Get detailed information about a specific torrent
- `POST /torrents/{info_hash}/start` - Start a paused torrent
- `POST /torrents/{info_hash}/stop` - Stop/pause a torrent
- `DELETE /torrents/{info_hash}` - Remove a torrent from the client

### Example Usage

#### Session-Based Authentication (Browser)

```python
import httpx

async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
    # Register
    await client.post("/auth/register", json={
        "username": "user",
        "password": "pass",
        "email": "user@example.com"
    })

    # Login
    await client.post("/auth/login", json={
        "username": "user",
        "password": "pass",
        "remember_me": True
    })

    # Access protected endpoint
    response = await client.get("/auth/me")
    print(response.json())
```

#### API Key Authentication (Programmatic)

```python
import httpx

# First, create an API key (requires login)
async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
    await client.post("/auth/login", json={
        "username": "user",
        "password": "pass",
        "remember_me": False
    })

    # Create API key
    response = await client.post("/auth/api-keys", json={
        "name": "My Script",
        "expires_days": 90
    })

    api_key = response.json()["api_key"]

# Use the API key for subsequent requests
async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
    response = await client.get(
        "/torrents",
        headers={"Authorization": f"Bearer {api_key}"}
    )
    print(response.json())
```

#### Using with curl

```bash
# Create API key (after login via browser or script)
curl -X POST http://localhost:8000/auth/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "curl-key", "expires_days": 30}' \
  --cookie "session=<your-session>"

# Use API key
curl -H "Authorization: Bearer <api_key>" \
  http://localhost:8000/auth/me
```

#### Managing Torrents

```python
import httpx

API_KEY = "your-api-key-here"
headers = {"Authorization": f"Bearer {API_KEY}"}

async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
    # List all torrents
    response = await client.get("/torrents", headers=headers)
    torrents = response.json()

    # Add torrent by magnet URI
    await client.post("/torrents", headers=headers, json={
        "uri": "magnet:?xt=urn:btih:...",
        "start": True
    })

    # Add torrent by URL
    await client.post("/torrents", headers=headers, json={
        "uri": "https://example.com/file.torrent"
    })

    # Upload .torrent file
    with open("file.torrent", "rb") as f:
        files = {"file": f}
        await client.post("/torrents/upload", headers=headers, files=files)

    # Start/stop/remove torrent
    info_hash = "abc123..."
    await client.post(f"/torrents/{info_hash}/start", headers=headers)
    await client.post(f"/torrents/{info_hash}/stop", headers=headers)
    await client.delete(f"/torrents/{info_hash}", headers=headers)
```

#### Using with curl

```bash
# List torrents
curl -H "Authorization: Bearer <api_key>" \
  http://localhost:8000/torrents

# Add magnet URI
curl -X POST http://localhost:8000/torrents \
  -H "Authorization: Bearer <api_key>" \
  -H "Content-Type: application/json" \
  -d '{"uri": "magnet:?xt=urn:btih:...", "start": true}'

# Upload torrent file
curl -X POST http://localhost:8000/torrents/upload \
  -H "Authorization: Bearer <api_key>" \
  -F "file=@file.torrent"

# Start torrent
curl -X POST http://localhost:8000/torrents/<info_hash>/start \
  -H "Authorization: Bearer <api_key>"

# Remove torrent
curl -X DELETE http://localhost:8000/torrents/<info_hash> \
  -H "Authorization: Bearer <api_key>"
```

See examples:
- `examples/auth_example.py` - Session-based authentication
- `examples/api_key_example.py` - API key authentication

## Testing

Run the authentication test suite:

```bash
# Test session-based authentication
pytest tests/test_auth.py -v

# Test API key authentication
pytest tests/test_api_keys.py -v

# Run all authentication tests
pytest tests/test_auth.py tests/test_api_keys.py -v
```

All 47 tests should pass, covering:
- User management and password authentication
- Session management with sliding expiration
- Remember-me token functionality
- API key creation, validation, and revocation
- Both session and API key authentication
- Protected endpoint access

## Lifecycle Callbacks

The callback system allows you to run custom Python scripts when torrent lifecycle events occur. Callbacks are automatically loaded from `~/.torrent_manager/callbacks/` on server startup.

### Supported Events

| Event | Trigger |
|-------|---------|
| `on_added` | Torrent added to a server |
| `on_started` | Torrent started/resumed |
| `on_stopped` | Torrent paused/stopped |
| `on_completed` | Torrent finished downloading (100%) |
| `on_removed` | Torrent removed from server |
| `on_error` | Error occurred with torrent |
| `on_transfer_started` | File transfer to local storage began |
| `on_transfer_completed` | File transfer to local storage finished |

### Creating a Callback

Create a Python file in `~/.torrent_manager/callbacks/` that defines a class inheriting from `TorrentCallback`:

```python
# ~/.torrent_manager/callbacks/my_callback.py
from torrent_manager.callbacks import TorrentCallback, TorrentInfo

class MyCallback(TorrentCallback):
    async def on_completed(self, torrent_info: TorrentInfo) -> None:
        print(f"Completed: {torrent_info.name}")
        print(f"Size: {torrent_info.size / 1024 / 1024:.1f} MB")
        print(f"Server: {torrent_info.server_name}")

        # Access database records
        if torrent_info.db_server:
            print(f"Auto-download: {torrent_info.db_server.get('auto_download_enabled')}")
```

### TorrentInfo Fields

Callbacks receive a `TorrentInfo` object with:

**Core fields:**
- `info_hash`, `name`, `server_id`, `server_name`, `server_type`
- `size`, `progress`, `state`, `is_active`, `is_complete`, `is_private`
- `download_rate`, `upload_rate`, `seeders`, `leechers`, `ratio`
- `base_path`, `labels`

**Database records:**
- `db_torrent` - Torrent table record
- `db_statuses` - Recent Status records (last 10)
- `db_actions` - Recent Action records (last 20)
- `db_server` - TorrentServer configuration
- `db_transfers` - TransferJob records
- `db_settings` - Per-torrent user settings

**Event metadata:**
- `event` - The event type (TorrentEvent enum)
- `event_time` - When the event occurred
- `error_message` - Error details (for error events)

### Example: Notification Callback

```python
# ~/.torrent_manager/callbacks/notify.py
import httpx
from torrent_manager.callbacks import TorrentCallback, TorrentInfo

class WebhookCallback(TorrentCallback):
    WEBHOOK_URL = "https://hooks.example.com/torrent"

    async def on_completed(self, torrent_info: TorrentInfo) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(self.WEBHOOK_URL, json={
                "event": "completed",
                "name": torrent_info.name,
                "size": torrent_info.size,
                "hash": torrent_info.info_hash,
            })
```

### Configuration

The callback directory can be customized via environment variable:

```bash
export CALLBACK_DIR="/path/to/custom/callbacks"
```

Default: `~/.torrent_manager/callbacks/`

See `examples/example_callback.py` for more callback examples.