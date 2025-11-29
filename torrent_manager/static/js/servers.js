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
        <div class="bg-white rounded-xl border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:shadow-md transition-shadow duration-200">
            <div class="flex items-start gap-4">
                <div class="p-3 rounded-lg bg-indigo-50 text-indigo-600">
                    <i class="fas fa-server text-xl"></i>
                </div>
                <div>
                    <h3 class="text-lg font-semibold text-slate-900 flex items-center gap-2">
                        ${s.name}
                        <span class="text-xs font-medium px-2.5 py-0.5 rounded-full ${s.server_type === 'rtorrent' ? 'bg-blue-100 text-blue-800' : 'bg-green-100 text-green-800'}">
                            ${s.server_type}
                        </span>
                    </h3>
                    <div class="text-sm text-slate-500 mt-1 font-mono">
                        ${s.host}:${s.port}
                    </div>
                    ${s.rpc_path ? `<div class="text-xs text-slate-400 mt-1">RPC: ${s.rpc_path}</div>` : ''}
                </div>
            </div>
            
            <div class="flex items-center gap-2">
                <button onclick="testServer('${s.id}')" class="px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors">
                    <i class="fas fa-plug mr-2"></i> Test
                </button>
                <button onclick="editServer('${s.id}')" class="px-4 py-2 text-sm font-medium text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors">
                    <i class="fas fa-edit mr-2"></i> Edit
                </button>
                <button onclick="deleteServer('${s.id}')" class="px-4 py-2 text-sm font-medium text-rose-600 bg-rose-50 hover:bg-rose-100 rounded-lg transition-colors">
                    <i class="fas fa-trash mr-2"></i> Delete
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
        use_ssl: form.use_ssl.checked
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
    
    document.getElementById('formContainer').scrollIntoView({ behavior: 'smooth' });
}

function resetForm() {
    document.getElementById('serverForm').reset();
    document.getElementById('editingServerId').value = '';
    document.getElementById('formTitle').textContent = 'Add New Server';
    document.getElementById('submitBtnText').textContent = 'Add Server';
}

async function deleteServer(id) {
    if (confirm('Delete this server configuration?')) {
        await apiRequest(`/servers/${id}`, { method: 'DELETE' });
        showToast('Server deleted');
        loadServers();
    }
}

async function testServer(id) {
    const btn = event.currentTarget;
    const icon = btn.querySelector('i');
    icon.className = 'fas fa-circle-notch fa-spin mr-2';
    
    try {
        const res = await apiRequest(`/servers/${id}/test`, { method: 'POST' });
        showToast(res.message, res.status === 'connected' ? 'success' : 'danger');
    } catch (e) {
        // handled
    } finally {
        icon.className = 'fas fa-plug mr-2';
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    injectNavbar('Servers');
    const user = await checkAuth();
    if (user) loadServers();
    
    document.getElementById('serverForm').addEventListener('submit', handleAddServer);
});
