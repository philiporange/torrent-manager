"""
Database models for the torrent manager application.

Includes models for user authentication (User, Session, RememberMeToken, ApiKey),
torrent server configuration (TorrentServer with HTTP download support),
and torrent tracking (Torrent, Status, Action).
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
    created_at = DateTimeField(default=datetime.datetime.now)
    # HTTP download server configuration (nginx autoindex)
    http_host = CharField(null=True)  # HTTP server host (defaults to main host if not set)
    http_port = IntegerField(null=True)  # HTTP server port
    http_path = CharField(null=True)  # Base path on the HTTP server (e.g., "/downloads/")
    http_username = CharField(null=True)  # HTTP Basic Auth username
    http_password = CharField(null=True)  # HTTP Basic Auth password
    http_use_ssl = BooleanField(default=False)  # Use HTTPS for HTTP downloads

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
    timestamp = DateTimeField(default=datetime.datetime.now)


class Action(BaseModel):
    torrent_hash = CharField(index=True)
    server_id = CharField(index=True, null=True)
    action = CharField()  # e.g., 'add', 'stop', 'remove'
    timestamp = DateTimeField(default=datetime.datetime.now)


db.connect()
db.create_tables([User, Session, RememberMeToken, ApiKey, TorrentServer, UserTorrent, Torrent, Status, Action])