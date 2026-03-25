/**
 * X-Ray ETF - Frontend Application Logic
 */

// ──────────────────────────────────────────────
//  State Management
// ──────────────────────────────────────────────
let currentHoldings = [];
let sectorChart = null;
let currentSort = { col: 'weight', dir: -1 }; // Default: Weight descending

const DOM = {
    form: document.getElementById('search-form'),
    input: document.getElementById('isin-input'),
    btn: document.getElementById('search-btn'),
    statusBox: document.getElementById('status-box'),
    results: document.getElementById('results'),
    tableBody: document.getElementById('holdings-body'),
    holdingsCount: document.getElementById('holdings-count'),
    partialWarning: document.getElementById('partial-warning'),
    cacheBadge: document.getElementById('cache-badge'),
    sectorLegend: document.getElementById('sector-legend'),
    sortableTh: document.querySelectorAll('.sortable')
};

// ──────────────────────────────────────────────
//  Initialization
// ──────────────────────────────────────────────
DOM.form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const isin = DOM.input.value.trim().toUpperCase();
    if (!isin || isin.length < 5) return;
    await fetchComposition(isin);
});

DOM.sortableTh.forEach(th => {
    th.addEventListener('click', () => {
        const col = th.dataset.col;
        if (currentSort.col === col) {
            currentSort.dir *= -1;
        } else {
            currentSort.col = col;
            currentSort.dir = col === 'weight' ? -1 : 1; 
        }
        renderTable();
    });
});

// ──────────────────────────────────────────────
//  Data Fetching
// ──────────────────────────────────────────────
async function fetchComposition(isin) {
    showStatus('Analyzing ETF structure...', 'loading');
    DOM.results.classList.add('hidden');
    DOM.partialWarning.classList.add('hidden');
    DOM.cacheBadge.classList.add('hidden');
    DOM.btn.disabled = true;

    try {
        const response = await fetch(`/api/etf/${isin}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to retrieve data');
        }

        currentHoldings = data.holdings;
        
        // UI Updates
        DOM.statusBox.classList.add('hidden');
        DOM.results.classList.remove('hidden');
        DOM.holdingsCount.textContent = `${currentHoldings.length} holdings found`;
        
        if (data.partialData) DOM.partialWarning.classList.remove('hidden');
        if (data.fromCache) DOM.cacheBadge.classList.remove('hidden');

        renderTable();
        renderChart();

    } catch (err) {
        showStatus(err.message, 'error');
    } finally {
        DOM.btn.disabled = false;
    }
}

function showStatus(msg, type) {
    DOM.statusBox.textContent = msg;
    DOM.statusBox.className = `status-box status-${type}`;
    DOM.statusBox.classList.remove('hidden');
}

// ──────────────────────────────────────────────
//  Rendering Logic
// ──────────────────────────────────────────────
function renderTable() {
    // Sort
    const sorted = [...currentHoldings].sort((a, b) => {
        let valA = a[currentSort.col];
        let valB = b[currentSort.col];
        
        if (typeof valA === 'string') {
            valA = valA.toLowerCase();
            valB = valB.toLowerCase();
        }
        
        if (valA < valB) return -1 * currentSort.dir;
        if (valA > valB) return 1 * currentSort.dir;
        return 0;
    });

    // Body
    DOM.tableBody.innerHTML = sorted.map(h => `
        <tr>
            <td><strong>${h.name}</strong></td>
            <td class="row-weight">${h.weight.toFixed(2)}%</td>
            <td>${h.sector}</td>
            <td class="row-ticker">${h.ticker}</td>
        </tr>
    `).join('');
}

function renderChart() {
    // Aggregate by sector
    const sectors = {};
    currentHoldings.forEach(h => {
        const s = h.sector || 'Others';
        sectors[s] = (sectors[s] || 0) + h.weight;
    });

    // Prepare data
    const sortedSectors = Object.entries(sectors)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8); // Top 8 + Others
    
    const othersWeight = Object.entries(sectors)
        .sort((a, b) => b[1] - a[1])
        .slice(8)
        .reduce((sum, curr) => sum + curr[1], 0);

    if (othersWeight > 0) {
        sortedSectors.push(['Others', othersWeight]);
    }

    const labels = sortedSectors.map(s => s[0]);
    const values = sortedSectors.map(s => s[1]);

    // Colors
    const colors = [
        '#58a6ff', '#f78166', '#3fb950', '#a371f7', 
        '#d29922', '#1f6feb', '#ff7b72', '#79c0ff', '#8b949e'
    ];

    if (sectorChart) sectorChart.destroy();

    const ctx = document.getElementById('sector-chart').getContext('2d');
    sectorChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 0,
                hoverOffset: 15
            }]
        },
        options: {
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => ` ${ctx.label}: ${ctx.raw.toFixed(2)}%`
                    }
                }
            },
            cutout: '70%',
            responsive: true,
            maintainAspectRatio: false
        }
    });

    // Custom Legend
    DOM.sectorLegend.innerHTML = sortedSectors.map((s, i) => `
        <div class="legend-item">
            <span class="legend-color" style="background: ${colors[i % colors.length]}"></span>
            <span class="legend-label">${s[0]}</span>
            <span class="badge" style="margin-left:auto">${s[1].toFixed(1)}%</span>
        </div>
    `).join('');
}
