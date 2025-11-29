// Common Utilities & Config

const API_BASE = window.API_CONFIG?.API_BASE_URL || 'http://localhost:8144';

// Toast Notification
function showToast(msg, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'fixed bottom-4 right-4 z-50 flex flex-col gap-3 pointer-events-none';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    const bgClass = type === 'success' ? 'bg-emerald-500' : type === 'danger' ? 'bg-rose-500' : 'bg-blue-500';
    
    toast.className = `${bgClass} text-white px-6 py-4 rounded-lg shadow-xl transform transition-all duration-300 translate-y-10 opacity-0 flex items-center gap-4 pointer-events-auto min-w-[300px]`;
    
    const icon = type === 'success' ? 'check-circle' : type === 'danger' ? 'exclamation-circle' : 'info-circle';
    
    toast.innerHTML = `
        <i class="fas fa-${icon} text-xl"></i>
        <span class="font-medium text-sm">${msg}</span>
        <button onclick="this.parentElement.remove()" class="ml-auto hover:bg-white/20 rounded-full p-1 w-6 h-6 flex items-center justify-center transition-colors">
            <i class="fas fa-times text-xs"></i>
        </button>
    `;

    container.appendChild(toast);

    // Animate in
    requestAnimationFrame(() => {
        toast.classList.remove('translate-y-10', 'opacity-0');
    });

    // Remove after 4s
    setTimeout(() => {
        if (toast.parentElement) {
            toast.classList.add('translate-y-4', 'opacity-0');
            setTimeout(() => toast.remove(), 300);
        }
    }, 4000);
}

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

        if (response.status === 401) {
             if (endpoint !== '/auth/login' && endpoint !== '/auth/me') {
                 window.location.href = '/login';
                 throw new Error('Session expired');
             }
        }

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Request failed');
        }

        return await response.json();
    } catch (error) {
        if (endpoint !== '/auth/me') {
            showToast(error.message, 'danger');
        }
        throw error;
    }
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

async function logout() {
    try {
        await apiRequest('/auth/logout', { method: 'POST' });
        window.location.href = '/login';
    } catch (error) {
        console.error(error);
    }
}

async function checkAuth() {
    try {
        const user = await apiRequest('/auth/me');
        return user;
    } catch {
        window.location.href = '/login';
        return null;
    }
}

// Inject Navbar
async function injectNavbar(activePage) {
    const navContainer = document.getElementById('navbar-placeholder');
    if (!navContainer) return;

    // Fetch user info first to check admin status
    let user = null;
    try {
        user = await apiRequest('/auth/me');
    } catch (e) {
        // Not logged in
    }

    const links = [
        { name: 'Torrents', href: '/', icon: 'bolt' },
        { name: 'Servers', href: '/manage-servers', icon: 'server' },
        { name: 'API Keys', href: '/manage-api-keys', icon: 'key' }
    ];

    if (user && user.is_admin) {
        links.push({ name: 'Admin', href: '/admin/console', icon: 'shield-alt' });
    }

    const navHtml = `
    <nav class="bg-white/80 backdrop-blur-md border-b border-slate-200 sticky top-0 z-40">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between h-16">
                <div class="flex items-center gap-8">
                    <div class="flex-shrink-0 flex items-center gap-2">
                        <div class="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white shadow-lg shadow-indigo-200">
                            <i class="fas fa-bolt text-sm"></i>
                        </div>
                        <span class="font-bold text-lg text-slate-800 tracking-tight">Torrent Manager</span>
                    </div>
                    <div class="hidden sm:flex sm:space-x-1">
                        ${links.map(link => {
                            const isActive = activePage === link.name;
                            const activeClass = isActive 
                                ? 'text-indigo-600 bg-indigo-50' 
                                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50';
                            return `
                            <a href="${link.href}" class="${activeClass} group inline-flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200">
                                <i class="fas fa-${link.icon} mr-2.5 ${isActive ? 'text-indigo-600' : 'text-slate-400 group-hover:text-slate-600'}"></i> ${link.name}
                            </a>
                            `;
                        }).join('')}
                    </div>
                </div>
                <div class="flex items-center gap-4">
                    <div id="user-info" class="hidden md:flex flex-col items-end">
                        <span id="nav-username" class="text-sm font-semibold text-slate-700 leading-none">${user ? user.username : ''}</span>
                        <span class="text-xs text-slate-400 mt-1">Connected</span>
                    </div>
                    <button onclick="logout()" class="p-2 text-slate-400 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors" title="Logout">
                        <i class="fas fa-sign-out-alt"></i>
                    </button>
                </div>
            </div>
        </div>
    </nav>
    `;
    navContainer.innerHTML = navHtml;
}
