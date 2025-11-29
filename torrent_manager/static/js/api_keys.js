async function loadApiKeys() {
    const listEl = document.getElementById('apiKeysList');
    try {
        const keys = await apiRequest('/auth/api-keys');
        renderKeysList(keys, listEl);
    } catch (error) {
        listEl.innerHTML = '<p class="text-rose-500">Failed to load keys</p>';
    }
}

function renderKeysList(keys, container) {
    if (keys.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 bg-white rounded-xl border border-slate-200">
                <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-100 mb-4">
                    <i class="fas fa-key text-slate-400 text-2xl"></i>
                </div>
                <h3 class="text-lg font-medium text-slate-900">No API Keys</h3>
                <p class="mt-1 text-slate-500">Create a key to access the API programmatically.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = keys.map(k => `
        <div class="bg-white rounded-xl border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:shadow-md transition-shadow duration-200">
            <div class="flex items-start gap-4">
                <div class="p-3 rounded-lg bg-amber-50 text-amber-600">
                    <i class="fas fa-key text-xl"></i>
                </div>
                <div>
                    <h3 class="text-lg font-semibold text-slate-900">${k.name}</h3>
                    <div class="font-mono text-sm text-slate-500 bg-slate-50 px-2 py-1 rounded mt-1 inline-block">
                        ${k.prefix}••••••••••••••••••••••••
                    </div>
                    <div class="text-xs text-slate-400 mt-2 flex gap-4">
                        <span><i class="far fa-clock mr-1"></i> Created: ${new Date(k.created_at).toLocaleDateString()}</span>
                        <span><i class="far fa-calendar-times mr-1"></i> Expires: ${k.expires_at ? new Date(k.expires_at).toLocaleDateString() : 'Never'}</span>
                    </div>
                </div>
            </div>
            
            <button onclick="revokeApiKey('${k.prefix}')" class="px-4 py-2 text-sm font-medium text-rose-600 bg-rose-50 hover:bg-rose-100 rounded-lg transition-colors">
                <i class="fas fa-ban mr-2"></i> Revoke
            </button>
        </div>
    `).join('');
}

async function createApiKey(event) {
    event.preventDefault();
    const form = event.target;
    const name = form.name.value;
    const expires = form.expires.value;

    try {
        const body = { name };
        if (expires) body.expires_days = parseInt(expires);

        const result = await apiRequest('/auth/api-keys', { method: 'POST', body: JSON.stringify(body) });

        // Show result in a nice overlay
        showKeyResult(result);
        
        form.reset();
        loadApiKeys();
    } catch (error) {
        // handled
    }
}

function showKeyResult(result) {
    const modal = document.getElementById('keyResultModal');
    const code = document.getElementById('newKeyCode');
    code.textContent = result.api_key;
    modal.classList.remove('hidden');
}

function closeKeyModal() {
    document.getElementById('keyResultModal').classList.add('hidden');
}

async function revokeApiKey(prefix) {
    if (confirm('Revoke this API key? It will stop working immediately.')) {
        await apiRequest(`/auth/api-keys/${prefix}`, { method: 'DELETE' });
        showToast('Key revoked');
        loadApiKeys();
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    injectNavbar('API Keys');
    const user = await checkAuth();
    if (user) loadApiKeys();
    
    document.getElementById('createKeyForm').addEventListener('submit', createApiKey);
});
