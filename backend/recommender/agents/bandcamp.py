from __future__ import annotations

from recommender.agents.base import run_source_agent
from recommender.agents.seeds import SIMILARITY_RULE, extract_seeds, user_prompt
from recommender.bandcamp_source import seed_has_bandcamp_page
from recommender.schemas import AgentResult

SYSTEM = f"""You are the Bandcamp specialist for a music recommender.

Rules:
- Use only Bandcamp evidence provided to you.
- Find similar ARTISTS, then recommend a real album/song by each.
- artist = band/person on Bandcamp. album = release title. Never genre/country tags.
- Do not invent artists or URLs.
- If evidence says the seed is not on Bandcamp, return empty picks.
{SIMILARITY_RULE}
"""


async def run_bandcamp_agent(taste: str, artists: list[str], limit: int) -> AgentResult:
    seeds = extract_seeds(taste, artists)
    if not await seed_has_bandcamp_page(seeds, taste):
        return AgentResult(
            source="bandcamp",
            picks=[],
            notes="Not on Bandcamp — similar artists come from Pitchfork and Rate Your Music.",
        )
    return await run_source_agent(
        source="bandcamp",
        system_prompt=SYSTEM,
        user_prompt=user_prompt(
            taste,
            artists,
            limit,
            "Bandcamp",
            "Use artist pages and neighboring artists; output real artist + album titles only.",
        ),
        allowed_site="bandcamp.com",
        taste=taste,
        artists=artists,
        limit=limit,
    )
