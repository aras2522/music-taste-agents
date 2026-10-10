from __future__ import annotations

from pathlib import Path

from django.conf import settings as django_settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from recommender.config import settings

FRONTEND_DIST = Path(django_settings.ROOT_DIR) / "frontend" / "dist"


def _base_context(**extra):
    ctx = {
        "react_dev_url": "http://127.0.0.1:5173",
        "react_app_url": "/app/" if (FRONTEND_DIST / "index.html").exists() else "http://127.0.0.1:5173",
    }
    ctx.update(extra)
    return ctx


class HomeView(View):
    """MVC controller: serves the Django template homepage."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(
            request,
            "web/home.html",
            _base_context(
                title="Music Taste Agents",
                provider=settings.llm_provider,
                model=settings.resolved_model,
            ),
        )


class AboutView(View):
    """MVC controller: simple about page rendered by Django templates."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(
            request,
            "web/about.html",
            _base_context(
                title="About Music Taste Agents",
                stack=[
                    "Django (Python backend, MVC)",
                    "Django REST Framework (REST API)",
                    "React + Tailwind (SPA frontend)",
                    "Pitchfork + Rate Your Music agents",
                ],
            ),
        )


class ReactAppView(View):
    """Serve the built React SPA (production / Docker)."""

    def get(self, request: HttpRequest, resource: str = "") -> HttpResponse:
        index = FRONTEND_DIST / "index.html"
        if not index.exists():
            raise Http404(
                "React build not found. Run `npm install && npm run build` in frontend/, "
                "or use the Vite dev server at http://127.0.0.1:5173"
            )
        if resource:
            candidate = (FRONTEND_DIST / resource).resolve()
            if str(candidate).startswith(str(FRONTEND_DIST.resolve())) and candidate.is_file():
                return FileResponse(candidate.open("rb"))
        return FileResponse(index.open("rb"), content_type="text/html")
