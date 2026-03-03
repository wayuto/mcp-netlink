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
if sys.platform == "win32":
    sys.stderr.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("MCP-Tools")

from ddgs import DDGS

# Create a combined MCP server
mcp = FastMCP("MCP-Tools")

# Global cache for URL content
_url_cache: dict = {}
MAX_CHUNK_SIZE = 64 * 1024  # 64KB max characters per chunk


# ==================== Calculator ====================
@mcp.tool()
def calculator(python_expression: str) -> dict:
    """For mathematical calculation, always use this tool to calculate the result of a python expression. You can use 'math' or 'random' directly, without 'import'.

    Args:
        python_expression: A Python expression to evaluate (e.g., '2+2', 'math.sqrt(16)')
    """
    start_time = time.time()
    logger.info(f"[Calculator] Evaluating expression: {python_expression}")
    try:
        result = eval(python_expression, {"math": math, "random": random})
        elapsed = time.time() - start_time
        logger.info(
            f"[Calculator] Success: {python_expression} = {result} (took {elapsed:.3f}s)"
        )
        return {"success": True, "result": result}
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"[Calculator] Failed: {python_expression} -> {type(e).__name__}: {e} (took {elapsed:.3f}s)"
        )
        return {"success": False, "error": str(e)}


# ==================== Web Search ====================
@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web using Bing.

    Args:
        query: The search query
        max_results: Maximum number of results to return (default: 5)
    """
    start_time = time.time()
    logger.info(
        f"[Search] Starting search: query='{query}', max_results={max_results}, backend=bing"
    )
    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results, backend="bing"):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", ""),
                    }
                )
                logger.debug(
                    f"[Search] Found: {r.get('title', '')[:50]}... -> {r.get('href', '')}"
                )

        elapsed = time.time() - start_time
        logger.info(
            f"[Search] Completed: query='{query}' -> {len(results)} results (took {elapsed:.3f}s)"
        )
        return {"success": True, "results": results, "count": len(results)}
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(
            f"[Search] Failed: query='{query}' -> {type(e).__name__}: {e} (took {elapsed:.3f}s)"
        )
        return {"success": False, "error": str(e)}


# ==================== Open URL ====================
@mcp.tool()
def open_url(url: str, chunk_index: int = -1, max_retries: int = 3) -> dict:
    """Fetch a URL and return the plain text content. Supports chunked reading for large content.

    Args:
        url: The URL to fetch
        chunk_index: Which chunk to read. -1 returns metadata and first chunk (default: -1)
                     0, 1, 2... returns the corresponding chunk
        max_retries: Maximum number of retries on failure (default: 3)

    Returns:
        If chunk_index == -1: returns metadata with total_chunks and first chunk content
        If chunk_index >= 0: returns the specified chunk content
    """
    global _url_cache
    start_time = time.time()

    # If content is cached and chunk_index >= 0, return the chunk directly
    if url in _url_cache and chunk_index >= 0:
        cached = _url_cache[url]
        total_chunks = cached["total_chunks"]
        logger.info(
            f"[OpenURL] Cache hit: url={url}, returning chunk {chunk_index}/{total_chunks}"
        )
        if chunk_index >= total_chunks:
            logger.warning(
                f"[OpenURL] Invalid chunk_index {chunk_index}, max is {total_chunks-1}"
            )
            return {
                "success": False,
                "error": f"chunk_index {chunk_index} out of range (0-{total_chunks-1})",
            }
        elapsed = time.time() - start_time
        logger.info(
            f"[OpenURL] Cache served: chunk {chunk_index}/{total_chunks} (took {elapsed:.3f}s)"
        )
        return {
            "success": True,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "content": cached["chunks"][chunk_index],
        }

    logger.info(
        f"[OpenURL] Cache miss, fetching: url={url}, chunk_index={chunk_index}, max_retries={max_retries}"
    )

    # Fetch and process the URL
    last_error = None
    for attempt in range(max_retries):
        try:
            logger.info(f"[OpenURL] Attempt {attempt + 1}/{max_retries}: {url}")
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; MCPCalculator/1.0)"},
            )
            fetch_start = time.time()
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read().decode("utf-8", errors="ignore")
            fetch_elapsed = time.time() - fetch_start
            original_size = len(html)
            logger.info(
                f"[OpenURL] Downloaded {original_size} chars in {fetch_elapsed:.3f}s"
            )

            # Remove <script> and <style> content
            text = re.sub(
                r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
            )
            text = re.sub(
                r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE
            )
            filtered_size = len(text)
            logger.debug(
                f"[OpenURL] Filtered: {original_size} -> {filtered_size} chars (removed {original_size - filtered_size})"
            )

            # Clean up whitespace
            text = re.sub(r"\s+", " ", text)
            text = text.strip()

            # Split into chunks dynamically
            # Ensure each chunk is at most MAX_CHUNK_SIZE (1.5MB)
            total_length = len(text)
            chunk_size = min(MAX_CHUNK_SIZE, total_length)
            total_chunks = max(1, (total_length + chunk_size - 1) // chunk_size)
            chunks = [
                text[i : i + chunk_size] for i in range(0, total_length, chunk_size)
            ]

            # Cache the result
            _url_cache[url] = {
                "total_chunks": total_chunks,
                "total_length": total_length,
                "chunks": chunks,
            }
            elapsed = time.time() - start_time
            logger.info(
                f"[OpenURL] Success: {total_length} chars, {total_chunks} chunks, cached (took {elapsed:.3f}s)"
            )

            # Return based on chunk_index
            if chunk_index == -1:
                return {
                    "success": True,
                    "total_chunks": total_chunks,
                    "total_length": total_length,
                }
            else:
                if chunk_index >= total_chunks:
                    return {
                        "success": False,
                        "error": f"chunk_index {chunk_index} out of range (0-{total_chunks-1})",
                    }
                return {
                    "success": True,
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks,
                    "content": chunks[chunk_index],
                }
        except Exception as e:
            last_error = e
            logger.warning(
                f"[OpenURL] Attempt {attempt + 1} failed: {type(e).__name__}: {e}"
            )
            if attempt < max_retries - 1:
                wait_time = 2**attempt  # Exponential backoff: 1, 2, 4 seconds
                logger.info(f"[OpenURL] Retrying in {wait_time}s...")
                time.sleep(wait_time)

    elapsed = time.time() - start_time
    logger.error(
        f"[OpenURL] All {max_retries} attempts failed for {url}: {last_error} (took {elapsed:.3f}s)"
    )
    return {"success": False, "error": str(last_error)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
