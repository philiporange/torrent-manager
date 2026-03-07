let rssFeeds = [];
let rssItems = [];
let torrentServers = [];

function formatTimestamp(value) {
    if (!value) return 'Never';
    return new Date(value).toLocaleString();
}

function statusBadge(status) {
    const styles = {
        pending: 'bg-amber-100 text-amber-800',
        added: 'bg-emerald-100 text-emerald-800',
        skipped: 'bg-slate-100 text-slate-700'
    };
    return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${styles[status] || styles.skipped}">${status}</span>`;
}

async function loadServersForFeeds() {
    torrentServers = await apiRequest('/servers');
    const select = document.querySelector('#rssForm select[name="server_id"]');
    if (!select) return;

    if (torrentServers.length === 0) {
        select.innerHTML = '<option value="">No servers configured</option>';
        return;
    }

    select.innerHTML = torrentServers.map(server => (
        `<option value="${server.id}">${server.name} (${server.server_type})</option>`
    )).join('');
}

function renderFeeds() {
    const container = document.getElementById('rssFeedsList');
    if (!container) return;

    if (rssFeeds.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 bg-white rounded-xl border border-slate-200">
                <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-100 mb-4">
                    <i class="fas fa-rss text-orange-400 text-2xl"></i>
                </div>
                <h3 class="text-lg font-medium text-slate-900">No RSS feeds configured</h3>
                <p class="mt-1 text-slate-500">Add a feed to start automated torrent discovery.</p>
            </div>
        `;
        return;
    }

    container.innerHTML = rssFeeds.map(feed => `
        <div class="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-md transition-shadow duration-200">
            <div class="p-5">
                <div class="flex items-start gap-4">
                    <div class="p-3 rounded-lg ${feed.enabled ? 'bg-orange-50 text-orange-500' : 'bg-slate-100 text-slate-400'} flex-shrink-0">
                        <i class="fas fa-rss text-xl"></i>
                    </div>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2 flex-wrap">
                            <h3 class="text-lg font-semibold text-slate-900">${feed.name}</h3>
                            ${feed.enabled ? '<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">Enabled</span>' : '<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">Paused</span>'}
                            <span class="text-xs font-medium px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-800">${feed.delay_hours}h delay</span>
                        </div>
                        <div class="text-sm text-slate-500 mt-1 break-all">${feed.url}</div>
                        <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-500 mt-3">
                            <div><span class="text-slate-400">Server:</span> ${feed.server_name || 'Missing server'}</div>
                            <div><span class="text-slate-400">Last check:</span> ${formatTimestamp(feed.last_checked_at)}</div>
                            <div><span class="text-slate-400">Seen this refresh:</span> ${feed.last_item_count}</div>
                            <div><span class="text-slate-400">Pending / Added:</span> ${feed.item_counts.pending} / ${feed.item_counts.added}</div>
                        </div>
                        ${feed.last_error ? `<div class="mt-3 text-xs text-rose-600 bg-rose-50 rounded-lg px-3 py-2">${feed.last_error}</div>` : ''}
                    </div>
                </div>
            </div>
            <div class="px-5 py-3 bg-slate-50 border-t border-slate-100 flex flex-wrap items-center gap-2">
                <button onclick="refreshFeed('${feed.id}')" class="px-3 py-1.5 text-xs font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded-lg transition-colors">
                    <i class="fas fa-rotate mr-1.5"></i>Refresh Now
                </button>
                <button onclick="editFeed('${feed.id}')" class="px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-100 rounded-lg transition-colors">
                    <i class="fas fa-edit mr-1.5"></i>Edit
                </button>
                <button onclick="toggleFeed('${feed.id}', ${!feed.enabled})" class="px-3 py-1.5 text-xs font-medium ${feed.enabled ? 'text-amber-700 bg-amber-50 hover:bg-amber-100' : 'text-emerald-700 bg-emerald-50 hover:bg-emerald-100'} rounded-lg transition-colors">
                    <i class="fas ${feed.enabled ? 'fa-pause' : 'fa-play'} mr-1.5"></i>${feed.enabled ? 'Pause' : 'Enable'}
                </button>
                <div class="flex-1"></div>
                <button onclick="deleteFeed('${feed.id}')" class="px-3 py-1.5 text-xs font-medium text-rose-700 bg-white border border-rose-200 hover:bg-rose-50 rounded-lg transition-colors">
                    <i class="fas fa-trash mr-1.5"></i>Delete
                </button>
            </div>
        </div>
    `).join('');
}

function renderItems() {
    const tbody = document.getElementById('rssItemsTable');
    if (!tbody) return;

    if (rssItems.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="px-4 py-8 text-center text-sm text-slate-500">No RSS items detected yet.</td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = rssItems.map(item => `
        <tr>
            <td class="px-4 py-3 align-top">
                <div class="font-medium text-slate-900">${item.title}</div>
                <div class="text-xs text-slate-400 break-all mt-1">${item.uri}</div>
                ${item.last_error ? `<div class="text-xs text-rose-600 mt-1">${item.last_error}</div>` : ''}
            </td>
            <td class="px-4 py-3 align-top">${statusBadge(item.status)}</td>
            <td class="px-4 py-3 align-top text-sm text-slate-500 hidden md:table-cell">${formatTimestamp(item.detected_at)}</td>
            <td class="px-4 py-3 align-top text-sm text-slate-500 hidden lg:table-cell">${item.status === 'added' ? formatTimestamp(item.added_at) : formatTimestamp(item.next_attempt_at)}</td>
        </tr>
    `).join('');
}

async function loadFeeds() {
    rssFeeds = await apiRequest('/rss/feeds');
    renderFeeds();
}

async function loadRssItems() {
    rssItems = await apiRequest('/rss/items?limit=50');
    renderItems();
}

async function refreshFeed(feedId) {
    const response = await apiRequest(`/rss/feeds/${feedId}/refresh`, { method: 'POST' });
    showToast(`Feed refreshed, ${response.new_items} new items detected`);
    await Promise.all([loadFeeds(), loadRssItems()]);
}

function editFeed(feedId) {
    const feed = rssFeeds.find(item => item.id === feedId);
    if (!feed) return;

    const form = document.getElementById('rssForm');
    document.getElementById('editingFeedId').value = feed.id;
    document.getElementById('rssFormTitle').textContent = 'Edit RSS Feed';
    document.getElementById('rssSubmitBtnText').textContent = 'Save Changes';

    form.name.value = feed.name;
    form.url.value = feed.url;
    form.server_id.value = feed.server_id;
    form.delay_hours.value = feed.delay_hours;
    form.enabled.checked = feed.enabled;

    document.getElementById('rssForm').scrollIntoView({ behavior: 'smooth' });
}

function resetRssForm() {
    const form = document.getElementById('rssForm');
    form.reset();
    document.getElementById('editingFeedId').value = '';
    document.getElementById('rssFormTitle').textContent = 'Add RSS Feed';
    document.getElementById('rssSubmitBtnText').textContent = 'Save Feed';
    if (torrentServers.length > 0) {
        form.server_id.value = torrentServers[0].id;
    }
    form.enabled.checked = true;
    form.delay_hours.value = 0;
}

async function toggleFeed(feedId, enabled) {
    await apiRequest(`/rss/feeds/${feedId}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled })
    });
    showToast(`Feed ${enabled ? 'enabled' : 'paused'}`);
    await loadFeeds();
}

async function deleteFeed(feedId) {
    if (!confirm('Delete this RSS feed and its tracked items?')) return;
    await apiRequest(`/rss/feeds/${feedId}`, { method: 'DELETE' });
    showToast('RSS feed deleted');
    await Promise.all([loadFeeds(), loadRssItems()]);
    resetRssForm();
}

async function handleFeedSubmit(event) {
    event.preventDefault();
    const form = event.target;
    const feedId = document.getElementById('editingFeedId').value;
    const payload = {
        name: form.name.value,
        url: form.url.value,
        server_id: form.server_id.value,
        delay_hours: parseInt(form.delay_hours.value || '0', 10),
        enabled: form.enabled.checked
    };

    if (feedId) {
        await apiRequest(`/rss/feeds/${feedId}`, {
            method: 'PUT',
            body: JSON.stringify(payload)
        });
        showToast('RSS feed updated');
    } else {
        await apiRequest('/rss/feeds', {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        showToast('RSS feed added');
    }

    resetRssForm();
    await Promise.all([loadFeeds(), loadRssItems()]);
}

document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
    await injectNavbar('RSS');
    document.getElementById('rssForm').addEventListener('submit', handleFeedSubmit);
    await loadServersForFeeds();
    resetRssForm();
    await Promise.all([loadFeeds(), loadRssItems()]);
});
