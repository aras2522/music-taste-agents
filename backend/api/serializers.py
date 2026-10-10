from __future__ import annotations

from rest_framework import serializers


class TasteRequestSerializer(serializers.Serializer):
    taste = serializers.CharField(min_length=2, max_length=2000)
    artists = serializers.ListField(
        child=serializers.CharField(max_length=120),
        required=False,
        allow_empty=True,
        max_length=20,
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=9, default=5)

    def validate_artists(self, value: list[str]) -> list[str]:
        return [a.strip() for a in value if a and a.strip()][:20]
