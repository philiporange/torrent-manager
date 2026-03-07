"""
Database models for the torrent manager application.

Includes models for user authentication (User, Session, RememberMeToken, ApiKey),
torrent server configuration (TorrentServer with HTTP download, local mount, and
auto-download via rsync over SSH), torrent tracking (Torrent, Status, Action),
file transfer management (TransferJob, UserTorrentSettings), automatic metadata
identification (TorrentMetadata), and RSS feed automation (RSSFeed, RSSFeedItem).
"""

import datetime
from peewee import Model, CharField, DateTimeField, IntegerField, FloatField, BooleanField
from .dbs import sdb as db


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    id = CharField(primary_key=True)
    username = CharField(index=True, unique=True)
    password = CharField()
    is_admin = BooleanField(default=False)
    timestamp = DateTimeField(default=datetime.datetime.now)


class TorrentServer(BaseModel):
    """
    Configuration for a remote torrent server (rTorrent or Transmission).
    Each user can have multiple servers configured.

    HTTP download fields (http_*) configure access to an nginx server serving
    the torrent downloads directory, enabling file browsing and download through
    the API proxy.

    mount_path optionally specifies a local sshfs-mounted directory path that
    maps to the server's download directory. When set, file serving will prefer
    the local mount for faster access before falling back to HTTP proxy.

    Auto-download fields configure automatic transfer of completed torrents
    to local storage via rsync over SSH.
    """
    id = CharField(primary_key=True)
    user_id = CharField(index=True)
    name = CharField()
    server_type = CharField()  # "rtorrent" or "transmission"
    host = CharField()
    port = IntegerField()
    username = CharField(null=True)
    password = CharField(null=True)
    rpc_path = CharField(null=True)  # For rTorrent (e.g., "/RPC2")
    use_ssl = BooleanField(default=False)  # Use HTTPS instead of HTTP
    enabled = BooleanField(default=True)
    is_default = BooleanField(default=False)  # Default server for adding torrents
    created_at = DateTimeField(default=datetime.datetime.now)
    # HTTP download server configuration (nginx autoindex)
    http_host = CharField(null=True)  # HTTP server host (defaults to main host if not set)
    http_port = IntegerField(null=True)  # HTTP server port
    http_path = CharField(null=True)  # Base path on the HTTP server (e.g., "/downloads/")
    http_username = CharField(null=True)  # HTTP Basic Auth username
    http_password = CharField(null=True)  # HTTP Basic Auth password
    http_use_ssl = BooleanField(default=False)  # Use HTTPS for HTTP downloads
    # Local mount path for sshfs-mounted directory (for direct file access)
    mount_path = CharField(null=True)
    # Download directory on the server (e.g., "/home/user/downloads/")
    # Used to compute relative paths for HTTP downloads
    download_dir = CharField(null=True)
    # Auto-download configuration (rsync over SSH)
    auto_download_enabled = BooleanField(default=False)
    auto_download_path = CharField(null=True)  # Local destination path
    auto_delete_remote = BooleanField(default=False)  # Delete remote after transfer
    # SSH configuration for rsync transfers
    ssh_host = CharField(null=True)  # SSH host (defaults to main host if not set)
    ssh_port = IntegerField(default=22)
    ssh_user = CharField(null=True)  # SSH username
    ssh_key_path = CharField(null=True)  # Path to SSH private key


class Session(BaseModel):
    """
    Stores user session data with sliding expiration.
    Sessions are reissued on each meaningful request to provide sliding window authentication.
    """
    session_id = CharField(primary_key=True, max_length=64)
    user_id = CharField(index=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    last_activity = DateTimeField(default=datetime.datetime.now)
    expires_at = DateTimeField()
    ip_address = CharField(null=True)
    user_agent = CharField(null=True)


class RememberMeToken(BaseModel):
    """
    Stores remember-me tokens for longer-lived authentication.
    These tokens can mint new sessions when the session expires.
    """
    token_id = CharField(primary_key=True, max_length=64)
    user_id = CharField(index=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    expires_at = DateTimeField()
    ip_address = CharField(null=True)
    user_agent = CharField(null=True)
    revoked = BooleanField(default=False)


class ApiKey(BaseModel):
    """
    Stores API keys for programmatic authentication.
    API keys are an alternative to session-based authentication for scripts and automation.
    """
    api_key = CharField(primary_key=True, max_length=64)
    user_id = CharField(index=True)
    name = CharField()  # User-provided name to identify the key
    created_at = DateTimeField(default=datetime.datetime.now)
    last_used_at = DateTimeField(null=True)
    expires_at = DateTimeField(null=True)  # Optional expiration
    revoked = BooleanField(default=False)


class UserTorrent(BaseModel):
    user = CharField(index=True)
    torrent_hash = CharField(index=True)
    server_id = CharField(index=True, null=True)
    timestamp = DateTimeField(default=datetime.datetime.now)


class Torrent(BaseModel):
    torrent_hash = CharField(index=True)
    server_id = CharField(index=True, null=True)
    name = CharField()
    path = CharField()
    files = CharField()
    size = IntegerField()
    is_private = BooleanField(default=False)
    timestamp = DateTimeField(default=datetime.datetime.now)


class Status(BaseModel):
    torrent_hash = CharField(index=True)
    server_id = CharField(index=True, null=True)
    status = CharField()  # e.g., 'downloading', 'seeding', 'stopped'
    progress = FloatField()  # 0.0 to 1.0
    seeders = IntegerField()
    leechers = IntegerField()
    down_rate = IntegerField()
    up_rate = IntegerField()
    is_private = BooleanField(default=False)
    timestamp = DateTimeField(default=datetime.datetime.now)


class Action(BaseModel):
    torrent_hash = CharField(index=True)
    server_id = CharField(index=True, null=True)
    action = CharField()  # e.g., 'add', 'stop', 'remove'
    timestamp = DateTimeField(default=datetime.datetime.now)


class TransferJob(BaseModel):
    """
    Tracks file transfer jobs from remote torrent servers to local storage.

    Uses rsync over SSH for robust, resumable transfers. Jobs are queued when
    torrents complete and processed by the TransferService background task.

    States:
    - pending: Queued, waiting to start
    - running: rsync in progress
    - completed: Transfer finished successfully
    - failed: Transfer failed after max retries (see error field)
    - cancelled: User cancelled the transfer
    """
    id = CharField(primary_key=True)
    user_id = CharField(index=True)
    server_id = CharField(index=True)
    torrent_hash = CharField(index=True)
    torrent_name = CharField()
    # Source and destination paths
    remote_path = CharField()
    local_path = CharField()
    # Status tracking
    status = CharField(default="pending")  # pending, running, completed, failed, cancelled
    progress_bytes = IntegerField(default=0)
    total_bytes = IntegerField(default=0)
    progress_percent = FloatField(default=0.0)
    # Timing
    created_at = DateTimeField(default=datetime.datetime.now)
    started_at = DateTimeField(null=True)
    completed_at = DateTimeField(null=True)
    # Error handling
    error = CharField(null=True)
    retry_count = IntegerField(default=0)
    max_retries = IntegerField(default=3)
    # Flags
    auto_delete_after = BooleanField(default=False)
    remote_deleted = BooleanField(default=False)  # True after remote deletion completes
    triggered_by = CharField(default="auto")  # "auto" or "manual"


class UserTorrentSettings(BaseModel):
    """
    Per-torrent settings for overriding server defaults.

    Created when user configures custom download location or auto-download
    behavior for a specific torrent. Null values mean inherit from server.
    """
    user_id = CharField(index=True)
    server_id = CharField(index=True)
    torrent_hash = CharField(index=True)
    # Override settings (null = use server default)
    download_path = CharField(null=True)
    auto_download = BooleanField(null=True)
    auto_delete_remote = BooleanField(null=True)

    class Meta:
        indexes = (
            (("user_id", "server_id", "torrent_hash"), True),
        )


class TorrentMetadata(BaseModel):
    """
    Tracks media identification and metadata for torrents.

    Stores identification results from torrent_match and metadata from
    media_metadata. Links to stored files in <info_hash>/metadata/ directory.

    Status values:
    - pending: Queued for identification
    - processing: Currently being identified
    - completed: Successfully identified and metadata written
    - failed: Identification failed (see error field)
    - low_confidence: Identified but confidence too low for auto-write
    - manual: Manually set by user
    """
    torrent_hash = CharField(index=True)
    server_id = CharField(index=True)
    media_id = CharField(null=True)
    media_type = CharField(null=True)
    title = CharField(null=True)
    year = IntegerField(null=True)
    imdb_id = CharField(null=True)
    tmdb_id = IntegerField(null=True)
    confidence = FloatField(null=True)
    confidence_level = CharField(null=True)
    status = CharField(default="pending")
    error = CharField(null=True)
    identified_at = DateTimeField(null=True)
    metadata_written_at = DateTimeField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        indexes = (
            (("torrent_hash", "server_id"), True),
        )


class RSSFeed(BaseModel):
    """
    Stores RSS feed configuration for automatic torrent ingestion.

    Each feed belongs to a user, targets a specific torrent server, and applies
    a configurable delay before newly detected items are added to the client.
    Background polling updates status fields for monitoring in the API and UI.
    """
    id = CharField(primary_key=True)
    user_id = CharField(index=True)
    server_id = CharField(index=True)
    name = CharField()
    url = CharField()
    delay_hours = IntegerField(default=0)
    enabled = BooleanField(default=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    last_checked_at = DateTimeField(null=True)
    last_success_at = DateTimeField(null=True)
    last_error = CharField(null=True)
    last_item_count = IntegerField(default=0)


class RSSFeedItem(BaseModel):
    """
    Tracks RSS-discovered torrents and their add lifecycle.

    Items are deduplicated per user by fingerprint so the same torrent entry is
    only scheduled once even if multiple feeds surface it. Pending items wait
    until next_attempt_at, which implements the per-feed delay before add.
    """
    id = CharField(primary_key=True)
    feed_id = CharField(index=True)
    user_id = CharField(index=True)
    server_id = CharField(index=True)
    title = CharField()
    guid = CharField(null=True)
    link = CharField(null=True)
    uri = CharField()
    fingerprint = CharField(index=True)
    info_hash = CharField(null=True, index=True)
    status = CharField(default="pending")  # pending, added, skipped
    detected_at = DateTimeField(default=datetime.datetime.now)
    next_attempt_at = DateTimeField(index=True)
    added_at = DateTimeField(null=True)
    last_error = CharField(null=True)
    attempt_count = IntegerField(default=0)

    class Meta:
        indexes = (
            (("user_id", "fingerprint"), True),
        )


db.connect(reuse_if_open=True)
db.create_tables(
    [
        User,
        Session,
        RememberMeToken,
        ApiKey,
        TorrentServer,
        UserTorrent,
        Torrent,
        Status,
        Action,
        TransferJob,
        UserTorrentSettings,
        TorrentMetadata,
        RSSFeed,
        RSSFeedItem,
    ],
    safe=True,
)
