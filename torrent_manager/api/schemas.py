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
