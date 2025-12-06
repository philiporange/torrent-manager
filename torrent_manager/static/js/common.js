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

// Menu Drawer Toggle
function toggleMenu() {
    const drawer = document.getElementById('menuDrawer');
    const overlay = document.getElementById('menuOverlay');
    const isOpen = drawer.classList.contains('open');

    if (isOpen) {
        drawer.classList.remove('open');
        overlay.classList.remove('active');
    } else {
        drawer.classList.add('open');
        overlay.classList.add('active');
    }
}

// Inject Menu Drawer HTML
function injectMenuDrawer() {
    // Check if already injected
    if (document.getElementById('menuDrawer')) return;

    const menuHtml = `
        <!-- Floating Menu Button -->
        <button id="menuToggle" onclick="toggleMenu()" class="fixed bottom-16 left-4 z-50 w-12 h-12 bg-white rounded-full shadow-lg border border-slate-200 flex items-center justify-center text-slate-600 hover:text-indigo-600 transition-all opacity-50 hover:opacity-100">
            <i class="fas fa-bars text-lg"></i>
        </button>

        <!-- Menu Drawer -->
        <div id="menuDrawer" class="menu-drawer">
            <div class="menu-drawer-content">
                <!-- Close button -->
                <button onclick="toggleMenu()" class="w-full flex items-center justify-center py-4 mb-4 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition-all border-b border-slate-100">
                    <i class="fas fa-times text-2xl"></i>
                </button>

                <!-- Navigation Links -->
                <nav id="menuNav" class="space-y-1 flex-1"></nav>

                <!-- Filter button (torrents page only) -->
                <div id="menuFilterBtn" class="hidden py-4">
                    <button onclick="openFilterModal(); toggleMenu();" class="w-full px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 transition-colors flex items-center justify-center gap-2">
                        <i class="fas fa-filter"></i> Filter Torrents
                    </button>
                </div>

                <!-- User info & Logout -->
                <div class="pt-6 border-t border-slate-200">
                    <div class="flex items-center justify-between">
                        <div>
                            <span id="nav-username" class="text-sm font-semibold text-slate-700"></span>
                            <span class="block text-xs text-slate-400 mt-0.5">Connected</span>
                        </div>
                        <button onclick="logout()" class="p-2 text-slate-400 hover:text-rose-500 hover:bg-rose-50 rounded-lg transition-colors" title="Logout">
                            <i class="fas fa-sign-out-alt"></i>
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Menu Overlay -->
        <div id="menuOverlay" class="menu-overlay" onclick="toggleMenu()"></div>
    `;

    document.body.insertAdjacentHTML('afterbegin', menuHtml);
}

// Populate Menu Drawer
async function injectNavbar(activePage) {
    // First inject the drawer HTML
    injectMenuDrawer();

    const menuNav = document.getElementById('menuNav');
    if (!menuNav) return;

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

    menuNav.innerHTML = links.map(link => {
        const isActive = activePage === link.name;
        const activeClass = isActive
            ? 'text-indigo-600 bg-indigo-50'
            : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50';
        return `
        <a href="${link.href}" class="${activeClass} flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all">
            <i class="fas fa-${link.icon} w-5 text-center ${isActive ? 'text-indigo-600' : 'text-slate-400'}"></i>
            ${link.name}
        </a>
        `;
    }).join('');

    // Update username
    const usernameEl = document.getElementById('nav-username');
    if (usernameEl && user) {
        usernameEl.textContent = user.username;
    }
}
