from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import json
import logging
import os
import sqlite3
import time

app = FastAPI(title="X-Ray ETF API")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  Cache configuration
# ──────────────────────────────────────────────
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days
_BASE_DIR = os.path.dirname(__file__)
_TMP_DIR = os.path.join(_BASE_DIR, "../.tmp")
os.makedirs(_TMP_DIR, exist_ok=True)
CACHE_DB_PATH = os.path.join(_TMP_DIR, "cache.db")


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etf_cache (
            isin        TEXT PRIMARY KEY,
            data        TEXT NOT NULL,
            partial     INTEGER NOT NULL DEFAULT 0,
            fetched_at  INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _cache_get(isin: str) -> dict | None:
    """Return cached entry or None if expired / missing."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT data, partial, fetched_at FROM etf_cache WHERE isin = ?",
            (isin.upper(),),
        ).fetchone()
    if row is None:
        return None
    data, partial, fetched_at = row
    if time.time() - fetched_at > CACHE_TTL_SECONDS:
        logger.info(f"[Cache] Entry for {isin} is stale (>30 days). Evicting.")
        with _get_db() as conn:
            conn.execute("DELETE FROM etf_cache WHERE isin = ?", (isin.upper(),))
        return None
    logger.info(f"[Cache] HIT for {isin}")
    return {"holdings": json.loads(data), "partial": bool(partial)}


def _cache_set(isin: str, holdings: list, partial: bool) -> None:
    """Persist holdings to the cache."""
    with _get_db() as conn:
        conn.execute(
            """
            INSERT INTO etf_cache (isin, data, partial, fetched_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(isin) DO UPDATE SET
                data       = excluded.data,
                partial    = excluded.partial,
                fetched_at = excluded.fetched_at
            """,
            (isin.upper(), json.dumps(holdings), int(partial), int(time.time())),
        )
    logger.info(f"[Cache] Stored {len(holdings)} holdings for {isin} (partial={partial})")


def _is_partial(holdings: list) -> bool:
    """
    Flag data as partial when:
      - fewer than 11 unique holdings, OR
      - total weight is below 80%  (suggesting only a top-N subset was returned)
    """
    if len(holdings) <= 10:
        return True
    total_weight = sum(h.get("weight", 0) for h in holdings)
    return total_weight < 80.0


# ──────────────────────────────────────────────
#  Static / UI routes
# ──────────────────────────────────────────────
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(_BASE_DIR, "../frontend")),
    name="static",
)


@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(_BASE_DIR, "../frontend/index.html"))


@app.get("/not-found")
async def serve_not_found():
    return FileResponse(os.path.join(_BASE_DIR, "../frontend/not-found.html"))


# ──────────────────────────────────────────────
#  ETF API
# ──────────────────────────────────────────────
@app.get("/api/etf/{isin}")
async def get_etf_composition(isin: str):
    isin = isin.strip().upper()
    logger.info(f"[API] Request for ISIN: {isin}")

    # 1. Try cache first
    cached = _cache_get(isin)
    if cached:
        return {
            "isin": isin,
            "holdings": cached["holdings"],
            "partialData": cached["partial"],
            "fromCache": True,
        }

    # 2. Run the execution script
    script_path = os.path.join(_BASE_DIR, "../execution/fetch_etf_composition.py")
    process = await asyncio.create_subprocess_exec(
        "python", script_path, isin,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode == 2:
        logger.warning(f"[API] ETF Not Found: {isin}. stderr: {stderr.decode().strip()}")
        raise HTTPException(status_code=404, detail="ETF not found or not supported")
    elif process.returncode != 0:
        logger.error(f"[API] Script error for {isin}. stderr: {stderr.decode()}")
        raise HTTPException(status_code=500, detail="Failed to fetch ETF composition.")

    try:
        holdings = json.loads(stdout.decode())
    except json.JSONDecodeError:
        logger.error(f"[API] JSON decode error for {isin}. stdout: {stdout.decode()[:500]}")
        raise HTTPException(status_code=500, detail="Failed to parse composition data.")

    partial = _is_partial(holdings)

    # 3. Store in cache
    _cache_set(isin, holdings, partial)

    return {
        "isin": isin,
        "holdings": holdings,
        "partialData": partial,
        "fromCache": False,
    }
