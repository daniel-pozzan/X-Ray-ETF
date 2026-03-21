import sys
import json
import logging
import requests
import pandas as pd
import io
import os
from bs4 import BeautifulSoup
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# Set up logging to stderr so stdout is strictly json
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger(__name__)

def fetch_etf_composition(isin: str):
    logger.info(f"Looking for ETF with ISIN: {isin}")
    
    results = []
    # Use DDGS to find the ETF page
    try:
        with DDGS() as ddgs_client:
            results = list(ddgs_client.text(f'site:ishares.com "{isin}"', max_results=5))
    except Exception as e:
        logger.warning(f"Error using DDGS: {e}. Attempting manual HTML fallback.")

    if not results:
        logger.info("DDGS library yielded no results or failed. Using html.duckduckgo.com POST fallback.")
        try:
            fallback_resp = requests.post(
                "https://html.duckduckgo.com/html/",
                data={"q": f'site:ishares.com "{isin}"'},
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
                timeout=15
            )
            fallback_resp.raise_for_status()
            fallback_soup = BeautifulSoup(fallback_resp.text, 'html.parser')
            for a in fallback_soup.find_all('a', class_='result__url'):
                href = a.get('href')
                if href and 'ishares.com' in href:
                    # Clean DuckDuckGo redirect url if necessary
                    if href.startswith('//duckduckgo.com/l/?uddg='):
                        from urllib.parse import unquote
                        href = unquote(href.split('uddg=')[1].split('&')[0])
                    results.append({'href': href})
        except Exception as e:
            logger.error(f"Fallback HTTP POST search failed: {e}")

    if not results:
        logger.error(f"No results found for ISIN {isin} even with fallback.")
        sys.exit(1)

    # Filter for product pages
    product_url = None
    for res in results:
        url = res.get('href', '')
        if '/products/' in url or '/prodotti/' in url or any(char.isdigit() for char in url.split('/')[-1]):
            product_url = url
            break
            
    if not product_url:
        # Fallback to the first result
        product_url = results[0].get('href')

    if not product_url:
        logger.error("No valid URL found.")
        sys.exit(1)

    logger.info(f"Using ETF URL: {product_url}")

    # Access the iShares page to find the CSV link
    # Append siteEntryPassthrough=true
    if '?' in product_url:
        url_with_bypass = product_url + '&siteEntryPassthrough=true'
    else:
        url_with_bypass = product_url + '?siteEntryPassthrough=true'

    cookies = {
        'cookieConsent': 'true',
        'bci-accept': 'true'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }

    try:
        resp = requests.get(url_with_bypass, headers=headers, cookies=cookies, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch iShares page: {e}")
        sys.exit(1)

    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Find CSV link
    csv_link = None
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if 'fileType=csv' in href and ('holdings' in href.lower() or 'fund' in href.lower()):
            csv_link = href
            break

    if not csv_link:
        logger.error("Could not find CSV link on the page.")
        sys.exit(1)
        
    if csv_link.startswith('/'):
        from urllib.parse import urlparse
        parsed_url = urlparse(product_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        csv_link = base_url + csv_link

    logger.info(f"Downloading CSV from: {csv_link}")

    try:
        csv_resp = requests.get(csv_link, headers=headers, cookies=cookies, timeout=15)
        csv_resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to download CSV: {e}")
        sys.exit(1)

    # Decode and parse CSV
    content = csv_resp.content.decode('utf-8-sig') # Handle BOM if present
    
    # Save raw CSV for debugging
    tmp_path = os.path.join(os.path.dirname(__file__), '..', '.tmp', f"{isin}_composition.csv")
    try:
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Saved raw CSV to {tmp_path}")
    except Exception as e:
        logger.warning(f"Could not save debug CSV: {e}")

    lines = content.splitlines()
    
    # Find start of table
    start_idx = 0
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if 'ticker' in line_lower or 'isin' in line_lower or 'name' in line_lower or 'nome' in line_lower:
            start_idx = i
            break
            
    if start_idx == 0 and not ('ticker' in lines[0].lower() or 'isin' in lines[0].lower()):
        logger.warning("Could not definitively find table header. Proceeding from row 0.")

    csv_data = '\n'.join(lines[start_idx:])
    
    try:
        df = pd.read_csv(io.StringIO(csv_data), skip_blank_lines=True)
    except Exception as e:
        logger.error(f"Failed to parse CSV: {e}")
        sys.exit(1)

    # Normalize column names for mapping
    df.columns = df.columns.astype(str).str.lower().str.strip()
    
    # Mapping
    col_mapping = {}
    for col in df.columns:
        if 'ticker' in col and 'ticker' not in col_mapping:
            col_mapping['ticker'] = col
        elif ('name' in col or 'nome' in col or 'issuer' in col) and 'name' not in col_mapping:
            col_mapping['name'] = col
        elif ('weight' in col or 'peso' in col or '%' in col) and 'weight' not in col_mapping:
            col_mapping['weight'] = col
        elif ('sector' in col or 'settore' in col or 'sektor' in col) and 'sector' not in col_mapping:
            col_mapping['sector'] = col

    # Check required cols: at least name and weight
    if 'name' not in col_mapping or 'weight' not in col_mapping:
        logger.error(f"Could not map essential columns. Found: {list(df.columns)}")
        sys.exit(1)

    holdings = []
    
    def safe_float(val):
        if pd.isna(val):
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        val_str = str(val).replace('%', '').replace(',', '.').strip()
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    for _, row in df.iterrows():
        weight_val = row.get(col_mapping['weight'])
        w = safe_float(weight_val)
        
        if w <= 0.0:
            continue # skip totals or cash if negative/zero
            
        ticker_val = row.get(col_mapping.get('ticker', ''), "-")
        if pd.isna(ticker_val) or str(ticker_val).strip() == "":
            ticker_val = "-"
            
        name_val = row.get(col_mapping.get('name', ''), "-")
        if pd.isna(name_val) or str(name_val).strip() == "":
            name_val = "-"
            
        sector_val = row.get(col_mapping.get('sector', ''), "-")
        if pd.isna(sector_val) or str(sector_val).strip() == "":
            sector_val = "-"
            
        holdings.append({
            "ticker": str(ticker_val).strip(),
            "name": str(name_val).strip(),
            "weight": w,
            "sector": str(sector_val).strip()
        })
        
    print(json.dumps(holdings))
    sys.exit(0)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python fetch_etf_composition.py <ISIN>")
        sys.exit(1)
    fetch_etf_composition(sys.argv[1])
