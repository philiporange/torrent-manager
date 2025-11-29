// User Management
let users = [];

async function loadUsers() {
    try {
        users = await apiRequest('/admin/users');
        renderUsers();
    } catch (error) {
        console.error(error);
    }
}

function renderUsers() {
    const container = document.getElementById('usersList');
    container.innerHTML = users.map(u => `
        <div class="flex items-center justify-between p-3 bg-slate-50 rounded-lg border border-slate-100">
            <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-full flex items-center justify-center ${u.is_admin ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-200 text-slate-500'}">
                    <i class="fas fa-user${u.is_admin ? '-shield' : ''}"></i>
                </div>
                <div>
                    <div class="font-medium text-sm text-slate-900">
                        ${u.username}
                        ${u.is_admin ? '<span class="ml-2 text-[10px] uppercase tracking-wider font-bold text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">Admin</span>' : ''}
                    </div>
                    <div class="text-xs text-slate-400">ID: ${u.id.substring(0, 8)}...</div>
                </div>
            </div>
            <div class="flex gap-2">
                <button onclick="editUser('${u.id}')" class="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors">
                    <i class="fas fa-pencil-alt"></i>
                </button>
                <button onclick="deleteUser('${u.id}')" class="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `).join('');
}

// Modal
function openUserModal() {
    document.getElementById('userModal').classList.remove('hidden');
    document.getElementById('userForm').reset();
    document.getElementById('editingUserId').value = '';
    document.getElementById('userModalTitle').textContent = 'Add User';
    document.getElementById('pwdHint').classList.add('hidden');
    document.getElementById('formPassword').required = true;
}

function closeUserModal() {
    document.getElementById('userModal').classList.add('hidden');
}

function editUser(id) {
    const u = users.find(x => x.id === id);
    if (!u) return;

    openUserModal();
    document.getElementById('editingUserId').value = u.id;
    document.getElementById('formUsername').value = u.username;
    document.getElementById('formIsAdmin').checked = u.is_admin;
    document.getElementById('userModalTitle').textContent = 'Edit User';
    document.getElementById('pwdHint').classList.remove('hidden');
    document.getElementById('formPassword').required = false;
}

async function deleteUser(id) {
    if (!confirm('Delete this user?')) return;
    try {
        await apiRequest(`/admin/users/${id}`, { method: 'DELETE' });
        showToast('User deleted');
        loadUsers();
    } catch (e) {}
}

document.getElementById('userForm').addEventListener('submit', async e => {
    e.preventDefault();
    const id = document.getElementById('editingUserId').value;
    const username = document.getElementById('formUsername').value;
    const password = document.getElementById('formPassword').value;
    const is_admin = document.getElementById('formIsAdmin').checked;

    const data = { is_admin };
    if (username) data.username = username; // Only sent on create
    if (password) data.password = password;

    try {
        if (id) {
            await apiRequest(`/admin/users/${id}`, { method: 'PUT', body: JSON.stringify(data) });
            showToast('User updated');
        } else {
            await apiRequest('/admin/users', { method: 'POST', body: JSON.stringify({ username, password, is_admin }) });
            showToast('User created');
        }
        closeUserModal();
        loadUsers();
    } catch (e) {}
});

// Live Logs
let ws = null;
let wsPaused = false;

function connectWs() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/admin/logs/ws`;
    
    ws = new WebSocket(url);
    
    ws.onopen = () => {
        document.getElementById('wsStatus').textContent = 'Connected';
        document.getElementById('wsStatus').classList.replace('bg-slate-100', 'bg-emerald-100');
        document.getElementById('wsStatus').classList.replace('text-slate-800', 'text-emerald-800');
    };
    
    ws.onmessage = (event) => {
        if (wsPaused) return;
        const terminal = document.getElementById('logTerminal');
        const line = document.createElement('div');
        line.textContent = event.data;
        line.className = 'whitespace-pre-wrap break-all hover:bg-slate-800/50 px-1';
        terminal.appendChild(line);
        
        // Auto scroll if near bottom
        if (terminal.scrollTop + terminal.clientHeight >= terminal.scrollHeight - 100) {
            terminal.scrollTop = terminal.scrollHeight;
        }
        
        // Limit lines
        if (terminal.children.length > 1000) {
            terminal.removeChild(terminal.firstChild);
        }
    };
    
    ws.onclose = () => {
        document.getElementById('wsStatus').textContent = 'Disconnected';
        document.getElementById('wsStatus').classList.replace('bg-emerald-100', 'bg-rose-100');
        document.getElementById('wsStatus').classList.replace('text-emerald-800', 'text-rose-800');
        // Reconnect
        setTimeout(connectWs, 3000);
    };
}

function toggleLogs() {
    wsPaused = !wsPaused;
    const btn = document.getElementById('toggleLogsBtn');
    btn.innerHTML = wsPaused ? '<i class="fas fa-play"></i>' : '<i class="fas fa-pause"></i>';
    btn.title = wsPaused ? 'Resume' : 'Pause';
}

function clearLogs() {
    document.getElementById('logTerminal').innerHTML = '';
}

// Init
document.addEventListener('DOMContentLoaded', async () => {
    injectNavbar('Admin');
    const user = await checkAuth();
    if (user && user.is_admin) {
        loadUsers();
        connectWs();
    } else {
        window.location.href = '/';
    }
});
