"""
Test for the seeding duration calculation fix.

This test verifies that calculate_seeding_duration correctly includes
the time from the last seeding record to now when the torrent is still seeding.
"""
import unittest
import datetime
import time

from torrent_manager.activity import Activity
from torrent_manager.models import Status
from torrent_manager.dbs import sdb as db


class TestSeedingDurationFix(unittest.TestCase):
    def setUp(self):
        db.connect(reuse_if_open=True)
        db.create_tables([Status], safe=True)
        self.activity = Activity()
        Status.delete().execute()

    def tearDown(self):
        self.activity.close()

    def test_seeding_duration_includes_current_time(self):
        """
        Test that seeding duration includes time from last record to now.

        This is the core fix: previously the calculation only counted time
        between records, missing the ongoing seeding time.
        """
        info_hash = "test_ongoing_seeding"

        # Create records showing continuous seeding over 5 minutes
        base_time = datetime.datetime.now() - datetime.timedelta(minutes=5)

        # Record seeding status every minute for 5 minutes
        for i in range(5):
            self.activity.record_torrent_status(
                info_hash,
                timestamp=base_time + datetime.timedelta(minutes=i)
            )

        # Calculate duration - should include time from last record (4 minutes ago) to now
        duration = self.activity.calculate_seeding_duration(info_hash)

        # Expected: 4 minutes between records + ~1 minute to now = ~5 minutes
        expected_min = 4 * 60  # At least 4 minutes (between records)
        expected_max = 5 * 60 + 10  # At most 5 minutes + some slack

        self.assertGreaterEqual(
            duration, expected_min,
            msg=f"Duration {duration}s should be at least {expected_min}s"
        )
        self.assertLessEqual(
            duration, expected_max,
            msg=f"Duration {duration}s should be at most {expected_max}s"
        )

    def test_seeding_duration_without_ongoing_seeding(self):
        """
        Test that stopped torrents don't include time to now.
        """
        info_hash = "test_stopped"

        # Create records showing seeding then stopping
        base_time = datetime.datetime.now() - datetime.timedelta(minutes=10)

        # Seed for 5 minutes
        for i in range(5):
            self.activity.record_torrent_status(
                info_hash,
                timestamp=base_time + datetime.timedelta(minutes=i),
                is_seeding=True
            )

        # Then stop
        self.activity.record_torrent_status(
            info_hash,
            timestamp=base_time + datetime.timedelta(minutes=5),
            is_seeding=False
        )

        # Calculate duration - should NOT include time after stopping
        duration = self.activity.calculate_seeding_duration(info_hash)

        # Expected: 4 minutes (time between 5 seeding records)
        expected = 4 * 60

        self.assertAlmostEqual(
            duration, expected, delta=5,
            msg=f"Duration {duration}s should be close to {expected}s"
        )

    def test_seeding_duration_realistic_scenario(self):
        """
        Test a realistic scenario matching the bug report.

        Simulates a torrent that has been seeding for ~46 minutes with
        status records every 60 seconds (idle polling interval).
        """
        info_hash = "realistic_test"

        # Simulate 46 minutes of seeding with 60-second polls
        minutes_seeding = 46
        poll_interval_seconds = 60

        base_time = datetime.datetime.now() - datetime.timedelta(minutes=minutes_seeding)

        # Create status records every 60 seconds
        num_records = minutes_seeding
        for i in range(num_records):
            self.activity.record_torrent_status(
                info_hash,
                timestamp=base_time + datetime.timedelta(seconds=i * poll_interval_seconds),
                is_seeding=True
            )

        # Calculate duration
        duration = self.activity.calculate_seeding_duration(info_hash, max_interval=300)

        # Expected: close to 46 minutes (2760 seconds)
        expected = minutes_seeding * 60

        # Should be within 2 minutes (120s) of expected
        self.assertAlmostEqual(
            duration, expected, delta=120,
            msg=f"Duration {duration}s should be close to {expected}s ({minutes_seeding} minutes)"
        )


if __name__ == '__main__':
    unittest.main()
