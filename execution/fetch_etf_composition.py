import sys
import json
import logging
import os

# Set up logging to stderr so stdout is strictly JSON
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def safe_float(val) -> float:
    """Convert any value to float, return 0.0 on failure."""
    if val is None:
        return 0.0
    try:
        import pandas as pd
        if pd.isna(val):
            return 0.0
    except Exception:
        pass
    try:
        return float(str(val).replace("%", "").replace(",", ".").strip())
    except (ValueError, AttributeError):
        return 0.0


def isin_to_ticker(isin: str) -> str | None:
    """
    Use yfinance to resolve an ISIN to a Ticker symbol.
    Returns the ticker string or None if not found.
    """
    try:
        import yfinance as yf
        logger.info(f"[🔄 Fallback] Attempting ISIN→Ticker conversion via yfinance for {isin}")
        result = yf.Ticker(isin)
        info = result.info
        # yfinance returns the ticker in 'symbol' if it resolves successfully
        symbol = info.get("symbol")
        if symbol and symbol.upper() != isin.upper():
            logger.info(f"[🔄 Fallback] Resolved {isin} → {symbol}")
            return symbol
    except Exception as e:
        logger.warning(f"[🔄 Fallback] yfinance ISIN→Ticker failed for {isin}: {e}")
    return None


def fetch_via_etfpy(identifier: str) -> list | None:
    """
    Attempt to retrieve ETF holdings using etfpy.
    Returns a list of holding dicts or None on failure.
    """
    try:
        import etfpy
        logger.info(f"[📡 etfpy] Fetching holdings for identifier: {identifier}")
        etf = etfpy.load_etf(identifier)
        holdings_df = etf.holdings
        if holdings_df is None or holdings_df.empty:
            logger.warning(f"[📡 etfpy] No holdings data returned for {identifier}")
            return None

        import pandas as pd
        holdings_df.columns = holdings_df.columns.str.lower().str.strip()

        # Flexible column mapping
        col_map = {}
        for col in holdings_df.columns:
            if ("ticker" in col or "symbol" in col) and "ticker" not in col_map:
                col_map["ticker"] = col
            elif ("name" in col or "nome" in col or "issuer" in col or "company" in col or "holding" in col) and "name" not in col_map:
                col_map["name"] = col
            elif ("weight" in col or "peso" in col or "%" in col or "allocation" in col) and "weight" not in col_map:
                col_map["weight"] = col
            elif ("sector" in col or "settore" in col or "industry" in col) and "sector" not in col_map:
                col_map["sector"] = col

        if "name" not in col_map and "ticker" not in col_map:
            logger.error(f"[📡 etfpy] Could not find name/ticker columns for {identifier}. Columns: {list(holdings_df.columns)}")
            return None

        holdings = []
        for _, row in holdings_df.iterrows():
            w = safe_float(row.get(col_map.get("weight", ""), 0.0))
            if w <= 0.0:
                continue

            ticker_val = str(row.get(col_map.get("ticker", ""), "-")).strip() or "-"
            name_val = str(row.get(col_map.get("name", ""), "-")).strip() or "-"
            sector_val = str(row.get(col_map.get("sector", ""), "-")).strip() or "-"

            # Skip cash/undefined rows
            if name_val in ("-", "", "nan", "None") and ticker_val in ("-", "", "nan", "None"):
                continue

            holdings.append({
                "ticker": ticker_val,
                "name": name_val,
                "weight": w,
                "sector": sector_val,
            })

        if not holdings:
            logger.warning(f"[📡 etfpy] Holdings list empty after filtering for {identifier}")
            return None

        logger.info(f"[📡 etfpy] Successfully retrieved {len(holdings)} holdings for {identifier}")
        return holdings

    except Exception as e:
        logger.warning(f"[📡 etfpy] Failed for identifier '{identifier}': {e}")
        return None


def fetch_via_yfinance_direct(identifier: str) -> list | None:
    """
    Attempt to retrieve ETF holdings directly from yfinance metadata (funds_data or info['holdings']).
    """
    try:
        import yfinance as yf
        logger.info(f"[💹 yfinance] Attempting direct holdings extraction for {identifier}")
        ticker = yf.Ticker(identifier)
        
        holdings_list = []
        
        # Method A: funds_data (Modern yfinance)
        try:
            if hasattr(ticker, 'funds_data') and ticker.funds_data and hasattr(ticker.funds_data, 'top_holdings'):
                df = ticker.funds_data.top_holdings
                if df is not None and not df.empty:
                    logger.info(f"[💹 yfinance] Found holdings via funds_data.top_holdings")
                    for symbol, row in df.iterrows():
                        holdings_list.append({
                            "ticker": str(symbol),
                            "name": str(row.get('Name', symbol)),
                            "weight": safe_float(row.get('Holding', 0.0)) * 100, # yfinance often uses 0.0-1.0
                            "sector": "-" # yfinance top_holdings usually lacks sectors
                        })
                    return holdings_list
        except Exception as e:
            logger.debug(f"[💹 yfinance] funds_data check failed: {e}")

        # Method B: info['holdings'] (Traditional)
        info = ticker.info
        raw_holdings = info.get('holdings')
        if raw_holdings and isinstance(raw_holdings, list):
            logger.info(f"[💹 yfinance] Found holdings via info['holdings']")
            for h in raw_holdings:
                holdings_list.append({
                    "ticker": h.get("symbol", "-"),
                    "name": h.get("holdingName", h.get("symbol", "-")),
                    "weight": safe_float(h.get("holdingPercent", 0.0)) * 100,
                    "sector": "-"
                })
            return holdings_list

        logger.warning(f"[💹 yfinance] No direct holdings data found for {identifier}")
        return None

    except Exception as e:
        logger.warning(f"[💹 yfinance] Direct extraction failed for {identifier}: {e}")
        return None


def fetch_etf_composition(isin: str):
    # Step 1: Try ISIN directly via etfpy
    holdings = fetch_via_etfpy(isin)

    # Step 2: Try resolve ISIN to Ticker, then retry etfpy
    ticker = None
    if holdings is None:
        ticker = isin_to_ticker(isin)
        if ticker:
            holdings = fetch_via_etfpy(ticker)

    # Step 3: NEW Fallback — direct yfinance extraction (highest coverage, last resort)
    if holdings is None:
        # Try it for the ISIN first
        holdings = fetch_via_yfinance_direct(isin)
        # If still none and we found a ticker, try the ticker
        if holdings is None and ticker:
            holdings = fetch_via_yfinance_direct(ticker)

    if holdings is None:
        logger.error(f"[❌ Not Found] No holdings found for ISIN {isin} via etfpy or direct yfinance fallback.")
        sys.exit(2)

    print(json.dumps(holdings))
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python fetch_etf_composition.py <ISIN>")
        sys.exit(1)
    fetch_etf_composition(sys.argv[1].strip().upper())
