let servers = [];

async function loadServers() {
    const listEl = document.getElementById('serversList');
    try {
        servers = await apiRequest('/servers');
        renderServersList(listEl);
    } catch (error) {
        // Error
    }
}

function renderServersList(container) {
    if (servers.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 bg-white rounded-xl border border-slate-200">
                <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-100 mb-4">
                    <i class="fas fa-server text-slate-400 text-2xl"></i>
                </div>
                <h3 class="text-lg font-medium text-slate-900">No servers configured</h3>
                <p class="mt-1 text-slate-500">Add a server to start managing torrents.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = servers.map(s => `
        <div class="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-md transition-shadow duration-200">
            <div class="p-5">
                <div class="flex items-start gap-4">
                    <div class="p-3 rounded-lg bg-indigo-50 text-indigo-600 flex-shrink-0">
                        <i class="fas fa-server text-xl"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 flex-wrap">
                            <h3 class="text-lg font-semibold text-slate-900">${s.name}</h3>
                            ${s.is_default ? `<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-800">
                                <i class="fas fa-star mr-1"></i>Default
                            </span>` : ''}
                            <span class="text-xs font-medium px-2 py-0.5 rounded-full ${s.server_type === 'rtorrent' ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800'}">
                                ${s.server_type}
                            </span>
                        </div>
                        <div class="text-sm text-slate-500 mt-1 font-mono">${s.host}:${s.port}</div>

                        <!-- Feature badges -->
                        <div class="flex flex-wrap gap-1.5 mt-2">
                            ${s.auto_download_enabled ? `<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800">
                                <i class="fas fa-cloud-download-alt mr-1"></i>Auto-DL
                            </span>` : ''}
                            ${s.auto_delete_remote ? `<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-rose-100 text-rose-800">
                                <i class="fas fa-trash-alt mr-1"></i>Del after seed
                            </span>` : ''}
                            ${s.http_enabled ? `<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">
                                <i class="fas fa-download mr-1"></i>HTTP
                            </span>` : ''}
                            ${s.mount_path ? `<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-violet-100 text-violet-800">
                                <i class="fas fa-folder-tree mr-1"></i>Mount
                            </span>` : ''}
                        </div>
                    </div>
                </div>

                <!-- Details -->
                <div class="mt-4 pt-4 border-t border-slate-100 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-500">
                    ${s.rpc_path ? `<div><span class="text-slate-400">RPC:</span> ${s.rpc_path}</div>` : ''}
                    ${s.http_enabled ? `<div><span class="text-slate-400">HTTP:</span> ${s.http_host || s.host}:${s.http_port}${s.http_path || '/'}</div>` : ''}
                    ${s.mount_path ? `<div><span class="text-slate-400">Mount:</span> ${s.mount_path}</div>` : ''}
                    ${s.download_dir ? `<div><span class="text-slate-400">Remote Dir:</span> ${s.download_dir}</div>` : ''}
                    ${s.auto_download_path ? `<div><span class="text-slate-400">Local Path:</span> ${s.auto_download_path}</div>` : ''}
                    ${s.ssh_host || s.ssh_user ? `<div><span class="text-slate-400">SSH:</span> ${s.ssh_user || 'root'}@${s.ssh_host || s.host}:${s.ssh_port || 22}</div>` : ''}
                </div>
            </div>

            <!-- Actions -->
            <div class="px-5 py-3 bg-slate-50 border-t border-slate-100 flex flex-wrap items-center gap-2">
                ${!s.is_default ? `<button onclick="setDefaultServer('${s.id}')" class="px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 rounded-lg transition-colors">
                    <i class="fas fa-star mr-1.5"></i>Set Default
                </button>` : ''}
                ${(s.http_enabled || s.mount_path) ? `<button onclick="browseFiles('${s.id}')" class="px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors">
                    <i class="fas fa-folder-open mr-1.5"></i>Files
                </button>` : ''}
                <button onclick="testServer('${s.id}')" class="px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors">
                    <i class="fas fa-plug mr-1.5"></i>Test
                </button>
                <div class="flex-1"></div>
                <button onclick="editServer('${s.id}')" class="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-100 rounded-lg transition-colors">
                    <i class="fas fa-edit mr-1.5"></i>Edit
                </button>
                <button onclick="deleteServer('${s.id}')" class="px-3 py-1.5 text-xs font-medium text-rose-700 bg-white border border-rose-200 hover:bg-rose-50 rounded-lg transition-colors">
                    <i class="fas fa-trash mr-1.5"></i>Delete
                </button>
            </div>
        </div>
    `).join('');
}

async function handleAddServer(event) {
    event.preventDefault();
    const form = event.target;
    const id = document.getElementById('editingServerId').value;

    const data = {
        name: form.name.value,
        server_type: form.server_type.value,
        host: form.host.value,
        port: parseInt(form.port.value),
        username: form.username.value || null,
        password: form.password.value || null,
        rpc_path: form.rpc_path.value || null,
        use_ssl: form.use_ssl.checked,
        // HTTP download configuration
        http_host: form.http_host.value || null,
        http_port: form.http_port.value ? parseInt(form.http_port.value) : null,
        http_path: form.http_path.value || null,
        http_username: form.http_username.value || null,
        http_password: form.http_password.value || null,
        http_use_ssl: form.http_use_ssl.checked,
        // Local mount configuration
        mount_path: form.mount_path.value || null,
        // Download directory for path mapping
        download_dir: form.download_dir.value || null,
        // Auto-download configuration
        auto_download_enabled: form.auto_download_enabled.checked,
        auto_download_path: form.auto_download_path.value || null,
        auto_delete_remote: form.auto_delete_remote.checked,
        // SSH configuration
        ssh_host: form.ssh_host.value || null,
        ssh_port: form.ssh_port.value ? parseInt(form.ssh_port.value) : 22,
        ssh_user: form.ssh_user.value || null,
        ssh_key_path: form.ssh_key_path.value || null
    };

    try {
        if (id) {
            await apiRequest(`/servers/${id}`, { method: 'PUT', body: JSON.stringify(data) });
            showToast('Server updated');
        } else {
            await apiRequest('/servers', { method: 'POST', body: JSON.stringify(data) });
            showToast('Server added');
        }

        resetForm();
        loadServers();
    } catch (error) {
        // handled
    }
}

function editServer(id) {
    const s = servers.find(x => x.id === id);
    if (!s) return;

    document.getElementById('editingServerId').value = s.id;
    document.getElementById('formTitle').textContent = 'Edit Server';
    document.getElementById('submitBtnText').textContent = 'Save Changes';

    const form = document.getElementById('serverForm');
    form.name.value = s.name;
    form.server_type.value = s.server_type;
    form.host.value = s.host;
    form.port.value = s.port;
    form.username.value = s.username || '';
    form.password.value = s.password || '';
    form.rpc_path.value = s.rpc_path || '';
    form.use_ssl.checked = s.use_ssl;
    // HTTP download fields
    form.http_host.value = s.http_host || '';
    form.http_port.value = s.http_port || '';
    form.http_path.value = s.http_path || '';
    form.http_username.value = s.http_username || '';
    form.http_password.value = '';
    form.http_use_ssl.checked = s.http_use_ssl || false;
    // Local mount field
    form.mount_path.value = s.mount_path || '';
    // Download directory field
    form.download_dir.value = s.download_dir || '';
    // Auto-download fields
    form.auto_download_enabled.checked = s.auto_download_enabled || false;
    form.auto_download_path.value = s.auto_download_path || '';
    form.auto_delete_remote.checked = s.auto_delete_remote || false;
    // SSH fields
    form.ssh_host.value = s.ssh_host || '';
    form.ssh_port.value = s.ssh_port || 22;
    form.ssh_user.value = s.ssh_user || '';
    form.ssh_key_path.value = s.ssh_key_path || '';

    // Expand sections that have data
    if (s.auto_download_enabled || s.auto_download_path || s.ssh_host || s.ssh_user) {
        expandSection('autoDownloadSection');
    }
    if (s.http_port || s.http_host) {
        expandSection('httpSection');
    }
    if (s.mount_path || s.download_dir) {
        expandSection('pathsSection');
    }

    document.getElementById('formContainer').scrollIntoView({ behavior: 'smooth' });
}

function resetForm() {
    document.getElementById('serverForm').reset();
    document.getElementById('editingServerId').value = '';
    document.getElementById('formTitle').textContent = 'Add New Server';
    document.getElementById('submitBtnText').textContent = 'Add Server';
    // Reset SSH port default
    document.querySelector('[name="ssh_port"]').value = 22;
}

async function deleteServer(id) {
    if (confirm('Delete this server configuration?')) {
        await apiRequest(`/servers/${id}`, { method: 'DELETE' });
        showToast('Server deleted');
        loadServers();
    }
}

async function setDefaultServer(id) {
    try {
        await apiRequest(`/servers/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ is_default: true })
        });
        showToast('Default server updated');
        loadServers();
    } catch (error) {
        // handled
    }
}

async function testServer(id) {
    const btn = event.currentTarget;
    const icon = btn.querySelector('i');
    icon.className = 'fas fa-circle-notch fa-spin mr-1.5';

    try {
        const res = await apiRequest(`/servers/${id}/test`, { method: 'POST' });
        showToast(res.message, res.status === 'connected' ? 'success' : 'danger');
    } catch (e) {
        // handled
    } finally {
        icon.className = 'fas fa-plug mr-1.5';
    }
}

// Section toggle functionality
function toggleSection(sectionId) {
    const section = document.getElementById(sectionId);
    const icon = document.getElementById(sectionId + '-icon');

    if (section.classList.contains('collapsed')) {
        section.classList.remove('collapsed');
        icon.style.transform = 'rotate(0deg)';
    } else {
        section.classList.add('collapsed');
        icon.style.transform = 'rotate(-90deg)';
    }
}

function expandSection(sectionId) {
    const section = document.getElementById(sectionId);
    const icon = document.getElementById(sectionId + '-icon');
    section.classList.remove('collapsed');
    if (icon) icon.style.transform = 'rotate(0deg)';
}

function collapseSection(sectionId) {
    const section = document.getElementById(sectionId);
    const icon = document.getElementById(sectionId + '-icon');
    section.classList.add('collapsed');
    if (icon) icon.style.transform = 'rotate(-90deg)';
}

// File browser state
let currentServerId = null;
let currentPath = '';

function browseFiles(serverId) {
    currentServerId = serverId;
    currentPath = '';
    openFileBrowser();
    loadFiles();
}

function openFileBrowser() {
    document.getElementById('fileBrowserModal').classList.remove('hidden');
}

function closeFileBrowser() {
    document.getElementById('fileBrowserModal').classList.add('hidden');
}

async function loadFiles(path = '') {
    currentPath = path;
    const container = document.getElementById('filesList');
    container.innerHTML = `<div class="text-center py-8"><i class="fas fa-circle-notch fa-spin text-indigo-500 text-2xl"></i></div>`;

    // Update breadcrumb
    updateBreadcrumb();

    try {
        const data = await apiRequest(`/servers/${currentServerId}/files?path=${encodeURIComponent(path)}`);
        renderFilesList(data.entries);
    } catch (error) {
        container.innerHTML = `<div class="text-center py-8 text-rose-500">Failed to load files</div>`;
    }
}

function updateBreadcrumb() {
    const breadcrumb = document.getElementById('fileBreadcrumb');
    const parts = currentPath.split('/').filter(p => p);

    let html = `<span class="cursor-pointer text-indigo-600 hover:underline" onclick="loadFiles('')">Root</span>`;
    let accumulated = '';

    for (const part of parts) {
        accumulated += part + '/';
        const pathCopy = accumulated.slice(0, -1);
        html += ` <span class="text-slate-400">/</span> <span class="cursor-pointer text-indigo-600 hover:underline" onclick="loadFiles('${pathCopy}')">${part}</span>`;
    }

    breadcrumb.innerHTML = html;
}

function renderFilesList(entries) {
    const container = document.getElementById('filesList');

    if (entries.length === 0) {
        container.innerHTML = `<div class="text-center py-8 text-slate-500">Empty directory</div>`;
        return;
    }

    // Sort: directories first, then files
    entries.sort((a, b) => {
        if (a.is_dir && !b.is_dir) return -1;
        if (!a.is_dir && b.is_dir) return 1;
        return a.name.localeCompare(b.name);
    });

    container.innerHTML = entries.map(e => {
        if (e.is_dir) {
            return `
                <div class="flex items-center gap-3 p-3 hover:bg-slate-50 rounded-lg cursor-pointer transition-colors" onclick="loadFiles('${e.path}')">
                    <i class="fas fa-folder text-amber-500 text-lg"></i>
                    <span class="flex-1 truncate">${e.name}</span>
                    <i class="fas fa-chevron-right text-slate-300"></i>
                </div>
            `;
        } else {
            const size = e.raw_size || formatBytes(e.size || 0);
            return `
                <div class="flex items-center gap-3 p-3 hover:bg-slate-50 rounded-lg transition-colors">
                    <i class="fas fa-file text-slate-400 text-lg"></i>
                    <span class="flex-1 truncate">${e.name}</span>
                    <span class="text-sm text-slate-400">${size}</span>
                    <a href="${API_BASE}/servers/${currentServerId}/download/${encodeURIComponent(e.path)}"
                       class="px-3 py-1.5 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors"
                       download>
                        <i class="fas fa-download"></i>
                    </a>
                </div>
            `;
        }
    }).join('');
}

document.addEventListener('DOMContentLoaded', async () => {
    injectNavbar('Servers');
    const user = await checkAuth();
    if (user) loadServers();

    document.getElementById('serverForm').addEventListener('submit', handleAddServer);

    // Collapse optional sections by default
    collapseSection('autoDownloadSection');
    collapseSection('httpSection');
    collapseSection('pathsSection');
});
