from typing import List, Optional
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str
    remember_me: bool = False


class RegisterRequest(BaseModel):
    username: str
    password: str


class CreateApiKeyRequest(BaseModel):
    name: str
    expires_days: Optional[int] = None  # Optional expiration in days


class AddTorrentRequest(BaseModel):
    uri: str  # Magnet URI or HTTP/HTTPS URL to torrent file
    server_id: str  # Which server to add the torrent to
    start: bool = True
    labels: Optional[List[str]] = None  # Labels to apply after adding


class TorrentActionRequest(BaseModel):
    info_hash: str


class AddServerRequest(BaseModel):
    name: str
    server_type: str  # "rtorrent" or "transmission"
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    rpc_path: Optional[str] = None  # For rTorrent (e.g., "/RPC2")
    use_ssl: bool = False
    is_default: bool = False
    # HTTP download server configuration
    http_host: Optional[str] = None
    http_port: Optional[int] = None
    http_path: Optional[str] = None
    http_username: Optional[str] = None
    http_password: Optional[str] = None
    http_use_ssl: bool = False
    # Local mount path for sshfs-mounted directory
    mount_path: Optional[str] = None
    # Download directory on the server (for computing relative paths)
    download_dir: Optional[str] = None
    # Auto-download configuration (rsync over SSH)
    auto_download_enabled: bool = False
    auto_download_path: Optional[str] = None
    auto_delete_remote: bool = False
    # SSH configuration for rsync transfers
    ssh_host: Optional[str] = None
    ssh_port: int = 22
    ssh_user: Optional[str] = None
    ssh_key_path: Optional[str] = None


class UpdateServerRequest(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    rpc_path: Optional[str] = None
    use_ssl: Optional[bool] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    # HTTP download server configuration
    http_host: Optional[str] = None
    http_port: Optional[int] = None
    http_path: Optional[str] = None
    http_username: Optional[str] = None
    http_password: Optional[str] = None
    http_use_ssl: Optional[bool] = None
    # Local mount path for sshfs-mounted directory
    mount_path: Optional[str] = None
    # Download directory on the server (for computing relative paths)
    download_dir: Optional[str] = None
    # Auto-download configuration (rsync over SSH)
    auto_download_enabled: Optional[bool] = None
    auto_download_path: Optional[str] = None
    auto_delete_remote: Optional[bool] = None
    # SSH configuration for rsync transfers
    ssh_host: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_user: Optional[str] = None
    ssh_key_path: Optional[str] = None


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class UpdateUserRequest(BaseModel):
    password: Optional[str] = None
    is_admin: Optional[bool] = None


class SetLabelsRequest(BaseModel):
    labels: List[str]


class AddLabelRequest(BaseModel):
    label: str


class StartTransferRequest(BaseModel):
    """Request to manually start a file transfer for a completed torrent."""
    torrent_hash: str
    server_id: str
    download_path: Optional[str] = None  # Override destination path


class UpdateTorrentSettingsRequest(BaseModel):
    """Request to update per-torrent download settings."""
    download_path: Optional[str] = None
    auto_download: Optional[bool] = None
    auto_delete_remote: Optional[bool] = None
