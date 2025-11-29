let pollingEnabled = true;
let servers = [];

async function loadTorrents() {
    const listEl = document.getElementById('torrentsList');
    const loadingEl = document.getElementById('loadingSpinner');
    
    // Only show spinner if list is empty (first load)
    if (listEl.children.length === 0) loadingEl.classList.remove('hidden');

    try {
        const torrents = await apiRequest('/torrents');
        loadingEl.classList.add('hidden');

        // Update stats
        let stats = { down: 0, up: 0, downTotal: 0, upTotal: 0, active: 0 };

        torrents.forEach(t => {
            stats.down += t.download_rate || 0;
            stats.up += t.upload_rate || 0;
            stats.downTotal += t.downloaded || 0;
            stats.upTotal += t.uploaded || 0;
            if (t.is_active) stats.active++;
        });

        updateGlobalStats(stats, torrents.length);
        renderTorrentList(torrents, listEl);

    } catch (error) {
        loadingEl.classList.add('hidden');
    }
}

function updateGlobalStats(stats, count) {
    document.getElementById('stat-down-speed').textContent = formatSpeed(stats.down);
    document.getElementById('stat-up-speed').textContent = formatSpeed(stats.up);
    document.getElementById('stat-total-dl').textContent = formatBytes(stats.downTotal);
    document.getElementById('stat-total-ul').textContent = formatBytes(stats.upTotal);
    document.getElementById('stat-count').textContent = count;
    document.getElementById('stat-active').textContent = stats.active;
}

function renderTorrentList(torrents, container) {
    if (torrents.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12">
                <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-100 mb-4">
                    <i class="fas fa-inbox text-slate-400 text-2xl"></i>
                </div>
                <h3 class="text-lg font-medium text-slate-900">No torrents active</h3>
                <p class="mt-1 text-slate-500">Get started by adding a new download.</p>
            </div>
        `;
        return;
    }

    // Determine if we need to re-render everything or update (simple re-render for now)
    container.innerHTML = torrents.map(t => {
        const pct = (t.progress * 100).toFixed(1);
        const isFinished = t.complete || t.state === 'finished';
        const statusColor = isFinished ? 'text-emerald-600 bg-emerald-50' : 'text-indigo-600 bg-indigo-50';
        const barColor = isFinished ? 'bg-emerald-500' : 'bg-indigo-500';

        return `
        <div class="bg-white rounded-xl border border-slate-200 p-5 hover:shadow-md transition-shadow duration-200">
            <div class="flex justify-between items-start mb-4">
                <div class="flex-1 min-w-0 mr-4">
                    <div class="flex items-center gap-2 mb-1">
                        <h3 class="text-base font-semibold text-slate-900 truncate" title="${t.name || t.info_hash}">
                            ${t.name || t.info_hash}
                        </h3>
                    </div>
                    <div class="flex items-center gap-2 text-xs">
                        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full font-medium ${statusColor}">
                            ${t.state || 'unknown'}
                        </span>
                        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full font-medium text-slate-600 bg-slate-100 border border-slate-200">
                            <i class="fas fa-server mr-1 text-slate-400"></i> ${t.server_name}
                        </span>
                    </div>
                </div>
                
                <div class="flex items-center gap-2">
                    ${t.is_active ? `
                        <button onclick="stopTorrent('${t.info_hash}', '${t.server_id}')" class="p-2 text-amber-600 hover:bg-amber-50 rounded-lg transition-colors" title="Pause">
                            <i class="fas fa-pause"></i>
                        </button>
                    ` : `
                        <button onclick="startTorrent('${t.info_hash}', '${t.server_id}')" class="p-2 text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="Resume">
                            <i class="fas fa-play"></i>
                        </button>
                    `}
                    <button onclick="removeTorrent('${t.info_hash}', '${t.server_id}')" class="p-2 text-rose-600 hover:bg-rose-50 rounded-lg transition-colors" title="Remove">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>

            <div class="relative w-full h-2 bg-slate-100 rounded-full overflow-hidden mb-4">
                <div class="absolute top-0 left-0 h-full ${barColor} transition-all duration-500" style="width: ${pct}%"></div>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm text-slate-500">
                <div class="flex items-center gap-2">
                    <i class="fas fa-chart-pie text-slate-400"></i>
                    <span class="font-medium text-slate-700">${pct}%</span>
                </div>
                <div class="flex items-center gap-2">
                    <i class="fas fa-arrow-down text-slate-400"></i>
                    <span>${formatSpeed(t.download_rate || 0)}</span>
                </div>
                <div class="flex items-center gap-2">
                    <i class="fas fa-arrow-up text-slate-400"></i>
                    <span>${formatSpeed(t.upload_rate || 0)}</span>
                </div>
                <div class="flex items-center gap-2">
                    <i class="fas fa-database text-slate-400"></i>
                    <span>${formatBytes(t.size || 0)}</span>
                </div>
            </div>
        </div>
        `;
    }).join('');
}

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
        
        if (servers.length === 1) select.value = servers[0].id;
    } catch (error) {
        // Error
    }
}

// Actions
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
    if (confirm('Are you sure? This will remove the torrent from the list.')) {
        const query = serverId ? `?server_id=${serverId}` : '';
        await apiRequest(`/torrents/${hash}${query}`, { method: 'DELETE' });
        showToast('Torrent removed');
        loadTorrents();
    }
}

async function addMagnet(event) {
    event.preventDefault();
    const uri = document.getElementById('magnetInput').value.trim();
    const server_id = document.getElementById('targetServer').value;
    
    if (!server_id) { showToast('Please select a server', 'danger'); return; }
    if (!uri) return;

    await apiRequest('/torrents', { method: 'POST', body: JSON.stringify({ uri, server_id }) });
    showToast('Magnet added successfully');
    document.getElementById('addModal').close(); // Helper function needed for modal closing
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

    showToast('Torrent uploaded successfully');
    closeModal('addModal');
    loadTorrents();
}


// Modal Helpers (Tailwind)
function openModal(id) {
    document.getElementById(id).classList.remove('hidden');
    loadServersForModal();
}
function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
}

// Initialization
document.addEventListener('DOMContentLoaded', async () => {
    injectNavbar('Torrents');
    
    const user = await checkAuth();
    if (user) {
        loadTorrents();
        setInterval(() => {
            if (pollingEnabled && !document.hidden) loadTorrents();
        }, 2000);
    }

    // Event Listeners
    document.getElementById('addMagnetForm').addEventListener('submit', async e => {
        e.preventDefault();
        const uri = document.getElementById('magnetInput').value.trim();
        const server_id = document.getElementById('targetServer').value;
        if (!server_id) { showToast('Select a server', 'danger'); return; }
        
        await apiRequest('/torrents', { method: 'POST', body: JSON.stringify({ uri, server_id }) });
        showToast('Magnet added');
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
