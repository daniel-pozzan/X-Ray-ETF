from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import asyncio
import json
import logging
import os

app = FastAPI(title="X-Ray ETF API")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mount frontend
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "../frontend")), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "../frontend/index.html"))

@app.get("/api/etf/{isin}")
async def get_etf_composition(isin: str):
    logger.info(f"API Request for ISIN: {isin}")
    
    script_path = os.path.join(os.path.dirname(__file__), "../execution/fetch_etf_composition.py")
    
    process = await asyncio.create_subprocess_exec(
        "python", script_path, isin,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    stdout, stderr = await process.communicate()
    
    if process.returncode != 0:
        logger.error(f"Script failed with stderr: {stderr.decode()}")
        raise HTTPException(status_code=500, detail="Failed to fetch composition. Check logs.")
        
    try:
        data = json.loads(stdout.decode())
        return {"isin": isin, "holdings": data}
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON. Output: {stdout.decode()}")
        raise HTTPException(status_code=500, detail="Failed to parse composition data.")
