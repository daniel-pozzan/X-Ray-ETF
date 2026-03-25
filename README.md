# X-Ray ETF (v2.0)

An advanced tool to "X-Ray" any Exchange-Traded Fund (ETF) by its ISIN, revealing its complete holdings, sector distribution, and weights.

## 🚀 Key Features
- **Deterministic Extraction**: Powered by `etfpy` with a robust `yfinance` fallback for ISIN-to-Ticker resolution.
- **Smart Caching**: Integrated SQLite caching layer that stores results for **30 days** to minimize API calls and external latency.
- **Interactive UI**: Premium dark-mode dashboard featuring **Chart.js** doughnut charts and sortable data tables.
- **Monetization Ready**: Pre-configured ad slots for Header, Sidebar, and Footer.
- **Robustness**: Automatic detection of "Partial Data" (top-N only) to ensure transparency.

## 🛠️ Stack
- **Backend / API**: FastAPI (Python)
- **Data Providers**: `etfpy`, `yfinance`, `pandas`
- **Cache**: SQLite3
- **Frontend**: Vanilla HTML/JS with **Chart.js** & **Inter** font.
- **Environment**: Docker Dev Container (Isolated environment)

## 📥 Quickstart

### 1. Rebuild and Open in Container
In VS Code, press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac) and select:
**`Dev Containers: Reopen in Container`**

*Note: As requirements have changed, a container rebuild is mandatory to install `etfpy` and `yfinance`.*

### 2. Run the Application
Once the container is ready, start the server:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Usage
Open [http://localhost:8000](http://localhost:8000) in your browser.

Enter any ISIN (e.g., `IE00B4L5Y983` for iShares Core MSCI World or `IE00B5BMR087` for Vanguard S&P 500) and explore the breakdown.

