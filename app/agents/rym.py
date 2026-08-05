from __future__ import annotations

from app.agents.base import run_source_agent
from app.agents.seeds import SIMILARITY_RULE, user_prompt
from app.models import AgentResult

SYSTEM = f"""You are the Rate Your Music (RYM) specialist for a music recommender.

Rules:
- Use only Rate Your Music evidence provided to you.
- Prefer RYM similar artists / same-descriptor neighbors, then pick a real album for each.
- artist = person/band. album = release title. Never genre labels alone.
- Do not invent artists, ratings, or URLs.
{SIMILARITY_RULE}
"""


async def run_rym_agent(taste: str, artists: list[str], limit: int) -> AgentResult:
    return await run_source_agent(
        source="rym",
        system_prompt=SYSTEM,
        user_prompt=user_prompt(
            taste,
            artists,
            limit,
            "Rate Your Music",
            "Use similar artists and descriptors; recommend those artists' albums.",
        ),
        allowed_site="rateyourmusic.com",
        taste=taste,
        artists=artists,
        limit=limit,
    )
