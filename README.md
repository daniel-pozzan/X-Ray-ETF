# X-Ray ETF

An advanced tool to extract the complete, exhaustive composition of any Exchange-Traded Fund (ETF) using its ISIN.

## Stack
- **Backend / API**: FastAPI (Python)
- **Data Scraping**: `duckduckgo-search` (ddgs), `requests`, `beautifulsoup4`, `pandas`
- **Frontend**: Vanilla HTML/JS/CSS with a premium dark-mode/glassmorphism UI.
- **Environment**: Docker Dev Container

## Quickstart

### 1. Rebuild and Open in Container
In VS Code, press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac) and select:
**`Dev Containers: Reopen in Container`**

This will automatically build the isolated environment and install all necessary dependencies outlined in `requirements.txt`.

### 2. Run the Application
Once the container is running and the terminal is available, boot the backend server:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 3000
```

### 3. Usage
Open a web browser on your host machine to:
[http://localhost:3000](http://localhost:3000)

Enter any iShares ISIN (e.g., `IE00B4L5Y983` for iShares Core MSCI World) and explore the extensive, dynamic extraction of the ETF's holdings.
