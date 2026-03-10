"""Tests for RSS feed management and delayed torrent ingestion."""

import os
import datetime
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from peewee import SqliteDatabase

os.environ["COOKIE_SECURE"] = "false"

from torrent_manager.api import app
from torrent_manager.auth import UserManager
from torrent_manager.config import Config
from torrent_manager.models import RSSFeed, RSSFeedItem, RememberMeToken, Session, TorrentServer, User
from torrent_manager.rss import RSSService


@pytest.fixture(autouse=True)
def setup_test_db():
    """Bind RSS tests to an isolated in-memory database."""
    from torrent_manager import models as model_module

    test_db = SqliteDatabase(':memory:')
    models_list = [User, Session, RememberMeToken, TorrentServer, RSSFeed, RSSFeedItem]
    test_db.bind(models_list, bind_refs=False, bind_backrefs=False)

    old_db = model_module.db
    model_module.db._state.closed = True
    for model in models_list:
        model._meta.database = test_db

    test_db.connect()
    test_db.create_tables(models_list)

    yield

    test_db.drop_tables(models_list)
    test_db.close()

    for model in models_list:
        model._meta.database = old_db


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as ac:
        yield ac


@pytest.fixture
def test_user():
    return UserManager.create_user(username='rssuser', password='secret')


@pytest_asyncio.fixture
async def authenticated_client(async_client, test_user):
    await async_client.post('/auth/login', json={
        'username': 'rssuser',
        'password': 'secret',
        'remember_me': False,
    })
    return async_client


@pytest_asyncio.fixture
async def rss_server(authenticated_client):
    response = await authenticated_client.post('/servers', json={
        'name': 'RSS Server',
        'server_type': 'transmission',
        'host': 'localhost',
        'port': 9091,
    })
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_rss_feed_crud(authenticated_client, rss_server):
    response = await authenticated_client.post('/rss/feeds', json={
        'name': 'Daily Feed',
        'url': 'https://example.com/feed.xml',
        'server_id': rss_server['id'],
        'delay_hours': 6,
        'enabled': True,
    })
    assert response.status_code == 200
    feed = response.json()
    assert feed['name'] == 'Daily Feed'
    assert feed['delay_hours'] == 6
    assert feed['server_id'] == rss_server['id']

    listing = await authenticated_client.get('/rss/feeds')
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    updated = await authenticated_client.put(f"/rss/feeds/{feed['id']}", json={
        'delay_hours': 1,
        'enabled': False,
    })
    assert updated.status_code == 200
    assert updated.json()['delay_hours'] == 1
    assert updated.json()['enabled'] is False


@pytest.mark.asyncio
async def test_rss_service_delays_and_deduplicates_items(test_user):
    server = TorrentServer.create(
        id='server1',
        user_id=test_user.id,
        name='RSS Server',
        server_type='transmission',
        host='localhost',
        port=9091,
    )
    feed = RSSFeed.create(
        id='feed1',
        user_id=test_user.id,
        server_id=server.id,
        name='Feed',
        url='https://example.com/rss.xml',
        delay_hours=2,
        enabled=True,
    )

    xml = '''<?xml version="1.0"?>
    <rss version="2.0">
      <channel>
        <title>Example</title>
        <item>
          <title>Episode 1</title>
          <guid>episode-1</guid>
          <link>magnet:?xt=urn:btih:ABCDEF0123456789ABCDEF0123456789ABCDEF01</link>
        </item>
      </channel>
    </rss>'''

    service = RSSService()

    async def fake_fetch(_url):
        return xml

    added_uris = []

    async def fake_add(server_obj, uri, **kwargs):
        added_uris.append((server_obj.id, uri, kwargs.get('user_id')))
        return {'uri': uri}

    with patch.object(service, '_fetch_feed_content', side_effect=fake_fetch), patch('torrent_manager.rss.add_torrent_to_server', side_effect=fake_add):
        created = await service.refresh_feed(feed)
        assert created == 1
        assert RSSFeedItem.select().count() == 1

        await service.process_pending_items()
        assert added_uris == []

        item = RSSFeedItem.get()
        item.next_attempt_at = datetime.datetime.now() - datetime.timedelta(minutes=1)
        item.save()

        await service.process_pending_items()
        assert len(added_uris) == 1
        item = RSSFeedItem.get_by_id(item.id)
        assert item.status == 'added'

        created_again = await service.refresh_feed(feed)
        assert created_again == 0
        assert RSSFeedItem.select().count() == 1


@pytest.mark.asyncio
async def test_rss_service_uses_exponential_backoff_for_429(test_user):
    server = TorrentServer.create(
        id='server429',
        user_id=test_user.id,
        name='RSS Server',
        server_type='transmission',
        host='localhost',
        port=9091,
    )
    RSSFeed.create(
        id='feed429',
        user_id=test_user.id,
        server_id=server.id,
        name='Feed',
        url='https://example.com/rss.xml',
        delay_hours=0,
        enabled=True,
    )
    item = RSSFeedItem.create(
        id='item429',
        feed_id='feed429',
        user_id=test_user.id,
        server_id=server.id,
        title='Rate limited item',
        guid='item429',
        link='https://example.com/file.torrent',
        uri='https://example.com/file.torrent',
        fingerprint='item429',
        status='pending',
        detected_at=datetime.datetime.now() - datetime.timedelta(hours=1),
        next_attempt_at=datetime.datetime.now() - datetime.timedelta(minutes=1),
    )

    service = RSSService()

    with patch('torrent_manager.rss.add_torrent_to_server', side_effect=Exception('429 Client Error: Too Many Requests')):
        await service.process_pending_items()

    item = RSSFeedItem.get_by_id(item.id)
    first_delay = round((item.next_attempt_at - datetime.datetime.now()).total_seconds())
    assert item.attempt_count == 1
    assert Config.RSS_429_BACKOFF_BASE - 5 <= first_delay <= Config.RSS_429_BACKOFF_BASE + 5

    item.next_attempt_at = datetime.datetime.now() - datetime.timedelta(minutes=1)
    item.save()

    with patch('torrent_manager.rss.add_torrent_to_server', side_effect=Exception('429 Client Error: Too Many Requests')):
        await service.process_pending_items()

    item = RSSFeedItem.get_by_id(item.id)
    second_delay = round((item.next_attempt_at - datetime.datetime.now()).total_seconds())
    assert item.attempt_count == 2
    expected = min(Config.RSS_429_BACKOFF_BASE * Config.RSS_429_BACKOFF_MULTIPLIER, Config.RSS_429_BACKOFF_MAX)
    assert expected - 5 <= second_delay <= expected + 5


@pytest.mark.asyncio
async def test_rss_service_marks_auth_errors_as_failed(test_user):
    """Test that authentication errors (401, 403) are marked as failed instead of retried."""
    server = TorrentServer.create(
        id='server_auth',
        user_id=test_user.id,
        name='Auth Server',
        server_type='transmission',
        host='localhost',
        port=9091,
    )
    RSSFeed.create(
        id='feed_auth',
        user_id=test_user.id,
        server_id=server.id,
        name='Feed',
        url='https://example.com/rss.xml',
        delay_hours=0,
        enabled=True,
    )
    item = RSSFeedItem.create(
        id='item_auth',
        feed_id='feed_auth',
        user_id=test_user.id,
        server_id=server.id,
        title='Auth failed item',
        guid='item_auth',
        link='https://example.com/file.torrent',
        uri='https://example.com/file.torrent',
        fingerprint='item_auth',
        status='pending',
        detected_at=datetime.datetime.now() - datetime.timedelta(hours=1),
        next_attempt_at=datetime.datetime.now() - datetime.timedelta(minutes=1),
    )

    service = RSSService()

    with patch('torrent_manager.rss.add_torrent_to_server', side_effect=Exception('401 Client Error: Unauthorized')):
        await service.process_pending_items()

    item = RSSFeedItem.get_by_id(item.id)
    assert item.status == 'failed'
    assert item.attempt_count == 1
    assert '401' in item.last_error
