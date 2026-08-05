from __future__ import annotations

import json
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.http_client import hardened_get


def rym_slugs(seed: str) -> list[str]:
    raw = seed.strip()
    variants = {
        raw.lower().replace(" ", "_").replace(".", "_").replace("-", "_"),
        raw.lower().replace(" ", "-").replace(".", "-"),
        raw.lower().replace(" ", "").replace(".", ""),
        re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_"),
        re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-"),
    }
    # mk.gee style
    if "." in raw:
        variants.add(raw.lower().replace(".", "_"))
        variants.add(raw.lower().replace(".", "-"))
    return [v for v in variants if v]


async def _cdx_snapshots(path: str, limit: int = 8) -> list[tuple[str, str]]:
    url = (
        "https://web.archive.org/cdx/search/cdx"
        f"?url={quote(path, safe='')}&output=json&limit={limit}&filter=statuscode:200"
        "&fl=timestamp,original"
    )
    status, text, _ = await hardened_get(url, timeout=60)
    if status >= 400 or not text.startswith("["):
        return []
    try:
        rows = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not rows:
        return []
    if rows[0] and rows[0][0] == "timestamp":
        rows = rows[1:]
    out: list[tuple[str, str]] = []
    for row in rows:
        if len(row) >= 2:
            out.append((row[0], row[1]))
    # newest first
    out.sort(key=lambda x: x[0], reverse=True)
    return out


async def _fetch_best_snapshot(path: str) -> tuple[str, str] | None:
    snaps = await _cdx_snapshots(path)
    for ts, original in snaps[:5]:
        snap_url = f"https://web.archive.org/web/{ts}id_/{original}"
        status, text, final = await hardened_get(snap_url, timeout=60)
        if status == 200 and len(text) > 15000 and "just a moment" not in text.lower():
            return final, text
    return None


def _parse_rym_artist_html(html: str, page_url: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    text = (soup.body or soup).get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    artist_links: list[str] = []
    for a in soup.select('a[href*="/artist/"]'):
        name = a.get_text(" ", strip=True)
        href = a.get("href", "")
        if not name or len(name) < 2:
            continue
        if name.lower() in {"rym", "charts", "music", "film", "games", "credits"}:
            continue
        if href.startswith("/"):
            href = "https://rateyourmusic.com" + href
        artist_links.append(f"- {name} | {href}")

    # Dedup preserve order
    seen: set[str] = set()
    uniq_links: list[str] = []
    for line in artist_links:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq_links.append(line)

    sections = [
        f"RYM archived page: {page_url}",
        f"Title: {title}",
        "Extracted text (genres/descriptors/discography/credits live here):\n" + text[:12000],
    ]
    if uniq_links:
        sections.append(
            "Artist links found on page (credits / appears-on / related):\n"
            + "\n".join(uniq_links[:40])
        )
    sections.append(
        "Instruction: recommend similar ARTISTS (people/bands) and a real album title for each. "
        "If seed genres are bedroom pop / indie pop / pop, stay in that lane — "
        "do not jump to IDM, glitchwave, downtempo, or experimental electronic. "
        "Never output genre lists as artist/album fields."
    )
    return "\n\n".join(sections)


async def gather_rym_evidence(seeds: list[str], taste: str) -> str:
    primary = seeds[0] if seeds else taste.strip().split(",")[0].strip()
    chunks = [
        f"Rate Your Music evidence for seed `{primary}`",
        "Note: live RYM is Cloudflare-protected; using Internet Archive snapshots of RYM pages.",
    ]

    found = False
    for slug in rym_slugs(primary):
        path = f"rateyourmusic.com/artist/{slug}"
        snap = await _fetch_best_snapshot(path)
        if not snap:
            continue
        page_url, html = snap
        chunks.append(_parse_rym_artist_html(html, page_url))
        found = True
        break

    if not found:
        chunks.append(
            "Could not retrieve an archived RYM artist page for this seed. "
            "Avoid inventing similar artists without RYM evidence."
        )

    return "\n\n".join(chunks)[:24000]
