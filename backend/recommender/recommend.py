from __future__ import annotations

import asyncio

from recommender.agents import run_pitchfork_agent, run_rym_agent, synthesize
from recommender.agents.seeds import extract_seeds, is_seed_artist
from recommender.schemas import AgentResult, RecommendResponse, TasteRequest


def _filter_agent(agent: AgentResult, seeds: list[str]) -> AgentResult:
    picks = [p for p in agent.picks if not is_seed_artist(p.artist, seeds)]
    return agent.model_copy(update={"picks": picks})


async def recommend(req: TasteRequest) -> RecommendResponse:
    seeds = extract_seeds(req.taste, req.artists)
    per_agent = min(12, req.limit + 3)
    try:
        pitchfork, rym = await asyncio.wait_for(
            asyncio.gather(
                run_pitchfork_agent(req.taste, req.artists, per_agent),
                run_rym_agent(req.taste, req.artists, per_agent),
            ),
            timeout=110,
        )
    except asyncio.TimeoutError:
        return RecommendResponse(
            taste=req.taste,
            recommendations=[],
            agents=[],
            message="Sorry, that search took too long. Try again.",
        )
    agents = [_filter_agent(a, seeds) for a in (pitchfork, rym)]
    merged = await synthesize(req.taste, agents, req.limit, seed_artists=seeds)
    merged = [r for r in merged if not is_seed_artist(r.artist, seeds)]

    message: str | None = None
    found = len(merged)
    if found == 0:
        message = "Sorry, I couldn't find any albums for this search."
    elif found < req.limit:
        message = f"Sorry, I can only show {found}."

    return RecommendResponse(
        taste=req.taste,
        recommendations=merged,
        agents=agents,
        message=message,
    )
