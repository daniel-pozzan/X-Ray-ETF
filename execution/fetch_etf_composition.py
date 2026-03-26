import sys
import json
import logging
import os

# 1. Clear ANY existing logging handlers to prevent leaks to stdout
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# 2. Configure logging strictly to stderr
# 'force=True' ensures this overrides any default config from dependencies
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(levelname)s: %(message)s",
    force=True
)
logger = logging.getLogger(__name__)

# 3. Silence noisy dependencies or ensure they use root config
for module in ["peewee", "yfinance", "urllib3", "requests"]:
    m_logger = logging.getLogger(module)
    m_logger.setLevel(logging.WARNING)
    m_logger.propagate = True


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
        # Handle cases like "5,2%" or "5.2" or 5.2
        s_val = str(val).replace("%", "").replace(",", ".").strip()
        return float(s_val)
    except (ValueError, AttributeError):
        return 0.0


def isin_to_ticker(isin: str) -> str | None:
    """
    Use yfinance to resolve an ISIN to a Ticker symbol.
    Tries direct lookup and Search API.
    """
    try:
        import yfinance as yf
        logger.info(f"[🔄 Fallback] Attempting ISIN→Ticker conversion for {isin}")
        
        # Method A: Direct Ticker (some ISINs work directly if known as symbols)
        result = yf.Ticker(isin)
        try:
            symbol = result.info.get("symbol")
            if symbol and symbol.upper() != isin.upper():
                logger.info(f"[🔄 Fallback] Resolved via info: {isin} → {symbol}")
                return symbol
        except Exception:
            pass

        # Method B: Search API (more reliable for ISINs)
        try:
            search = yf.Search(isin, max_results=3)
            if search.quotes:
                # Pick the first one that looks like a valid ticker
                symbol = search.quotes[0].get('symbol')
                if symbol:
                    logger.info(f"[🔄 Fallback] Resolved via search: {isin} → {symbol}")
                    return symbol
        except Exception as se:
            logger.debug(f"[🔄 Fallback] yfinance Search failed: {se}")

    except Exception as e:
        logger.warning(f"[🔄 Fallback] yfinance resolution failed for {isin}: {e}")
    return None


def fetch_via_etfpy(identifier: str) -> list | None:
    """
    Attempt to retrieve ETF holdings using etfpy.
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
            logger.error(f"[📡 etfpy] Missing required columns for {identifier}. Found: {list(holdings_df.columns)}")
            return None

        holdings = []
        for _, row in holdings_df.iterrows():
            w = safe_float(row.get(col_map.get("weight", ""), 0.0))
            if w <= 0.0:
                continue

            ticker_val = str(row.get(col_map.get("ticker", ""), "-")).strip() or "-"
            name_val = str(row.get(col_map.get("name", ""), "-")).strip() or "-"
            sector_val = str(row.get(col_map.get("sector", ""), "-")).strip() or "-"

            if name_val in ("-", "", "nan", "None") and ticker_val in ("-", "", "nan", "None"):
                continue

            holdings.append({
                "ticker": ticker_val,
                "name": name_val,
                "weight": w,
                "sector": sector_val,
            })

        if not holdings:
            return None

        logger.info(f"[📡 etfpy] Retrieved {len(holdings)} holdings for {identifier}")
        return holdings

    except Exception as e:
        logger.warning(f"[📡 etfpy] Failed for identifier '{identifier}': {e}")
        return None


def fetch_via_yfinance_direct(identifier: str) -> list | None:
    """
    Attempt to retrieve ETF holdings directly from yfinance metadata.
    """
    try:
        import yfinance as yf
        logger.info(f"[💹 yfinance] Attempting direct extraction for {identifier}")
        ticker = yf.Ticker(identifier)
        
        holdings_list = []
        
        # Try funds_data (Modern yfinance)
        try:
            if hasattr(ticker, 'funds_data') and ticker.funds_data and hasattr(ticker.funds_data, 'top_holdings'):
                df = ticker.funds_data.top_holdings
                if df is not None and not df.empty:
                    for symbol, row in df.iterrows():
                        holdings_list.append({
                            "ticker": str(symbol),
                            "name": str(row.get('Name', symbol)),
                            "weight": safe_float(row.get('Holding', 0.0)) * 100,
                            "sector": "-"
                        })
                    return holdings_list
        except Exception:
            pass

        # Try info['holdings'] (Traditional)
        info = ticker.info
        raw_holdings = info.get('holdings')
        if raw_holdings and isinstance(raw_holdings, list):
            for h in raw_holdings:
                holdings_list.append({
                    "ticker": h.get("symbol", "-"),
                    "name": h.get("holdingName", h.get("symbol", "-")),
                    "weight": safe_float(h.get("holdingPercent", 0.0)) * 100,
                    "sector": "-"
                })
            return holdings_list

        return None
    except Exception as e:
        logger.warning(f"[💹 yfinance] Direct extraction failed for {identifier}: {e}")
        return None


def fetch_etf_composition(isin: str):
    # REDIRECT STDOUT TO STDERR during processing to catch any accidental prints from libs
    original_stdout = sys.stdout
    sys.stdout = sys.stderr
    
    holdings = None
    try:
        # Step 1: Direct ISIN via etfpy
        holdings = fetch_via_etfpy(isin)

        # Step 2: Resolve ISIN to Ticker, then retry etfpy
        ticker = None
        if holdings is None:
            ticker = isin_to_ticker(isin)
            if ticker:
                holdings = fetch_via_etfpy(ticker)

        # Step 3: Direct yfinance extraction (as ISIN or Ticker)
        if holdings is None:
            holdings = fetch_via_yfinance_direct(isin)
            if holdings is None and ticker:
                holdings = fetch_via_yfinance_direct(ticker)

    except Exception as e:
        logger.error(f"[🔥 Critical] Uncaught error during extraction: {e}")
    finally:
        # RESTORE STDOUT
        sys.stdout = original_stdout

    if holdings:
        # Final output is the ONLY thing allowed on stdout
        print(json.dumps(holdings))
        sys.exit(0)
    else:
        logger.error(f"[❌ Not Found] Could not find holdings for {isin} via any provider.")
        sys.exit(2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python fetch_etf_composition.py <ISIN>")
        sys.exit(1)
    fetch_etf_composition(sys.argv[1].strip().upper())
