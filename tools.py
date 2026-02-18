from typing import Dict, Any, List, Optional
from datetime import datetime
import asyncio
import httpx
import os
import platform
import re
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
# How many extra results to request from SearXNG to compensate for filtered-out ones.
# e.g. if num_results=2 and multiplier=5, we ask for 10 then filter down to 2.
_search_fetch_multiplier = int(os.getenv("SEARCH_FETCH_MULTIPLIER", "5"))
_search_max_fetch = int(os.getenv("SEARCH_MAX_FETCH", "20"))  # hard cap sent to SearXNG

# --- URL Blocklist ---
# Hard-coded domains that return no useful text content (video/social/media platforms)
_BLOCKED_DOMAINS_DEFAULT = {
    # Video platforms
    "youtube.com", "youtu.be", "aparat.com", "vimeo.com", "dailymotion.com",
    "twitch.tv", "tiktok.com", "rumble.com", "odysee.com", "bitchute.com",
    "filimo.com", "namava.ir", "telewebion.com",
    # Pure social / short content
    "instagram.com", "twitter.com", "x.com", "facebook.com",
    "t.me", "telegram.me",
    # Audio
    "spotify.com", "soundcloud.com", "podcast.ir",
    # Maps / image search
    "maps.google.com", "google.com/maps",
    # Download aggregators (usually paywalled or binary)
    "4shared.com", "mediafire.com", "zippyshare.com", "uploadfiles.io",
}

# Extra domains from environment variable (comma-separated)
_extra_blocked = os.getenv("BLOCKED_DOMAINS", "")
_BLOCKED_DOMAINS: set = _BLOCKED_DOMAINS_DEFAULT | {
    d.strip().lower() for d in _extra_blocked.split(",") if d.strip()
}

# File extensions that are not readable text
_BLOCKED_EXTENSIONS_DEFAULT = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff",
    ".mp4", ".mp3", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
    ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".rar", ".7z", ".tar", ".gz",
    ".exe", ".dmg", ".apk", ".deb", ".rpm",
}
_extra_ext = os.getenv("BLOCKED_EXTENSIONS", "")
_BLOCKED_EXTENSIONS: set = _BLOCKED_EXTENSIONS_DEFAULT | {
    e.strip().lower() for e in _extra_ext.split(",") if e.strip()
}


def _is_blocked_url(url: str) -> bool:
    """Return True if this URL should be excluded from search results."""
    try:
        # Normalize
        url_lower = url.lower().split("?")[0].split("#")[0]
        # Check extension
        if any(url_lower.endswith(ext) for ext in _BLOCKED_EXTENSIONS):
            return True
        # Extract domain (strip scheme)
        domain = re.sub(r"^https?://", "", url_lower).split("/")[0]
        # Remove port
        domain = domain.split(":")[0]
        # Check exact domain and parent domains (e.g. "sub.youtube.com" → blocked by "youtube.com")
        parts = domain.split(".")
        for i in range(len(parts) - 1):
            candidate = ".".join(parts[i:])
            if candidate in _BLOCKED_DOMAINS:
                return True
    except Exception:
        pass
    return False


async def _searxng_search(query: str, num_results: int) -> List[Dict[str, Any]]:
    try:
        # Request more than needed so filtering still leaves enough usable results
        fetch_count = min(num_results * _search_fetch_multiplier, _search_max_fetch)
        params = {
            "q": query,
            "format": "json",
            "language": "auto",
            "safesearch": 1,
            "count": fetch_count,
        }
        async with httpx.AsyncClient(timeout=_searxng_timeout) as client:
            resp = await client.get(f"{_searxng_base_url}/search", params=params)
            resp.raise_for_status()
            data = resp.json()
        raw_results = data.get("results") or []
        cleaned = []
        blocked_count = 0
        for item in raw_results:
            url = item.get("url")
            if not url:
                continue
            if _is_blocked_url(url):
                blocked_count += 1
                logger.debug(f"Blocked URL filtered: {url}")
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
        logger.info(
            f"SearXNG: requested {fetch_count}, got {len(raw_results)}, "
            f"filtered {blocked_count} blocked → {len(cleaned)} usable for query: {query}"
        )
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

    if tool_name == "datetime":
        return get_current_datetime()

    if tool_name == "system_info":
        return get_system_info()

    return f"Unknown tool: {tool_name}"


def get_current_datetime() -> str:
    """Returns the current local date and time with weekday info."""
    now = datetime.now()
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    weekdays_fa = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه", "شنبه", "یکشنبه"]
    return (
        f"Current system date and time:\n"
        f"- ISO: {now.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"- Day of week: {weekdays[now.weekday()]} / {weekdays_fa[now.weekday()]}\n"
        f"- Time zone: local (server)\n"
    )


def get_system_info() -> str:
    """Returns basic information about the host OS and Python runtime."""
    return (
        f"Host system information:\n"
        f"- OS: {platform.system()} {platform.release()} ({platform.version()})\n"
        f"- Architecture: {platform.machine()}\n"
        f"- Python: {platform.python_version()}\n"
        f"- Processor: {platform.processor() or 'N/A'}\n"
    )
