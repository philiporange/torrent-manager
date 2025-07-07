import datetime
from peewee import fn

from .models import Status
from .config import Config
from .dbs import sdb as db


class Activity:
    def __init__(self, db_path=Config.DB_PATH):
        self.db_path = db_path
        self.db = db
        if not self.db.is_closed():
            self.db.close()
        self.db.init(self.db_path)
        self.db.connect()

    def record_torrent_status(self, info_hash, is_seeding=True, timestamp=None):
        if timestamp is None:
            timestamp = datetime.datetime.now()
        Status.create(
            torrent_hash=info_hash,
            status='seeding' if is_seeding else 'stopped',
            progress=1.0 if is_seeding else 0.0,
            seeders=0,
            leechers=0,
            down_rate=0,
            up_rate=0,
            timestamp=timestamp,
        )

    def calculate_seeding_duration(self, info_hash, max_interval=300):
        logs = (Status
                .select()
                .where(Status.torrent_hash == info_hash)
                .order_by(Status.timestamp))

        seeding_duration = 0
        last_seeding_time = None

        for log in logs:
            if log.status == 'seeding':
                if last_seeding_time is not None:
                    time_since_last_seeding = (log.timestamp - last_seeding_time).total_seconds()
                    if time_since_last_seeding < max_interval:
                        seeding_duration += time_since_last_seeding

                last_seeding_time = log.timestamp
            else:
                last_seeding_time = None

        return seeding_duration

    def get_never_seeded_torrents(self):
        subquery = (Status
                    .select(Status.torrent_hash)
                    .where(Status.status != 'seeding')
                    .group_by(Status.torrent_hash)
                    .having(fn.COUNT(fn.DISTINCT(Status.status)) == 1))
        
        return [status.torrent_hash for status in subquery]

    def remove_old_status_records(self, days_to_keep=30):
        cutoff_time = datetime.datetime.now() - datetime.timedelta(days=days_to_keep)
        Status.delete().where(Status.timestamp < cutoff_time).execute()

    def delete_torrent_status_history(self, info_hash):
        Status.delete().where(Status.torrent_hash == info_hash).execute()

    def close(self):
        if not self.db.is_closed():
            self.db.close()