from __future__ import annotations

from curl_cffi.requests import AsyncSession
import httpx

from app.config import settings
from app.tools import USER_AGENT

_CHALLENGE_MARKERS = (
    "just a moment",
    "client challenge",
    "cf-browser-verification",
    "attention required",
)


def looks_blocked(status: int, text: str) -> bool:
    if status in {401, 403, 429, 503}:
        return True
    if status == 200 and len(text) < 8000:
        low = text.lower()
        return any(m in low for m in _CHALLENGE_MARKERS)
    return False


async def hardened_get(url: str, *, timeout: float | None = None) -> tuple[int, str, str]:
    """
    Fetch URL with Chrome TLS impersonation first, then httpx fallback.
    Returns (status_code, text, final_url).
    """
    timeout = timeout or settings.request_timeout_s
    try:
        async with AsyncSession(impersonate="chrome131") as session:
            resp = await session.get(
                url,
                timeout=timeout,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/json",
                },
            )
            text = resp.text or ""
            final = str(resp.url)
            if not looks_blocked(resp.status_code, text):
                return resp.status_code, text, final
            blocked_status, blocked_text, blocked_url = resp.status_code, text, final
    except Exception:
        blocked_status, blocked_text, blocked_url = 0, "", url

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
            text = resp.text or ""
            if not looks_blocked(resp.status_code, text):
                return resp.status_code, text, str(resp.url)
            return resp.status_code, text, str(resp.url)
    except Exception as exc:
        if blocked_text:
            return blocked_status, blocked_text, blocked_url
        return 0, f"Error fetching {url}: {exc}", url


async def hardened_post_json(url: str, payload: dict, *, timeout: float | None = None) -> tuple[int, str]:
    timeout = timeout or settings.request_timeout_s
    async with AsyncSession(impersonate="chrome131") as session:
        resp = await session.post(
            url,
            json=payload,
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        return resp.status_code, resp.text or ""
