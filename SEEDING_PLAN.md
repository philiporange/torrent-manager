# Seeding Duration Tracking & Auto-Pause Plan

This document outlines the implementation plan for tracking torrent seeding duration and automatically pausing torrents based on configurable duration thresholds for private and public torrents.

## Requirements

1. Track time each torrent has spent actively seeding
2. Separate configurable durations for private vs public torrents:
   - `PRIVATE_SEED_DURATION` - minimum seeding time for private torrents (longer, to maintain ratio)
   - `PUBLIC_SEED_DURATION` - minimum seeding time for public torrents (shorter)
3. Automatically pause torrents when their respective duration threshold is met
4. Expose seeding duration in the API and frontend

## Current State

The codebase already has foundational components:

- **`activity.py`**: `Activity` class with `calculate_seeding_duration()` that computes seeding time from status logs
- **`models.py`**: `Status` model that records torrent states with timestamps
- **`manager.py`**: `Manager` class with `pause_seeded()` method (uses single `MIN_SEEDING_DURATION`)
- **`config.py`**: Has `MIN_SEEDING_DURATION` setting (24 hours default)

## Implementation Plan

### 1. Configuration Changes

**File: `torrent_manager/config.py`**

Add new duration settings with sensible defaults:

```python
# Seeding duration settings (in seconds)
PUBLIC_SEED_DURATION = 24 * 3600      # 24 hours for public torrents
PRIVATE_SEED_DURATION = 7 * 24 * 3600  # 7 days for private torrents
AUTO_PAUSE_SEEDING = True              # Enable/disable auto-pause feature
```

Add to `Config` class:
```python
PUBLIC_SEED_DURATION = int(os.getenv("PUBLIC_SEED_DURATION", PUBLIC_SEED_DURATION))
PRIVATE_SEED_DURATION = int(os.getenv("PRIVATE_SEED_DURATION", PRIVATE_SEED_DURATION))
AUTO_PAUSE_SEEDING = os.getenv("AUTO_PAUSE_SEEDING", str(AUTO_PAUSE_SEEDING)).lower() == "true"
```

### 2. Database Model Updates

**File: `torrent_manager/models.py`**

The `Status` model already tracks torrent states. We need to ensure `is_private` is available when calculating durations. Two options:

**Option A (Recommended)**: Store `is_private` in the `Status` model for historical accuracy:
```python
class Status(BaseModel):
    torrent_hash = CharField(index=True)
    server_id = CharField(index=True, null=True)
    status = CharField()
    progress = FloatField()
    seeders = IntegerField()
    leechers = IntegerField()
    down_rate = IntegerField()
    up_rate = IntegerField()
    is_private = BooleanField(default=False)  # Add this
    timestamp = DateTimeField(default=datetime.datetime.now)
```

**Option B**: Query `is_private` from the torrent client at pause-check time (simpler but requires active torrent).

### 3. Activity Tracking Updates

**File: `torrent_manager/activity.py`**

Update `record_torrent_status()` to accept and store `is_private`:

```python
def record_torrent_status(self, info_hash, server_id=None, is_seeding=True,
                          is_private=False, timestamp=None):
    if timestamp is None:
        timestamp = datetime.datetime.now()
    Status.create(
        torrent_hash=info_hash,
        server_id=server_id,
        status='seeding' if is_seeding else 'stopped',
        progress=1.0 if is_seeding else 0.0,
        seeders=0,
        leechers=0,
        down_rate=0,
        up_rate=0,
        is_private=is_private,
        timestamp=timestamp,
    )
```

Add method to get torrent's private status from most recent record:

```python
def is_torrent_private(self, info_hash) -> bool:
    """Get the private status from the most recent status record."""
    latest = (Status
              .select()
              .where(Status.torrent_hash == info_hash)
              .order_by(Status.timestamp.desc())
              .first())
    return latest.is_private if latest else False
```

### 4. Manager Updates

**File: `torrent_manager/manager.py`**

Update `pause_seeded()` to use separate durations based on private status:

```python
from .config import Config

def pause_seeded(self):
    """Pause torrents that have exceeded their seeding duration threshold."""
    if not Config.AUTO_PAUSE_SEEDING:
        return

    for torrent in self.client.list_torrents():
        info_hash = torrent['info_hash']

        # Skip if not actively seeding
        if not torrent.get('is_active') or not torrent.get('complete'):
            continue

        is_private = torrent.get('is_private', False)
        seeding_duration = self.activity.calculate_seeding_duration(info_hash)

        # Select threshold based on private status
        threshold = Config.PRIVATE_SEED_DURATION if is_private else Config.PUBLIC_SEED_DURATION

        if seeding_duration >= threshold:
            name = torrent.get('name', info_hash)
            logger.info(f"Auto-pausing {'private' if is_private else 'public'} torrent: {name} "
                       f"(seeded for {seeding_duration / 3600:.1f} hours)")
            self.client.stop(info_hash)
```

### 5. Background Task / Scheduler

**File: `torrent_manager/api/main.py`**

Add a background task that periodically:
1. Records current seeding status for all torrents
2. Checks and pauses torrents exceeding their thresholds

```python
import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Torrent Manager API")
    SessionManager.cleanup_expired_sessions()
    SessionManager.cleanup_expired_tokens()
    ApiKeyManager.cleanup_expired_keys()
    await fetch_trackers()

    # Start background seeding monitor
    task = asyncio.create_task(seeding_monitor_task())

    yield

    # Shutdown
    task.cancel()

async def seeding_monitor_task():
    """Background task to monitor seeding and auto-pause torrents."""
    from torrent_manager.models import TorrentServer
    from torrent_manager.client_factory import get_client
    from torrent_manager.activity import Activity
    from torrent_manager.config import Config

    while True:
        try:
            if Config.AUTO_PAUSE_SEEDING:
                activity = Activity()

                for server in TorrentServer.select().where(TorrentServer.enabled == True):
                    try:
                        client = get_client(server)
                        for torrent in client.list_torrents():
                            info_hash = torrent['info_hash']
                            is_seeding = torrent.get('is_active') and torrent.get('complete')
                            is_private = torrent.get('is_private', False)

                            # Record status
                            activity.record_torrent_status(
                                info_hash,
                                server_id=server.id,
                                is_seeding=is_seeding,
                                is_private=is_private
                            )

                            # Check for auto-pause
                            if is_seeding:
                                duration = activity.calculate_seeding_duration(info_hash)
                                threshold = (Config.PRIVATE_SEED_DURATION if is_private
                                           else Config.PUBLIC_SEED_DURATION)

                                if duration >= threshold:
                                    logger.info(f"Auto-pausing torrent: {torrent.get('name')}")
                                    client.stop(info_hash)
                    except Exception as e:
                        logger.error(f"Error monitoring server {server.name}: {e}")

                activity.close()
        except Exception as e:
            logger.error(f"Error in seeding monitor: {e}")

        # Run every 5 minutes
        await asyncio.sleep(300)
```

### 6. API Endpoint Updates

**File: `torrent_manager/api/routes/torrents.py`**

Add seeding duration to torrent list response:

```python
@router.get("/torrents")
async def list_torrents(...):
    activity = Activity()

    for torrent in torrents:
        # ... existing code ...
        torrent["seeding_duration"] = activity.calculate_seeding_duration(torrent["info_hash"])

        # Add threshold info for frontend
        is_private = torrent.get("is_private", False)
        torrent["seed_threshold"] = (Config.PRIVATE_SEED_DURATION if is_private
                                     else Config.PUBLIC_SEED_DURATION)

    activity.close()
    return all_torrents
```

Add endpoint to get/update seeding settings:

```python
@router.get("/settings/seeding")
async def get_seeding_settings(user: User = Depends(get_current_user)):
    """Get current seeding duration settings."""
    return {
        "public_seed_duration": Config.PUBLIC_SEED_DURATION,
        "private_seed_duration": Config.PRIVATE_SEED_DURATION,
        "auto_pause_enabled": Config.AUTO_PAUSE_SEEDING,
    }
```

### 7. Frontend Updates

**File: `torrent_manager/static/js/dashboard.js`**

Display seeding duration and progress toward threshold:

```javascript
// In renderTorrentList, add seeding progress indicator for completed torrents
const seedingInfo = t.complete ? `
    <div class="flex items-center gap-2">
        <i class="fas fa-seedling text-slate-400"></i>
        <span>${formatDuration(t.seeding_duration)} / ${formatDuration(t.seed_threshold)}</span>
    </div>
` : '';

// Add helper function
function formatDuration(seconds) {
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
    return `${(seconds / 86400).toFixed(1)}d`;
}
```

Add a seeding progress bar for completed torrents showing time toward auto-pause threshold.

## Files to Modify

| File | Changes |
|------|---------|
| `torrent_manager/config.py` | Add `PUBLIC_SEED_DURATION`, `PRIVATE_SEED_DURATION`, `AUTO_PAUSE_SEEDING` |
| `torrent_manager/models.py` | Add `is_private` to `Status` model |
| `torrent_manager/activity.py` | Update `record_torrent_status()`, add `is_torrent_private()` |
| `torrent_manager/manager.py` | Update `pause_seeded()` to use separate thresholds |
| `torrent_manager/api/main.py` | Add background seeding monitor task using lifespan |
| `torrent_manager/api/routes/torrents.py` | Add seeding duration to responses, add settings endpoint |
| `torrent_manager/static/js/dashboard.js` | Display seeding duration and threshold progress |
| `torrent_manager/static/index.html` | Add UI elements for seeding info display |

## New Files (Optional)

| File | Purpose |
|------|---------|
| `torrent_manager/seeding.py` | Dedicated module for seeding logic (if refactoring for clarity) |

## Environment Variables

```bash
# Seeding duration settings
PUBLIC_SEED_DURATION=86400      # 24 hours in seconds
PRIVATE_SEED_DURATION=604800    # 7 days in seconds
AUTO_PAUSE_SEEDING=true         # Enable auto-pause feature
```

## Migration Considerations

1. The `Status` table schema change (adding `is_private`) requires a migration
2. Existing status records will have `is_private=False` by default
3. Consider running a one-time script to backfill `is_private` from current torrent states

## Testing

Add tests to `tests/test_activity.py`:
- Test seeding duration calculation with private/public torrents
- Test auto-pause triggers at correct thresholds
- Test that private torrents use longer threshold
- Test that disabled auto-pause setting prevents pausing

## Future Enhancements

1. Per-torrent override of seeding duration (for special cases)
2. Ratio-based pause rules (pause when ratio >= X)
3. Combined rules (pause when duration AND ratio met)
4. Notification when torrent is auto-paused
5. Admin UI to configure seeding settings
