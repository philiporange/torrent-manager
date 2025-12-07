/**
 * Dashboard module for torrent management.
 * Displays torrents in a table format with efficient DOM updates.
 * Uses Intersection Observer for lazy row rendering.
 * Supports long-press/double-click to open management modal.
 * Media player (Plyr) is lazy-loaded only when first used.
 */

let pollingEnabled = true;
let servers = [];
let torrentCache = {};  // Cache for efficient updates
let torrentData = {};   // Full torrent data by hash
let currentTorrent = null;  // Currently selected torrent for management modal
let longPressTimer = null;
const LONG_PRESS_DURATION = 500;  // ms

// Intersection Observer for lazy rendering
let rowObserver = null;
function initRowObserver() {
    if (rowObserver) return;
    const scrollContainer = document.querySelector('#torrentsTableContainer > div');
    if (!scrollContainer) return;

    rowObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const row = entry.target;
                const hash = row.dataset.hash;
                if (row.dataset.rendered !== 'true' && torrentData[hash]) {
                    updateRow(row, torrentData[hash]);
                    row.dataset.rendered = 'true';
                }
            }
        });
    }, {
        root: scrollContainer,
        rootMargin: '200px 0px'  // Load rows 200px before they enter viewport
    });
}

// Filter state
let activeFilters = {
    status: { download: true, seeding: true, finished: true },
    privacy: { public: true, private: true },
    server: ''
};

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return '0m';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
    return `${(seconds / 86400).toFixed(1)}d`;
}

async function loadTorrents() {
    const loadingEl = document.getElementById('loadingSpinner');
    const emptyEl = document.getElementById('emptyState');
    const tableEl = document.getElementById('torrentsTableContainer');
    const tbody = document.getElementById('torrentsTbody');

    // Show spinner only on first load
    if (Object.keys(torrentCache).length === 0 && tbody.children.length === 0) {
        loadingEl.classList.remove('hidden');
    }

    try {
        const torrents = await apiRequest('/torrents');
        loadingEl.classList.add('hidden');

        // Update stats
        let stats = { down: 0, up: 0, active: 0 };
        torrents.forEach(t => {
            stats.down += t.download_rate || 0;
            stats.up += t.upload_rate || 0;
            if (t.is_active) stats.active++;
        });
        updateGlobalStats(stats, torrents.length);

        // Show/hide empty state
        if (torrents.length === 0) {
            emptyEl.classList.remove('hidden');
            tableEl.classList.add('hidden');
            torrentCache = {};
            return;
        }

        emptyEl.classList.add('hidden');
        tableEl.classList.remove('hidden');

        // Sort by added_at (newest first), fallback to name
        torrents.sort((a, b) => {
            const dateA = a.added_at ? new Date(a.added_at) : new Date(0);
            const dateB = b.added_at ? new Date(b.added_at) : new Date(0);
            return dateB - dateA;
        });

        // Apply filters
        const filteredTorrents = filterTorrents(torrents);

        // Efficient DOM update
        updateTorrentTable(filteredTorrents, tbody);

    } catch (error) {
        loadingEl.classList.add('hidden');
    }
}

function updateGlobalStats(stats, count) {
    document.getElementById('stat-down-speed').textContent = formatSpeed(stats.down);
    document.getElementById('stat-up-speed').textContent = formatSpeed(stats.up);
    document.getElementById('stat-count').textContent = count;
    document.getElementById('stat-active').textContent = stats.active;
}

// Track which servers have HTTP enabled
let serverHttpStatus = {};

async function loadServerHttpStatus() {
    try {
        const serversList = await apiRequest('/servers');
        serverHttpStatus = {};
        for (const s of serversList) {
            serverHttpStatus[s.id] = s.http_enabled;
        }
    } catch (e) {
        // Ignore
    }
}

function updateTorrentTable(torrents, tbody) {
    initRowObserver();
    const newCache = {};
    const existingRows = {};

    // Store full torrent data for lazy rendering
    torrents.forEach(t => {
        torrentData[t.info_hash] = t;
    });

    // Index existing rows
    for (const row of tbody.children) {
        existingRows[row.dataset.hash] = row;
    }

    // Track order for reordering
    const orderedHashes = torrents.map(t => t.info_hash);

    torrents.forEach((t, index) => {
        const hash = t.info_hash;
        newCache[hash] = t;

        let row = existingRows[hash];
        if (row) {
            // Update existing row only if rendered and data changed
            if (row.dataset.rendered === 'true' && hasChanged(torrentCache[hash], t)) {
                updateRow(row, t);
            }
            delete existingRows[hash];
        } else {
            // Create new placeholder row
            row = createPlaceholderRow(t);
            tbody.appendChild(row);
            rowObserver.observe(row);
        }
    });

    // Remove rows that no longer exist and clean up torrentData
    for (const hash in existingRows) {
        rowObserver.unobserve(existingRows[hash]);
        existingRows[hash].remove();
        delete torrentData[hash];
    }

    // Reorder rows to match sorted order
    orderedHashes.forEach((hash, index) => {
        const row = tbody.querySelector(`[data-hash="${hash}"]`);
        if (row && tbody.children[index] !== row) {
            tbody.insertBefore(row, tbody.children[index]);
        }
    });

    torrentCache = newCache;
}

function hasChanged(oldData, newData) {
    if (!oldData) return true;
    return oldData.progress !== newData.progress ||
           oldData.download_rate !== newData.download_rate ||
           oldData.upload_rate !== newData.upload_rate ||
           oldData.state !== newData.state ||
           oldData.is_active !== newData.is_active;
}

function createPlaceholderRow(t) {
    const row = document.createElement('tr');
    row.dataset.hash = t.info_hash;
    row.dataset.serverId = t.server_id;
    row.dataset.rendered = 'false';
    row.className = 'hover:bg-slate-50 cursor-pointer transition-colors';
    row.style.height = '52px';  // Reserve space for the row

    // Add interaction handlers
    row.addEventListener('dblclick', () => openManagementModal(t.info_hash, t.server_id));
    row.addEventListener('mousedown', (e) => startLongPress(e, t.info_hash, t.server_id));
    row.addEventListener('mouseup', cancelLongPress);
    row.addEventListener('mouseleave', cancelLongPress);
    row.addEventListener('touchstart', (e) => startLongPress(e, t.info_hash, t.server_id), { passive: true });
    row.addEventListener('touchend', cancelLongPress);
    row.addEventListener('touchcancel', cancelLongPress);

    // Empty placeholder cells matching table structure
    row.innerHTML = `
        <td class="px-4 py-3" colspan="6"></td>
    `;
    return row;
}

function getDisplayStatus(t) {
    const isFinished = t.complete || t.state === 'finished' || t.progress >= 1;
    if (isFinished) {
        return t.is_active ? 'seeding' : 'finished';
    }
    return 'download';
}

function getStatusStyle(status) {
    switch (status) {
        case 'download': return 'text-indigo-600 bg-indigo-50';
        case 'seeding': return 'text-amber-600 bg-amber-50';
        case 'finished': return 'text-emerald-600 bg-emerald-50';
        default: return 'text-slate-600 bg-slate-50';
    }
}

function formatSeedRemaining(t) {
    const threshold = t.seed_threshold || 0;
    const duration = t.seeding_duration || 0;
    const remaining = threshold - duration;

    if (remaining <= 0) return '<span class="text-emerald-600">done</span>';

    const hours = Math.ceil(remaining / 3600);
    return `${hours}`;
}

function formatSizeGB(bytes) {
    if (!bytes || bytes === 0) return '0';
    const gb = bytes / (1024 * 1024 * 1024);
    return gb >= 10 ? gb.toFixed(0) : gb.toFixed(1);
}

function formatSpeedMB(bytesPerSec) {
    if (!bytesPerSec || bytesPerSec === 0) return '0';
    const mb = bytesPerSec / (1024 * 1024);
    return mb >= 10 ? mb.toFixed(0) : mb.toFixed(1);
}

function updateRow(row, t) {
    const pct = Math.min(100, (t.progress || 0) * 100);
    const status = getDisplayStatus(t);
    const statusStyle = getStatusStyle(status);
    const isComplete = t.complete || t.state === 'finished' || t.progress >= 1;

    // Row background as progress bar
    if (!isComplete && pct > 0) {
        row.style.background = `linear-gradient(to right, rgba(187, 247, 208, 0.5) ${pct}%, transparent ${pct}%)`;
    } else {
        row.style.background = '';
    }

    // Combined speed display
    const downSpeed = t.download_rate || 0;
    const upSpeed = t.upload_rate || 0;
    let speedDisplay = '';
    if (downSpeed > 0 || upSpeed > 0) {
        const parts = [];
        if (downSpeed > 0) parts.push(`<i class="fas fa-arrow-down text-emerald-500"></i>${formatSpeedMB(downSpeed)}`);
        if (upSpeed > 0) parts.push(`<i class="fas fa-arrow-up text-indigo-500"></i>${formatSpeedMB(upSpeed)}`);
        speedDisplay = parts.join(' ');
    } else {
        speedDisplay = '<span class="text-slate-300">-</span>';
    }

    // Seed remaining
    const seedRemaining = isComplete ? formatSeedRemaining(t) : '<span class="text-slate-300">-</span>';

    row.innerHTML = `
        <td class="px-4 py-3">
            <div class="flex items-center gap-2 min-w-0">
                <span class="truncate text-sm font-medium text-slate-900" title="${t.name || t.info_hash}">
                    ${t.name || t.info_hash.substring(0, 16) + '...'}
                </span>
                ${t.is_private ? '<i class="fas fa-lock text-amber-500 text-xs flex-shrink-0" title="Private"></i>' : ''}
            </div>
        </td>
        <td class="px-4 py-3">
            <span class="inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${statusStyle}">${status}</span>
        </td>
        <td class="px-4 py-3 text-sm text-slate-600 hidden sm:table-cell">
            ${formatSizeGB(t.size || 0)}
        </td>
        <td class="px-4 py-3 text-sm text-slate-600 hidden md:table-cell">
            ${seedRemaining}
        </td>
        <td class="px-4 py-3 text-xs text-slate-500 hidden lg:table-cell truncate">
            ${t.server_name || ''}
        </td>
        <td class="px-4 py-3 text-xs text-slate-600 hidden xl:table-cell">
            ${speedDisplay}
        </td>
    `;
}

// Long press handling
function startLongPress(e, hash, serverId) {
    cancelLongPress();
    longPressTimer = setTimeout(() => {
        openManagementModal(hash, serverId);
    }, LONG_PRESS_DURATION);
}

function cancelLongPress() {
    if (longPressTimer) {
        clearTimeout(longPressTimer);
        longPressTimer = null;
    }
}

// Management Drawer
async function openManagementModal(hash, serverId) {
    const t = torrentData[hash];
    if (!t) return;

    currentTorrent = { hash, serverId };

    document.getElementById('managementDrawer').classList.add('open');
    document.getElementById('managementOverlay').classList.add('active');

    // Header
    document.getElementById('managementTitle').textContent = t.name || hash;
    document.getElementById('mgmtInfoHash').textContent = hash;

    // Row 1: Status, Progress, Size, Downloaded, Uploaded, Ratio
    document.getElementById('mgmtStatus').textContent = getDisplayStatus(t);
    document.getElementById('mgmtProgress').textContent = ((t.progress || 0) * 100).toFixed(1) + '%';
    document.getElementById('mgmtSize').textContent = formatBytes(t.size || 0);
    document.getElementById('mgmtDownloaded').textContent = formatBytes(t.downloaded || 0);
    document.getElementById('mgmtUploaded').textContent = formatBytes(t.uploaded || 0);
    document.getElementById('mgmtRatio').textContent = (t.ratio || 0).toFixed(2);

    // Row 2: Down Speed, Up Speed, Peers, Seeds, Added, Server
    document.getElementById('mgmtDownSpeed').textContent = formatSpeed(t.download_rate || 0);
    document.getElementById('mgmtUpSpeed').textContent = formatSpeed(t.upload_rate || 0);
    document.getElementById('mgmtPeers').textContent = t.peers || 0;
    document.getElementById('mgmtSeeds').textContent = t.seeds || 0;
    document.getElementById('mgmtAdded').textContent = t.added_at ? new Date(t.added_at).toLocaleDateString() : '-';
    document.getElementById('mgmtServer').textContent = t.server_name || '-';

    // Update button visibility
    document.getElementById('mgmtStartBtn').classList.toggle('hidden', t.is_active);
    document.getElementById('mgmtStopBtn').classList.toggle('hidden', !t.is_active);

    // Load files
    const filesList = document.getElementById('managementFilesList');
    filesList.innerHTML = '<div class="text-center py-6"><i class="fas fa-circle-notch fa-spin text-indigo-500"></i></div>';

    try {
        const data = await apiRequest(`/torrents/${hash}/files?server_id=${serverId}`);
        renderManagementFiles(data);
    } catch (error) {
        filesList.innerHTML = '<div class="text-center py-6 text-slate-400">Unable to load files</div>';
    }
}

// Media file detection
const AUDIO_EXTENSIONS = ['mp3', 'm4a', 'm4b', 'wav', 'ogg', 'flac', 'aac'];
const VIDEO_EXTENSIONS = ['mp4', 'webm', 'mkv', 'avi', 'mov', 'm4v'];

function getMediaType(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    if (AUDIO_EXTENSIONS.includes(ext)) return 'audio';
    if (VIDEO_EXTENSIONS.includes(ext)) return 'video';
    return null;
}

function renderManagementFiles(data) {
    const container = document.getElementById('managementFilesList');
    const files = data.files || [];

    if (files.length === 0) {
        container.innerHTML = '<div class="text-center py-6 text-slate-400">No files</div>';
        return;
    }

    container.innerHTML = files.map(f => {
        const size = formatBytes(f.size || 0);
        const filename = f.path.split('/').pop() || f.path;
        const mediaType = getMediaType(filename);
        const canPlay = data.http_enabled && f.download_url && mediaType;

        return `
            <div class="flex items-center gap-3 px-3 py-2 hover:bg-slate-50">
                <i class="fas fa-file text-slate-300"></i>
                <div class="flex-1 min-w-0">
                    <div class="truncate text-sm text-slate-700" title="${f.path}">${filename}</div>
                </div>
                <span class="text-xs text-slate-400">${size}</span>
                ${canPlay ? `
                    <button onclick="playMedia('${API_BASE}${f.download_url}', '${mediaType}', '${filename.replace(/'/g, "\\'")}')" class="w-11 h-11 flex items-center justify-center text-emerald-500 hover:text-emerald-700 active:bg-emerald-100 rounded-full select-none touch-manipulation">
                        <i class="fas fa-play text-xl pointer-events-none"></i>
                    </button>
                ` : ''}
                ${data.http_enabled && f.download_url ? `
                    <a href="${API_BASE}${f.download_url}" class="w-11 h-11 flex items-center justify-center text-indigo-500 hover:text-indigo-700 active:bg-indigo-100 rounded-full select-none touch-manipulation" download>
                        <i class="fas fa-download text-xl pointer-events-none"></i>
                    </a>
                ` : ''}
            </div>
        `;
    }).join('');
}

// Media player - Plyr-based fullscreen player
let plyrInstance = null;
let plyrLoaded = false;

async function loadPlyr() {
    if (plyrLoaded) return;

    // Load CSS
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/static/vendor/plyr.css';
    document.head.appendChild(link);

    // Load JS
    await new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/static/vendor/plyr.polyfilled.js';
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });

    plyrLoaded = true;
}

async function playMedia(url, type, filename) {
    // Load Plyr on first use
    await loadPlyr();

    // Destroy existing Plyr instance
    if (plyrInstance) {
        plyrInstance.destroy();
        plyrInstance = null;
    }

    let player = document.getElementById('mediaPlayerModal');
    if (!player) {
        player = document.createElement('div');
        player.id = 'mediaPlayerModal';
        player.className = 'fixed inset-0 z-[100] hidden bg-black';
        player.dataset.minimized = 'false';
        player.innerHTML = `
            <div id="mediaPlayerControls" class="absolute top-4 right-4 z-20 flex gap-2 opacity-0 transition-opacity duration-300">
                <button onclick="toggleMinimizePlayer()" id="minimizePlayerBtn" class="w-12 h-12 flex items-center justify-center text-white/70 hover:text-white bg-black/50 rounded-full transition-all">
                    <i class="fas fa-compress-alt text-xl"></i>
                </button>
                <button onclick="closeMediaPlayer()" class="w-12 h-12 flex items-center justify-center text-white/70 hover:text-white bg-black/50 rounded-full transition-all">
                    <i class="fas fa-times text-2xl"></i>
                </button>
            </div>
            <div id="mediaPlayerContent" class="w-full h-full flex items-center justify-center"></div>
        `;
        document.body.appendChild(player);

        // Show controls on interaction
        let hideTimeout = null;
        const showControls = () => {
            const controls = document.getElementById('mediaPlayerControls');
            if (controls) {
                controls.classList.remove('opacity-0');
                controls.classList.add('opacity-100');
            }
            clearTimeout(hideTimeout);
            hideTimeout = setTimeout(() => {
                const ctrl = document.getElementById('mediaPlayerControls');
                if (ctrl) {
                    ctrl.classList.remove('opacity-100');
                    ctrl.classList.add('opacity-0');
                }
            }, 2500);
        };
        player.addEventListener('mousemove', showControls);
        player.addEventListener('touchstart', showControls);
        player.addEventListener('click', showControls);
    }

    const content = document.getElementById('mediaPlayerContent');
    const ext = filename.split('.').pop().toLowerCase();

    // Determine MIME type
    let mimeType = '';
    if (type === 'audio') {
        if (ext === 'm4b' || ext === 'm4a') mimeType = 'audio/mp4';
        else if (ext === 'mp3') mimeType = 'audio/mpeg';
        else if (ext === 'ogg') mimeType = 'audio/ogg';
        else if (ext === 'wav') mimeType = 'audio/wav';
        else if (ext === 'flac') mimeType = 'audio/flac';
        else if (ext === 'aac') mimeType = 'audio/aac';
    } else {
        if (ext === 'mp4' || ext === 'm4v') mimeType = 'video/mp4';
        else if (ext === 'webm') mimeType = 'video/webm';
        else if (ext === 'mkv') mimeType = 'video/x-matroska';
        else if (ext === 'avi') mimeType = 'video/x-msvideo';
        else if (ext === 'mov') mimeType = 'video/quicktime';
    }

    if (type === 'audio') {
        content.innerHTML = `
            <div class="w-full max-w-2xl px-8">
                <div class="text-white text-center mb-4 text-lg truncate">${filename}</div>
                <audio id="mediaElement" preload="metadata">
                    <source src="${url}" type="${mimeType}">
                </audio>
                <div class="flex items-center justify-center gap-3 mt-6">
                    <button onclick="mediaSkip(-30)" class="w-10 h-10 flex items-center justify-center text-white/70 hover:text-white bg-white/10 hover:bg-white/20 rounded-full transition-colors" title="Back 30s">
                        <i class="fas fa-undo"></i>
                    </button>
                    <button onclick="mediaSkip(-10)" class="w-10 h-10 flex items-center justify-center text-white/70 hover:text-white bg-white/10 hover:bg-white/20 rounded-full transition-colors" title="Back 10s">
                        <i class="fas fa-backward"></i>
                    </button>
                    <button onclick="mediaSkip(10)" class="w-10 h-10 flex items-center justify-center text-white/70 hover:text-white bg-white/10 hover:bg-white/20 rounded-full transition-colors" title="Forward 10s">
                        <i class="fas fa-forward"></i>
                    </button>
                    <button onclick="mediaSkip(30)" class="w-10 h-10 flex items-center justify-center text-white/70 hover:text-white bg-white/10 hover:bg-white/20 rounded-full transition-colors" title="Forward 30s">
                        <i class="fas fa-redo"></i>
                    </button>
                </div>
                <div class="flex items-center justify-center gap-2 mt-4">
                    <span class="text-white/60 text-sm mr-2">Speed:</span>
                    <button onclick="setPlaybackSpeed(1)" class="px-3 py-1 text-sm text-white bg-white/20 rounded transition-colors">1x</button>
                    <button onclick="setPlaybackSpeed(1.2)" class="px-3 py-1 text-sm text-white/80 hover:text-white bg-white/10 hover:bg-white/20 rounded transition-colors">1.2x</button>
                    <button onclick="setPlaybackSpeed(1.5)" class="px-3 py-1 text-sm text-white/80 hover:text-white bg-white/10 hover:bg-white/20 rounded transition-colors">1.5x</button>
                    <button onclick="setPlaybackSpeed(2)" class="px-3 py-1 text-sm text-white/80 hover:text-white bg-white/10 hover:bg-white/20 rounded transition-colors">2x</button>
                    <button onclick="setPlaybackSpeed(2.5)" class="px-3 py-1 text-sm text-white/80 hover:text-white bg-white/10 hover:bg-white/20 rounded transition-colors">2.5x</button>
                    <button onclick="setPlaybackSpeed(3)" class="px-3 py-1 text-sm text-white/80 hover:text-white bg-white/10 hover:bg-white/20 rounded transition-colors">3x</button>
                    <button onclick="setPlaybackSpeed(3.5)" class="px-3 py-1 text-sm text-white/80 hover:text-white bg-white/10 hover:bg-white/20 rounded transition-colors">3.5x</button>
                </div>
            </div>
        `;
    } else {
        content.innerHTML = `
            <video id="mediaElement" preload="metadata" playsinline webkit-playsinline class="w-full h-full">
                <source src="${url}" type="${mimeType}">
            </video>
        `;
    }

    // Reset to fullscreen and show
    player.className = 'fixed inset-0 z-[100] bg-black';
    player.dataset.minimized = 'false';
    const minimizeIcon = player.querySelector('#minimizePlayerBtn i');
    if (minimizeIcon) minimizeIcon.className = 'fas fa-compress-alt text-xl';

    // Initialize Plyr
    const mediaEl = document.getElementById('mediaElement');
    if (mediaEl && typeof Plyr !== 'undefined') {
        plyrInstance = new Plyr(mediaEl, {
            controls: type === 'audio'
                ? ['play', 'progress', 'current-time', 'duration', 'mute', 'volume']
                : ['play-large', 'play', 'progress', 'current-time', 'duration', 'mute', 'volume', 'settings', 'fullscreen'],
            settings: ['speed'],
            speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3] },
            keyboard: { focused: true, global: false },
            tooltips: { controls: true, seek: true },
            fullscreen: { enabled: true, fallback: true, iosNative: true }
        });
    }

    // Reset speed to 1x for new media
    setPlaybackSpeed(1);

    // Autoplay
    if (plyrInstance) {
        plyrInstance.play();
    }

    // Setup keyboard controls
    setupMediaListeners();
}

function closeMediaPlayer() {
    // Destroy Plyr instance first
    if (plyrInstance) {
        plyrInstance.destroy();
        plyrInstance = null;
    }

    const player = document.getElementById('mediaPlayerModal');
    if (player) {
        const media = player.querySelector('audio, video');
        if (media) {
            media.pause();
            media.removeAttribute('src');
            media.load();
        }
        player.classList.add('hidden');
        // Reset to fullscreen state
        player.className = 'fixed inset-0 z-[100] hidden bg-black';
        player.dataset.minimized = 'false';
        const icon = player.querySelector('#minimizePlayerBtn i');
        if (icon) icon.className = 'fas fa-compress-alt text-xl';
    }
    // Clean up keyboard handler
    if (mediaKeyHandler) {
        document.removeEventListener('keydown', mediaKeyHandler);
        mediaKeyHandler = null;
    }
}

function setPlaybackSpeed(speed) {
    if (plyrInstance) {
        plyrInstance.speed = speed;
    }
    // Update button styles
    const buttons = document.querySelectorAll('#mediaPlayerContent button[onclick^="setPlaybackSpeed"]');
    buttons.forEach(btn => {
        const btnSpeed = parseFloat(btn.textContent);
        if (btnSpeed === speed) {
            btn.classList.remove('text-white/80', 'bg-white/10');
            btn.classList.add('text-white', 'bg-white/20');
        } else {
            btn.classList.remove('text-white', 'bg-white/20');
            btn.classList.add('text-white/80', 'bg-white/10');
        }
    });
}

function mediaSkip(seconds) {
    if (plyrInstance) {
        plyrInstance.currentTime = Math.max(0, Math.min(plyrInstance.duration || 0, plyrInstance.currentTime + seconds));
    }
}

function formatMediaTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) {
        return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function updateMediaTimeDisplay() {
    const media = document.getElementById('mediaElement');
    const display = document.getElementById('mediaTimeDisplay');
    if (media && display) {
        const current = formatMediaTime(media.currentTime);
        const total = formatMediaTime(media.duration);
        display.textContent = `${current} / ${total}`;
    }
}

let mediaKeyHandler = null;

function setupMediaListeners() {
    const media = document.getElementById('mediaElement');
    if (!media) return;

    // Time display updates
    media.addEventListener('timeupdate', updateMediaTimeDisplay);
    media.addEventListener('loadedmetadata', updateMediaTimeDisplay);

    // Remove old keyboard handler if exists
    if (mediaKeyHandler) {
        document.removeEventListener('keydown', mediaKeyHandler);
    }

    // Keyboard controls
    mediaKeyHandler = (e) => {
        const player = document.getElementById('mediaPlayerModal');
        if (!player || player.classList.contains('hidden') || !plyrInstance) return;

        switch (e.key) {
            case ' ':
                e.preventDefault();
                plyrInstance.togglePlay();
                break;
            case 'ArrowLeft':
                e.preventDefault();
                mediaSkip(-10);
                break;
            case 'ArrowRight':
                e.preventDefault();
                mediaSkip(10);
                break;
            case 'ArrowUp':
                e.preventDefault();
                plyrInstance.volume = Math.min(1, plyrInstance.volume + 0.1);
                break;
            case 'ArrowDown':
                e.preventDefault();
                plyrInstance.volume = Math.max(0, plyrInstance.volume - 0.1);
                break;
            case 'Escape':
                closeMediaPlayer();
                break;
            case 'm':
                toggleMinimizePlayer();
                break;
        }
    };
    document.addEventListener('keydown', mediaKeyHandler);
}

function toggleMinimizePlayer() {
    const player = document.getElementById('mediaPlayerModal');
    if (!player) return;

    const isMinimized = player.dataset.minimized === 'true';
    const btn = document.getElementById('minimizePlayerBtn');
    const icon = btn.querySelector('i');

    if (isMinimized) {
        // Expand
        player.className = 'fixed inset-0 z-[100] bg-black';
        player.dataset.minimized = 'false';
        icon.className = 'fas fa-compress-alt text-xl';
    } else {
        // Minimize to bottom-right corner
        player.className = 'fixed bottom-20 right-4 z-[100] bg-black/95 rounded-lg shadow-2xl w-80 overflow-hidden';
        player.dataset.minimized = 'true';
        icon.className = 'fas fa-expand-alt text-xl';
    }
}

function closeManagementModal() {
    document.getElementById('managementDrawer').classList.remove('open');
    document.getElementById('managementOverlay').classList.remove('active');
    currentTorrent = null;
}

// Management actions
async function mgmtStart() {
    if (!currentTorrent) return;
    await startTorrent(currentTorrent.hash, currentTorrent.serverId);
    closeManagementModal();
}

async function mgmtStop() {
    if (!currentTorrent) return;
    await stopTorrent(currentTorrent.hash, currentTorrent.serverId);
    closeManagementModal();
}

function mgmtDelete() {
    if (!currentTorrent) return;
    document.getElementById('deleteConfirmModal').classList.remove('hidden');
}

function closeDeleteConfirm() {
    document.getElementById('deleteConfirmModal').classList.add('hidden');
}

async function confirmDelete() {
    if (!currentTorrent) return;
    closeDeleteConfirm();
    await removeTorrent(currentTorrent.hash, currentTorrent.serverId);
    closeManagementModal();
}

// Server modal helpers
async function loadServersForModal() {
    try {
        servers = await apiRequest('/servers');
        const select = document.getElementById('targetServer');
        select.innerHTML = '<option value="" disabled selected>Select a server...</option>';
        servers.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.id;
            opt.textContent = `${s.name} (${s.server_type})`;
            select.appendChild(opt);
        });

        // Auto-select: default server, or first server
        const defaultServer = servers.find(s => s.is_default);
        if (defaultServer) {
            select.value = defaultServer.id;
        } else if (servers.length > 0) {
            select.value = servers[0].id;
        }
    } catch (error) {
        // Error
    }
}

// Torrent actions
async function startTorrent(hash, serverId) {
    const query = serverId ? `?server_id=${serverId}` : '';
    await apiRequest(`/torrents/${hash}/start${query}`, { method: 'POST' });
    showToast('Torrent started');
    loadTorrents();
}

async function stopTorrent(hash, serverId) {
    const query = serverId ? `?server_id=${serverId}` : '';
    await apiRequest(`/torrents/${hash}/stop${query}`, { method: 'POST' });
    showToast('Torrent stopped');
    loadTorrents();
}

async function removeTorrent(hash, serverId) {
    const query = serverId ? `?server_id=${serverId}` : '';
    await apiRequest(`/torrents/${hash}${query}`, { method: 'DELETE' });
    showToast('Torrent removed');
    loadTorrents();
}

async function addTorrentFile(file) {
    const server_id = document.getElementById('targetServer').value;
    if (!server_id) { showToast('Please select a server', 'danger'); return; }

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/torrents/upload?server_id=${server_id}`, {
        method: 'POST',
        credentials: 'include',
        body: formData
    });

    if (!response.ok) {
        const error = await response.json();
        showToast(error.detail || 'Upload failed', 'danger');
        return;
    }

    showToast('Torrent uploaded');
    closeModal('addModal');
    loadTorrents();
}

// Modal helpers
function openModal(id) {
    document.getElementById(id).classList.remove('hidden');
    loadServersForModal();
}

function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
}

// Filter functions
function openFilterModal() {
    // Populate server dropdown
    const serverSelect = document.getElementById('filterServer');
    serverSelect.innerHTML = '<option value="">All Servers</option>';
    servers.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.name;
        if (activeFilters.server === s.id) opt.selected = true;
        serverSelect.appendChild(opt);
    });

    // Set checkbox states
    document.getElementById('filterDownload').checked = activeFilters.status.download;
    document.getElementById('filterSeeding').checked = activeFilters.status.seeding;
    document.getElementById('filterFinished').checked = activeFilters.status.finished;
    document.getElementById('filterPublic').checked = activeFilters.privacy.public;
    document.getElementById('filterPrivate').checked = activeFilters.privacy.private;

    document.getElementById('filterModal').classList.remove('hidden');
}

function closeFilterModal() {
    document.getElementById('filterModal').classList.add('hidden');
}

function applyFilters() {
    activeFilters.status.download = document.getElementById('filterDownload').checked;
    activeFilters.status.seeding = document.getElementById('filterSeeding').checked;
    activeFilters.status.finished = document.getElementById('filterFinished').checked;
    activeFilters.privacy.public = document.getElementById('filterPublic').checked;
    activeFilters.privacy.private = document.getElementById('filterPrivate').checked;
    activeFilters.server = document.getElementById('filterServer').value;

    closeFilterModal();
    loadTorrents();
}

function resetFilters() {
    activeFilters = {
        status: { download: true, seeding: true, finished: true },
        privacy: { public: true, private: true },
        server: ''
    };
    applyFilters();
}

function filterTorrents(torrents) {
    return torrents.filter(t => {
        const status = getDisplayStatus(t);

        // Status filter
        if (!activeFilters.status[status]) return false;

        // Privacy filter
        if (t.is_private && !activeFilters.privacy.private) return false;
        if (!t.is_private && !activeFilters.privacy.public) return false;

        // Server filter
        if (activeFilters.server && t.server_id !== activeFilters.server) return false;

        return true;
    });
}

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
    injectNavbar('Torrents');

    // Show filter button in menu (torrents page only)
    const filterBtn = document.getElementById('menuFilterBtn');
    if (filterBtn) filterBtn.classList.remove('hidden');

    const user = await checkAuth();
    if (user) {
        await loadServerHttpStatus();
        // Load servers for filter dropdown
        try {
            servers = await apiRequest('/servers');
        } catch (e) {}
        loadTorrents();
        setInterval(() => {
            if (pollingEnabled && !document.hidden) loadTorrents();
        }, 15000);
    }

    // Add magnet form
    document.getElementById('addMagnetForm').addEventListener('submit', async e => {
        e.preventDefault();
        const uri = document.getElementById('magnetInput').value.trim();
        const server_id = document.getElementById('targetServer').value;
        if (!server_id) { showToast('Select a server', 'danger'); return; }

        await apiRequest('/torrents', { method: 'POST', body: JSON.stringify({ uri, server_id }) });
        showToast('Torrent added');
        closeModal('addModal');
        document.getElementById('magnetInput').value = '';
        loadTorrents();
    });

    // Drag & Drop
    const dropZone = document.getElementById('dropZone');
    if (dropZone) {
        dropZone.addEventListener('click', () => document.getElementById('fileInput').click());
        document.getElementById('fileInput').addEventListener('change', e => {
            if (e.target.files[0]) addTorrentFile(e.target.files[0]);
        });

        dropZone.addEventListener('dragover', e => {
            e.preventDefault();
            dropZone.classList.add('border-indigo-500', 'bg-indigo-50');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('border-indigo-500', 'bg-indigo-50');
        });
        dropZone.addEventListener('drop', e => {
            e.preventDefault();
            dropZone.classList.remove('border-indigo-500', 'bg-indigo-50');
            if (e.dataTransfer.files[0]) addTorrentFile(e.dataTransfer.files[0]);
        });
    }
});
