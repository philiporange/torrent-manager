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
    timestamp = DateTimeField(default=datetime.datetime.now)

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
    timestamp = DateTimeField(default=datetime.datetime.now)

class Torrent(BaseModel):
    torrent_hash = CharField(index=True)
    name = CharField()
    path = CharField()
    files = CharField()
    size = IntegerField()
    timestamp = DateTimeField(default=datetime.datetime.now)

class Status(BaseModel):
    torrent_hash = CharField(index=True)
    status = CharField()  # e.g., 'downloading', 'seeding', 'stopped'
    progress = FloatField()  # 0.0 to 1.0
    seeders = IntegerField()
    leechers = IntegerField()
    down_rate = IntegerField()
    up_rate = IntegerField()
    timestamp = DateTimeField(default=datetime.datetime.now)

class Action(BaseModel):
    torrent_hash = CharField(index=True)
    action = CharField()  # e.g., 'add', 'stop', 'remove'
    timestamp = DateTimeField(default=datetime.datetime.now)


db.connect()
db.create_tables([User, Session, RememberMeToken, ApiKey, UserTorrent, Torrent, Status, Action])