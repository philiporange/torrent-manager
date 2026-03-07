# Automatic Media Metadata Integration Plan

This document outlines the integration of `torrent_match` and `media_metadata` into `torrent_manager` to automatically identify torrent contents and retrieve full metadata during download.

## Overview

When a torrent is added, the system will:
1. Identify the media content from the torrent name and file structure
2. Retrieve comprehensive metadata from TMDB/IMDB (movies/TV) or Goodreads/Audible (books/audiobooks)
3. Generate Jellyfin-compatible NFO files and download artwork
4. Store everything in `<info_hash>/metadata/` on the torrent server

## Dependencies

```
torrent_match    - Media identification from torrent names
media_metadata   - Metadata retrieval and Jellyfin formatting
```

Both are local packages already installed on this system.

## Data Storage Structure

All metadata will be stored in a `metadata/` subdirectory within each torrent's info_hash folder:

```
<download_dir>/<info_hash>/
├── data/
│   └── <torrent files...>
└── metadata/
    ├── media.id              # Standardized media ID (e.g., "id:imdb:tt0133093")
    ├── media.json            # Full metadata as JSON
    ├── media.nfo             # Jellyfin-compatible NFO file
    ├── poster.jpg            # Primary artwork (movie poster / TV poster / book cover)
    ├── fanart.jpg            # Background artwork (movies/TV only)
    ├── identification.json   # Raw torrent_match output with confidence scores
    └── match_log.txt         # Processing log for debugging
```

### File Contents

**media.id**
```
id:imdb:tt0133093
```

**media.json** (example for movie)
```json
{
  "media_id": "id:imdb:tt0133093",
  "media_type": "movie",
  "title": "The Matrix",
  "year": 1999,
  "imdb_id": "tt0133093",
  "tmdb_id": 603,
  "overview": "A computer hacker learns...",
  "genres": ["Action", "Science Fiction"],
  "runtime": 136,
  "rating": 8.2,
  "poster_url": "https://image.tmdb.org/t/p/original/...",
  "fanart_url": "https://image.tmdb.org/t/p/original/...",
  "cast": [...],
  "crew": [...],
  "identified_at": "2024-01-15T10:30:00",
  "confidence": 0.95,
  "confidence_level": "HIGH"
}
```

**identification.json** (raw torrent_match output)
```json
{
  "torrent_name": "The.Matrix.1999.1080p.BluRay.x264-SPARKS",
  "files": ["The.Matrix.1999.1080p.BluRay.x264-SPARKS.mkv"],
  "result": {
    "imdb_id": "tt0133093",
    "tmdb_id": 603,
    "title": "The Matrix",
    "year": 1999,
    "media_type": "movie",
    "confidence": 0.95,
    "parser_used": "Consensus(4)",
    "consensus": {...}
  },
  "processed_at": "2024-01-15T10:30:00"
}
```

## Implementation Architecture

### New Module: `torrent_manager/metadata_service.py`

Core service that orchestrates identification and metadata retrieval:

```python
class MetadataService:
    """
    Service for automatic media identification and metadata retrieval.

    Integrates torrent_match for identification and media_metadata for
    enrichment. Writes results to the torrent's metadata/ directory.
    """

    def __init__(self, tmdb_api_key: str = None):
        self.matcher = TorrentMatcher(enable_enricher=True)
        self.metadata = MediaMetadata()

    async def identify_torrent(self, torrent_info: TorrentInfo) -> IdentificationResult:
        """Identify media content from torrent name and files."""

    async def fetch_metadata(self, media_id: str) -> dict:
        """Fetch full metadata for identified media."""

    async def write_metadata(self, server: TorrentServer, info_hash: str,
                            metadata: dict) -> bool:
        """Write metadata files to torrent directory."""

    async def process_torrent(self, torrent_info: TorrentInfo,
                             server: TorrentServer) -> ProcessingResult:
        """Full pipeline: identify -> fetch -> write."""
```

### New Callback: `~/.torrent_manager/callbacks/metadata_callback.py`

Callback that triggers metadata processing on torrent events:

```python
class MetadataCallback(TorrentCallback):
    """Automatically identify and fetch metadata for new torrents."""

    async def on_added(self, torrent_info: TorrentInfo) -> None:
        """Trigger identification when torrent is added."""
        # Start identification in background (don't block add operation)

    async def on_completed(self, torrent_info: TorrentInfo) -> None:
        """Re-validate identification when download completes."""
        # File structure now available for better identification
```

### Database Model Extension

New model to track metadata processing status:

```python
class TorrentMetadata(BaseModel):
    """Tracks metadata identification status for torrents."""
    torrent_hash = CharField(index=True)
    server_id = CharField(index=True)
    media_id = CharField(null=True)           # e.g., "id:imdb:tt0133093"
    media_type = CharField(null=True)         # movie, tv_episode, tv_season, etc.
    title = CharField(null=True)
    year = IntegerField(null=True)
    confidence = FloatField(null=True)
    confidence_level = CharField(null=True)   # HIGH, MEDIUM, LOW, VERY_LOW
    status = CharField(default="pending")     # pending, processing, completed, failed
    error = CharField(null=True)
    identified_at = DateTimeField(null=True)
    metadata_written = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)
```

## Processing Flow

### 1. Torrent Added Event

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Torrent Added  │────▶│ MetadataCallback │────▶│ MetadataService │
│    (API/UI)     │     │   on_added()     │     │  queue_task()   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │ Background Task │
                                                 │   (asyncio)     │
                                                 └─────────────────┘
```

### 2. Identification Pipeline

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Torrent Name   │────▶│  torrent_match   │────▶│  MediaID +      │
│  + File List    │     │  TorrentMatcher  │     │  Confidence     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │ Confidence OK?  │
                                                 │  (>= MEDIUM)    │
                                                 └─────────────────┘
                                                    │         │
                                              YES   │         │  NO
                                                    ▼         ▼
                                           ┌──────────┐  ┌──────────┐
                                           │ Continue │  │   Flag   │
                                           │          │  │ for      │
                                           └──────────┘  │ Review   │
                                                         └──────────┘
```

### 3. Metadata Retrieval

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│    MediaID      │────▶│ media_metadata   │────▶│ Full Metadata   │
│ (id:imdb:...)   │     │ get_metadata()   │     │ + Artwork URLs  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │ JellyfinFormat  │
                                                 │ generate_nfo()  │
                                                 └─────────────────┘
```

### 4. Writing to Server

Two strategies depending on server configuration:

**A. Local Mount Available (mount_path configured)**
```python
# Direct file write to mounted directory
metadata_dir = Path(server.mount_path) / info_hash / "metadata"
metadata_dir.mkdir(exist_ok=True)
(metadata_dir / "media.json").write_text(json.dumps(metadata))
```

**B. SSH Access Only**
```python
# Create locally, rsync to server
local_tmp = Path(f"/tmp/metadata_{info_hash}")
# ... write files locally ...
rsync_to_server(local_tmp, f"{server.download_dir}/{info_hash}/metadata/")
```

## Configuration

### Environment Variables

```bash
# Required for movie/TV identification
TMDB_API_KEY=your_tmdb_api_key

# Optional: LLM fallback for difficult identifications
LLM_API_KEY=your_openrouter_key
LLM_API_ENDPOINT=https://openrouter.ai/api/v1
LLM_MODEL=google/gemini-2.0-flash-exp

# Metadata service settings
METADATA_AUTO_IDENTIFY=true          # Enable automatic identification
METADATA_MIN_CONFIDENCE=0.7          # Minimum confidence to write metadata
METADATA_DOWNLOAD_ARTWORK=true       # Download poster/fanart images
METADATA_GENERATE_NFO=true           # Generate Jellyfin NFO files
```

### Config Class Extension

```python
# In config.py
class Config:
    # ... existing config ...

    # Metadata service settings
    METADATA_AUTO_IDENTIFY = os.getenv("METADATA_AUTO_IDENTIFY", "true").lower() == "true"
    METADATA_MIN_CONFIDENCE = float(os.getenv("METADATA_MIN_CONFIDENCE", "0.7"))
    METADATA_DOWNLOAD_ARTWORK = os.getenv("METADATA_DOWNLOAD_ARTWORK", "true").lower() == "true"
    METADATA_GENERATE_NFO = os.getenv("METADATA_GENERATE_NFO", "true").lower() == "true"
```

## API Endpoints

### GET /torrents/{info_hash}/metadata

Retrieve metadata for a torrent:

```json
{
  "info_hash": "ABC123...",
  "status": "completed",
  "media_id": "id:imdb:tt0133093",
  "media_type": "movie",
  "title": "The Matrix",
  "year": 1999,
  "confidence": 0.95,
  "confidence_level": "HIGH",
  "metadata": {
    "overview": "...",
    "genres": ["Action", "Science Fiction"],
    "runtime": 136,
    "rating": 8.2
  },
  "artwork": {
    "poster": "/servers/{server_id}/download/{info_hash}/metadata/poster.jpg",
    "fanart": "/servers/{server_id}/download/{info_hash}/metadata/fanart.jpg"
  }
}
```

### POST /torrents/{info_hash}/identify

Manually trigger identification (re-run or first-time):

```json
{
  "force": true,           // Re-identify even if already done
  "parsers": ["ptn", "llm"] // Optional: specific parsers to use
}
```

### PUT /torrents/{info_hash}/metadata

Manually set/correct metadata:

```json
{
  "media_id": "id:imdb:tt0133093"  // Override with correct ID
}
```

## Frontend Integration

### Dashboard Enhancements

1. **Metadata Status Indicator**
   - Icon showing identification status (pending/completed/failed)
   - Confidence level badge (HIGH=green, MEDIUM=yellow, LOW=red)

2. **Metadata Panel**
   - Expandable section showing identified media info
   - Poster thumbnail
   - Quick edit button for corrections

3. **Bulk Actions**
   - "Identify All" button for unidentified torrents
   - Filter by identification status

### Example UI Component

```html
<div class="torrent-metadata">
  <img src="/api/torrents/{hash}/poster" class="poster-thumb" />
  <div class="meta-info">
    <span class="title">The Matrix (1999)</span>
    <span class="confidence high">95% confidence</span>
    <span class="media-type">Movie</span>
  </div>
  <button onclick="editMetadata('{hash}')">Edit</button>
</div>
```

## Error Handling

### Identification Failures

1. **No Match Found**
   - Status: `failed`
   - Error: "Could not identify media content"
   - Action: Flag for manual identification

2. **Low Confidence**
   - Status: `completed` but flagged
   - Store result but mark for review
   - Don't write metadata files until confirmed

3. **API Errors (TMDB down, etc.)**
   - Status: `pending` (will retry)
   - Implement exponential backoff
   - Max 3 retries over 24 hours

### Write Failures

1. **SSH/Mount Unavailable**
   - Queue for retry when connection restored
   - Store metadata in local DB as backup

2. **Disk Full**
   - Log error, don't retry automatically
   - Notify user via frontend

## Re-identification Triggers

Metadata can be re-processed when:

1. **Torrent Completed** - File structure now available for better matching
2. **Manual Request** - User clicks "Re-identify" button
3. **Torrent Renamed** - If torrent name changes in client
4. **Confidence Upgrade** - Periodic re-check of LOW confidence items with LLM

## Performance Considerations

### Rate Limiting

- TMDB: 40 requests/10 seconds (respect API limits)
- Batch identification with delays
- Cache responses in database

### Async Processing

- All identification runs in background tasks
- Don't block torrent add operations
- Use asyncio semaphore for concurrency control

```python
class MetadataService:
    def __init__(self):
        self._semaphore = asyncio.Semaphore(3)  # Max 3 concurrent identifications

    async def process_torrent(self, ...):
        async with self._semaphore:
            # ... do work ...
```

### Caching

- Store identification results in database
- Cache TMDB responses (24 hour TTL)
- Don't re-download existing artwork

## Implementation Phases

### Phase 1: Core Infrastructure
- [ ] Create `metadata_service.py` module
- [ ] Add `TorrentMetadata` database model
- [ ] Implement basic identification pipeline
- [ ] Add configuration options

### Phase 2: Callback Integration
- [ ] Create metadata callback script
- [ ] Wire up ADDED and COMPLETED events
- [ ] Implement background task queue

### Phase 3: Storage & Writing
- [ ] Implement local mount writing
- [ ] Implement SSH/rsync writing
- [ ] Generate NFO files
- [ ] Download artwork

### Phase 4: API & Frontend
- [ ] Add metadata API endpoints
- [ ] Create metadata UI components
- [ ] Add manual identification flow
- [ ] Implement bulk operations

### Phase 5: Polish & Edge Cases
- [ ] Handle TV seasons/episodes properly
- [ ] Support audiobooks (if detected)
- [ ] Retry logic for failures
- [ ] Admin dashboard for review queue

## Testing Strategy

### Unit Tests
- Identification with various torrent name formats
- Metadata parsing and NFO generation
- File writing (mocked filesystem)

### Integration Tests
- Full pipeline with test TMDB responses
- Callback triggering
- Database state management

### Manual Testing
- Real torrents with known media
- Edge cases (foreign titles, ambiguous names)
- Server connectivity scenarios

## Security Considerations

1. **API Keys** - Store securely, never log
2. **File Paths** - Validate to prevent traversal
3. **SSH Access** - Use key-based auth only
4. **User Input** - Sanitize manual media ID corrections

## Future Enhancements

1. **Music Detection** - Extend to albums/tracks via MusicBrainz
2. **Subtitle Fetching** - Auto-download subtitles for identified media
3. **Plex Integration** - Alternative to Jellyfin NFO format
4. **Recommendation Engine** - Suggest similar content based on library
5. **Duplicate Detection** - Flag same media across multiple torrents
