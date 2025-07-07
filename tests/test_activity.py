import unittest
import tempfile
import os
import datetime
import time

from src.torrent_manager.activity import Activity
from src.torrent_manager.models import Status
from src.torrent_manager.dbs import sdb as db


class TestActivity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_db = tempfile.NamedTemporaryFile(delete=False)
        cls.temp_db.close()
        db.init(cls.temp_db.name)
        db.connect()
        db.create_tables([Status])
        db.close()

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.temp_db.name)

    def setUp(self):
        self.activity = Activity(self.temp_db.name)
        Status.delete().execute()  # Clear the database before each test

    def tearDown(self):
        self.activity.close()

    def test_record_torrent_status(self):
        info_hash = "test_hash"
        self.activity.record_torrent_status(info_hash)
        
        status = Status.select().where(Status.torrent_hash == info_hash).get()
        
        self.assertIsNotNone(status)
        self.assertEqual(status.torrent_hash, info_hash)
        self.assertEqual(status.status, 'seeding')
        self.assertEqual(status.progress, 1.0)

    def test_calculate_seeding_duration(self):
        info_hash = "test_hash"
        start_time = datetime.datetime.now() - datetime.timedelta(hours=2)
        
        # Record seeding at different times
        for i in range(61):
            self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=i))

        duration = self.activity.calculate_seeding_duration(info_hash)
        
        expected_duration = 60 * 60  # 60 minutes * 60 seconds
        self.assertAlmostEqual(duration, expected_duration, delta=5)

    def test_calculate_seeding_duration_with_gaps(self):
        info_hash = "test_hash"
        start_time = datetime.datetime.now() - datetime.timedelta(minutes=35)
        
        # Record seeding with gaps
        self.activity.record_torrent_status(info_hash, timestamp=start_time)
        self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=1))
        self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=2))
        # Gap
        self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=32))
        self.activity.record_torrent_status(info_hash, timestamp=start_time + datetime.timedelta(minutes=33))
                
        duration = self.activity.calculate_seeding_duration(info_hash)
        expected_duration = 3 * 60  # 3 minutes * 60 seconds
        self.assertAlmostEqual(duration, expected_duration, delta=5)

    def test_get_never_seeded_torrents(self):
        self.activity.record_torrent_status("seeded_hash", is_seeding=True)
        self.activity.record_torrent_status("never_seeded_hash1", is_seeding=False)
        self.activity.record_torrent_status("never_seeded_hash2", is_seeding=False)
        
        never_seeded = self.activity.get_never_seeded_torrents()
        
        self.assertEqual(set(never_seeded), {"never_seeded_hash1", "never_seeded_hash2"})
        self.assertNotIn("seeded_hash", never_seeded)

    def test_remove_old_status_records(self):
        current_time = datetime.datetime.now()
        old_time = current_time - datetime.timedelta(days=31)
        
        self.activity.record_torrent_status("old_hash", timestamp=old_time)
        self.activity.record_torrent_status("new_hash", timestamp=current_time)
        
        self.activity.remove_old_status_records(days_to_keep=30)
        
        statuses = list(Status.select())
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].torrent_hash, "new_hash")

    def test_delete_torrent_status_history(self):
        info_hash = "test_hash"
        self.activity.record_torrent_status(info_hash)
        self.activity.record_torrent_status(info_hash)
        self.activity.record_torrent_status("other_hash")
        
        self.activity.delete_torrent_status_history(info_hash)
        
        statuses = list(Status.select())
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].torrent_hash, "other_hash")


if __name__ == '__main__':
    unittest.main()