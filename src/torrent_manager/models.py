import datetime
from peewee import Model, CharField, DateTimeField, IntegerField, FloatField
from .dbs import sdb as db


class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    id = CharField(primary_key=True)
    username = CharField(index=True)
    password = CharField()
    email = CharField()
    timestamp = DateTimeField(default=datetime.datetime.now)

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
db.create_tables([User, Torrent, Status, Action])