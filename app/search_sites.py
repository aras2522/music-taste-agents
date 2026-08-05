from __future__ import annotations

import re
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.tools import USER_AGENT, fetch_page, unwrap_result_url

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=settings.request_timeout_s,
        headers=HEADERS,
        follow_redirects=True,
    )


def _clean(text: str, limit: int = 5000) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text[:limit] + ("\n…[truncated]" if len(text) > limit else "")


async def pitchfork_search(query: str, max_results: int = 8) -> tuple[str, list[str]]:
    url = f"https://pitchfork.com/search/?q={quote_plus(query)}"
    async with _client() as client:
        resp = await client.get(url)
    if resp.status_code >= 400:
        return f"Pitchfork search failed HTTP {resp.status_code}", []

    soup = BeautifulSoup(resp.text, "lxml")
    links: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for a in soup.select('a[href*="/reviews/"], a[href*="/artists/"], a[href*="/news/"], a[href*="/features/"]'):
        href = a.get("href", "")
        if href.startswith("/"):
            href = "https://pitchfork.com" + href
        if "pitchfork.com" not in href or href in seen:
            continue
        # skip nav / section indexes
        path = urlparse(href).path.rstrip("/")
        if path in {
            "",
            "/reviews",
            "/reviews/albums",
            "/news",
            "/artists",
            "/features",
            "/features/lists-and-guides",
        }:
            continue
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 2:
            continue
        # Prefer concrete pages; boost if query terms appear in title/url
        score = 0
        if "/reviews/albums/" in href:
            score = 3
        elif "/artists/" in href:
            score = 2
        elif "/news/" in href or "/features/" in href:
            score = 1
        q_tokens = [t for t in re.split(r"[^a-z0-9]+", query.lower()) if len(t) >= 3]
        blob = f"{title} {href}".lower()
        if q_tokens and all(t in blob for t in q_tokens):
            score += 5
        elif q_tokens and any(t in blob for t in q_tokens):
            score += 2
        seen.add(href)
        links.append((score, title, href))
        if len(links) >= max_results * 2:
            break

    ranked = [(t, u) for _, t, u in sorted(links, key=lambda x: -x[0])[:max_results]]

    if not ranked:
        return f"No Pitchfork search hits for `{query}`", []

    blob = f"Pitchfork search for `{query}`:\n" + "\n".join(f"- {t}\n  URL: {u}" for t, u in ranked)
    return blob, [u for _, u in ranked]


async def google_site_search(query: str, site: str, max_results: int = 6) -> tuple[str, list[str]]:
    q = f"site:{site} {query}"
    url = f"https://www.google.com/search?q={quote_plus(q)}&hl=en&num=10"
    async with _client() as client:
        resp = await client.get(url)
    if resp.status_code >= 400:
        return f"Google search failed HTTP {resp.status_code} for `{q}`", []

    soup = BeautifulSoup(resp.text, "lxml")
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.select("a"):
        href = a.get("href", "")
        # Google wraps as /url?q=
        if href.startswith("/url?"):
            qs = parse_qs(urlparse(href).query)
            href = qs.get("q", [""])[0]
        href = unwrap_result_url(href)
        if site not in href or href in seen:
            continue
        if not href.startswith("http"):
            continue
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 3:
            continue
        seen.add(href)
        links.append((title, href))
        if len(links) >= max_results:
            break

    if not links:
        return f"No Google hits for `{q}`", []
    blob = f"Google results for `{q}`:\n" + "\n".join(f"- {t}\n  URL: {u}" for t, u in links)
    return blob, [u for _, u in links]


async def duckduckgo_site_search(query: str, site: str, max_results: int = 6) -> tuple[str, list[str]]:
    """Fallback; often blocked with HTTP 202."""
    from app.tools import web_search

    blob = await web_search(query=query, site=site, max_results=max_results)
    urls: list[str] = []
    for match in re.finditer(r"URL:\s*(\S+)", blob):
        raw = unwrap_result_url(match.group(1).rstrip(").,;"))
        if site in raw and raw not in urls:
            urls.append(raw)
    return blob, urls


async def site_search(query: str, site: str) -> tuple[str, list[str]]:
    if site == "pitchfork.com":
        blob, urls = await pitchfork_search(query)
        if urls:
            return blob, urls

    blob, urls = await google_site_search(query, site)
    if urls:
        return blob, urls

    return await duckduckgo_site_search(query, site)


async def gather_source_evidence(seeds: list[str], taste: str, allowed_site: str) -> str:
    if allowed_site == "bandcamp.com":
        from app.bandcamp_source import gather_bandcamp_evidence

        return await gather_bandcamp_evidence(seeds, taste)

    if allowed_site == "rateyourmusic.com":
        from app.rym_source import gather_rym_evidence

        return await gather_rym_evidence(seeds, taste)

    if allowed_site == "pitchfork.com":
        from app.pitchfork_source import gather_pitchfork_evidence

        return await gather_pitchfork_evidence(seeds, taste)

    primary = seeds[0] if seeds else taste.strip().split(",")[0].strip()
    queries = [
        primary,
        f"{primary} review",
        f"{primary} similar artists OR sounds like OR like",
    ]
    chunks: list[str] = []
    seen_urls: set[str] = set()

    for query in queries:
        blob, urls = await site_search(query, allowed_site)
        chunks.append(blob)
        for url in urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            page = await fetch_page(url)
            if page.startswith("Error"):
                chunks.append(page)
                continue
            chunks.append(page)
            if len(seen_urls) >= 5:
                break
        if len(seen_urls) >= 5:
            break

    return _clean("\n\n---\n\n".join(chunks), limit=28000)
