from __future__ import annotations

from asgiref.sync import async_to_sync
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from recommender.config import settings
from recommender.schemas import TasteRequest
from recommender.recommend import recommend

from .serializers import TasteRequestSerializer


class HealthView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request: Request) -> Response:
        return Response(
            {
                "ok": True,
                "provider": settings.llm_provider,
                "model": settings.resolved_model,
                "has_api_key": settings.has_valid_api_key,
                "backend": "django",
            }
        )


class RecommendView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request: Request) -> Response:
        serializer = TasteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not settings.has_valid_api_key:
            return Response(
                {
                    "detail": (
                        "GEMINI_API_KEY missing. Get a free key at "
                        "https://aistudio.google.com/apikey and paste it into .env"
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        req = TasteRequest(
            taste=data["taste"],
            artists=data.get("artists") or [],
            limit=data.get("limit", 5),
        )
        try:
            result = async_to_sync(recommend)(req)
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(result.model_dump())
