This document provides usage instructions and examples for the `torrent_manager` project, focusing on its core functionalities: managing torrent clients, handling authentication, and interacting with the REST API.

The primary way to interact with the project programmatically is through the `TorrentManagerClient` class, which wraps the FastAPI REST API.

## Torrent Manager Client (`torrent_manager.client.TorrentManagerClient`)

The `TorrentManagerClient` class provides a Python interface to the Torrent Manager REST API, supporting both session-based and API key authentication.

### Initialization

To begin, instantiate the client, optionally providing the `base_url` and an `api_key`.

```python
from torrent_manager.client import TorrentManagerClient

# Initialize client using default URL (http://localhost:8144)
client = TorrentManagerClient()

# Initialize client with an API key for programmatic access
API_KEY = "tm_your_api_key_here"
client_with_key = TorrentManagerClient(api_key=API_KEY)
```

### Authentication Methods

The client supports session-based login (for interactive use) and API key authentication (for scripts).

#### Registering a New User

- Use the `register` method to create a new user account.

```python
# client.register(username, password)
try:
    result = client.register("newuser", "securepassword")
    print(f"User registered: {result['username']} ({result['user_id']})")
except Exception as e:
    print(f"Registration failed: {e}")
```

#### Logging In

- Use the `login` method to establish a session. This is required before creating API keys or managing servers via session authentication.

```python
# client.login(username, password, remember_me=False)
try:
    result = client.login("newuser", "securepassword", remember_me=True)
    print(f"Logged in as: {result['username']}")
except Exception as e:
    print(f"Login failed: {e}")
```

#### Getting Current User Information

- The `get_me` method returns details about the currently authenticated user and the authentication method used.

```python
# client.get_me()
try:
    user_info = client.get_me()
    print(f"Current User: {user_info['username']}, Auth Method: {user_info['auth_method']}")
except Exception as e:
    print(f"Authentication required: {e}")
```

#### Logging Out

- The `logout` method terminates the current session.

```python
# client.logout()
try:
    result = client.logout()
    print(result['message'])
except Exception as e:
    print(f"Logout failed: {e}")
```

### API Key Management

API keys are the preferred method for non-interactive, programmatic access.

#### Creating an API Key

- Requires prior session authentication. The full key is returned only once.

```python
# client.create_api_key(name, expires_days=None)
try:
    # Assuming client is logged in
    key_result = client.create_api_key("My Automation Script", expires_days=90)
    print(f"New API Key created: {key_result['api_key']}")
    # Store this key securely!
except Exception as e:
    print(f"Failed to create API key: {e}")
```

#### Listing API Keys

- Lists all API keys associated with the current user (key values are masked).

```python
# client.list_api_keys()
try:
    keys_list = client.list_api_keys()
    print("Existing API Keys:")
    for key in keys_list['api_keys']:
        print(f"  - {key['name']} (Prefix: {key['prefix']})")
except Exception as e:
    print(f"Failed to list API keys: {e}")
```

#### Revoking an API Key

- Revokes a key using its prefix (first 8 characters).

```python
# client.revoke_api_key(key_prefix)
try:
    # Assuming 'abc12345' is the prefix of a key
    revoke_result = client.revoke_api_key("abc12345")
    print(revoke_result['message'])
except Exception as e:
    print(f"Failed to revoke API key: {e}")
```

### Server Management

The client allows configuration of multiple torrent servers (rTorrent or Transmission).

#### Adding a Server

- Use `add_server` to configure a new torrent client instance.

```python
# client.add_server(name, server_type, host, port, ...)
try:
    server_config = client.add_server(
        name="My rTorrent Seedbox",
        server_type="rtorrent",
        host="192.168.1.10",
        port=8080,
        rpc_path="/RPC2",
        username="rpc_user",
        password="rpc_password"
    )
    SERVER_ID = server_config['id']
    print(f"Server added with ID: {SERVER_ID}")
except Exception as e:
    print(f"Failed to add server: {e}")
```

#### Listing Servers

- Retrieves a list of all configured servers for the authenticated user.

```python
# client.list_servers()
try:
    servers_list = client.list_servers()
    print("Configured Servers:")
    for s in servers_list:
        print(f"  - {s['name']} ({s['server_type']}) - ID: {s['id']}")
except Exception as e:
    print(f"Failed to list servers: {e}")
```

#### Testing Server Connection

- Verifies connectivity to a configured server.

```python
# client.test_server(server_id)
try:
    # Assuming SERVER_ID is defined from the previous example
    test_result = client.test_server(SERVER_ID)
    print(f"Connection status: {test_result['status']} - {test_result['message']}")
except Exception as e:
    print(f"Failed to test server: {e}")
```

#### Updating a Server

- Modifies an existing server configuration. Only provided fields are updated.

```python
# client.update_server(server_id, name=None, enabled=None, ...)
try:
    updated_server = client.update_server(
        server_id=SERVER_ID,
        name="Renamed rTorrent Seedbox",
        enabled=False
    )
    print(f"Server updated: {updated_server['name']}, Enabled: {updated_server['enabled']}")
except Exception as e:
    print(f"Failed to update server: {e}")
```

#### Deleting a Server

- Removes a server configuration from the manager.

```python
# client.delete_server(server_id)
try:
    delete_result = client.delete_server(SERVER_ID)
    print(delete_result['message'])
except Exception as e:
    print(f"Failed to delete server: {e}")
```

### Torrent Operations

These methods allow interaction with torrents on the configured servers.

#### Listing Torrents

- Retrieves a list of all torrents across all configured and enabled servers.

```python
# client.list_torrents(server_id=None)
try:
    all_torrents = client.list_torrents()
    print(f"Found {len(all_torrents)} torrents.")
    for t in all_torrents[:2]:
        print(f"  - {t['name']} ({t['progress']:.1f}%) on {t['server_name']}")
except Exception as e:
    print(f"Failed to list torrents: {e}")
```

#### Adding a Torrent (Magnet URI or URL)

- Adds a torrent using a magnet link, info hash, or a URL pointing to a `.torrent` file.

```python
# client.add_torrent(uri, server_id, start=True)
MAGNET_URI = "magnet:?xt=urn:btih:ABC123DEF456..."
try:
    add_result = client.add_torrent(
        uri=MAGNET_URI,
        server_id=SERVER_ID,
        start=True
    )
    print(add_result['message'])
except Exception as e:
    print(f"Failed to add torrent: {e}")
```

#### Uploading a Torrent File

- Uploads a local `.torrent` file to the server.

```python
# client.upload_torrent(file_path, server_id, start=True)
# Note: This requires a valid local .torrent file path
try:
    # Create a dummy file for demonstration (replace with actual file)
    with open("test.torrent", "w") as f:
        f.write("d8:announce