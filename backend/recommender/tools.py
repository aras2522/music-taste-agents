from __future__ import annotations

import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from recommender.config import settings

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

ALLOWED_HOST_SUFFIXES = (
    "bandcamp.com",
    "pitchfork.com",
    "rateyourmusic.com",
    "duckduckgo.com",
    "web.archive.org",
)


def _host_allowed(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    return any(host == s or host.endswith("." + s) for s in ALLOWED_HOST_SUFFIXES)


def unwrap_result_url(url: str) -> str:
    """DuckDuckGo HTML results often wrap targets in /l/?uddg=..."""
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    except Exception:
        pass
    return url


async def web_search(query: str, site: str | None = None, max_results: int = 6) -> str:
    """DuckDuckGo HTML search, optionally restricted to a site."""
    q = f"site:{site} {query}" if site else query
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}"
    async with httpx.AsyncClient(
        timeout=settings.request_timeout_s,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    results: list[str] = []
    for result in soup.select(".result"):
        title_el = result.select_one(".result__a")
        snippet_el = result.select_one(".result__snippet")
        if not title_el:
            continue
        href = unwrap_result_url(title_el.get("href", ""))
        title = title_el.get_text(" ", strip=True)
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        results.append(f"- {title}\n  URL: {href}\n  {snippet}")
        if len(results) >= max_results:
            break

    if not results:
        return f"No search results for: {q}"
    return f"Search results for `{q}`:\n" + "\n".join(results)



def _clean_text(text: str, limit: int = 6000) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = text.strip()
    if len(text) > limit:
        return text[:limit] + "\n…[truncated]"
    return text


async def fetch_page(url: str) -> str:
    """Fetch a page and return cleaned visible text (source domains only)."""
    if not url.startswith(("http://", "https://")):
        return "Error: URL must be http(s)."
    if not _host_allowed(url):
        return (
            "Error: URL host not allowed. "
            "Only bandcamp.com, pitchfork.com, rateyourmusic.com, duckduckgo.com, web.archive.org."
        )

    from recommender.http_client import hardened_get, looks_blocked

    status, body, final_url = await hardened_get(url)
    if status == 0:
        return body
    if looks_blocked(status, body) or status >= 400:
        return f"Error: HTTP {status} or challenge page for {url}"

    soup = BeautifulSoup(body, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        tag.decompose()

    title = (soup.title.get_text(strip=True) if soup.title else "") or ""
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True) if main else ""
    return _clean_text(f"Title: {title}\nURL: {final_url}\n\n{text}")
