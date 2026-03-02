# main.py - Combined MCP Server
from fastmcp import FastMCP
import sys
import logging
import math
import random
import urllib.request
import re
import time

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stderr.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('MCP-Tools')

from ddgs import DDGS

# Create a combined MCP server
mcp = FastMCP("MCP-Tools")

# ==================== Calculator ====================
@mcp.tool()
def calculator(python_expression: str) -> dict:
    """For mathematical calculation, always use this tool to calculate the result of a python expression. You can use 'math' or 'random' directly, without 'import'.
    
    Args:
        python_expression: A Python expression to evaluate (e.g., '2+2', 'math.sqrt(16)')
    """
    try:
        result = eval(python_expression, {"math": math, "random": random})
        logger.info(f"[Calculator] {python_expression} = {result}")
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"[Calculator] Error: {e}")
        return {"success": False, "error": str(e)}

# ==================== Web Search ====================
@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web using Bing.
    
    Args:
        query: The search query
        max_results: Maximum number of results to return (default: 5)
    """
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results, backend="bing"):
                results.append({
                    "title": r.get("title", ""),
                    "href": r.get("href", ""),
                    "body": r.get("body", "")
                })
        
        logger.info(f"[Search] Query: '{query}' -> {len(results)} results")
        return {"success": True, "results": results, "count": len(results)}
    except Exception as e:
        logger.error(f"[Search] Error: {e}")
        return {"success": False, "error": str(e)}

# ==================== Open URL ====================
@mcp.tool()
def open_url(url: str, max_retries: int = 3) -> dict:
    """Fetch a URL and return the plain text content.
    
    Args:
        url: The URL to fetch
        max_retries: Maximum number of retries on failure (default: 3)
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            logger.info(f"[OpenURL] Fetching: {url} (attempt {attempt + 1}/{max_retries})")
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (compatible; MCPCalculator/1.0)'}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read().decode('utf-8', errors='ignore')
            
            # Remove script and style content only
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
            
            logger.info(f"[OpenURL] Fetched {len(text)} chars from {url}")
            return {"success": True, "content": text}
        except Exception as e:
            last_error = e
            logger.warning(f"[OpenURL] Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.info(f"[OpenURL] Retrying in {wait_time}s...")
                time.sleep(wait_time)
    
    logger.error(f"[OpenURL] All {max_retries} attempts failed: {last_error}")
    return {"success": False, "error": str(last_error)}

if __name__ == "__main__":
    mcp.run(transport="stdio")