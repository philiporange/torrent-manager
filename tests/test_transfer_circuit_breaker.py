"""
Test transfer service respects polling service's circuit breaker.

Verifies that the transfer service skips deletion attempts when the polling
service has detected connection errors, preventing log flooding.
"""

import pytest
import time
from unittest.mock import Mock, patch
from peewee import SqliteDatabase
from torrent_manager.transfer import TransferService
from torrent_manager.models import TransferJob, TorrentServer
from torrent_manager.polling import ServerCache
from torrent_manager.auth import UserManager


@pytest.fixture(autouse=True)
def setup_test_db():
    """Setup test database before each test."""
    from torrent_manager import models as model_module

    test_db = SqliteDatabase(':memory:')
    models = [
        model_module.User,
        model_module.TorrentServer,
        model_module.RSSFeed,
        model_module.RSSFeedItem,
        model_module.TransferJob,
        model_module.ApiKey,
        model_module.UserTorrentSettings,
    ]

    test_db.bind(models)
    test_db.connect()
    test_db.create_tables(models)

    yield test_db

    test_db.drop_tables(models)
    test_db.close()


@pytest.fixture
def test_user():
    """Create a test user."""
    return UserManager.create_user("test_user", "password")


@pytest.fixture
def test_server(test_user):
    """Create a test torrent server."""
    return TorrentServer.create(
        id="test_server",
        user_id=test_user.id,
        name="Test Server",
        host="example.com",
        port=443,
        server_type="rtorrent",
        enabled=True,
        auto_download_enabled=True,
        auto_download_path="/downloads",
        auto_delete_remote=True
    )


@pytest.fixture
def test_job(test_server):
    """Create a test transfer job."""
    return TransferJob.create(
        id="test_job",
        user_id=test_server.user_id,
        server_id=test_server.id,
        torrent_hash="ABC123",
        torrent_name="Test Torrent",
        remote_path="/remote/path",
        local_path="/local/path",
        status="completed",
        auto_delete_after=True
    )


@pytest.mark.asyncio
async def test_delete_skipped_when_circuit_breaker_engaged(test_server, test_job):
    """Test that deletion is skipped when circuit breaker is engaged."""
    service = TransferService()

    # Mock the poller to return a cache with circuit breaker engaged
    mock_cache = ServerCache()
    mock_cache.skip_until = time.time() + 1800  # 30 minutes from now
    mock_cache.consecutive_errors = 2
    mock_cache.error = "Connection timeout"

    with patch('torrent_manager.polling.get_poller') as mock_get_poller:
        mock_poller = Mock()
        mock_poller._cache = {test_server.id: mock_cache}
        mock_get_poller.return_value = mock_poller

        # Attempt deletion
        result = await service._delete_remote(test_job, test_server)

        # Should return False (deferred) without attempting connection
        assert result is False
        assert test_job.remote_deleted is False


@pytest.mark.asyncio
async def test_delete_skipped_when_consecutive_errors_present(test_server, test_job):
    """Test that deletion proceeds when server has errors but circuit breaker not engaged."""
    service = TransferService()

    # Mock the poller to return a cache with 1 consecutive error (before circuit breaker)
    mock_cache = ServerCache()
    mock_cache.skip_until = 0.0  # Circuit breaker not engaged yet
    mock_cache.consecutive_errors = 1  # But has errors
    mock_cache.error = "Connection timeout"

    with patch('torrent_manager.polling.get_poller') as mock_get_poller, \
         patch('torrent_manager.client_factory.get_client') as mock_get_client:

        mock_poller = Mock()
        mock_poller._cache = {test_server.id: mock_cache}
        mock_get_poller.return_value = mock_poller

        # Mock client to raise "torrent not found" error (permanent error)
        mock_client = Mock()
        mock_client.get_torrent.return_value = iter([])  # Empty iterator (torrent not found)
        mock_get_client.return_value = mock_client

        # Attempt deletion
        result = await service._delete_remote(test_job, test_server)

        # Should proceed with deletion attempt since circuit breaker not engaged
        assert result is True
        # Reload from DB to check the saved state
        job_from_db = TransferJob.get_by_id(test_job.id)
        assert job_from_db.remote_deleted is True


@pytest.mark.asyncio
async def test_delete_proceeds_when_no_errors(test_server, test_job):
    """Test that deletion proceeds normally when server has no errors."""
    service = TransferService()

    # Mock the poller to return a cache with no errors
    mock_cache = ServerCache()
    mock_cache.skip_until = 0.0
    mock_cache.consecutive_errors = 0
    mock_cache.error = None

    with patch('torrent_manager.polling.get_poller') as mock_get_poller, \
         patch('torrent_manager.client_factory.get_client') as mock_get_client:

        mock_poller = Mock()
        mock_poller._cache = {test_server.id: mock_cache}
        mock_get_poller.return_value = mock_poller

        # Mock client to raise "torrent not found" error (permanent error)
        mock_client = Mock()
        mock_client.get_torrent.return_value = iter([])  # Empty iterator (torrent not found)
        mock_get_client.return_value = mock_client

        # Attempt deletion
        result = await service._delete_remote(test_job, test_server)

        # Should attempt deletion and mark as deleted (torrent already gone)
        assert result is True
        # Reload from DB to check the saved state
        job_from_db = TransferJob.get_by_id(test_job.id)
        assert job_from_db.remote_deleted is True


@pytest.mark.asyncio
async def test_delete_skipped_when_cache_is_none(test_server, test_job):
    """Test that deletion is skipped when poller hasn't cached the server yet."""
    service = TransferService()

    # Mock the poller to return empty cache (server not yet polled)
    with patch('torrent_manager.polling.get_poller') as mock_get_poller:
        mock_poller = Mock()
        mock_poller._cache = {}  # Empty cache - server not yet polled
        mock_get_poller.return_value = mock_poller

        # Attempt deletion
        result = await service._delete_remote(test_job, test_server)

        # Should return False (deferred) without attempting connection
        assert result is False
        assert test_job.remote_deleted is False


@pytest.mark.asyncio
async def test_process_pending_deletions_groups_by_server(test_server, test_user):
    """Test that process_pending_deletions groups jobs by server to check health once."""
    service = TransferService()

    # Create multiple jobs for the same server
    jobs = []
    for i in range(3):
        job = TransferJob.create(
            id=f"test_job_{i}",
            user_id=test_user.id,
            server_id=test_server.id,
            torrent_hash=f"HASH{i}",
            torrent_name=f"Test Torrent {i}",
            remote_path=f"/remote/path{i}",
            local_path=f"/local/path{i}",
            status="completed",
            auto_delete_after=True
        )
        jobs.append(job)

    # Mock the poller to return a cache with circuit breaker engaged
    mock_cache = ServerCache()
    mock_cache.skip_until = time.time() + 1800  # Circuit breaker engaged
    mock_cache.consecutive_errors = 1  # Server has errors
    mock_cache.error = "Connection timeout"

    with patch('torrent_manager.polling.get_poller') as mock_get_poller, \
         patch.object(service, '_delete_remote') as mock_delete:

        mock_poller = Mock()
        mock_poller._cache = {test_server.id: mock_cache}
        mock_get_poller.return_value = mock_poller

        # Process pending deletions
        await service.process_pending_deletions()

        # _delete_remote should NOT be called for any job because circuit breaker engaged
        assert mock_delete.call_count == 0


@pytest.mark.asyncio
async def test_process_pending_deletions_skips_unhealthy_server(test_server, test_user):
    """Test that process_pending_deletions skips all jobs when server circuit breaker engaged."""
    service = TransferService()

    # Create a second server
    server2 = TorrentServer.create(
        id="test_server_2",
        user_id=test_user.id,
        name="Test Server 2",
        host="example2.com",
        port=443,
        server_type="rtorrent",
        enabled=True,
        auto_download_enabled=True,
        auto_download_path="/downloads",
        auto_delete_remote=True
    )

    # Create jobs for both servers
    job1 = TransferJob.create(
        id="job1",
        user_id=test_user.id,
        server_id=test_server.id,
        torrent_hash="HASH1",
        torrent_name="Torrent 1",
        remote_path="/remote/path1",
        local_path="/local/path1",
        status="completed",
        auto_delete_after=True
    )

    job2 = TransferJob.create(
        id="job2",
        user_id=test_user.id,
        server_id=server2.id,
        torrent_hash="HASH2",
        torrent_name="Torrent 2",
        remote_path="/remote/path2",
        local_path="/local/path2",
        status="completed",
        auto_delete_after=True
    )

    # Server 1 has circuit breaker engaged, server 2 is healthy
    cache1 = ServerCache()
    cache1.skip_until = time.time() + 1800  # Circuit breaker engaged
    cache1.consecutive_errors = 1
    cache1.error = "Connection timeout"

    cache2 = ServerCache()
    cache2.skip_until = 0.0  # Circuit breaker not engaged
    cache2.consecutive_errors = 0
    cache2.error = None

    with patch('torrent_manager.polling.get_poller') as mock_get_poller, \
         patch.object(service, '_delete_remote') as mock_delete:

        mock_poller = Mock()
        mock_poller._cache = {test_server.id: cache1, server2.id: cache2}
        mock_get_poller.return_value = mock_poller

        # Process pending deletions
        await service.process_pending_deletions()

        # _delete_remote should only be called for job2 (server2's circuit breaker not engaged)
        assert mock_delete.call_count == 1
        mock_delete.assert_called_once_with(job2, server2)
