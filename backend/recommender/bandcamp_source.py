from __future__ import annotations

import json
import re
import unicodedata

from recommender.http_client import hardened_get, hardened_post_json

AUTOCOMPLETE = "https://bandcamp.com/api/bcsearch_public_api/1/autocomplete_elastic"
BAND_DETAILS = "https://bandcamp.com/api/mobile/25/band_details"
TRALBUM_DETAILS = "https://bandcamp.com/api/mobile/25/tralbum_details"

_DECORATIVE_RE = re.compile(r"[^\w\s&.\-']+", re.UNICODE)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _clean_band_name(name: str) -> str:
    s = unicodedata.normalize("NFKC", name or "")
    s = _DECORATIVE_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _is_decorative_or_spoof(name: str) -> bool:
    """Reject unicode-stylized clones like '░▒▓█ ｏｌｉｖｉａ　ｒｏｄｒｉｇｏ'."""
    if not name:
        return True
    if unicodedata.normalize("NFKC", name) != name and _DECORATIVE_RE.search(name):
        return True
    # Lots of non-ascii letters used as decoration
    letters = [c for c in name if c.isalpha()]
    if not letters:
        return True
    non_ascii = sum(1 for c in letters if ord(c) > 127)
    if non_ascii / max(len(letters), 1) > 0.3:
        return True
    if re.search(r"[░▒▓█■□▪▫【】《》＠]", name):
        return True
    return False


async def _autocomplete(query: str, search_filter: str = "") -> list[dict]:
    status, text = await hardened_post_json(
        AUTOCOMPLETE,
        {
            "search_text": query,
            "search_filter": search_filter,
            "full_page": True,
            "fan_id": None,
        },
    )
    if status >= 400:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return list(data.get("auto", {}).get("results") or [])


def _pick_seed_band(results: list[dict], seed: str, *, exact_only: bool = False) -> dict | None:
    """Only accept a real Bandcamp artist page for the seed — never unicode spoofs."""
    seed_n = _norm(seed)
    bands = [r for r in results if r.get("type") == "b"]
    for b in bands:
        raw = b.get("name") or ""
        if _is_decorative_or_spoof(raw):
            continue
        cleaned = _clean_band_name(raw)
        if _norm(cleaned) == seed_n:
            return b
    if exact_only:
        return None
    # Substring match only if clean and close in length
    for b in bands:
        raw = b.get("name") or ""
        if _is_decorative_or_spoof(raw):
            continue
        cleaned = _clean_band_name(raw)
        cn = _norm(cleaned)
        if seed_n and seed_n in cn and abs(len(cn) - len(seed_n)) <= 4:
            return b
    return None  # Never fall back to an unrelated first hit


async def seed_has_bandcamp_page(seeds: list[str], taste: str) -> bool:
    primary = seeds[0] if seeds else taste.strip().split(",")[0].strip()
    if not primary:
        return False
    results = await _autocomplete(primary)
    return _pick_seed_band(results, primary) is not None if results else False


async def gather_bandcamp_evidence(seeds: list[str], taste: str) -> str:
    primary = seeds[0] if seeds else taste.strip().split(",")[0].strip()
    chunks: list[str] = [f"Bandcamp evidence for seed `{primary}`"]

    results = await _autocomplete(primary)
    if not results:
        chunks.append("Bandcamp autocomplete returned no results.")
        results = []

    band = _pick_seed_band(results, primary) if results else None

    if not band:
        return (
            f"Bandcamp evidence for seed `{primary}`\n\n"
            f"No legitimate Bandcamp artist page for `{primary}`.\n"
            "Major-label artists are often not on Bandcamp; only covers, karaoke, or spoof pages exist.\n\n"
            'Instruction: return {"notes": "Artist not on Bandcamp", "picks": []}.\n'
            "Do not invent artists or recommend from other sources."
        )

    # Ignore cover/karaoke/mashup albums when collecting tags for the seed lane
    albums = [
        r
        for r in results
        if r.get("type") == "a"
        and not re.search(
            r"\b(cover|karaoke|mashup|8d|remix|instrumental|tribute)\b",
            (r.get("name") or ""),
            re.I,
        )
    ]
    tags: set[str] = set()

    if band:
        chunks.append(
            "Seed band match (official-looking Bandcamp page):\n"
            f"- name: {band.get('name')}\n"
            f"- url: {band.get('item_url_root')}\n"
            f"- location: {band.get('location')}\n"
            f"- tags: {', '.join(band.get('tag_names') or [])}\n"
            f"- genre: {band.get('genre_name')}"
        )
        for t in band.get("tag_names") or []:
            tags.add(t)

        band_id = band.get("id")
        if band_id:
            status, text, _ = await hardened_get(f"{BAND_DETAILS}?band_id={band_id}")
            if status == 200:
                try:
                    details = json.loads(text)
                except json.JSONDecodeError:
                    details = {}
                disco = details.get("discography") or []
                lines = []
                for item in disco[:12]:
                    title = item.get("title")
                    item_id = item.get("item_id")
                    item_type = item.get("item_type") or "album"
                    lines.append(f"- {title} ({item_type}, id={item_id})")
                    if item_id and str(item_type).startswith("a"):
                        st2, tr_text, _ = await hardened_get(
                            f"{TRALBUM_DETAILS}?band_id={band_id}&tralbum_type=a&tralbum_id={item_id}"
                        )
                        if st2 == 200:
                            try:
                                tr = json.loads(tr_text)
                            except json.JSONDecodeError:
                                tr = {}
                            album_tags = [t.get("name") for t in (tr.get("tags") or []) if t.get("name")]
                            for t in album_tags:
                                tags.add(t)
                            chunks.append(
                                f"Album `{tr.get('title')}` tags: {', '.join(album_tags)}\n"
                                f"URL: {tr.get('bandcamp_url')}"
                            )
                if lines:
                    chunks.append("Discography:\n" + "\n".join(lines))

    if albums and band:
        lines = []
        for a in albums[:10]:
            name = a.get("name")
            url = a.get("item_url_root") or a.get("item_url_path")
            tag_names = a.get("tag_names") or []
            for t in tag_names:
                tags.add(t)
            lines.append(f"- {name} | {url} | tags: {', '.join(tag_names)}")
        chunks.append("Autocomplete album hits:\n" + "\n".join(lines))

    # Related artists: search only style tags that match the seed's lane
    _LOCATION_TAG_BLOCKLIST = {
        "united states",
        "united kingdom",
        "england",
        "uk",
        "usa",
        "california",
        "los angeles",
        "new york",
        "london",
        "canada",
        "australia",
        "germany",
        "france",
        "japan",
        "czech",
        "czech republic",
        "czechia",
        "poland",
        "spain",
        "italy",
        "brazil",
        "mexico",
        "sweden",
        "norway",
        "denmark",
        "netherlands",
        "belgium",
        "portugal",
        "austria",
        "switzerland",
        "russia",
        "china",
        "korea",
        "india",
        "ireland",
        "scotland",
        "wales",
    }
    _BROAD_OR_DRIFT_TAGS = {
        "rock",
        "alternative",
        "experimental",
        "electronic",
        "metal",
        "ambient",
        "techno",
        "house",
        "idm",
        "glitch",
        "glitchwave",
        "downtempo",
        "noise",
        "soundtrack",
    }
    _POP_LANE = {
        "pop",
        "indie pop",
        "bedroom pop",
        "synth-pop",
        "synthpop",
        "art pop",
        "dance pop",
        "teen pop",
        "singer-songwriter",
        "indie",
        "alternative pop",
        "dream pop",
        "soft rock",
        "r&b",
        "rnb",
        "indie r&b",
        "alternative r&b",
    }

    seed_tag_set = {t.lower() for t in tags}
    seed_is_pop_lane = bool(seed_tag_set & _POP_LANE) or any(
        w in primary.lower() for w in ("rodrigo", "bedroom", "olivia", "taylor", "swift", "pop")
    )

    # Prefer specific style tags; if seed is pop/bedroom, never chase IDM/glitch tags
    distinctive: list[str] = []
    for t in tags:
        tl = t.lower()
        if tl in _LOCATION_TAG_BLOCKLIST:
            continue
        if re.search(r"\b(city|state|county|republic|kingdom)\b", t, re.I):
            continue
        if seed_is_pop_lane and tl in _BROAD_OR_DRIFT_TAGS:
            continue
        if tl in _BROAD_OR_DRIFT_TAGS and not (seed_tag_set & _BROAD_OR_DRIFT_TAGS):
            continue
        distinctive.append(t)
    if seed_is_pop_lane:
        for boost in ("bedroom pop", "indie pop", "singer-songwriter", "pop"):
            if boost not in {x.lower() for x in distinctive}:
                distinctive.insert(0, boost)
    distinctive = distinctive[:6]

    related_lines: list[str] = []
    seen_bands: set[str] = set()
    seed_n = _norm(primary)

    chunks.append(
        "Seed style lane: "
        + ("pop / women-in-pop / alt-pop" if seed_is_pop_lane else "from tags below")
        + f"\nSeed tags: {', '.join(sorted(tags)) or '(none)'}"
    )

    for tag in distinctive:
        hits = await _autocomplete(tag, search_filter="b")
        if not hits:
            continue
        for item in hits:
            if item.get("type") != "b":
                continue
            name = item.get("name") or ""
            if not name or seed_n and seed_n in _norm(name):
                continue
            low = name.lower()
            if "," in name or re.search(r"\brecords?\s*$", name, re.I):
                continue
            if any(
                junk in low
                for junk in (
                    "tribute",
                    "backing track",
                    "sample pack",
                    "karaoke",
                    "various artists",
                )
            ):
                continue
            # Skip joke/tag-pun band names from tag search (e.g. "Bedroom Cop")
            tag_token = re.sub(r"[^a-z]+", "", tag.lower())
            if tag_token and tag_token[:6] in _norm(name) and len(name) < 28:
                continue
            band_url = item.get("item_url_root") or ""
            if not band_url or "bandcamp.com" not in band_url:
                continue
            item_tags = [t for t in (item.get("tag_names") or [])]
            item_tag_set = {t.lower() for t in item_tags}
            if seed_is_pop_lane and not (item_tag_set & _POP_LANE):
                # Don't recommend glitch/IDM neighbors for pop/bedroom seeds
                continue
            if seed_is_pop_lane and (item_tag_set & _BROAD_OR_DRIFT_TAGS) and not (
                item_tag_set & _POP_LANE
            ):
                continue
            overlap = sorted(item_tag_set & seed_tag_set, key=str)
            if seed_is_pop_lane:
                overlap = sorted((item_tag_set & _POP_LANE) | set(overlap), key=str)
            if not overlap and not seed_is_pop_lane:
                continue
            if not overlap and seed_is_pop_lane and not (item_tag_set & _POP_LANE):
                continue
            key = _norm(name) + band_url
            if key in seen_bands:
                continue
            seen_bands.add(key)
            style_tags = [t for t in item_tags if t.lower() not in _LOCATION_TAG_BLOCKLIST]
            related_lines.append(
                f"- Artist: {name}\n"
                f"  Bandcamp: {band_url}\n"
                f"  Shared style tags: {', '.join(overlap) or ', '.join(sorted(item_tag_set & _POP_LANE))}\n"
                f"  Other tags: {', '.join(style_tags[:8])}"
            )
            if len(related_lines) >= 20:
                break
        if len(related_lines) >= 20:
            break

    # Remix/cover hosts of the seed — only if we have a real seed page (otherwise noise)
    if band:
        collab_lines = []
        for item in results:
            if item.get("type") != "a":
                continue
            name = item.get("name") or ""
            url = item.get("item_url_root") or ""
            if seed_n in _norm(name) and url and primary.lower() not in url:
                collab_lines.append(f"- {name} on {url} tags={item.get('tag_names')}")
        if collab_lines:
            chunks.append(
                "Weak cover/remix signals (ignore unless also a real similar artist):\n"
                + "\n".join(collab_lines[:5])
            )
    if related_lines:
        chunks.append(
            "Similar Bandcamp ARTISTS (candidates — pick a real album/song for each):\n"
            + "\n".join(related_lines)
        )
    elif tags:
        chunks.append(
            "Seed style tags found, but few neighboring artists. "
            f"Tags: {', '.join(sorted(tags))}"
        )

    chunks.append(
        "Instruction: recommend similar ARTISTS and one real ALBUM/SONG each "
        f"to `{primary}` (e.g. other women in pop / alt-pop / bedroom-pop if that is the lane). "
        "Never follow experimental spoof pages or output genre lists."
    )
    return "\n\n".join(chunks)[:24000]
