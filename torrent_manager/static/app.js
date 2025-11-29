// Use API configuration from server, fallback to localhost for development
const API_BASE = window.API_CONFIG?.API_BASE_URL || 'http://localhost:8144';

// --- UI Helpers ---

function showToast(msg, type = 'success') {
    const wrap = document.querySelector('.toast-container');
    const id = `toast-${Date.now()}`;
    const bgClass = type === 'success' ? 'bg-success' : type === 'danger' ? 'bg-danger' : 'bg-info';
    const icon = type === 'success' ? 'check-circle' : type === 'danger' ? 'exclamation-circle' : 'info-circle';

    wrap.insertAdjacentHTML('beforeend', `
        <div class="toast border-0 shadow-sm" id="${id}" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="toast-header ${bgClass} text-white border-0">
                <i class="fas fa-${icon} me-2"></i>
                <strong class="me-auto">Torrent Manager</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body bg-white rounded-bottom">
                ${msg}
            </div>
        </div>
    `);
    new bootstrap.Toast(document.getElementById(id)).show();
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatSpeed(bps) {
    return formatBytes(bps) + '/s';
}

// --- API Service ---

async function apiRequest(endpoint, options = {}) {
    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            ...options,
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        if (response.status === 401 && endpoint !== '/auth/login' && endpoint !== '/auth/me') {
            // Session expired
            await checkAuth();
            throw new Error('Session expired');
        }

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Request failed');
        }

        return await response.json();
    } catch (error) {
        if (endpoint !== '/auth/me') { // Don't show toast for initial auth check
            showToast(error.message, 'danger');
        }
        throw error;
    }
}

// --- Auth Logic ---

// --- Global State ---
let servers = [];

async function checkAuth() {
    try {
        const user = await apiRequest('/auth/me');
        document.getElementById('username').textContent = user.username;
        document.getElementById('loginPage').classList.add('d-none');
        document.getElementById('appPage').classList.remove('d-none');
        await loadServers();
        loadTorrents();
        return true;
    } catch {
        document.getElementById('loginPage').classList.remove('d-none');
        document.getElementById('appPage').classList.add('d-none');
        return false;
    }
}

async function login(event) {
    event.preventDefault();
    const username = document.getElementById('loginUsername').value;
    const password = document.getElementById('loginPassword').value;
    const rememberMe = document.getElementById('rememberMe').checked;

    try {
        await apiRequest('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ username, password, remember_me: rememberMe })
        });
        showToast('Login successful!', 'success');
        await checkAuth();
    } catch (error) {
        // Error handled by apiRequest
    }
}

async function register(event) {
    event.preventDefault();
    const username = document.getElementById('registerUsername').value;
    const password = document.getElementById('registerPassword').value;

    try {
        await apiRequest('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ username, password })
        });
        showToast('Registration successful! Please login.', 'success');
        
        const loginTab = new bootstrap.Tab(document.querySelector('[href="#loginTab"]'));
        loginTab.show();
        document.getElementById('loginUsername').value = username;
        document.getElementById('registerUsername').value = '';
        document.getElementById('registerPassword').value = '';
    } catch (error) {
        // Error handled by apiRequest
    }
}

async function logout() {
    try {
        await apiRequest('/auth/logout', { method: 'POST' });
        showToast('Logged out successfully', 'success');
        stopAutoRefresh();
        await checkAuth();
    } catch (error) {
        // Error handled by apiRequest
    }
}

// --- Torrent Management ---

async function loadTorrents() {
    const listEl = document.getElementById('torrentsList');
    const loadingEl = document.getElementById('torrentsLoading');
    
    // Only show spinner on first load or manual refresh, not background polling
    if (!pollingEnabled) loadingEl.classList.remove('d-none');

    try {
        const torrents = await apiRequest('/torrents');
        loadingEl.classList.add('d-none');

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
        loadingEl.classList.add('d-none');
    }
}

function updateGlobalStats(stats, count) {
    document.getElementById('globalDownSpeed').textContent = formatSpeed(stats.down);
    document.getElementById('globalUpSpeed').textContent = formatSpeed(stats.up);
    document.getElementById('totalDownloaded').textContent = `Total: ${formatBytes(stats.downTotal)}`;
    document.getElementById('totalUploaded').textContent = `Total: ${formatBytes(stats.upTotal)}`;
    document.getElementById('totalTorrents').textContent = count;
    document.getElementById('activeTorrents').textContent = `Downloading: ${stats.active}`;
}

function renderTorrentList(torrents, container) {
    if (torrents.length === 0) {
        const hasServers = servers.length > 0;
        container.innerHTML = `
            <div class="text-center py-5 text-muted">
                <i class="fas fa-${hasServers ? 'inbox' : 'server'} fa-3x mb-3"></i>
                <p>${hasServers ? 'No torrents found. Add one to get started.' : 'No servers configured. Add a server first.'}</p>
            </div>
        `;
        return;
    }

    container.innerHTML = torrents.map(t => {
        const pct = (t.progress * 100).toFixed(1);
        const isFinished = t.complete || t.state === 'finished';
        const statusColor = isFinished ? 'success' : 'primary';
        const serverBadgeColor = t.server_type === 'rtorrent' ? 'primary' : 'success';

        return `
        <div class="card torrent-card mb-3">
            <div class="card-body">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div class="overflow-hidden me-3">
                        <h6 class="card-title mb-1 text-truncate" title="${t.name || t.info_hash}">
                            ${t.name || t.info_hash}
                        </h6>
                        <span class="badge bg-${statusColor} bg-opacity-10 text-${statusColor} border border-${statusColor} border-opacity-10 me-1">
                            ${t.state || 'unknown'}
                        </span>
                        ${t.server_name ? `<span class="badge bg-${serverBadgeColor} bg-opacity-10 text-${serverBadgeColor} border border-${serverBadgeColor} border-opacity-10">
                            <i class="fas fa-server me-1"></i>${t.server_name}
                        </span>` : ''}
                    </div>
                    <div class="btn-group">
                        ${t.is_active ?
                            `<button class="btn btn-sm btn-outline-warning" onclick="stopTorrent('${t.info_hash}', '${t.server_id}')" title="Pause">
                                <i class="fas fa-pause"></i>
                            </button>` :
                            `<button class="btn btn-sm btn-outline-success" onclick="startTorrent('${t.info_hash}', '${t.server_id}')" title="Resume">
                                <i class="fas fa-play"></i>
                            </button>`
                        }
                        <button class="btn btn-sm btn-outline-danger" onclick="removeTorrent('${t.info_hash}', '${t.server_id}')" title="Remove">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>

                <div class="progress" style="height: 6px;">
                    <div class="progress-bar bg-${statusColor}" style="width: ${pct}%"></div>
                </div>

                <div class="d-flex justify-content-between text-muted small mt-2">
                    <span>${pct}%</span>
                    <span><i class="fas fa-arrow-down"></i> ${formatSpeed(t.download_rate || 0)}</span>
                    <span><i class="fas fa-arrow-up"></i> ${formatSpeed(t.upload_rate || 0)}</span>
                    <span class="d-none d-md-inline"><i class="fas fa-users"></i> ${t.peers || 0}</span>
                    <span><i class="fas fa-database"></i> ${formatBytes(t.size || 0)}</span>
                </div>
            </div>
        </div>
    `;
    }).join('');
}

function getSelectedServer() {
    const select = document.getElementById('targetServer');
    if (!select || !select.value) {
        showToast('Please select a server first', 'danger');
        return null;
    }
    return select.value;
}

async function addMagnet(uri) {
    const server_id = getSelectedServer();
    if (!server_id) return;

    await apiRequest('/torrents', { method: 'POST', body: JSON.stringify({ uri, server_id }) });
    showToast('Magnet added successfully');
    loadTorrents();
}

async function addUrl(uri) {
    const server_id = getSelectedServer();
    if (!server_id) return;

    await apiRequest('/torrents', { method: 'POST', body: JSON.stringify({ uri, server_id }) });
    showToast('URL added successfully');
    loadTorrents();
}

async function addTorrentFile(file) {
    const server_id = getSelectedServer();
    if (!server_id) return;

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(`${API_BASE}/torrents/upload?server_id=${server_id}`, {
        method: 'POST',
        credentials: 'include',
        body: formData
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
    }

    showToast('Torrent uploaded successfully');
    loadTorrents();
}

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

// --- API Key Management ---

async function loadApiKeys() {
    const listEl = document.getElementById('apiKeysList');
    try {
        const keys = await apiRequest('/auth/api-keys');
        
        if (keys.length === 0) {
            listEl.innerHTML = `
                <div class="alert alert-light border text-center">
                    No API keys found. Create one to access the API programmatically.
                </div>`;
            return;
        }

        listEl.innerHTML = keys.map(k => `
            <div class="card mb-2">
                <div class="card-body py-2 d-flex justify-content-between align-items-center">
                    <div>
                        <div class="fw-bold">${k.name}</div>
                        <div class="api-key-code text-muted small">${k.prefix}••••••••••••••••••••••••</div>
                        <div class="small text-muted mt-1">
                            Expires: ${k.expires_at ? new Date(k.expires_at).toLocaleDateString() : 'Never'}
                        </div>
                    </div>
                    <button class="btn btn-sm btn-outline-danger border-0" onclick="revokeApiKey('${k.prefix}')">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        listEl.innerHTML = '<p class="text-danger small">Failed to load API keys</p>';
    }
}

async function createApiKey(event) {
    event.preventDefault();
    const name = document.getElementById('apiKeyName').value;
    const expires = document.getElementById('apiKeyExpires').value;
    
    try {
        const body = { name };
        if (expires) body.expires_days = parseInt(expires);
        
        const result = await apiRequest('/auth/api-keys', { method: 'POST', body: JSON.stringify(body) });
        
        showToast(`
            <div class="mb-2">API Key Created! Copy it now:</div>
            <div class="api-key-code select-all bg-light p-2 rounded mb-2">${result.api_key}</div>
            <small class="text-danger">This key will not be shown again.</small>
        `, 'success');
        
        document.getElementById('apiKeyName').value = '';
        loadApiKeys();
    } catch (error) {
        // Handled
    }
}

async function revokeApiKey(prefix) {
    if (confirm('Revoke this API key?')) {
        await apiRequest(`/auth/api-keys/${prefix}`, { method: 'DELETE' });
        showToast('Key revoked');
        loadApiKeys();
    }
}

// --- Server Management ---

async function loadServers() {
    try {
        servers = await apiRequest('/servers');
        updateServerSelects();
        return servers;
    } catch (error) {
        servers = [];
        return [];
    }
}

function updateServerSelects() {
    const targetServer = document.getElementById('targetServer');
    if (!targetServer) return;

    const currentValue = targetServer.value;
    targetServer.innerHTML = '<option value="" disabled>Select a server...</option>';

    servers.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = `${s.name} (${s.server_type})`;
        targetServer.appendChild(opt);
    });

    if (currentValue && servers.some(s => s.id === currentValue)) {
        targetServer.value = currentValue;
    } else if (servers.length === 1) {
        targetServer.value = servers[0].id;
    }
}

async function renderServersList() {
    const listEl = document.getElementById('serversList');
    if (!listEl) return;

    if (servers.length === 0) {
        listEl.innerHTML = `
            <div class="alert alert-light border text-center">
                No servers configured. Add one above to start managing torrents.
            </div>`;
        return;
    }

    listEl.innerHTML = servers.map(s => `
        <div class="card mb-2">
            <div class="card-body py-2 d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center gap-3">
                    <div>
                        <div class="fw-bold">${s.name}</div>
                        <div class="small text-muted">
                            <span class="badge bg-${s.server_type === 'rtorrent' ? 'primary' : 'success'} bg-opacity-75 me-1">${s.server_type}</span>
                            ${s.host}:${s.port}
                        </div>
                    </div>
                </div>
                <div class="btn-group">
                    <button class="btn btn-sm btn-outline-secondary" onclick="editServer('${s.id}')" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-primary" onclick="testServer('${s.id}')" title="Test Connection">
                        <i class="fas fa-plug"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteServer('${s.id}')" title="Delete">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

async function addServer(event) {
    event.preventDefault();

    const editingServerId = document.getElementById('editingServerId').value;
    const data = {
        name: document.getElementById('serverName').value,
        server_type: document.getElementById('serverType').value,
        host: document.getElementById('serverHost').value,
        port: parseInt(document.getElementById('serverPort').value),
        username: document.getElementById('serverUsername').value || null,
        password: document.getElementById('serverPassword').value || null,
        rpc_path: document.getElementById('serverRpcPath').value || null,
        use_ssl: document.getElementById('serverUseSsl').checked
    };

    try {
        if (editingServerId) {
            // Update existing server
            await apiRequest(`/servers/${editingServerId}`, { method: 'PUT', body: JSON.stringify(data) });
            showToast('Server updated successfully');
        } else {
            // Add new server
            await apiRequest('/servers', { method: 'POST', body: JSON.stringify(data) });
            showToast('Server added successfully');
        }

        resetServerForm();
        await loadServers();
        renderServersList();
    } catch (error) {
        // Error handled
    }
}

function editServer(serverId) {
    const server = servers.find(s => s.id === serverId);
    if (!server) return;

    // Populate form fields
    document.getElementById('editingServerId').value = server.id;
    document.getElementById('serverName').value = server.name;
    document.getElementById('serverType').value = server.server_type;
    document.getElementById('serverHost').value = server.host;
    document.getElementById('serverPort').value = server.port;
    document.getElementById('serverUsername').value = server.username || '';
    document.getElementById('serverPassword').value = server.password || '';
    document.getElementById('serverRpcPath').value = server.rpc_path || '';
    document.getElementById('serverUseSsl').checked = server.use_ssl || false;

    // Update submit button
    const submitBtn = document.getElementById('serverFormSubmitBtn');
    submitBtn.innerHTML = '<i class="fas fa-save"></i>';
    submitBtn.classList.remove('btn-primary');
    submitBtn.classList.add('btn-success');

    // Scroll to form
    document.getElementById('addServerForm').scrollIntoView({ behavior: 'smooth' });
}

function resetServerForm() {
    document.getElementById('addServerForm').reset();
    document.getElementById('editingServerId').value = '';

    // Reset submit button
    const submitBtn = document.getElementById('serverFormSubmitBtn');
    submitBtn.innerHTML = '<i class="fas fa-plus"></i>';
    submitBtn.classList.remove('btn-success');
    submitBtn.classList.add('btn-primary');
}

async function testServer(serverId) {
    try {
        const result = await apiRequest(`/servers/${serverId}/test`, { method: 'POST' });
        if (result.status === 'connected') {
            showToast(result.message, 'success');
        } else {
            showToast(result.message, 'danger');
        }
    } catch (error) {
        // Error handled
    }
}

async function deleteServer(serverId) {
    if (confirm('Delete this server? Torrents will remain on the server but will no longer be tracked here.')) {
        await apiRequest(`/servers/${serverId}`, { method: 'DELETE' });
        showToast('Server deleted');
        await loadServers();
        renderServersList();
    }
}

// --- Initialization & Event Listeners ---

let pollingEnabled = true;
function startAutoRefresh() {
    setInterval(() => {
        if (pollingEnabled && !document.getElementById('appPage').classList.contains('d-none')) {
            loadTorrents();
        }
    }, 2000);
}
function stopAutoRefresh() { pollingEnabled = false; }

document.addEventListener('DOMContentLoaded', () => {
    // Check auth immediately
    checkAuth().then(isAuth => {
        if (isAuth) startAutoRefresh();
    });

    // Form Submissions
    document.getElementById('apiKeyForm').addEventListener('submit', createApiKey);
    
    document.getElementById('magnetForm').addEventListener('submit', async e => {
        e.preventDefault();
        const input = document.getElementById('magnetInput');
        if (input.value.trim()) {
            await addMagnet(input.value.trim());
            input.value = '';
            bootstrap.Modal.getInstance(document.getElementById('addTorrentModal')).hide();
        }
    });

    document.getElementById('urlForm').addEventListener('submit', async e => {
        e.preventDefault();
        const input = document.getElementById('urlInput');
        if (input.value.trim()) {
            await addUrl(input.value.trim());
            input.value = '';
            bootstrap.Modal.getInstance(document.getElementById('addTorrentModal')).hide();
        }
    });

    document.getElementById('torrentInput').addEventListener('change', async e => {
        if (e.target.files[0]) {
            await addTorrentFile(e.target.files[0]);
            e.target.value = '';
            bootstrap.Modal.getInstance(document.getElementById('addTorrentModal')).hide();
        }
    });

    // Server Management
    document.getElementById('addServerForm').addEventListener('submit', addServer);
    document.getElementById('serversModal').addEventListener('show.bs.modal', () => {
        resetServerForm();
        renderServersList();
    });
    document.getElementById('addTorrentModal').addEventListener('show.bs.modal', updateServerSelects);

    // UI Toggles
    document.getElementById('refreshButton').addEventListener('click', () => loadTorrents());
    document.getElementById('apiKeysModal').addEventListener('show.bs.modal', loadApiKeys);
    
    document.getElementById('togglePolling').addEventListener('click', function() {
        pollingEnabled = !pollingEnabled;
        this.innerHTML = pollingEnabled ? 
            '<i class="fas fa-pause"></i> Pause' : 
            '<i class="fas fa-play"></i> Resume';
    });

    // Drag & Drop
    const dropZone = document.getElementById('dropZone');
    dropZone.addEventListener('click', () => document.getElementById('torrentInput').click());
    
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
        document.body.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(name => {
        dropZone.addEventListener(name, () => dropZone.classList.add('drag-over'), false);
    });

    ['dragleave', 'drop'].forEach(name => {
        dropZone.addEventListener(name, () => dropZone.classList.remove('drag-over'), false);
    });

    dropZone.addEventListener('drop', e => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files[0]) {
            document.getElementById('torrentInput').files = files;
            // Trigger change event manually if needed, or just call upload
            addTorrentFile(files[0]).then(() => {
                bootstrap.Modal.getInstance(document.getElementById('addTorrentModal')).hide();
            });
        }
    });
    
    // Global Drag & Drop Overlay
    const overlay = document.getElementById('globalDropOverlay');
    let dragCounter = 0;

    window.addEventListener('dragenter', e => {
        dragCounter++;
        if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
            overlay.classList.add('active');
        }
    });

    window.addEventListener('dragleave', e => {
        dragCounter--;
        if (dragCounter === 0) {
            overlay.classList.remove('active');
        }
    });

    window.addEventListener('drop', e => {
        dragCounter = 0;
        overlay.classList.remove('active');
        if (e.dataTransfer.files[0] && e.dataTransfer.files[0].name.endsWith('.torrent')) {
            addTorrentFile(e.dataTransfer.files[0]);
        }
    });
});
