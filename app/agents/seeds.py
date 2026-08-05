from __future__ import annotations

import re


def clean_artist_name(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s&.\-]", "", s)
    return re.sub(r"\s+", " ", s)


def extract_seeds(taste: str, artists: list[str]) -> list[str]:
    """Collect seed artists from the artists field and taste text."""
    seeds: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        name = raw.strip(" \t\n\r,\"'")
        if not name or len(name) < 2:
            return
        key = clean_artist_name(name)
        if not key or key in seen:
            return
        seen.add(key)
        seeds.append(name)

    for a in artists:
        add(a)

    for part in re.split(r"[,;/|]+|\band\b", taste, flags=re.I):
        part = part.strip()
        part = re.sub(
            r"^(?:artists?(?:\s+like)?|like|similar to|sounds? like|fans? of)\s+",
            "",
            part,
            flags=re.I,
        ).strip()
        if not part or len(part) > 60 or " " in part and len(part.split()) > 4:
            continue
        if part.lower() in {
            "ambient",
            "jazz",
            "rock",
            "pop",
            "indie",
            "electronic",
            "hip hop",
            "rap",
            "metal",
            "folk",
            "soul",
            "r&b",
            "rnb",
            "bedroom pop",
            "indie folk",
        }:
            continue
        add(part)

    return seeds


def is_seed_artist(artist: str, seeds: list[str]) -> bool:
    a = clean_artist_name(artist)
    if not a:
        return False
    for seed in seeds:
        s = clean_artist_name(seed)
        if not s:
            continue
        if a == s or a in s or s in a:
            return True
    return False


SIMILARITY_RULE = """
Recommend similar ARTISTS and their ALBUMS/SONGS only.
1) From this source, find artists similar to the seed (similar-artist lists, "sounds like", shared listeners, review comparisons).
2) For each similar artist, pick a real album or well-known release — never a genre word, country, or tag.
3) Output format must be: artist = person/band name, album = release title.
4) Never put genres, locations, labels, or "Various Artists" in artist/album fields.
5) Never recommend the seed artist back.
6) In "why", say how they are similar as artists (sound/scene), not just a shared tag label or vague theme.
7) Match the sonic lane: punk seeds get punk/pop-punk peers; pop seeds get pop peers.
   Do not jump from The Offspring to Lana Del Rey / dream pop.
""".strip()


def user_prompt(taste: str, artists: list[str], limit: int, source_name: str, search_tips: str) -> str:
    seeds = extract_seeds(taste, artists)
    seed_line = ", ".join(seeds) if seeds else "(infer seed artists from taste text)"
    return f"""Listener taste:
{taste}

Seed artists (do NOT recommend these): {seed_line}

On {source_name}:
1) Find artists similar to the seed.
2) Recommend those artists' real albums/songs.
3) Return up to {limit} picks as JSON (artist + album title).

{search_tips}

artist = band/person. album = release title. Not genre. Not country."""
