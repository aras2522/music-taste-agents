from __future__ import annotations

import re
from urllib.parse import quote_plus

from app.lanes import is_punk_lane
from app.search_sites import pitchfork_search, _clean
from app.tools import fetch_page

_COMPARE_PATTERNS = [
    re.compile(r"((?:[A-Z][\w&']+\s*){1,3}?)-inspired\b"),
    re.compile(r"((?:[A-Z][\w&']+\s*){1,3}?)-indebted\b"),
    re.compile(
        r"((?:[A-Z][\w&']+\s*){1,3}?)\s*meets\s*((?:[A-Z][\w&']+\s*){1,3}?)\b"
    ),
    re.compile(
        r"(?:like|evokes?|recalls?|à la|in the vein of|reminiscent of)\s+((?:[A-Z][\w&']+\s*){1,3}?)\b"
    ),
    re.compile(r"\bas\s+([A-Z][\w&']+(?:\s+[A-Z][\w&']+)?)(?:['’]s)?\s+(?:wiry|guitarist)\b"),
]

_STOP = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "in",
    "on",
    "for",
    "with",
    "his",
    "her",
    "their",
    "this",
    "that",
    "album",
    "record",
    "song",
    "track",
    "music",
    "review",
    "pitchfork",
    "best",
    "new",
    "save",
    "story",
    "reader",
    "score",
    "genre",
    "label",
    "release",
    "date",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _seed_tokens(seed: str) -> list[str]:
    # Drop tiny words like "the"
    return [t for t in re.split(r"[^a-z0-9]+", seed.lower()) if len(t) >= 3]


def _relevant_to_seed(title: str, url: str, seed: str) -> bool:
    """Only keep Pitchfork hits that actually mention the seed."""
    seed_n = _norm(seed)
    blob = _norm(f"{title} {url}")
    if seed_n and seed_n in blob:
        return True
    tokens = _seed_tokens(seed)
    if tokens and all(t in blob for t in tokens):
        return True
    return False


def extract_comparison_artists(text: str, seeds: list[str]) -> list[str]:
    seed_norms = {_norm(s) for s in seeds}
    found: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        name = name.strip(" ,.;:\"'-–—")
        name = re.sub(r"['’]s$", "", name)
        parts = [p for p in name.split() if p.lower() not in _STOP and not p.lower().startswith("pop-")]
        # Drop trailing lowercase fragment words (e.g. "Arthur Russell pop-rock")
        while parts and (parts[-1][:1].islower() or "-" in parts[-1]):
            parts.pop()
        if not parts:
            return
        name = " ".join(parts[:4]).strip(" -")
        if len(name) < 3:
            return
        key = _norm(name)
        if len(key) < 4 or key in seed_norms or key in seen:
            return
        if not name[0].isupper():
            return
        seen.add(key)
        found.append(name)

    for pat in _COMPARE_PATTERNS:
        for m in pat.finditer(text):
            for g in m.groups():
                if g:
                    add(g)

    # Do NOT scrape incidental celebrity names from unrelated news sidebars.
    return found[:20]


async def gather_pitchfork_evidence(seeds: list[str], taste: str) -> str:
    primary = seeds[0] if seeds else taste.strip().split(",")[0].strip()
    chunks: list[str] = [f"Pitchfork evidence for seed `{primary}`"]
    seen_urls: set[str] = set()
    all_text: list[str] = []

    # Try the canonical artist page first
    slug = re.sub(r"[^a-z0-9]+", "-", primary.lower()).strip("-")
    if slug:
        artist_url = f"https://pitchfork.com/artists/{slug}/"
        page = await fetch_page(artist_url)
        if page and not page.startswith("Error") and "We couldn't find that page" not in page:
            chunks.append(page)
            all_text.append(page)
            seen_urls.add(artist_url)

    queries = [primary, f"{primary} album review", f'"{primary}" review']
    for query in queries:
        blob, urls = await pitchfork_search(query)
        # Keep the search listing but mark which hits are seed-relevant
        chunks.append(blob)
        # Re-parse titles from blob lines roughly via urls only
        for url in urls:
            if url in seen_urls:
                continue
            if "/reviews/albums/" not in url and "/artists/" not in url and "/news/" not in url:
                continue
            # URL/path must relate to the seed (blocks Jon Batiste etc.)
            if not _relevant_to_seed(url, url, primary):
                continue
            seen_urls.add(url)
            page = await fetch_page(url)
            if primary.lower().split()[0] not in page.lower() and _norm(primary) not in _norm(page):
                # Page body doesn't mention seed — skip
                continue
            chunks.append(page)
            all_text.append(page)
            if len(seen_urls) >= 5:
                break
        if len(seen_urls) >= 5:
            break

    # Hard-known review for mk.gee when search is thin
    if _norm(primary) in {"mkgee"} or primary.lower() in {"mk.gee", "mk gee"}:
        for url in [
            "https://pitchfork.com/reviews/albums/mk-gee-two-star-and-the-dream-police/",
            "https://pitchfork.com/artists/mkgee/",
        ]:
            if url not in seen_urls:
                page = await fetch_page(url)
                chunks.append(page)
                all_text.append(page)

    combined = "\n".join(all_text)
    comparisons = extract_comparison_artists(combined, seeds + [primary])

    # Festival / bill mates: only for punk/pop-punk seeds (avoids Green Day on rap pages)
    if is_punk_lane(seeds + [primary], taste):
        for known in (
            "Green Day",
            "Blink-182",
            "Good Charlotte",
            "Sum 41",
            "NOFX",
            "Bad Religion",
            "Rancid",
            "FIDLAR",
            "Paramore",
            "My Chemical Romance",
            "Fall Out Boy",
            "Panic! at the Disco",
            "Simple Plan",
            "New Found Glory",
        ):
            if _norm(known) in {_norm(s) for s in seeds + [primary]}:
                continue
            if re.search(rf"\b{re.escape(known)}\b", combined, re.I):
                if known not in comparisons:
                    comparisons.append(known)

    if comparisons:
        chunks.append(
            "STYLE / BILL-MATE ARTISTS found on seed-relevant Pitchfork pages "
            "(prefer these — never recommend unrelated atmospheric pop):\n"
            + "\n".join(f"- {c}" for c in comparisons[:12])
        )
        for name in comparisons[:8]:
            blob, urls = await pitchfork_search(name)
            chunks.append(f"Pitchfork follow-up search for comparison `{name}`:\n{blob}")
            for url in urls:
                if "/reviews/albums/" in url and url not in seen_urls and _relevant_to_seed(name, url, name):
                    seen_urls.add(url)
                    page = await fetch_page(url)
                    chunks.append(page)
                    break
    else:
        chunks.append(
            "No explicit comparison artists parsed from Pitchfork text about this seed. "
            "Do not invent artists (no Lana Del Rey / Billie Eilish for punk seeds). "
            "Empty picks is better than wrong-lane guesses."
        )

    chunks.append(
        "Instruction: recommend similar ARTISTS in the SAME sonic lane as the seed "
        "(punk/pop-punk peers for The Offspring — not dream pop or singer-songwriter). "
        "artist = person/band, album = real release title. "
        "Use as many STYLE / BILL-MATE ARTISTS as you can — up to the requested pick count."
    )
    return _clean("\n\n---\n\n".join(chunks), limit=28000)


def parse_pitchfork_candidates(evidence: str) -> list[tuple[str, str | None, str | None]]:
    """Pull (artist, album|None, url|None) from Pitchfork evidence for backfill."""
    candidates: list[tuple[str, str | None, str | None]] = []
    seen: set[str] = set()

    listed: list[str] = []
    # Match the bill-mate block even if the header wraps across lines
    m = re.search(
        r"STYLE\s*/\s*BILL-MATE ARTISTS[^\n]*:\s*\n((?:- .+\n?)+)",
        evidence,
        re.I,
    )
    if not m:
        # Fallback: any run of "- Artist" lines after BILL-MATE
        m2 = re.search(r"BILL-MATE ARTISTS.*?:\s*\n((?:- .+\n?)+)", evidence, re.I | re.S)
        m = m2
    if m:
        for line in m.group(1).splitlines():
            line = line.strip()
            if line.startswith("-"):
                name = line.lstrip("- ").strip()
                if name and len(name) < 80:
                    listed.append(name)

    # Also catch plain "- Name" lists under "prefer these"
    if not listed:
        for line in evidence.splitlines():
            if re.match(r"^- [A-Z0-9]", line):
                name = line.lstrip("- ").strip()
                # skip long review titles
                if name and len(name) <= 40 and "http" not in name.lower():
                    listed.append(name)

    album_by_artist: dict[str, tuple[str, str]] = {}
    for block in re.finditer(
        r"Pitchfork follow-up search for comparison `([^`]+)`:\s*\n(.*?)(?=\n---|\nPitchfork |\nSTYLE |\nInstruction:|\Z)",
        evidence,
        re.S | re.I,
    ):
        name = block.group(1).strip()
        blob = block.group(2)
        # Prefer a reviews/albums URL whose slug starts with the artist tokens
        name_tokens = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]
        best: tuple[str, str] | None = None
        for url_m in re.finditer(
            r"(?:URL:\s*)?(https://pitchfork\.com/reviews/albums/([a-z0-9-]+)/)",
            blob,
            re.I,
        ):
            url, slug = url_m.group(1), url_m.group(2).lower()
            if name_tokens and not slug.startswith(name_tokens[0]):
                continue
            parts = slug.split("-")
            i = 0
            for tok in name_tokens:
                if i < len(parts) and (parts[i] == tok or tok.startswith(parts[i])):
                    i += 1
            album_guess = " ".join(p.capitalize() for p in parts[i:]) if i < len(parts) else None
            title_m = re.search(
                rf"- (.+?)\n\s*URL:\s*{re.escape(url)}",
                blob,
            )
            album = (title_m.group(1).strip() if title_m else None) or album_guess
            if album:
                best = (album, url)
                break
        if best:
            album_by_artist[_norm(name)] = best

    for name in listed:
        key = _norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        album, url = album_by_artist.get(key, (None, None))
        candidates.append((name, album, url))

    return candidates
