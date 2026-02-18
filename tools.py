from typing import Dict, Any, List, Optional
import asyncio
import httpx
import os
import trafilatura
import logging

logger = logging.getLogger(__name__)

_searxng_base_url = os.getenv("SEARXNG_BASE_URL", "http://localhost:8888")
_searxng_timeout = float(os.getenv("SEARXNG_TIMEOUT", "12"))
_fetch_timeout = float(os.getenv("FETCH_TIMEOUT", "15"))
_max_doc_chars = int(os.getenv("MAX_DOC_CHARS", "4000"))
_max_snippet_chars = int(os.getenv("MAX_SNIPPET_CHARS", "200"))
_user_agent = os.getenv(
    "FETCH_UA",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
)


async def _searxng_search(query: str, num_results: int) -> List[Dict[str, Any]]:
    try:
        params = {
            "q": query,
            "format": "json",
            "language": "auto",
            "safesearch": 1,
            "count": num_results,
        }
        async with httpx.AsyncClient(timeout=_searxng_timeout) as client:
            resp = await client.get(f"{_searxng_base_url}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
        results = data.get("results") or []
        cleaned = []
        for item in results:
            url = item.get("url")
            if not url:
                continue
            cleaned.append(
                {
                    "url": url,
                    "title": item.get("title") or "",
                    "snippet": item.get("content") or "",
                }
            )
            if len(cleaned) >= num_results:
                break
        logger.info(f"SearXNG returned {len(cleaned)} results for query: {query}")
        return cleaned
    except httpx.ConnectError as e:
        logger.error(
            f"SearXNG connection failed at {_searxng_base_url}: {e}. "
            "Make sure SearXNG is running or set SEARXNG_BASE_URL env var."
        )
        return []
    except httpx.HTTPStatusError as e:
        logger.error(f"SearXNG HTTP error {e.response.status_code}: {e}")
        return []
    except Exception as e:
        logger.error(f"SearXNG unexpected error: {e}")
        return []


def _clean_html_to_text(html: str) -> str:
    if not html:
        return ""
    text = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
        include_images=False,
        include_formatting=False,
        favor_precision=True,
        favor_recall=False,
        no_fallback=False,
        output_format="txt",
    )
    if not text:
        return ""
    cleaned = text.strip()
    lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
    cleaned = "\n".join(lines)
    if _max_doc_chars > 0 and len(cleaned) > _max_doc_chars:
        cleaned = cleaned[:_max_doc_chars] + "\n[...]"
    return cleaned


async def _fetch_url(url: str) -> Optional[str]:
    headers = {"User-Agent": _user_agent, "Accept": "text/html"}
    try:
        async with httpx.AsyncClient(timeout=_fetch_timeout, headers=headers) as client:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code != 200:
                logger.warning(f"Fetch failed for {url}: HTTP {resp.status_code}")
                return None
            return resp.text
    except httpx.TimeoutException:
        logger.warning(f"Fetch timeout for {url} after {_fetch_timeout}s")
        return None
    except httpx.ConnectError as e:
        logger.warning(f"Connection error fetching {url}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error fetching {url}: {e}")
        return None


async def search_web(query: str, num_results: int = 2) -> str:
    # فاز ۱: گرفتن نتایج از SearXNG
    results = await _searxng_search(query, num_results=num_results)
    if not results:
        return (
            f"[Search failed: SearXNG unavailable at {_searxng_base_url}]\n"
            "Please ensure SearXNG is running or configure SEARXNG_BASE_URL."
        )

    # فاز ۲: فچ لینک‌ها و پاک‌سازی متن
    async def fetch_one(item: Dict[str, Any]) -> Dict[str, Any]:
        try:
            html = await _fetch_url(item["url"])
            markdown = ""
            if html:
                markdown = await asyncio.to_thread(_clean_html_to_text, html)
            return {
                "url": item["url"],
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "markdown": markdown,
            }
        except Exception as e:
            logger.warning(f"Error processing {item['url']}: {e}")
            return {
                "url": item["url"],
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "markdown": "",
            }

    fetched = await asyncio.gather(*[fetch_one(item) for item in results])

    parts = []
    for idx, item in enumerate(fetched, start=1):
        content = item.get("markdown", "") or "[no content]"
        parts.append(
            f"## Source {idx}: {item.get('title', 'No title')}\n"
            f"URL: {item.get('url', '')}\n"
            f"{content}"
        )

    return "\n\n".join(parts)


async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> str:
    if tool_name == "search":
        return await search_web(
            query=arguments["query"], num_results=arguments.get("num_results", 2)
        )

    return f"Unknown tool: {tool_name}"
