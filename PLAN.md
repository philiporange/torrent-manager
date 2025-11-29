# Multi-Server Torrent Manager Implementation Plan

## Overview

Add support for multiple remote torrent servers (rTorrent and Transmission) with full API and UI integration.

## Phase 1: Database Models

### Add TorrentServer Model (`models.py`)

```python
class TorrentServer(BaseModel):
    id = CharField(primary_key=True)  # UUID
    user_id = CharField(index=True)   # Owner of this server config
    name = CharField()                 # Display name (e.g., "Home Server")
    server_type = CharField()          # "rtorrent" or "transmission"
    host = CharField()                 # Host/IP address
    port = IntegerField()              # Port number
    username = CharField(null=True)    # Auth username (optional)
    password = CharField(null=True)    # Auth password (optional)
    rpc_path = CharField(null=True)    # RPC path for rTorrent (e.g., "/RPC2")
    enabled = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.datetime.now)
```

### Modify Existing Models

- Add `server_id` ForeignKey to `Torrent` model
- Add `server_id` ForeignKey to `UserTorrent` model
- Add `server_id` ForeignKey to `Status` model
- Add `server_id` ForeignKey to `Action` model

## Phase 2: Client Abstraction

### Create Base Client Interface (`base_client.py`)

Create abstract base class defining the common interface:

```python
from abc import ABC, abstractmethod

class BaseTorrentClient(ABC):
    @abstractmethod
    def list_torrents(self, info_hash=None, files=False): pass

    @abstractmethod
    def add_torrent(self, path, start=True): pass

    @abstractmethod
    def add_magnet(self, uri, start=True): pass

    @abstractmethod
    def add_torrent_url(self, url, start=True): pass

    @abstractmethod
    def start(self, info_hash): pass

    @abstractmethod
    def stop(self, info_hash): pass

    @abstractmethod
    def erase(self, info_hash): pass

    @abstractmethod
    def check_connection(self) -> bool: pass
```

### Update RTorrentClient and TransmissionClient

- Inherit from `BaseTorrentClient`
- Ensure consistent return types
- Accept connection params in `__init__` (not from config)

### Update Config

Add Transmission defaults to `config.py`:

```python
TRANSMISSION_HOST = os.getenv("TRANSMISSION_HOST", "localhost")
TRANSMISSION_PORT = int(os.getenv("TRANSMISSION_PORT", "9091"))
TRANSMISSION_USERNAME = os.getenv("TRANSMISSION_USERNAME", "")
TRANSMISSION_PASSWORD = os.getenv("TRANSMISSION_PASSWORD", "")
```

### Create Client Factory (`client_factory.py`)

```python
def get_client(server: TorrentServer) -> BaseTorrentClient:
    if server.server_type == "rtorrent":
        url = f"http://{server.host}:{server.port}{server.rpc_path or '/RPC2'}"
        return RTorrentClient(url=url)
    elif server.server_type == "transmission":
        return TransmissionClient(
            host=server.host,
            port=server.port,
            username=server.username,
            password=server.password
        )
    else:
        raise ValueError(f"Unknown server type: {server.server_type}")
```

## Phase 3: API Endpoints

### Server Management Endpoints (`api.py`)

```
POST   /servers              - Add new server
GET    /servers              - List user's servers
GET    /servers/{id}         - Get server details
PUT    /servers/{id}         - Update server
DELETE /servers/{id}         - Remove server
POST   /servers/{id}/test    - Test connection to server
```

### Request/Response Models

```python
class AddServerRequest(BaseModel):
    name: str
    server_type: str  # "rtorrent" or "transmission"
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    rpc_path: Optional[str] = None  # For rTorrent

class ServerResponse(BaseModel):
    id: str
    name: str
    server_type: str
    host: str
    port: int
    enabled: bool
    status: Optional[str]  # "connected", "error", etc.
```

### Modify Torrent Endpoints

```
GET  /torrents                    - List torrents from ALL servers (aggregated)
GET  /torrents?server_id=X        - List torrents from specific server
POST /torrents                    - Add torrent (requires server_id in body)
POST /torrents/upload             - Upload torrent (requires server_id param)
GET  /torrents/{hash}             - Get torrent (auto-detect server)
POST /torrents/{hash}/start       - Start torrent (auto-detect server)
POST /torrents/{hash}/stop        - Stop torrent (auto-detect server)
DELETE /torrents/{hash}           - Remove torrent (auto-detect server)
```

### Update AddTorrentRequest

```python
class AddTorrentRequest(BaseModel):
    uri: str
    server_id: str  # Required - which server to add to
    start: bool = True
```

### Torrent Response Changes

Each torrent response includes:
```python
{
    "info_hash": "...",
    "name": "...",
    "server_id": "abc123",
    "server_name": "Home Server",
    "server_type": "rtorrent",
    # ... other fields
}
```

## Phase 4: UI Changes

### Server Management Modal

Add new modal for managing servers:

```html
<!-- Servers Modal -->
<div class="modal fade" id="serversModal">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header">
                <h5>Torrent Servers</h5>
            </div>
            <div class="modal-body">
                <!-- Server list -->
                <div id="serversList"></div>

                <!-- Add server form -->
                <form id="addServerForm">
                    <select id="serverType">
                        <option value="rtorrent">rTorrent</option>
                        <option value="transmission">Transmission</option>
                    </select>
                    <!-- Host, port, name, credentials fields -->
                </form>
            </div>
        </div>
    </div>
</div>
```

### Navbar Updates

Add servers link to user dropdown menu:
```html
<li><a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#serversModal">
    <i class="fas fa-server me-2"></i> Servers
</a></li>
```

### Main View Updates

1. **Server Filter Dropdown** - Filter torrents by server
2. **Server Badge** - Show server name on each torrent card
3. **Status Indicators** - Show connection status per server in stats area

### Add Torrent Modal Updates

Add server selector:
```html
<div class="mb-3">
    <label>Add to Server</label>
    <select id="targetServer" class="form-select" required>
        <!-- Populated from API -->
    </select>
</div>
```

### JavaScript Updates (`app.js`)

New functions:
- `loadServers()` - Fetch and render server list
- `addServer(data)` - Add new server
- `updateServer(id, data)` - Update server
- `deleteServer(id)` - Remove server
- `testServerConnection(id)` - Test connectivity

Update existing functions:
- `loadTorrents()` - Group by server, handle multiple sources
- `addMagnet(uri)` - Include server_id
- `addUrl(uri)` - Include server_id
- `addTorrentFile(file)` - Include server_id
- `renderTorrentList()` - Show server badges

## Phase 5: Tests

### Add New Test Files

- `tests/test_servers.py` - Server CRUD API tests
- `tests/test_multi_server_torrents.py` - Multi-server torrent operations

### Test Coverage

1. Server CRUD operations
2. Connection testing (mock clients)
3. Adding torrents to specific servers
4. Listing torrents from multiple servers
5. Torrent operations route to correct server
6. User isolation (can't access other users' servers)

## Implementation Order

1. **models.py** - Add TorrentServer model and update tables
2. **base_client.py** - Create abstract base class
3. **config.py** - Add Transmission config defaults
4. **rtorrent_client.py** - Update to inherit from base, accept params
5. **transmission_client.py** - Update to inherit from base, fix config refs
6. **client_factory.py** - Create factory function
7. **api.py** - Add server endpoints, update torrent endpoints
8. **index.html** - Add servers modal, update add torrent modal
9. **app.js** - Add server management functions, update torrent functions
10. **style.css** - Add server-related styles
11. **tests/** - Add test coverage

## Notes

- Passwords stored in plain text for now (consider encryption later)
- Server connection tested on-demand, not continuously polled
- Torrents aggregated from all enabled servers on main view
- Server-specific errors shown per-server, don't break entire view
