from __future__ import annotations

import json
import re

from openai.types.chat import ChatCompletionMessageParam

from recommender.agents.seeds import extract_seeds, is_seed_artist
from recommender.config import settings
from recommender.lanes import lane_mismatch
from recommender.llm import get_client
from recommender.schemas import AgentResult, MergedRecommendation, SourcePick

_BAD_NAMES = {
    "",
    "unknown",
    "unknown artist",
    "unknown album",
    "n/a",
    "none",
    "tbd",
    "...",
    "artist",
    "album",
    "various",
    "various artists",
    "va",
    "v/a",
}

_META_ARTIST_NAMES = {
    "alternative",
    "experimental",
    "electronic",
    "rock",
    "pop",
    "indie",
    "jazz",
    "folk",
    "hip hop",
    "r b",
    "rnb",
    "soul",
    "metal",
    "ambient",
    "soundtrack",
    "punk",
    "techno",
    "house",
    "disco",
    "funk",
    "blues",
    "classical",
    "world",
    "spoken word",
    "united states",
    "united kingdom",
    "england",
    "scotland",
    "wales",
    "ireland",
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
}

_LOCATION_WORDS = {
    "czech",
    "czechia",
    "czech republic",
    "american",
    "british",
    "english",
    "french",
    "german",
    "japanese",
    "canadian",
    "australian",
    "polish",
    "spanish",
    "italian",
    "brazilian",
    "mexican",
    "swedish",
    "norwegian",
    "danish",
    "dutch",
    "portuguese",
    "austrian",
    "swiss",
    "russian",
    "chinese",
    "korean",
    "indian",
    "uk",
    "usa",
    "us",
}

_GENRE_ALBUM_NAMES = {
    "metal",
    "electronic",
    "ambient",
    "rock",
    "pop",
    "indie",
    "jazz",
    "folk",
    "punk",
    "techno",
    "house",
    "hip hop",
    "r b",
    "soul",
    "experimental",
    "alternative",
    "soundtrack",
    "singer songwriter",
    "singersongwriter",
    "soft rock",
    "acoustic",
}

_JUNK_TITLE_RE = re.compile(
    r"\b(tribute|covers?|backing track|drumless|sample pack|karaoke|type beat|"
    r"various artists|compilation)\b",
    re.I,
)

_LABEL_AS_ARTIST_RE = re.compile(
    r"\b(records?|recordings?|music|label|productions?)\s*$",
    re.I,
)


def _norm_name(value: str) -> str:
    s = value.lower().strip()
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s)


def _norm_key(artist: str, album: str) -> str:
    return f"{_norm_name(artist)}::{_norm_name(album)}"


def is_real_title(value: str | None) -> bool:
    if not value:
        return False
    return _norm_name(value) not in _BAD_NAMES


_GENRE_TOKEN_RE = re.compile(
    r"\b("
    r"glitchwave|glitch|idm|downtempo|experimental|electronic|ambient|techno|house|"
    r"metal|indie|alternative|progressive\s+electronic|drum\s+and\s+bass|dnb|"
    r"bedroom\s+pop|indie\s+pop|synth[\s-]?pop|art\s+pop|hypnagogic|"
    r"neo[\s-]?psychedelia|indietronica|vaporwave|footwork"
    r")\b",
    re.I,
)


def _looks_like_tag_list(value: str) -> bool:
    """Catch Bandcamp metadata dumped into artist/album fields."""
    raw = value.strip()
    if not raw:
        return False
    # "Glitchwave, Electronic, Experimental" or "Experimental, downtempo, idm, ..."
    parts = [p.strip() for p in re.split(r"[,/|]", raw) if p.strip()]
    if len(parts) >= 2:
        genreish = 0
        for p in parts:
            n = _norm_name(p)
            if (
                n in _META_ARTIST_NAMES
                or n in _GENRE_ALBUM_NAMES
                or _GENRE_TOKEN_RE.search(p)
                or n in _LOCATION_WORDS
            ):
                genreish += 1
        if genreish >= 2:
            return True
    if raw.count(",") >= 2 and _GENRE_TOKEN_RE.search(raw):
        return True
    # Entire string is only genre tokens
    tokens = [t for t in re.split(r"\W+", raw.lower()) if t]
    if tokens and all(
        t in _META_ARTIST_NAMES
        or t in _GENRE_ALBUM_NAMES
        or t in {"progressive", "electronic", "glitchwave", "idm", "downtempo"}
        for t in tokens
    ):
        return True
    return False


def is_junk_release(artist: str, album: str) -> bool:
    """Tribute comps / metadata / VA / location+genre junk."""
    a = artist.strip()
    b = album.strip()
    if _JUNK_TITLE_RE.search(a) or _JUNK_TITLE_RE.search(b):
        return True
    na, nb = _norm_name(a), _norm_name(b)
    if na in _BAD_NAMES or nb in _BAD_NAMES:
        return True
    if na in _META_ARTIST_NAMES or _looks_like_tag_list(a) or _looks_like_tag_list(b):
        return True
    # Album field is just a genre word: "Sekhmet Czech — Metal"
    if nb in _GENRE_ALBUM_NAMES or nb in _META_ARTIST_NAMES:
        return True
    if _GENRE_TOKEN_RE.fullmatch(b.strip()) or _GENRE_TOKEN_RE.fullmatch(a.strip()):
        return True
    # Artist ends with / contains a location word and album is genre-ish
    artist_tokens = set(na.split())
    if artist_tokens & _LOCATION_WORDS and (nb in _GENRE_ALBUM_NAMES or len(nb) <= 12):
        return True
    if any(na.endswith(" " + loc) or na.endswith(loc) for loc in _LOCATION_WORDS):
        if nb in _GENRE_ALBUM_NAMES or nb in _META_ARTIST_NAMES:
            return True
    if _LABEL_AS_ARTIST_RE.search(a) and (
        "various" in nb or nb in _META_ARTIST_NAMES or "experimental" in na
    ):
        return True
    if "various artists" in nb or nb == "various artists":
        return True
    if na and nb and (na == nb or na in nb or nb in na):
        return True
    return False


def is_usable_pick(pick: SourcePick) -> bool:
    if not is_real_title(pick.artist) or not is_real_title(pick.album):
        return False
    if is_junk_release(pick.artist, pick.album):
        return False
    return True


def _catalog(agents: list[AgentResult]) -> dict[str, SourcePick]:
    """Map normalized artist::album -> first real pick."""
    out: dict[str, SourcePick] = {}
    for agent in agents:
        for pick in agent.picks:
            if not is_usable_pick(pick):
                continue
            key = _norm_key(pick.artist, pick.album)
            out.setdefault(key, pick)
    return out


async def synthesize(
    taste: str,
    agents: list[AgentResult],
    limit: int,
    seed_artists: list[str] | None = None,
) -> list[MergedRecommendation]:
    """Merge agent picks. Local models use deterministic merge (more reliable)."""
    seeds = seed_artists or extract_seeds(taste, [])
    fallback = _fallback_merge(agents, limit, seeds, taste=taste)

    # llama via Ollama often invents "Unknown Artist" — skip LLM merge there
    if settings.llm_provider == "ollama":
        return fallback

    catalog = _catalog(agents)
    if not catalog:
        return fallback

    payload = {
        "taste": taste,
        "seed_artists_do_not_recommend": seeds,
        "allowed_picks": [
            {"artist": p.artist, "album": p.album, "year": p.year}
            for p in catalog.values()
        ],
        "agents": [a.model_dump() for a in agents],
        "limit": limit,
    }

    system = """You merge music recommendations from two source agents: pitchfork, rym.

HARD RULES:
- artist and album MUST be copied EXACTLY from allowed_picks — never invent names
- NEVER output "Unknown Artist", "Unknown Album", or placeholders
- NEVER includes any seed artist from seed_artists_do_not_recommend
- Prefer similar artists + real albums/songs; drop genre/location junk if any slipped in
- Prefer albums backed by multiple sources when they are style matches
- In "why", cite artist similarity, not tag labels alone

Respond with ONLY JSON:
{
  "recommendations": [
    {
      "artist": "Exact Artist From allowed_picks",
      "album": "Exact Album From allowed_picks",
      "year": "optional or null",
      "urls": {"pitchfork": "...", "rym": "..."},
      "why": "...",
      "sources": ["pitchfork", "rym"],
      "confidence": 0.0-1.0,
      "tags": []
    }
  ]
}
Only include URLs that appeared in the agent picks. Omit missing url keys.
"""

    client = get_client()
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload)},
    ]

    try:
        response = await client.chat.completions.create(
            model=settings.resolved_model,
            messages=messages,
            temperature=0.2,
        )
        content = response.choices[0].message.content or ""
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start : end + 1])
        recs: list[MergedRecommendation] = []
        for raw in data.get("recommendations", []):
            rec = MergedRecommendation.model_validate(raw)
            if not is_real_title(rec.artist) or not is_real_title(rec.album):
                continue
            if is_seed_artist(rec.artist, seeds):
                continue
            key = _norm_key(rec.artist, rec.album)
            if key not in catalog:
                continue
            # Normalize to catalog spelling
            pick = catalog[key]
            recs.append(
                rec.model_copy(update={"artist": pick.artist, "album": pick.album, "year": rec.year or pick.year})
            )
        if not recs:
            return fallback
        return recs[:limit]
    except Exception:
        return fallback


def _fallback_merge(
    agents: list[AgentResult],
    limit: int,
    seeds: list[str] | None = None,
    taste: str = "",
) -> list[MergedRecommendation]:
    """Merge picks from all agents.

    Prefer one album per artist, round-robin across sources so Pitchfork
    and RYM both contribute instead of one source filling the whole list.
    """
    seeds = seeds or []

    # artist_key -> merged recommendation (first album wins, sources accumulate)
    by_artist: dict[str, MergedRecommendation] = {}
    # Per-source ordered artist keys (first time that source names the artist)
    per_source: dict[str, list[str]] = {}

    for agent in agents:
        seen_here: set[str] = set()
        per_source[agent.source] = []
        for pick in agent.picks:
            if not is_usable_pick(pick):
                continue
            if is_seed_artist(pick.artist, seeds):
                continue
            if lane_mismatch(pick.artist, seeds, taste):
                continue
            artist_key = _norm_name(pick.artist)
            if not artist_key:
                continue

            if artist_key not in by_artist:
                by_artist[artist_key] = MergedRecommendation(
                    artist=pick.artist,
                    album=pick.album,
                    year=pick.year,
                    urls={agent.source: pick.url} if pick.url else {},
                    why=pick.why,
                    sources=[agent.source],
                    confidence=0.45,
                    tags=list(pick.tags),
                )
            else:
                rec = by_artist[artist_key]
                if agent.source not in rec.sources:
                    rec.sources.append(agent.source)
                if pick.url:
                    rec.urls[agent.source] = pick.url
                if pick.why and pick.why not in rec.why:
                    rec.why = f"{rec.why} Also: {pick.why}"
                for tag in pick.tags:
                    if tag not in rec.tags:
                        rec.tags.append(tag)
                rec.confidence = min(1.0, 0.35 + 0.25 * len(rec.sources))

            if artist_key not in seen_here:
                seen_here.add(artist_key)
                per_source[agent.source].append(artist_key)

    # Round-robin across Pitchfork and RYM
    source_order = [s for s in ("pitchfork", "rym") if per_source.get(s)]
    chosen: list[str] = []
    chosen_set: set[str] = set()
    indices = {s: 0 for s in source_order}

    while len(chosen) < limit and source_order:
        progress = False
        still_active: list[str] = []
        for source in source_order:
            keys = per_source[source]
            i = indices[source]
            while i < len(keys) and keys[i] in chosen_set:
                i += 1
            indices[source] = i
            if i >= len(keys):
                continue
            artist_key = keys[i]
            indices[source] = i + 1
            chosen.append(artist_key)
            chosen_set.add(artist_key)
            progress = True
            still_active.append(source)
            if len(chosen) >= limit:
                break
        source_order = still_active if progress else []
        if not progress:
            break

    # If still under limit, add any remaining artists we haven't shown
    if len(chosen) < limit:
        for artist_key in by_artist:
            if artist_key in chosen_set:
                continue
            chosen.append(artist_key)
            chosen_set.add(artist_key)
            if len(chosen) >= limit:
                break

    return [by_artist[k] for k in chosen]
