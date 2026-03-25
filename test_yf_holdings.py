import yfinance as yf
import json

def test_yf_holdings(isin):
    ticker = yf.Ticker(isin)
    info = ticker.info
    print(f"Ticker: {info.get('symbol')}")
    
    # Check for direct holdings in info (sometimes present)
    holdings = info.get('holdings')
    if holdings:
        print("Found holdings in info")
        print(json.dumps(holdings, indent=2))
        return

    # Check funds_data (newer yfinance feature)
    try:
        if hasattr(ticker, 'funds_data'):
            fd = ticker.funds_data
            print("Found funds_data")
            if hasattr(fd, 'top_holdings'):
                print("Found top_holdings in funds_data")
                print(fd.top_holdings.to_json())
    except Exception as e:
        print(f"Error checking funds_data: {e}")

    # Check for sector weightings
    sector_w = info.get('sectorWeightings')
    if sector_w:
        print("Found sector weightings")
        print(json.dumps(sector_w, indent=2))

if __name__ == "__main__":
    test_yf_holdings("IE00B5BMR087")
    print("-" * 20)
    test_yf_holdings("CSSPX.MI")
