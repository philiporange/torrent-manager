"""
Database connection configuration for SQLite and Redis.

Configures SQLite with Write-Ahead Logging (WAL) mode to enable concurrent
reads and writes from multiple async tasks without database locking errors.
The WAL mode allows readers and writers to operate concurrently, which is
essential for applications with background asyncio tasks that write to the
database simultaneously (transfer service, metadata service, seeding monitor).

WAL pragmas configured:
- journal_mode=wal: Enable Write-Ahead Logging for concurrent access
- synchronous=normal: Balance between safety and performance
- busy_timeout=30000: Wait up to 30 seconds for locks to clear
- cache_size=-64000: Use 64MB page cache for better performance
"""
from redislite import Redis
from peewee import SqliteDatabase

from .config import Config


SQLITE_DB_PATH = Config.SQLITE_DB_PATH
REDISLITE_DB_PATH = Config.REDISLITE_DB_PATH


sdb = SqliteDatabase(
    SQLITE_DB_PATH,
    pragmas={
        'journal_mode': 'wal',
        'synchronous': 'normal',
        'cache_size': -64000,
        'foreign_keys': 1,
        'ignore_check_constraints': 0,
        'busy_timeout': 30000,
    },
    timeout=30
)
rdb = Redis(REDISLITE_DB_PATH)