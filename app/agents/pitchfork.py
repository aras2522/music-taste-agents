from __future__ import annotations

from app.agents.base import run_source_agent
from app.agents.seeds import SIMILARITY_RULE, user_prompt
from app.models import AgentResult

SYSTEM = f"""You are the Pitchfork specialist for a music recommender.

Rules:
- Use only Pitchfork evidence provided to you.
- Find artists Pitchfork compares to the seed or puts in the same lane, then pick a real album by each.
- artist = person/band. album = release title reviewed or clearly named.
- Do not invent artists, scores, or URLs.
{SIMILARITY_RULE}
"""


async def run_pitchfork_agent(taste: str, artists: list[str], limit: int) -> AgentResult:
    return await run_source_agent(
        source="pitchfork",
        system_prompt=SYSTEM,
        user_prompt=user_prompt(
            taste,
            artists,
            limit,
            "Pitchfork",
            "Use review comparisons and related artists; recommend their albums/songs.",
        ),
        allowed_site="pitchfork.com",
        taste=taste,
        artists=artists,
        limit=limit,
    )
