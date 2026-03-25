try:
    import etfpy
    print("etfpy installed")
except ImportError:
    print("etfpy NOT installed")

try:
    import yfinance as yf
    print("yfinance installed")
    ticker = yf.Ticker("IE00B4L5Y983")
    print(f"yfinance info keys: {list(ticker.info.keys())[:5] if ticker.info else 'None'}")
    print(f"yfinance symbol: {ticker.info.get('symbol')}")
except ImportError:
    print("yfinance NOT installed")
except Exception as e:
    print(f"yfinance error: {e}")
