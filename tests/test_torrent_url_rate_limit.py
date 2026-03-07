"""Tests for rate limiting remote torrent file downloads."""

from unittest.mock import patch

from torrent_manager.utils import rate_limited_get, _download_last_request_by_host


class DummyResponse:
    def raise_for_status(self):
        return None


def test_rate_limited_get_waits_between_requests_to_same_host():
    _download_last_request_by_host.clear()
    monotonic_values = iter([0.0, 1.0, 5.2])
    sleeps = []

    def fake_monotonic():
        return next(monotonic_values)

    def fake_sleep(seconds):
        sleeps.append(seconds)

    with patch('torrent_manager.utils.time.monotonic', side_effect=fake_monotonic), \
         patch('torrent_manager.utils.time.sleep', side_effect=fake_sleep), \
         patch('torrent_manager.utils.requests.get', return_value=DummyResponse()) as mock_get:
        rate_limited_get('https://example.com/file1.torrent', min_interval_seconds=5)
        rate_limited_get('https://example.com/file2.torrent', min_interval_seconds=5)

    assert len(sleeps) == 1
    assert round(sleeps[0], 2) == 4.0
    assert mock_get.call_count == 2


def test_rate_limited_get_does_not_wait_for_different_hosts():
    _download_last_request_by_host.clear()
    with patch('torrent_manager.utils.time.sleep') as mock_sleep, \
         patch('torrent_manager.utils.requests.get', return_value=DummyResponse()) as mock_get:
        rate_limited_get('https://a.example/file.torrent', min_interval_seconds=5)
        rate_limited_get('https://b.example/file.torrent', min_interval_seconds=5)

    mock_sleep.assert_not_called()
    assert mock_get.call_count == 2
