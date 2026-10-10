from __future__ import annotations

import json
import re
from typing import Any, Literal

from openai import APIConnectionError, APITimeoutError, AuthenticationError, APIStatusError
from openai.types.chat import ChatCompletionMessageParam

from recommender.agents.seeds import extract_seeds, is_seed_artist
from recommender.agents.synthesizer import _norm_name, is_usable_pick
from recommender.config import settings
from recommender.lanes import is_punk_lane, lane_mismatch
from recommender.llm import get_client
from recommender.schemas import AgentResult, SourcePick
from recommender.search_sites import gather_source_evidence
from recommender.tools import fetch_page, web_search

SourceName = Literal["pitchfork", "rym"]

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web, optionally restricted to one site domain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "site": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": "Fetch readable text from an allowed music-site URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
]

FINAL_JSON_INSTRUCTIONS = """
Return ONLY a JSON object (no tool calls, no markdown):
{
  "notes": "which similar artists you used",
  "picks": [
    {
      "artist": "Real Artist Name",
      "album": "Real Album Or Song Title",
      "year": "optional",
      "url": "optional url from evidence",
      "why": "why this artist/release is similar to the seed",
      "score_or_signal": "optional",
      "tags": []
    }
  ]
}
HARD RULES:
- Recommend similar artists and their albums/songs.
- artist MUST be a person or band name.
- album MUST be a real release/song title — never a genre (Metal, Ambient, Singer-Songwriter) or country.
- Never use Bandcamp metadata as fields (no "Alternative, United States", no "Glitchwave, Electronic, Experimental", no genre lists).
- Never recommend seed artists.
- Stay in the seed's SONIC lane:
  - Olivia Rodrigo / pop / bedroom pop → similar pop / alt-pop (not IDM/glitch).
  - The Offspring / Green Day / punk / pop-punk → similar punk / pop-punk bands
    (Blink-182, Sum 41, Bad Religion) — NEVER Lana Del Rey / dream pop.
  - Injury Reserve / experimental hip-hop / rap → similar rap / experimental hip-hop
    (Death Grips, clipping., JPEGMAFIA, Armand Hammer) — NEVER Green Day or pop-punk.
- Similarity means sound/scene/listeners — not vague shared themes.
- Prefer artists named as similar / compared / neighboring in the evidence.
- Empty picks is better than junk or wrong-lane guesses.
""".strip()


def _tool_name(name: str) -> str:
    """Gemini 3 may prefix tool names, e.g. default_api:web_search."""
    return name.rsplit(":", 1)[-1]


def _assistant_tool_call(tc: Any, *, needs_signature: bool) -> dict[str, Any]:
    """Echo a tool call, including the Gemini 3 thought signature."""
    payload: dict[str, Any] = {
        "id": tc.id,
        "type": "function",
        "function": {
            "name": tc.function.name,
            "arguments": tc.function.arguments,
        },
    }
    extra = getattr(tc, "extra_content", None)
    if not extra:
        extra = (getattr(tc, "model_extra", None) or {}).get("extra_content")
    if extra:
        payload["extra_content"] = extra
    elif needs_signature:
        # Required on the first call of each step. A missing signature is a 400.
        payload["extra_content"] = {
            "google": {"thought_signature": "skip_thought_signature_validator"}
        }
    return payload


async def _run_tool(name: str, args: dict[str, Any]) -> str:
    name = _tool_name(name)
    if name == "web_search":
        return await web_search(query=args["query"], site=args.get("site"))
    if name == "fetch_page":
        return await fetch_page(args["url"])
    return f"Unknown tool: {name}"


def _normalize_pick_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce common LLM field variants before Pydantic validation."""
    out = dict(raw)
    album = out.get("album") or out.get("release") or out.get("track") or out.get("title")
    if not album and out.get("song"):
        album = out["song"]
    if album:
        out["album"] = album
    why = out.get("why") or out.get("reason") or out.get("note")
    if why:
        out["why"] = why
    return out


def _parse_picks(content: str) -> tuple[list[SourcePick], str]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in agent response")

    data = json.loads(text[start : end + 1])
    if "name" in data and "parameters" in data and "picks" not in data:
        raise ValueError("Model returned a tool call instead of picks JSON")

    picks: list[SourcePick] = []
    for raw in data.get("picks", []):
        if not isinstance(raw, dict):
            continue
        try:
            picks.append(SourcePick.model_validate(_normalize_pick_raw(raw)))
        except Exception:
            continue
    notes = str(data.get("notes", ""))
    return picks, notes


_SOURCE_EMPTY_NOTES: dict[SourceName, str] = {
    "pitchfork": "Pitchfork didn't turn up enough grounded picks.",
    "rym": "Rate Your Music didn't turn up enough grounded picks.",
}

# Well-known albums used only to backfill Pitchfork bill-mates missing a title in evidence
_DEFAULT_ALBUMS = {
    "greenday": "Dookie",
    "blink182": "Enema of the State",
    "sum41": "All Killer No Filler",
    "badreligion": "Suffer",
    "goodcharlotte": "The Young and the Hopeless",
    "fidlar": "Too",
    "nofx": "Punk in Drublic",
    "rancid": "...And Out Come the Wolves",
    "paramore": "Riot!",
    "mychemicalromance": "The Black Parade",
    "falloutboy": "From Under the Cork Tree",
    "simpleplan": "No Pads, No Helmets...Just Balls",
    "newfoundglory": "Sticks and Stones",
    "panicatthedisco": "A Fever You Can't Sweat Out",
}


def _friendly_agent_notes(source: SourceName, notes: str = "") -> str:
    cleaned = (notes or "").strip()
    if cleaned and not cleaned.startswith("{") and "validation error" not in cleaned.lower():
        return cleaned
    return _SOURCE_EMPTY_NOTES[source]


def _empty_agent_result(source: SourceName, notes: str = "") -> AgentResult:
    return AgentResult(
        source=source,
        picks=[],
        notes=_friendly_agent_notes(source, notes),
        error=None,
    )


def _artist_mentioned(artist: str, evidence: str) -> bool:
    """Require a real name hit — not loose tokens like green+day → Dylan Green / Monday."""
    if not artist or not evidence:
        return False
    ev = evidence.lower()
    parts = [p for p in re.split(r"\W+", artist.lower().strip()) if p]
    if not parts:
        return False
    # Contiguous name with flexible separators (Blink-182, Green Day, JPEGMAFIA)
    pattern = r"\b" + r"[\s\-&.]*".join(re.escape(p) for p in parts) + r"\b"
    return bool(re.search(pattern, ev, re.I))


def _clean_picks(
    picks: list[SourcePick],
    allowed_site: str,
    seeds: list[str],
    evidence: str = "",
    taste: str = "",
    limit: int | None = None,
) -> list[SourcePick]:
    # Pitchfork: keep name-in-evidence grounding (comparisons are explicit).
    # Bandcamp/RYM: allow genre-lane picks even if the exact artist isn't quoted —
    # those sources are used for genre/tags + "people recommend" discovery.
    require_name_in_evidence = allowed_site == "pitchfork.com"
    cap = limit if limit is not None else settings.recommendations_per_agent

    cleaned: list[SourcePick] = []
    for pick in picks[: max(cap, settings.recommendations_per_agent)]:
        if not is_usable_pick(pick):
            continue
        if is_seed_artist(pick.artist, seeds):
            continue
        if lane_mismatch(pick.artist, seeds, taste):
            continue
        if require_name_in_evidence and evidence and not _artist_mentioned(pick.artist, evidence):
            continue
        if pick.url and allowed_site not in pick.url and "web.archive.org" not in (pick.url or ""):
            pick = pick.model_copy(update={"url": None})
        cleaned.append(pick)
        if len(cleaned) >= cap:
            break
    return cleaned


def _backfill_pitchfork_picks(
    existing: list[SourcePick],
    evidence: str,
    seeds: list[str],
    taste: str,
    limit: int,
) -> list[SourcePick]:
    """If the model under-filled, promote STYLE / BILL-MATE artists from evidence."""
    if len(existing) >= limit or not evidence:
        return existing
    try:
        from recommender.pitchfork_source import parse_pitchfork_candidates
    except Exception:
        return existing

    have = {_norm_name(p.artist) for p in existing}
    out = list(existing)
    for artist, album, url in parse_pitchfork_candidates(evidence):
        if len(out) >= limit:
            break
        if not artist or _norm_name(artist) in have:
            continue
        if is_seed_artist(artist, seeds) or lane_mismatch(artist, seeds, taste):
            continue
        if not album:
            # Punk-peer defaults only when the seed is actually punk/pop-punk
            if is_punk_lane(seeds, taste):
                album = _DEFAULT_ALBUMS.get(_norm_name(artist).replace(" ", ""))
            if not album:
                continue
            url = None
        pick = SourcePick(
            artist=artist,
            album=album,
            url=url,
            why="Named alongside the seed in Pitchfork coverage (similar scene / bill).",
        )
        if not is_usable_pick(pick):
            continue
        out.append(pick)
        have.add(_norm_name(artist))
    return out


def _result_from_content(
    source: SourceName,
    content: str,
    allowed_site: str,
    seeds: list[str],
    evidence: str = "",
    taste: str = "",
    limit: int | None = None,
) -> AgentResult:
    picks, notes = _parse_picks(content)
    cleaned = _clean_picks(
        picks, allowed_site, seeds, evidence=evidence, taste=taste, limit=limit
    )
    if source == "pitchfork" and limit:
        cleaned = _backfill_pitchfork_picks(cleaned, evidence, seeds, taste, limit)
    if not cleaned and picks:
        dropped = ", ".join(dict.fromkeys(p.artist for p in picks))
        return AgentResult(
            source=source,
            picks=[],
            notes=(
                f"Considered {dropped}, but none were grounded enough in {source} evidence "
                "to keep — check the other sources."
            ),
            error=None,
        )
    if not cleaned:
        return _empty_agent_result(source, notes)
    # Notes must match what we actually show (models often "consider" extra names).
    shown = ", ".join(dict.fromkeys(p.artist for p in cleaned))
    return AgentResult(
        source=source,
        picks=cleaned,
        notes=f"Showing: {shown}.",
    )


async def _run_ollama_agent(
    *,
    source: SourceName,
    system_prompt: str,
    taste: str,
    artists: list[str],
    allowed_site: str,
    limit: int,
) -> AgentResult:
    seeds = extract_seeds(taste, artists)
    evidence = await gather_source_evidence(seeds, taste, allowed_site)
    seed_line = ", ".join(seeds) if seeds else taste

    user = f"""You are recommending music using evidence from {allowed_site} only.

Listener taste: {taste}
Seed artists (do NOT recommend): {seed_line}
Need up to {limit} picks: similar artists and one real album/song each.

EVIDENCE FROM {allowed_site}:
{evidence}

{FINAL_JSON_INSTRUCTIONS}
"""
    client = get_client()
    response = await client.chat.completions.create(
        model=settings.resolved_model,
        messages=[
            {
                "role": "system",
                "content": system_prompt + "\n\nDo not call tools. Answer with JSON only.",
            },
            {"role": "user", "content": user},
        ],
        temperature=0.2,
    )
    content = response.choices[0].message.content or ""
    try:
        return _result_from_content(
            source,
            content,
            allowed_site,
            seeds,
            evidence=evidence,
            taste=taste,
            limit=limit,
        )
    except Exception:
        retry = await client.chat.completions.create(
            model=settings.resolved_model,
            messages=[
                {"role": "system", "content": "Return ONLY the picks JSON object. No tool calls."},
                {
                    "role": "user",
                    "content": (
                        f"Seeds (exclude): {seed_line}\nEvidence:\n{evidence[:14000]}\n\n"
                        f"Your previous answer was invalid:\n{content[:1500]}\n\n"
                        f"{FINAL_JSON_INSTRUCTIONS}"
                    ),
                },
            ],
            temperature=0.1,
        )
        content2 = retry.choices[0].message.content or ""
        try:
            return _result_from_content(
                source,
                content2,
                allowed_site,
                seeds,
                evidence=evidence,
                taste=taste,
                limit=limit,
            )
        except Exception:
            for attempt in (content2, content):
                try:
                    picks, notes = _parse_picks(attempt)
                    cleaned = _clean_picks(
                        picks,
                        allowed_site,
                        seeds,
                        evidence=evidence,
                        taste=taste,
                        limit=limit,
                    )
                    if source == "pitchfork":
                        cleaned = _backfill_pitchfork_picks(
                            cleaned, evidence, seeds, taste, limit
                        )
                    if cleaned:
                        shown = ", ".join(dict.fromkeys(p.artist for p in cleaned))
                        return AgentResult(
                            source=source, picks=cleaned, notes=f"Showing: {shown}."
                        )
                except Exception:
                    continue
            return _empty_agent_result(source)


async def _force_final_answer(
    client: Any,
    messages: list[ChatCompletionMessageParam],
) -> str:
    messages = list(messages)
    messages.append(
        {
            "role": "user",
            "content": (
                "Stop using tools. Using only evidence already in this conversation, "
                f"respond with picks JSON.\n{FINAL_JSON_INSTRUCTIONS}"
            ),
        }
    )
    response = await client.chat.completions.create(
        model=settings.resolved_model,
        messages=messages,
        temperature=0.2,
    )
    return response.choices[0].message.content or ""


async def run_source_agent(
    *,
    source: SourceName,
    system_prompt: str,
    user_prompt: str,
    allowed_site: str,
    taste: str = "",
    artists: list[str] | None = None,
    limit: int = 5,
) -> AgentResult:
    artists = artists or []
    seeds = extract_seeds(taste or user_prompt, artists)

    if settings.llm_provider == "ollama":
        try:
            return await _run_ollama_agent(
                source=source,
                system_prompt=system_prompt,
                taste=taste or user_prompt,
                artists=artists,
                allowed_site=allowed_site,
                limit=limit,
            )
        except AuthenticationError:
            return AgentResult(source=source, picks=[], notes="", error="ollama rejected request")
        except APIConnectionError as exc:
            cause = f" ({exc.__cause__})" if exc.__cause__ else ""
            return AgentResult(
                source=source,
                picks=[],
                notes="",
                error=f"Could not reach ollama{cause}",
            )
        except Exception as exc:  # noqa: BLE001
            return AgentResult(source=source, picks=[], notes="", error=str(exc))

    client = get_client()
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        for round_idx in range(settings.max_tool_rounds):
            force_wrap_up = round_idx >= settings.max_tool_rounds - 1
            response = await client.chat.completions.create(
                model=settings.resolved_model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="none" if force_wrap_up else "auto",
                temperature=0.3,
            )
            message = response.choices[0].message
            tool_calls = list(message.tool_calls or [])[:4]

            if tool_calls and not force_wrap_up:
                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            _assistant_tool_call(tc, needs_signature=index == 0)
                            for index, tc in enumerate(tool_calls)
                        ],
                    }
                )
                for tc in tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if _tool_name(tc.function.name) == "web_search" and not args.get("site"):
                        args["site"] = allowed_site
                    result = await _run_tool(tc.function.name, args)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result[:8000],
                        }
                    )
                continue

            content = message.content or ""
            if content.strip():
                try:
                    return _result_from_content(
                        source,
                        content,
                        allowed_site,
                        seeds,
                        taste=taste or user_prompt,
                        limit=limit,
                    )
                except Exception:
                    pass

            final = await _force_final_answer(client, messages)
            try:
                return _result_from_content(
                    source,
                    final,
                    allowed_site,
                    seeds,
                    taste=taste or user_prompt,
                    limit=limit,
                )
            except Exception:
                try:
                    picks, notes = _parse_picks(final)
                    cleaned = _clean_picks(
                        picks,
                        allowed_site,
                        seeds,
                        taste=taste or user_prompt,
                        limit=limit,
                    )
                    if cleaned:
                        shown = ", ".join(dict.fromkeys(p.artist for p in cleaned))
                        return AgentResult(
                            source=source, picks=cleaned, notes=f"Showing: {shown}."
                        )
                except Exception:
                    pass
                return _empty_agent_result(source)

        return _empty_agent_result(source)
    except AuthenticationError:
        return AgentResult(
            source=source,
            picks=[],
            notes="",
            error=f"{settings.llm_provider} rejected the API key. Check .env",
        )
    except APITimeoutError:
        return AgentResult(
            source=source,
            picks=[],
            notes="",
            error=f"{settings.llm_provider} took too long to answer. Try again.",
        )
    except APIConnectionError as exc:
        cause = f" ({exc.__cause__})" if exc.__cause__ else ""
        return AgentResult(
            source=source,
            picks=[],
            notes="",
            error=f"Could not reach {settings.llm_provider}{cause}",
        )
    except APIStatusError as exc:
        return AgentResult(
            source=source,
            picks=[],
            notes="",
            error=f"{settings.llm_provider} HTTP {exc.status_code}: {exc.message}",
        )
    except Exception as exc:  # noqa: BLE001
        return AgentResult(source=source, picks=[], notes="", error=str(exc))
