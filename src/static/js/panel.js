/**
 * Arbion Manager Panel JavaScript
 */

// Utility functions
function formatMoney(value) {
    return new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: 'RUB',
        maximumFractionDigits: 0
    }).format(value);
}

function formatDate(dateStr) {
    return new Date(dateStr).toLocaleDateString('ru-RU');
}

function formatTime(dateStr) {
    return new Date(dateStr).toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Status labels
function getStatusLabel(status) {
    const labels = {
        'cold': 'Cold',
        'in_progress': 'В процессе',
        'warm': 'Warm',
        'handed_to_manager': 'В работе',
        'won': 'Выиграна',
        'lost': 'Проиграна',
    };
    return labels[status] || status;
}

// API helpers
async function apiGet(url) {
    const response = await fetch(url);
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP error ${response.status}`);
    }
    return response.json();
}

async function apiPost(url, data = {}) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.detail || 'Error');
    }
    return result;
}

// Export
window.ArbionPanel = {
    formatMoney,
    formatDate,
    formatTime,
    escapeHtml,
    getStatusLabel,
    apiGet,
    apiPost,
};
