"""RSS feed management routes for automated torrent ingestion."""

import secrets
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, status

from torrent_manager.models import RSSFeed, RSSFeedItem, TorrentServer, User
from torrent_manager.rss import get_rss_service
from ..dependencies import get_current_user, get_user_server
from ..schemas import RSSFeedRequest, RSSFeedUpdateRequest

router = APIRouter(tags=["rss"])


def serialize_item(item: RSSFeedItem) -> dict:
    return {
        "id": item.id,
        "feed_id": item.feed_id,
        "server_id": item.server_id,
        "title": item.title,
        "guid": item.guid,
        "link": item.link,
        "uri": item.uri,
        "info_hash": item.info_hash,
        "status": item.status,
        "detected_at": item.detected_at.isoformat(),
        "next_attempt_at": item.next_attempt_at.isoformat(),
        "added_at": item.added_at.isoformat() if item.added_at else None,
        "last_error": item.last_error,
        "attempt_count": item.attempt_count,
    }


def serialize_feed(feed: RSSFeed) -> dict:
    try:
        server = TorrentServer.get_by_id(feed.server_id)
        server_name = server.name
    except TorrentServer.DoesNotExist:
        server_name = None

    items = list(
        RSSFeedItem.select()
        .where(RSSFeedItem.feed_id == feed.id)
        .order_by(RSSFeedItem.detected_at.desc())
        .limit(10)
    )
    counts = Counter(item.status for item in RSSFeedItem.select().where(RSSFeedItem.feed_id == feed.id))
    return {
        "id": feed.id,
        "name": feed.name,
        "url": feed.url,
        "server_id": feed.server_id,
        "server_name": server_name,
        "delay_hours": feed.delay_hours,
        "enabled": feed.enabled,
        "created_at": feed.created_at.isoformat(),
        "last_checked_at": feed.last_checked_at.isoformat() if feed.last_checked_at else None,
        "last_success_at": feed.last_success_at.isoformat() if feed.last_success_at else None,
        "last_error": feed.last_error,
        "last_item_count": feed.last_item_count,
        "item_counts": {
            "pending": counts.get("pending", 0),
            "added": counts.get("added", 0),
            "skipped": counts.get("skipped", 0),
        },
        "recent_items": [serialize_item(item) for item in items],
    }


@router.get("/rss/feeds")
async def list_rss_feeds(user: User = Depends(get_current_user)):
    feeds = RSSFeed.select().where(RSSFeed.user_id == user.id).order_by(RSSFeed.created_at.desc())
    return [serialize_feed(feed) for feed in feeds]


@router.post("/rss/feeds")
async def create_rss_feed(request: RSSFeedRequest, user: User = Depends(get_current_user)):
    server = get_user_server(request.server_id, user)
    feed = RSSFeed.create(
        id=secrets.token_urlsafe(16),
        user_id=user.id,
        server_id=server.id,
        name=request.name,
        url=request.url,
        delay_hours=max(request.delay_hours, 0),
        enabled=request.enabled,
    )
    return serialize_feed(feed)


@router.get("/rss/feeds/{feed_id}")
async def get_rss_feed(feed_id: str, user: User = Depends(get_current_user)):
    try:
        feed = RSSFeed.get((RSSFeed.id == feed_id) & (RSSFeed.user_id == user.id))
    except RSSFeed.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RSS feed not found")
    return serialize_feed(feed)


@router.put("/rss/feeds/{feed_id}")
async def update_rss_feed(feed_id: str, request: RSSFeedUpdateRequest, user: User = Depends(get_current_user)):
    try:
        feed = RSSFeed.get((RSSFeed.id == feed_id) & (RSSFeed.user_id == user.id))
    except RSSFeed.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RSS feed not found")

    if request.server_id is not None:
        server = get_user_server(request.server_id, user)
        feed.server_id = server.id
    if request.name is not None:
        feed.name = request.name
    if request.url is not None:
        feed.url = request.url
    if request.delay_hours is not None:
        feed.delay_hours = max(request.delay_hours, 0)
    if request.enabled is not None:
        feed.enabled = request.enabled
    feed.save()
    return serialize_feed(feed)


@router.delete("/rss/feeds/{feed_id}")
async def delete_rss_feed(feed_id: str, user: User = Depends(get_current_user)):
    try:
        feed = RSSFeed.get((RSSFeed.id == feed_id) & (RSSFeed.user_id == user.id))
    except RSSFeed.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RSS feed not found")

    RSSFeedItem.delete().where(RSSFeedItem.feed_id == feed.id).execute()
    feed.delete_instance()
    return {"message": "RSS feed deleted"}


@router.post("/rss/feeds/{feed_id}/refresh")
async def refresh_rss_feed(feed_id: str, user: User = Depends(get_current_user)):
    try:
        feed = RSSFeed.get((RSSFeed.id == feed_id) & (RSSFeed.user_id == user.id))
    except RSSFeed.DoesNotExist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RSS feed not found")

    service = get_rss_service()
    created = await service.refresh_feed(feed)
    await service.process_pending_items()
    feed = RSSFeed.get_by_id(feed.id)
    return {"message": "RSS feed refreshed", "new_items": created, "feed": serialize_feed(feed)}


@router.get("/rss/items")
async def list_rss_items(
    user: User = Depends(get_current_user),
    feed_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    query = RSSFeedItem.select().where(RSSFeedItem.user_id == user.id)
    if feed_id:
        try:
            RSSFeed.get((RSSFeed.id == feed_id) & (RSSFeed.user_id == user.id))
        except RSSFeed.DoesNotExist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="RSS feed not found")
        query = query.where(RSSFeedItem.feed_id == feed_id)
    items = query.order_by(RSSFeedItem.detected_at.desc()).limit(limit)
    return [serialize_item(item) for item in items]
