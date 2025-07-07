from redislite import Redis
from peewee import SqliteDatabase

from .config import Config


SQLITE_DB_PATH = Config.SQLITE_DB_PATH
REDISLITE_DB_PATH = Config.REDISLITE_DB_PATH


sdb = SqliteDatabase(SQLITE_DB_PATH)
rdb = Redis(REDISLITE_DB_PATH)