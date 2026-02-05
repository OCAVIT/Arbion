/**
 * Arbion Admin Dashboard JavaScript
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

function formatDateTime(dateStr) {
    return new Date(dateStr).toLocaleString('ru-RU');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// API helpers
async function apiGet(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
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
    return response.json();
}

async function apiPut(url, data = {}) {
    const response = await fetch(url, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
    });
    return response.json();
}

async function apiDelete(url) {
    const response = await fetch(url, {
        method: 'DELETE',
    });
    return response.json();
}

// Chart helpers
function initOrdersChart(ctx, data) {
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: 'Покупка',
                    data: data.buy_orders,
                    borderColor: '#22c55e',
                    backgroundColor: 'rgba(34, 197, 94, 0.1)',
                    tension: 0.3,
                    fill: true,
                },
                {
                    label: 'Продажа',
                    data: data.sell_orders,
                    borderColor: '#eab308',
                    backgroundColor: 'rgba(234, 179, 8, 0.1)',
                    tension: 0.3,
                    fill: true,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#a0a0a0',
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: '#a0a0a0' },
                    grid: { color: '#333333' },
                },
                y: {
                    ticks: { color: '#a0a0a0' },
                    grid: { color: '#333333' },
                },
            },
        },
    });
}

function initFunnelChart(ctx, data) {
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.stages,
            datasets: [
                {
                    label: 'Сделок',
                    data: data.values,
                    backgroundColor: [
                        '#6366f1',
                        '#8b5cf6',
                        '#a855f7',
                        '#3b82f6',
                        '#22c55e',
                    ],
                    borderRadius: 4,
                },
            ],
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            plugins: {
                legend: {
                    display: false,
                },
            },
            scales: {
                x: {
                    ticks: { color: '#a0a0a0' },
                    grid: { color: '#333333' },
                },
                y: {
                    ticks: { color: '#a0a0a0' },
                    grid: { display: false },
                },
            },
        },
    });
}

// Toast notifications
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-show');
    }, 10);

    setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Confirm dialog
function confirmAction(message) {
    return window.confirm(message);
}

// Export
window.Arbion = {
    formatMoney,
    formatDate,
    formatDateTime,
    escapeHtml,
    apiGet,
    apiPost,
    apiPut,
    apiDelete,
    initOrdersChart,
    initFunnelChart,
    showToast,
    confirmAction,
};
