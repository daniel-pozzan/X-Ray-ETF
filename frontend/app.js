document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('isin-input');
    const searchBtn = document.getElementById('search-btn');
    const loader = document.getElementById('loader');
    const resultsContainer = document.getElementById('results-container');
    const errorMsg = document.getElementById('error-message');
    const tbody = document.getElementById('holdings-body');
    const stats = document.getElementById('etf-stats');

    const search = async () => {
        const isin = input.value.trim().toUpperCase();
        if (!isin) return;

        // Reset state
        loader.classList.remove('hidden');
        resultsContainer.classList.add('hidden');
        errorMsg.classList.add('hidden');
        tbody.innerHTML = '';

        try {
            const response = await fetch(`/api/etf/${isin}`);
            if (!response.ok) {
                if (response.status === 404) {
                    window.location.href = '/static/not-found.html';
                    return;
                }
                const err = await response.json();
                throw new Error(err.detail || 'Failed to fetch ETF data');
            }

            const data = await response.json();
            renderResults(data);
        } catch (error) {
            errorMsg.textContent = error.message;
            errorMsg.classList.remove('hidden');
        } finally {
            loader.classList.add('hidden');
        }
    };

    searchBtn.addEventListener('click', search);
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') search();
    });

    function renderResults(data) {
        const holdings = data.holdings;
        stats.textContent = `${holdings.length} holdings found`;

        // Sort by weight descending
        holdings.sort((a, b) => b.weight - a.weight);

        const maxWeight = holdings[0]?.weight || 100;

        holdings.forEach((h, index) => {
            const tr = document.createElement('tr');
            tr.style.animation = `fadeInUp 0.3s ease-out ${index % 50 * 0.02}s both`; // Limiting animation delay for very long lists

            const fillWidth = (h.weight / maxWeight) * 100;

            tr.innerHTML = `
                <td><span class="ticker-badge">${h.ticker !== '-' ? h.ticker : 'CASH'}</span></td>
                <td style="font-weight: 500;">${h.name}</td>
                <td style="color: var(--text-secondary); font-size: 0.9rem;">${h.sector}</td>
                <td class="right-align weight-cell">${h.weight.toFixed(2)}%</td>
                <td style="width: 150px;">
                    <div class="bar-bg">
                        <div class="bar-fill" style="width: ${fillWidth}%"></div>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });

        resultsContainer.classList.remove('hidden');
    }
});
